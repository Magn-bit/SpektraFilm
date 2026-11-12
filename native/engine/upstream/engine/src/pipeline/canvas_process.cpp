// Bounded physical film canvas. Global exposure statistics and film geometry
// are resolved once; only a source rectangle and an optical region live on GPU.
// The original exposure plane is a delete-on-close float32 disk checkpoint.
#include "pipeline.hpp"
#include "view_process.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif

namespace spk {
namespace {
using File=std::unique_ptr<std::FILE,decltype(&std::fclose)>;
std::FILE* canvas_file(std::string& error) {
#if defined(_WIN32)
    std::vector<wchar_t> path(32768);
    const DWORD length=GetTempPathW(DWORD(path.size()),path.data());
    if(!length||length>=path.size()){error="canvas: cannot locate temporary directory";return nullptr;}
    static std::atomic<uint64_t> serial{0};
    for(unsigned i=0;i<32;++i){
        const auto name=std::wstring(path.data(),length)+L"spektrafilm-canvas-"+
            std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64())+
            L"-"+std::to_wstring(++serial)+L".tmp";
        HANDLE handle=CreateFileW(name.c_str(),GENERIC_READ|GENERIC_WRITE|DELETE,
            FILE_SHARE_READ|FILE_SHARE_DELETE,nullptr,CREATE_NEW,
            FILE_ATTRIBUTE_TEMPORARY|FILE_FLAG_DELETE_ON_CLOSE,nullptr);
        if(handle==INVALID_HANDLE_VALUE){
            const auto code=GetLastError();
            if(code==ERROR_FILE_EXISTS||code==ERROR_ALREADY_EXISTS)continue;
            error="canvas: cannot create exposure checkpoint (Windows "+std::to_string(code)+")";return nullptr;
        }
        const int fd=_open_osfhandle(reinterpret_cast<intptr_t>(handle),_O_RDWR|_O_BINARY);
        if(fd<0){CloseHandle(handle);error="canvas: cannot open checkpoint stream";return nullptr;}
        auto* file=_fdopen(fd,"w+b");
        if(!file){_close(fd);error="canvas: cannot wrap checkpoint stream";}
        return file;
    }
    error="canvas: temporary filename collision";return nullptr;
#else
    auto* file=std::tmpfile();if(!file)error="canvas: cannot create exposure checkpoint";return file;
#endif
}
bool seek_file(std::FILE* f,uint64_t offset,std::string& error){
#if defined(_WIN32)
    const int result=_fseeki64(f,static_cast<int64_t>(offset),SEEK_SET);
#else
    const int result=fseeko(f,off_t(offset),SEEK_SET);
#endif
    if(result){error="canvas: cannot seek exposure checkpoint";return false;}return true;
}

// Mappings reserve virtual address space, not resident image planes. The OS
// can evict clean checkpoint pages; GPU uploads remain bounded independently
// of canvas dimensions. Delete-on-close owns cancellation/failure cleanup.
struct CanvasPlane {
    File file{nullptr, &std::fclose};
    float* data=nullptr;
    uint32_t w=0,h=0;
    size_t bytes=0;
#if defined(_WIN32)
    HANDLE mapping=nullptr;
#endif
    ~CanvasPlane(){
#if defined(_WIN32)
        if(data)UnmapViewOfFile(data);if(mapping)CloseHandle(mapping);
#else
        if(data)munmap(data,bytes);
#endif
    }
    bool open(File checkpoint,uint32_t width,uint32_t height,std::string& error){
        file=std::move(checkpoint);w=width;h=height;bytes=size_t(w)*h*12;
        if(!file)return false;
#if defined(_WIN32)
        if(_chsize_s(_fileno(file.get()),bytes)){error="canvas: insufficient temporary disk space";return false;}
        const HANDLE handle=reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(file.get())));
        mapping=CreateFileMappingW(handle,nullptr,PAGE_READWRITE,DWORD(uint64_t(bytes)>>32),DWORD(bytes),nullptr);
        if(mapping)data=static_cast<float*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,bytes));
#else
        if(ftruncate(fileno(file.get()),off_t(bytes))){error="canvas: insufficient temporary disk space";return false;}
        auto* mapped=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fileno(file.get()),0);
        if(mapped!=MAP_FAILED)data=static_cast<float*>(mapped);
#endif
        if(!data){error="canvas: checkpoint mapping failed";return false;}return true;
    }
};
using Plane=std::shared_ptr<CanvasPlane>;
double finite_number(const Json& j,const char* key,double fallback,double lo,double hi){
    if(!j.has(key))return fallback;
    const auto& value=j.at(key);const double n=value.as_double();
    if(!value.is_number()||!std::isfinite(n)||n<lo||n>hi)
        throw std::runtime_error(std::string("canvas: invalid ")+key);
    return n;
}
}

bool Pipeline::run_canvas_bounded(const Image& in,uint16_t* rgba,uint32_t width,uint32_t height,
                                  const Json& request,Progress* progress,Json& report,
                                  std::string& error){
#if defined(__APPLE__) && !defined(SPK_VULKAN_BACKEND)
    (void)in;(void)rgba;(void)width;(void)height;(void)request;(void)progress;(void)report;
    error="canvas: bounded checkpoint execution is currently Vulkan-only";return false;
#else
    if(!built_||!in.valid()||!rgba||!width||!height){error="canvas: invalid pipeline, source or output";return false;}
    if(!params_.io.geometry.is_identity()){
        error="canvas: prepare source crop and geometry before bounded physical rendering";return false;
    }
    if(params_.print_render.contrast_mask.active){
        error="canvas: whole-negative contrast mask is unavailable in bounded execution";return false;
    }
    if(!request.is_object()){error="canvas: request must be an object";return false;}
    const auto saved_settings=params_.settings;
    const auto saved_enlarger=params_.enlarger;
    const auto saved_region=canvas_region_;
    const bool saved_admission=canvas_resident_admitted_;
    const auto saved_progress=progress_;
    const auto saved_strip=strip_plane_h_,saved_band=band_row0_;
    struct Restore{
        Pipeline* p;SettingsParams settings;EnlargerParams enlarger;CanvasRegion region;
        Progress* progress;uint32_t strip,band;bool admitted;
        ~Restore(){p->params_.settings=std::move(settings);p->params_.enlarger=std::move(enlarger);
            p->canvas_region_=region;p->progress_=progress;p->strip_plane_h_=strip;p->band_row0_=band;p->canvas_resident_admitted_=admitted;}
    } restore{this,saved_settings,saved_enlarger,saved_region,saved_progress,saved_strip,saved_band,saved_admission};
    progress_=progress;
    const auto canvas_started=std::chrono::steady_clock::now();
    auto cancelled=[&](){if(progress&&progress->cancelled){error="render cancelled";return true;}return false;};
    auto flush=[&](bool ok){return ok&&!cancelled()&&gpu_->flush(error);};
    try{
        params_.settings.striped=false;
        params_.settings.tile_full_width=in.w;params_.settings.tile_full_height=in.h;
        params_.settings.tile_origin_x=params_.settings.tile_origin_y=0;
        params_.settings.frame_exposure_peak=params_.settings.frame_boosted_peak=-1;
        set_source_shape(in.w,in.h,in.w,in.h);
        uint32_t expected_w,expected_h;
        if(!full_output_size(in.w,in.h,expected_w,expected_h,error))return false;
        if(width!=expected_w||height!=expected_h){error="canvas: output buffer shape does not match native canvas";return false;}
        if(overscan_wanted()&&!overscan_layout(in.w,in.h,error))return false;
        if(uint64_t(width)*height>uint64_t(SIZE_MAX)/8){error="canvas: output exceeds host address range";return false;}

        struct Layer{bool printed=false,graded=false;Json delta=Json::object(),grade=Json::object();} layers[2];
        const bool has_pair=request.has("pair")&&!request.at("pair").is_null();
        const bool has_grade=request.has("adjustments");
        const Json grade=request.at("adjustments").is_null()?Json::object():request.at("adjustments");
        if(!grade.is_object()){error="canvas: adjustments must be an object";return false;}
        std::array<std::array<float,4>,2> rects{};
        bool layered=false;
        if(has_pair){
            if(di_active_||params_.io.output_color_space!="ProPhoto RGB"||!params_.io.output_cctf_encoding){
                error="canvas: pair grading requires encoded ProPhoto RGB and no DI";return false;
            }
            const auto& pair=request.at("pair");if(!pair.is_object())throw std::runtime_error("canvas: pair must be an object");
            const char* names[]={"left","right"};
            const char* keys[]={"print_exposure","y_filter_shift","m_filter_shift","preflash_exposure"};
            const double base[]={saved_enlarger.print_exposure,saved_enlarger.y_filter_shift,
                saved_enlarger.m_filter_shift,saved_enlarger.preflash_exposure};
            Json gates=pair.at("gates");
            if(overscan_wanted()){
                Json layout;if(!Json::parse(overscan_geometry_json(),layout,error))return false;
                gates=layout.at("gates");
            }
            if(!gates.is_array()||gates.items().size()!=2)throw std::runtime_error("canvas: pair requires two native gates");
            for(int side=0;side<2;++side){
                const auto& hole=pair.at(names[side]);auto& layer=layers[side];layer.grade=grade;
                if(!hole.is_null()&&!hole.is_object())throw std::runtime_error("canvas: pair hole must be an object");
                if(hole.has("adjustments")&&!hole.at("adjustments").is_null()){
                    if(!hole.at("adjustments").is_object())throw std::runtime_error("canvas: pair adjustments must be an object");
                    layer.grade=hole.at("adjustments");layer.graded=layer.grade.dump()!=grade.dump();
                }
                const auto& trim=hole.at("print");
                if(!trim.is_null()){
                    if(!trim.is_object())throw std::runtime_error("canvas: pair print must be an object");
                    const double values[]={std::clamp(std::pow(2.,-finite_number(trim,"brightnessStops",0,-20,20)),.05,20.),
                        finite_number(trim,"yFilterShift",0,-1,1),finite_number(trim,"mFilterShift",0,-1,1),
                        pair.at("printEffects").as_bool(true)?finite_number(trim,"preflashExposure",0,0,1):0};
                    for(int i=0;i<4;++i){layer.delta.set(keys[i],Json(values[i]));layer.printed|=values[i]!=base[i];}
                }
                layered|=layer.printed||layer.graded;
                const auto& gate=gates.items()[side];
                if(!gate.is_array()||(gate.items().size()!=4&&gate.items().size()!=8))throw std::runtime_error("canvas: invalid pair gate");
                double x0=1,y0=1,x1=0,y1=0;
                for(size_t k=0;k<gate.items().size();k+=2){
                    const auto& a=gate.items()[k];const auto& b=gate.items()[k+1];
                    if(!a.is_number()||!b.is_number()||!std::isfinite(a.as_double())||!std::isfinite(b.as_double()))throw std::runtime_error("canvas: nonfinite pair gate");
                    x0=std::min(x0,a.as_double());x1=std::max(x1,a.as_double());
                    y0=std::min(y0,b.as_double());y1=std::max(y1,b.as_double());
                }
                if(x0<0||y0<0||x1>1||y1>1||x0>=x1||y0>=y1)throw std::runtime_error("canvas: pair gate outside canvas");
                rects[side]={float(x0*width),float(y0*height),float(x1*width),float(y1*height)};
            }
            const size_t axis=pair.at("turned").as_bool()?1:0;
            if(rects[1][axis]<rects[0][axis])std::swap(rects[0],rects[1]);
        }
        if(has_grade&&(params_.io.output_color_space!="ProPhoto RGB"||!params_.io.output_cctf_encoding||di_active_)){
            error="canvas: post grading requires encoded ProPhoto RGB and no DI";return false;
        }

        const uint64_t budget=uint64_t(finite_number(request,"budget_bytes",
            saved_settings.strip_budget_bytes>0?saved_settings.strip_budget_bytes:double(uint64_t(512)<<20),
            double(uint64_t(16)<<20),double(uint64_t(8)<<30)));
        // Ordinary single-frame composition keeps the existing native graph
        // resident when the measured device heap can hold its five-plane
        // maximum. The disk executor remains the exact low-memory route.
        const size_t canvas_bytes=size_t(width)*height*12;
        const size_t resident_bytes=canvas_bytes*5+(size_t(128)<<20);
        std::string resident_error;
        if(!has_grade&&!layered&&(!request.has("budget_bytes")||resident_bytes<=budget)&&
           gpu_->check_working_set(resident_bytes,canvas_bytes,resident_error)){
            canvas_resident_admitted_=true;canvas_region_={};strip_plane_h_=band_row0_=0;
            params_.settings.tile_full_width=params_.settings.tile_full_height=0;
            params_.settings.tile_origin_x=params_.settings.tile_origin_y=0;
            double before=0,after=0;
            if(params_.film_render.halation.boost_ev!=0||
                (params_.film_render.halation.back_reflection&&params_.film_render.halation.headroom_ev>0)){
                if(!measure_film_exposure_peaks(in,before,after,nullptr,error))return false;
                params_.settings.frame_exposure_peak=before;params_.settings.frame_boosted_peak=after;
            }
            if(progress)progress->canvas_fraction=-1;
            Blur::SweepReport sweep;blur_.set_sweep_report(&sweep);
            struct ClearSweep{Blur* blur;~ClearSweep(){blur->set_sweep_report(nullptr);}} clear{&blur_};
            Image negative,rgb,packed;
            const auto film_started=std::chrono::steady_clock::now();
            if(!run_film(in,negative,progress,error))return false;
            const auto print_started=std::chrono::steady_clock::now();
            if(!run_print(negative,rgb,progress,error))return false;negative={};
            if(rgb.w!=width||rgb.h!=height){error="canvas: resident output shape does not match native geometry";return false;}
            const auto pack_started=std::chrono::steady_clock::now();
            packed.w=width;packed.h=height;packed.c=2;packed.buf=gpu_->alloc(packed.bytes(),error);if(!packed.buf)return false;
            const uint32_t m[]={uint32_t(rgb.pixels()),width,width};
            if(!flush(gpu_->dispatch("spk_to_rgba16",{gpu::Arg::buf(rgb.buf),gpu::Arg::inline_bytes(m,3),gpu::Arg::buf(packed.buf)},rgb.pixels(),error)))return false;
            rgb={};
            for(uint32_t y=0;y<height;y+=64){
                if(cancelled())return false;const uint32_t h=std::min(64u,height-y);
                if(!gpu_->read(packed.buf.get(),size_t(y)*width*8,rgba+size_t(y)*width*4,size_t(h)*width*8,error))return false;
            }
            report=Json::object();report.set("resident_pipeline",Json(true));
            report.set("width",Json(double(width)));report.set("height",Json(double(height)));
            report.set("source_bands",Json(1.));report.set("regions",Json(1.));report.set("region_core",Json(double(std::max(width,height))));
            report.set("halo_pixels",Json(0.));report.set("largest_region_pixels",Json(double(width)*height));
            report.set("largest_source_pixels",Json(double(in.pixels())));report.set("exposure_checkpoint_bytes",Json(0.));
            report.set("checkpoint_peak_bytes",Json(0.));report.set("resident_admission_bytes",Json(double(resident_bytes)));
            report.set("frame_exposure_peak",Json(before));report.set("frame_boosted_peak",Json(after));
            report.set("finite_iir_context",Json(false));report.set("exact_iir_sweeps",Json(true));
            report.set("complete_line_passes",Json(double(sweep.launches)));report.set("resident_gaussian_calls",Json(double(sweep.launches/2)));
            report.set("pointwise_passes",Json(0.));report.set("pair_layers_applied",Json(false));report.set("post_adjustments_applied",Json(false));
            Json times=Json::object();times.set("canvas.film",Json(std::chrono::duration<double,std::milli>(print_started-film_started).count()));
            times.set("canvas.print",Json(std::chrono::duration<double,std::milli>(pack_started-print_started).count()));
            times.set("canvas.output",Json(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-pack_started).count()));
            report.set("stage_ms",std::move(times));Json layout;if(!Json::parse(overscan_geometry_json(),layout,error))return false;report.set("geometry",std::move(layout));
            if(progress){progress->canvas_fraction=1;progress->done=true;}return true;
        }
        const uint32_t desired=uint32_t(finite_number(request,"region_edge",1024,16,8192));
        const uint32_t core=std::max(16u,std::min(desired,uint32_t(std::sqrt(double(budget)/192.))));
        const uint32_t source_rows=std::max(1u,std::min(512u,4000000u/std::max(1u,in.w)));
        File exposure(canvas_file(error),&std::fclose);if(!exposure)return false;
        std::vector<float> host;
        double peak=0;
        const double work=double(in.pixels())*8.;
        auto update=[&](double pixels,const char* stage){if(progress){progress->canvas_fraction=std::clamp(pixels/work,0.,1.);progress->stage=stage;}};
        const auto& fg=params_.film_render.grain;
        film_seed_=(fg.active&&params_.settings.grain_sampler!="exact")?fresh_seed():0x5EEDu;
        if(saved_settings.tile_seed>0)film_seed_=uint32_t(saved_settings.tile_seed);
        const auto& pg=params_.print_render.glare;
        print_seed_=(pg.active&&pg.percent*pg.amount>0)?fresh_seed():0u;
        if(saved_settings.tile_seed>0)print_seed_=uint32_t(saved_settings.tile_seed)^0x9e3779b9u;
        strip_plane_h_=in.h;
        uint32_t source_bands=0;
        for(uint32_t y=0;y<in.h;y+=source_rows){
            if(cancelled())return false;
            update(double(y)*in.w,"canvas.source_exposure");
            const uint32_t rows=std::min(source_rows,in.h-y);
            Image slice;slice.w=in.w;slice.h=rows;slice.c=in.c;
            slice.buf=gpu_->alloc(slice.bytes(),error);if(!slice.buf)return false;
            if(!gpu_->copy(slice.buf.get(),0,in.buf.get(),size_t(y)*in.w*in.c*4,slice.bytes(),error))return false;
            params_.settings.tile_origin_y=y;
            Image cur,next;
            if(!flush(node_input_cast(slice,cur,error)))return false;slice={};
            if(!flush(node_decode_input(cur,next,error)))return false;cur=std::move(next);
            if(!flush(node_auto_exposure(cur,next,error)))return false;cur=std::move(next);
            Chain chain,scaled;chain.cur=std::move(cur);
            if(!flush(film_scale_and_expose(std::move(chain),scaled,error)))return false;
            if(params_.film_render.halation.boost_ev!=0||
                (params_.film_render.halation.back_reflection&&params_.film_render.halation.headroom_ev>0)){
                double maximum=0;if(!device_max(scaled.cur,maximum,error))return false;peak=std::max(peak,maximum);
            }
            host.resize(scaled.cur.elements());
            if(!gpu_->read(scaled.cur.buf.get(),0,host.data(),host.size()*4,error))return false;
            if(std::fwrite(host.data(),4,host.size(),exposure.get())!=host.size()){
                error="canvas: exposure checkpoint write failed (check free disk space)";return false;
            }
            ++source_bands;
        }
        if(std::fflush(exposure.get())){error="canvas: exposure checkpoint flush failed";return false;}
        params_.settings.frame_exposure_peak=peak;
        double boosted_peak=peak;
        if(params_.film_render.halation.boost_ev!=0&&peak>0){
            const float value[3]={float(peak),float(peak),float(peak)};Image sample,boosted;
            sample.w=sample.h=1;sample.buf=gpu_->upload(value,sizeof value,error);
            if(!sample.buf||!flush(node_boost(sample,boosted,error))||!device_max(boosted,boosted_peak,error))return false;
        }
        params_.settings.frame_boosted_peak=boosted_peak;
        params_.settings.tile_full_width=width;params_.settings.tile_full_height=height;
        params_.settings.tile_origin_y=0;
        if(!params_.io.scan_film&&!di_active_&&!refresh_print_constants(error))return false;

        // The exact staged executor owns checkpoint planes through RAII. A
        // complete row/column is always passed to the same native blur kernel;
        // there is no artificial IIR boundary and no optical-tail truncation.
#include "canvas_staged.inc"
    }catch(const std::exception& e){error=e.what();return false;}
#endif
}
} // namespace spk
