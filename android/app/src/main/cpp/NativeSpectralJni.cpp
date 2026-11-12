// GPL-3.0: Android bounded spectral executor over the shared SpektraLab core.
// Keeps only one tile/negative on the device. No proxy or RGB8 export input.
#include <jni.h>
#include <android/bitmap.h>
#include <android/log.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <fstream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <chrono>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "blob.hpp"
#include "colour.hpp"
#include "params.hpp"
#include "halation_psf.hpp"
#include "pipeline/pipeline.hpp"
#include "pipeline/editor_process.hpp"
#include "pipeline/editor_analyze.hpp"
#include "gpu/gpu.hpp"

namespace {
using SteadyClock = std::chrono::steady_clock;
static double elapsed_ms(SteadyClock::time_point start) {
    return std::chrono::duration<double, std::milli>(SteadyClock::now() - start).count();
}
struct Executor {
    std::string root;
    spk::Blob blob;
    spk::Colour colour;
    spk::Json neutral;
    std::unique_ptr<spk::gpu::Gpu> gpu;
    spk::SetupCache cache;
    std::unique_ptr<spk::Pipeline> pipeline;
    spk::Image negative;
    struct CachedNegative {std::string key;spk::Image image;};
    std::vector<CachedNegative> previews;
    std::string shootKey, paramsKey;
    uint64_t inputHash = 0;
    uint64_t memoryPixels=0,memoryHostBytes=0,memoryLivePeak=0,memoryResidentPeak=0;
    uint32_t width = 0, height = 0;
    FILE* sourceFile = nullptr;
    std::string sourcePath;
    int sourceWidth = 0, sourceHeight = 0;
    std::mutex lock;
    ~Executor() { negative = {}; previews.clear(); pipeline.reset(); if(sourceFile)fclose(sourceFile); }
};
void fail(JNIEnv* env, const std::string& error) {
    if (!env->ExceptionCheck()) env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), error.c_str());
}
std::string string(JNIEnv* env, jstring text) {
    const char* bytes=env->GetStringUTFChars(text,nullptr);
    if (!bytes) throw std::runtime_error("Unable to read native parameter");
    std::string value(bytes); env->ReleaseStringUTFChars(text,bytes); return value;
}
uint64_t hash(const float* pixels, size_t size) {
    uint64_t result=1469598103934665603ull;
    const auto* bytes=reinterpret_cast<const unsigned char*>(pixels);
    for(size_t i=0;i<size*sizeof(float);++i)result=(result^bytes[i])*1099511628211ull;
    return result;
}

spk::Params resolved(Executor* e, const spk::Json& delta) {
    spk::Params params;std::string error;
    if(!spk::init_params(e->root,delta.at("film_stock").as_string(),delta.at("print_stock").as_string(),e->neutral,params,error))throw std::runtime_error(error);
    params.enlarger.print_exposure_compensation=false;
    spk::apply_delta(params,delta);
    if(!spk::digest(params,e->neutral,error))throw std::runtime_error(error);
    if(params.film.info.stock=="kodak_tri_x_400" || params.film.info.stock=="kodak_tmax_100" ||
       params.film.info.stock=="ilford_hp5_plus_400" || params.film.info.stock=="fujifilm_neopan_acros_100_ii") {
        params.settings.apply_hanatos2025_adaptation_window=false;
        params.settings.apply_hanatos2025_adaptation_surface=false;
    }
    return params;
}

int reflect(int64_t coordinate,int extent) {
    if(extent<=1)return 0;
    const int64_t period=2ll*(extent-1);
    const int64_t folded=(coordinate%period+period)%period;
    return int(folded<extent?folded:period-folded);
}

size_t elements(int width,int height) {
    if(width<=0 || height<=0 || int64_t(width)*height>11184810)
        throw std::runtime_error("Spectral region exceeds the bounded native plane budget");
    return size_t(width)*height*3;
}

// Reads RGB16 directly into one native float region. No Java full-region
// FloatArray, GetFloatArrayElements copy, or RGB8 conversion is involved.
std::vector<float> file_region(Executor* e,const std::string& path,int width,int height,
                               int originX,int originY,int fullWidth,int fullHeight) {
    const size_t count=elements(width,height);
    if(fullWidth<=0 || fullHeight<=0)throw std::runtime_error("Invalid source size");
    if(!e)throw std::runtime_error("Spectral executor is closed");
    if(!e->sourceFile || e->sourcePath!=path || e->sourceWidth!=fullWidth || e->sourceHeight!=fullHeight) {
        if(e->sourceFile)fclose(e->sourceFile);
        e->sourceFile=fopen(path.c_str(),"rb");
        if(!e->sourceFile)throw std::runtime_error("Cannot open complete RGB16 source cache");
        e->sourcePath=path;e->sourceWidth=fullWidth;e->sourceHeight=fullHeight;
    }
    if(fseeko(e->sourceFile,0,SEEK_END)!=0 || ftello(e->sourceFile)!=int64_t(fullWidth)*fullHeight*6)
        throw std::runtime_error("Complete RGB16 source cache length changed");
    std::vector<int> xs(size_t(width),0);
    for(int x=0;x<width;++x)xs[size_t(x)]=reflect(int64_t(originX)+x,fullWidth);
    const auto bounds=std::minmax_element(xs.begin(),xs.end());
    const int minX=*bounds.first,maxX=*bounds.second;
    std::vector<uint8_t> row(size_t(maxX-minX+1)*6);
    std::vector<float> result(count);
    for(int y=0;y<height;++y) {
        const auto offset=(int64_t(reflect(int64_t(originY)+y,fullHeight))*fullWidth+minX)*6;
        if(fseeko(e->sourceFile,off_t(offset),SEEK_SET)!=0 || fread(row.data(),1,row.size(),e->sourceFile)!=row.size())
            throw std::runtime_error("Cannot read complete RGB16 source region");
        for(int x=0;x<width;++x)for(int c=0;c<3;++c) {
            const size_t i=size_t(xs[size_t(x)]-minX)*6+size_t(c)*2;
            result[(size_t(y)*width+x)*3+c]=float(uint16_t(row[i])|(uint16_t(row[i+1])<<8))*(1.f/65535.f);
        }
    }
    return result;
}

std::vector<float> bitmap_region(JNIEnv* env,jobject bitmap,int width,int height) {
    AndroidBitmapInfo info{};
    if(AndroidBitmap_getInfo(env,bitmap,&info)!=ANDROID_BITMAP_RESULT_SUCCESS ||
       info.width!=uint32_t(width) || info.height!=uint32_t(height) || info.format!=ANDROID_BITMAP_FORMAT_RGBA_8888)
        throw std::runtime_error("Spectral bitmap region must be software RGBA8888 at its original region size");
    std::vector<float> result(elements(width,height));void* data=nullptr;
    if(AndroidBitmap_lockPixels(env,bitmap,&data)!=ANDROID_BITMAP_RESULT_SUCCESS || !data)
        throw std::runtime_error("Cannot lock original bitmap region");
    struct Unlock {JNIEnv* env;jobject bitmap;~Unlock(){AndroidBitmap_unlockPixels(env,bitmap);}} unlock{env,bitmap};
    for(int y=0;y<height;++y) {
        const auto* row=static_cast<const uint8_t*>(data)+size_t(y)*info.stride;
        for(int x=0;x<width;++x)for(int c=0;c<3;++c)
            result[(size_t(y)*width+x)*3+c]=float(row[size_t(x)*4+c])*(1.f/255.f);
    }
    return result;
}

// These are actual, digested material parameters, including the broad DIR
// exponential tail. Serial stages add; alternative mixture components max.
// IIR support is infinite: six sigma is a documented finite context, not a
// claim that a tiled recurrence is mathematically bit-exact to a full sweep.
int region_halo(const spk::Params& p,int width,int height) {
    if(width<=0 || height<=0)throw std::runtime_error("Invalid source dimensions for spatial context");
    const double px=p.camera.film_format_mm*1000./std::max(width,height);
    if(!(px>0.) || !std::isfinite(px))throw std::runtime_error("Invalid physical film pixel pitch");
    double serial=std::max(0.,p.camera.lens_blur_um/px);
    const auto& h=p.film_render.halation;
    if(h.active) {
        double scatter=0.,bounce=0.;
        for(int c=0;c<3;++c) {
            if(h.scatter_amount>0.)scatter=std::max(scatter,std::max(h.scatter_core_um[c],h.scatter_tail_um[c]*2.7684)*h.scatter_spatial_scale/px);
            if(h.halation_amount>0. && h.halation_strength[c]>0.) {
                if(h.back_reflection)for(int k=0;k<spk::kBackReflectionComponents;++k)
                    bounce=std::max(bounce,h.base_thickness_um*h.halation_spatial_scale*std::sqrt(h.halation_amount)*spk::kBackReflectionSigmaOverBase[k][c]/px);
                else bounce=std::max(bounce,h.halation_first_sigma_um[c]*h.halation_spatial_scale*std::sqrt(h.halation_amount*std::max(0,h.halation_n_bounces))/px);
            }
        }
        serial+=scatter+bounce;
    }
    const auto& d=p.film_render.dir_couplers;
    if(d.active && d.diffusion_size_um>0.)serial+=std::max(d.diffusion_size_um,d.diffusion_tail_um*2.7684)/px;
    const auto& g=p.film_render.grain;
    if(g.active && g.amount>0. && g.texture==0) {
        double cloud=0.;
        if(g.sublayers_active && g.blur_dye_clouds_um>0.)for(size_t c=0;c<3;++c) {
            double total=0.;
            for(size_t sl=0;sl<3;++sl) {
                double maximum=0.;
                for(size_t j=0;j<p.film.data.n_exposure;++j) {
                    const double value=p.film.data.density_curves_layers[j*9+sl*3+c];
                    if(std::isfinite(value))maximum=std::max(maximum,value);
                }
                total+=maximum;
            }
            for(size_t sl=0;sl<3;++sl)cloud=std::max(cloud,g.blur_dye_clouds_um*std::sqrt(std::max(0.,(total+g.density_min[c])*g.particle_area_um2*g.particle_scale[c]*g.particle_scale_layers[sl]/(px*px))));
        }
        const double micro=g.micro_structure[1]*.001/px>.05?std::max(0.,g.micro_structure[0]/px):0.;
        serial+=std::max(cloud,micro)+std::max(0.,g.blur);
    }
    const auto& glare=p.print_render.glare;
    if(!p.io.scan_film && glare.active && glare.percent*glare.amount>0.)serial+=std::max(0.,glare.blur*std::sqrt(std::max(0.,glare.amount)));
    serial+=std::max(0.,p.scanner.lens_blur);
    if(p.scanner.unsharp_mask[1]>0.)serial+=std::max(0.,p.scanner.unsharp_mask[0]);
    return std::max(16,int(std::ceil(6.*serial+8.)));
}
}

extern "C" JNIEXPORT jlong JNICALL Java_com_spektra_film_NativeSpectral_nativeCreate(JNIEnv* env,jobject,jstring root) {
    try {
        auto e=std::make_unique<Executor>(); e->root=string(env,root); std::string error;
        if(!e->blob.open(e->root+"/spektrafilm_constants.bin",error) || !e->colour.init(e->blob,error))throw std::runtime_error(error);
        std::ifstream input(e->root+"/neutral_print_filters.json"); std::stringstream body;body<<input.rdbuf();
        if(!spk::Json::parse(body.str(),e->neutral,error))throw std::runtime_error(error);
        e->gpu.reset(spk::gpu::Gpu::create_vulkan(e->root+"/vulkan",error));
        if(!e->gpu)throw std::runtime_error(error);
        if(!e->gpu->check_math_mode(error))throw std::runtime_error(error);
        return reinterpret_cast<jlong>(e.release());
    } catch(const std::exception& error) {fail(env,error.what());return 0;}
}

namespace {
jshortArray render_pixels(JNIEnv* env,Executor* e,const float* pixels,int width,int height,jstring parameters,
    jstring shoot,float strength,float vignette,int originX,int originY,int fullWidth,int fullHeight,bool preview,
    int coreX,int coreY,int coreWidth,int coreHeight) {
        if(!e || !pixels || width<=0 || height<=0 || fullWidth<=0 || fullHeight<=0 || coreX<0 || coreY<0 ||
           coreWidth<=0 || coreHeight<=0 || int64_t(coreX)+coreWidth>width || int64_t(coreY)+coreHeight>height)
            throw std::runtime_error("Invalid complete-resolution spectral region bounds");
        std::lock_guard<std::mutex> guard(e->lock);
        std::string error;spk::Json incoming;
        if(!spk::Json::parse(string(env,parameters),incoming,error))throw std::runtime_error(error);
        const auto settings=incoming.at("editor_settings");
        const bool useFilm=incoming.at("editor_film_enabled").as_bool(true);
        auto delta=spk::Json::object();
        for(const auto& pair:incoming.fields())if(pair.first.rfind("editor_",0)!=0)delta.set(pair.first,pair.second);
        const auto paramsKey=delta.dump();
        const auto renderStart=SteadyClock::now();
        e->gpu->begin_frame();
        struct Frame {spk::gpu::Gpu* gpu;~Frame(){gpu->end_frame();}} frame{e->gpu.get()};
        const double scaleX=preview?double(fullWidth)/width:1.,scaleY=preview?double(fullHeight)/height:1.;
        auto editorStage=[&](const char* stage,const float* input,float* output,int ew,int eh,double ox,double oy) {
            auto request=spk::Json::object();request.set("stage",spk::Json(std::string(stage)));request.set("settings",settings);
            request.set("source_color_space",spk::Json(std::string("sRGB")));request.set("source_linear",spk::Json(false));
            request.set("source_width",spk::Json(double(fullWidth)));request.set("source_height",spk::Json(double(fullHeight)));
            request.set("origin_x",spk::Json(ox));request.set("origin_y",spk::Json(oy));
            request.set("pixel_scale_x",spk::Json(scaleX));request.set("pixel_scale_y",spk::Json(scaleY));
            request.set("memory_budget_bytes",spk::Json(64.*1024*1024));
            spk_image image{input,uint32_t(ew),uint32_t(eh),3};double duration=0;
            if(!spk::editor::process(e->gpu.get(),e->colour,image,request,output,duration,error))throw std::runtime_error(error);
        };
        std::vector<float> prepared(size_t(width)*height*3);
        if(incoming.at(useFilm?"editor_capture_active":"editor_active").as_bool(true))editorStage(useFilm?"pre":"all",pixels,prepared.data(),width,height,originX,originY);
        else std::copy(pixels,pixels+prepared.size(),prepared.data());
        if(!useFilm) {
            std::vector<jshort> result(size_t(coreWidth)*coreHeight*3);
            for(int y=0;y<coreHeight;++y)for(int x=0;x<coreWidth;++x)for(int c=0;c<3;++c) {
                float v=prepared[((size_t(coreY+y)*width)+coreX+x)*3+c];
                result[(size_t(y)*coreWidth+x)*3+c]=jshort(std::lround(std::clamp(std::isfinite(v)?v:0.f,0.f,1.f)*65535.f));
            }
            auto array=env->NewShortArray(jsize(result.size()));if(array)env->SetShortArrayRegion(array,0,jsize(result.size()),result.data());return array;
        }
        pixels=prepared.data();
        const std::string tileKey=preview?"":":"+std::to_string(fullWidth)+":"+std::to_string(fullHeight)+":"+std::to_string(originX)+":"+std::to_string(originY)+":"+std::to_string(width)+":"+std::to_string(height);
        const auto buildKey=paramsKey+(preview?":preview":":regions"),shootKey=string(env,shoot)+tileKey;
        const auto fingerprint=preview?hash(pixels,size_t(width)*height*3):0;
        const std::string cacheKey=std::to_string(fingerprint)+":"+std::to_string(width)+":"+std::to_string(height)+":"+shootKey;
        const bool sameInput=preview && e->width==uint32_t(width) && e->height==uint32_t(height) && e->inputHash==fingerprint;
        if(!e->pipeline || e->paramsKey!=buildKey || (preview && (e->width!=uint32_t(width) || e->height!=uint32_t(height)))) {
            auto params=resolved(e,delta);
            // Shared bounded-frame contract preserves physical pitch and gives
            // overlap pixels one global grain/glare realization across tiles.
            if(!preview) {
                params.settings.tile_full_width=fullWidth;params.settings.tile_full_height=fullHeight;
                params.settings.tile_origin_x=originX;params.settings.tile_origin_y=originY;params.settings.tile_seed=1442695041;
            }
            params.settings.working_precision="float32";
            params.settings.striped=false;
            auto next=std::make_unique<spk::Pipeline>(e->gpu.get(),&e->colour,&e->blob,&e->cache);
            if(!next->build(params,error))throw std::runtime_error(error);
            e->pipeline=std::move(next);e->paramsKey=buildKey;
        }
        if(!preview) {
            // Region coordinates affect runtime indexing and physical pitch,
            // never the spectral tables. Keep one baked pipeline per recipe.
            auto region=spk::Json::object();
            region.set("tile_full_width",spk::Json(double(fullWidth)));region.set("tile_full_height",spk::Json(double(fullHeight)));
            region.set("tile_origin_x",spk::Json(double(originX)));region.set("tile_origin_y",spk::Json(double(originY)));
            region.set("tile_seed",spk::Json(1442695041.));e->pipeline->apply_live_delta(region);
        }
        double filmMs=0.,printMs=0.,readMs=0.;
        const uint64_t observation=e->gpu->begin_memory_observation();
        struct Observe {
            Executor* executor;spk::gpu::Gpu* gpu;uint64_t token;size_t pixels,corePixels;bool preview;
            ~Observe(){
                const auto memory=gpu->end_memory_observation(token);
                executor->memoryPixels=pixels;executor->memoryHostBytes=(pixels+corePixels)*sizeof(float)*3;
                executor->memoryLivePeak=memory.live_peak;executor->memoryResidentPeak=memory.resident_peak;
                if(!preview)__android_log_print(ANDROID_LOG_INFO,"SpektraNative",
                    "region_pixels=%zu gpu_live_peak=%zu gpu_resident_peak=%zu host_float_bytes=%zu staging_reserve_bytes=134217728",
                    pixels,memory.live_peak,memory.resident_peak,executor->memoryHostBytes);
            }
        } observe{e,e->gpu.get(),observation,size_t(width)*height,size_t(width)*coreHeight,preview};
        e->pipeline->set_source_long_edge(std::max(width,height),std::max(width,height));
        bool reused=false;
        if(preview)for(const auto& cached:e->previews)if(cached.key==cacheKey){e->negative=cached.image;reused=true;break;}
        if(!reused && (!sameInput || e->shootKey!=shootKey || !e->negative.valid())) {
            e->negative={};spk::Image source;source.w=width;source.h=height;source.c=3;
            source.buf=e->gpu->upload(pixels,source.bytes(),error);
            if(!source.buf || !e->pipeline->run_film(source,e->negative,nullptr,error))throw std::runtime_error(error);
            filmMs=elapsed_ms(renderStart);
            e->inputHash=fingerprint;e->width=width;e->height=height;e->shootKey=shootKey;
            if(preview && e->negative.bytes()<=(size_t(24)<<20)) {
                e->previews.push_back({cacheKey,e->negative});
                size_t bytes=0;for(const auto& cached:e->previews)bytes+=cached.image.bytes();
                while(e->previews.size()>2 || bytes>(size_t(24)<<20)){bytes-=e->previews.front().image.bytes();e->previews.erase(e->previews.begin());}
            }
        }
        e->inputHash=fingerprint;e->width=width;e->height=height;e->shootKey=shootKey;
        spk::Image developed;
        const auto printStart=SteadyClock::now();
        if(!e->pipeline->run_print(e->negative,developed,nullptr,error) || !e->gpu->flush(error))throw std::runtime_error(error);
        printMs=elapsed_ms(printStart);
        // One contiguous readback of only the needed vertical slab. Reading
        // each core row separately would create thousands of synchronous
        // Vulkan transfers; reading the full halo downloaded many pixels that
        // were immediately discarded. Horizontal context stays in this slab
        // so the transfer still needs at most a few staging chunks per tile.
        const bool spatial=std::abs(settings.at("texture").as_double())>0 || std::abs(settings.at("clarity").as_double())>0;
        const int slabTop=spatial?0:coreY,slabHeight=spatial?height:coreHeight;
        std::vector<float> output(size_t(width)*slabHeight*3);
        const auto readStart=SteadyClock::now();
        if(developed.w!=uint32_t(width) || developed.h!=uint32_t(height) ||
           !e->gpu->read(developed.buf.get(),size_t(slabTop)*width*3*sizeof(float),output.data(),output.size()*sizeof(float),error))throw std::runtime_error(error.empty()?"Spectral dimensions changed":error);
        readMs=elapsed_ms(readStart);
        const auto quantizeStart=SteadyClock::now();
        const double exposure=std::pow(2.,delta.at("exposure_compensation_ev").as_double());
        if(strength!=1.f)for(int y=0;y<slabHeight;++y)for(int x=0;x<width;++x)for(int c=0;c<3;++c) {
            const size_t i=(size_t(y)*width+x)*3+c;
            double source=pixels[(size_t(y+slabTop)*width+x)*3+c];
            double linear=source<=.04045?source/12.92:std::pow((source+.055)/1.055,2.4);
            linear*=exposure;source=linear<=.0031308?linear*12.92:1.055*std::pow(std::max(0.,linear),1./2.4)-.055;
            output[i]=float(source+(output[i]-source)*strength);
        }
        if(incoming.at("editor_post_active").as_bool(true))editorStage("post",output.data(),output.data(),width,slabHeight,originX,originY+slabTop*scaleY);
        std::vector<jshort> result(size_t(coreWidth)*coreHeight*3);
        for(int cy=0;cy<coreHeight;++cy)for(int cx=0;cx<coreWidth;++cx)for(int c=0;c<3;++c) {
            const float value=output[(size_t(coreY+cy-slabTop)*width+coreX+cx)*3+c];
            result[(size_t(cy)*coreWidth+cx)*3+c]=jshort(std::lround(std::clamp(std::isfinite(value)?value:0.f,0.f,1.f)*65535.f));
        }
        auto array=env->NewShortArray(jsize(result.size()));
        if(array)env->SetShortArrayRegion(array,0,jsize(result.size()),result.data());
        if(!preview)__android_log_print(ANDROID_LOG_INFO,"SpektraNative",
            "tile_ms total=%.1f film=%.1f print=%.1f read=%.1f quantize_jni=%.1f tile=%dx%d core=%dx%d origin=%d,%d",
            elapsed_ms(renderStart),filmMs,printMs,readMs,elapsed_ms(quantizeStart),width,height,coreWidth,coreHeight,originX,originY);
        return array;
}
}

extern "C" JNIEXPORT jshortArray JNICALL Java_com_spektra_film_NativeSpectral_nativeRender(
    JNIEnv* env,jobject,jlong handle,jfloatArray input,jint width,jint height,jstring parameters,
    jstring shoot,jfloat strength,jfloat vignette,jint originX,jint originY,jint fullWidth,jint fullHeight,jboolean preview) {
    if(!input || width<=0 || height<=0 || int64_t(width)*height*3!=env->GetArrayLength(input)) {
        fail(env,"Invalid spectral tile dimensions");return nullptr;
    }
    jfloat* pixels=env->GetFloatArrayElements(input,nullptr);if(!pixels)return nullptr;
    struct Release {JNIEnv* env;jfloatArray input;jfloat* pixels;~Release(){env->ReleaseFloatArrayElements(input,pixels,JNI_ABORT);}} release{env,input,pixels};
    try {
        return render_pixels(env,reinterpret_cast<Executor*>(handle),pixels,width,height,parameters,shoot,strength,vignette,
                             originX,originY,fullWidth,fullHeight,preview,0,0,width,height);
    } catch(const std::exception& error) {fail(env,error.what());return nullptr;}
}

extern "C" JNIEXPORT jshortArray JNICALL Java_com_spektra_film_NativeSpectral_nativeRenderFile(
    JNIEnv* env,jobject,jlong handle,jstring path,jint width,jint height,jstring parameters,
    jstring shoot,jfloat strength,jfloat vignette,jint originX,jint originY,jint fullWidth,jint fullHeight,
    jint coreX,jint coreY,jint coreWidth,jint coreHeight) {
    try {
        const auto ioStart=SteadyClock::now();
        auto input=file_region(reinterpret_cast<Executor*>(handle),string(env,path),width,height,originX,originY,fullWidth,fullHeight);
        __android_log_print(ANDROID_LOG_INFO,"SpektraNative","region_io_ms=%.1f source=%dx%d origin=%d,%d",
            elapsed_ms(ioStart),width,height,originX,originY);
        return render_pixels(env,reinterpret_cast<Executor*>(handle),input.data(),width,height,parameters,shoot,strength,vignette,
                             originX,originY,fullWidth,fullHeight,false,coreX,coreY,coreWidth,coreHeight);
    } catch(const std::exception& error) {fail(env,error.what());return nullptr;}
}

extern "C" JNIEXPORT jshortArray JNICALL Java_com_spektra_film_NativeSpectral_nativeRenderBitmap(
    JNIEnv* env,jobject,jlong handle,jobject bitmap,jint width,jint height,jstring parameters,
    jstring shoot,jfloat strength,jfloat vignette,jint originX,jint originY,jint fullWidth,jint fullHeight,
    jint coreX,jint coreY,jint coreWidth,jint coreHeight) {
    try {
        auto input=bitmap_region(env,bitmap,width,height);
        return render_pixels(env,reinterpret_cast<Executor*>(handle),input.data(),width,height,parameters,shoot,strength,vignette,
                             originX,originY,fullWidth,fullHeight,false,coreX,coreY,coreWidth,coreHeight);
    } catch(const std::exception& error) {fail(env,error.what());return nullptr;}
}

extern "C" JNIEXPORT jint JNICALL Java_com_spektra_film_NativeSpectral_nativeTileHalo(
    JNIEnv* env,jobject,jlong handle,jstring parameters,jint fullWidth,jint fullHeight) {
    try {
        auto* e=reinterpret_cast<Executor*>(handle);
        if(!e)throw std::runtime_error("Spectral engine is closed");
        std::lock_guard<std::mutex> guard(e->lock);spk::Json delta;std::string error;
        if(!spk::Json::parse(string(env,parameters),delta,error))throw std::runtime_error(error);
        return region_halo(resolved(e,delta),fullWidth,fullHeight);
    } catch(const std::exception& error) {fail(env,error.what());return 0;}
}

extern "C" JNIEXPORT jstring JNICALL Java_com_spektra_film_NativeSpectral_nativeAnalyze(
    JNIEnv* env,jobject,jlong handle,jobject bitmap,jstring parameters,jstring target,jstring request) {
    try {
        auto* e=reinterpret_cast<Executor*>(handle);if(!e)throw std::runtime_error("Analysis engine is closed");
        std::lock_guard<std::mutex> guard(e->lock);std::string error;spk::Json incoming,req;
        if(!spk::Json::parse(string(env,parameters),incoming,error) || !spk::Json::parse(string(env,request),req,error))throw std::runtime_error(error);
        auto delta=spk::Json::object();for(const auto& pair:incoming.fields())if(pair.first.rfind("editor_",0)!=0)delta.set(pair.first,pair.second);
        AndroidBitmapInfo info{};if(AndroidBitmap_getInfo(env,bitmap,&info)!=ANDROID_BITMAP_RESULT_SUCCESS)throw std::runtime_error("Analysis source is unavailable");
        auto pixels=bitmap_region(env,bitmap,int(info.width),int(info.height));
        e->gpu->begin_frame();struct Frame{spk::gpu::Gpu* gpu;~Frame(){gpu->end_frame();}} frame{e->gpu.get()};
        spk_image image{pixels.data(),info.width,info.height,3};
        if(incoming.at("editor_capture_active").as_bool()) {
            auto pre=spk::Json::object();pre.set("stage",spk::Json(std::string("pre")));pre.set("settings",incoming.at("editor_settings"));double duration=0;
            if(!spk::editor::process(e->gpu.get(),e->colour,image,pre,pixels.data(),duration,error))throw std::runtime_error(error);
        }
        auto params=resolved(e,delta);spk::Json reply;
        if(!spk::editor::analyze(e->gpu.get(),&e->colour,&e->blob,&e->cache,e->neutral,params,image,string(env,target),req,reply,error))throw std::runtime_error(error);
        return env->NewStringUTF(reply.dump().c_str());
    }catch(const std::exception& error){fail(env,error.what());return nullptr;}
}

extern "C" JNIEXPORT jlongArray JNICALL Java_com_spektra_film_NativeSpectral_nativeMemoryPeak(
    JNIEnv* env,jobject,jlong handle) {
    auto* e=reinterpret_cast<Executor*>(handle);
    if(!e){fail(env,"Spectral engine is closed");return nullptr;}
    std::lock_guard<std::mutex> guard(e->lock);
    // GPU pool excludes its two <=64MiB staging chunks. Host float buffers
    // are the input and readback, and Java only owns the finished core/band.
    const jlong values[5]={jlong(e->memoryPixels),jlong(e->memoryLivePeak),jlong(e->memoryResidentPeak),jlong(e->memoryHostBytes),134217728};
    auto result=env->NewLongArray(5);if(result)env->SetLongArrayRegion(result,0,5,values);return result;
}

extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_NativeSpectral_nativeTrim(
    JNIEnv* env,jobject,jlong handle) {
    try {
        auto* e=reinterpret_cast<Executor*>(handle);if(!e)return;
        std::lock_guard<std::mutex> guard(e->lock);std::string error;
        if(!e->gpu->flush(error))throw std::runtime_error(error);
        e->negative={};e->previews.clear();e->pipeline.reset();
        if(e->sourceFile){fclose(e->sourceFile);e->sourceFile=nullptr;}
        e->sourcePath.clear();e->sourceWidth=0;e->sourceHeight=0;
        e->paramsKey.clear();e->shootKey.clear();e->width=0;e->height=0;e->inputHash=0;
        e->gpu->trim_pool(0);
    } catch(const std::exception& error) {fail(env,error.what());}
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_NativeSpectral_nativeClose(JNIEnv*,jobject,jlong handle) {delete reinterpret_cast<Executor*>(handle);}
extern "C" JNIEXPORT jstring JNICALL Java_com_spektra_film_NativeSpectral_nativeDevice(JNIEnv* env,jobject,jlong handle) {
    auto* e=reinterpret_cast<Executor*>(handle);
    return env->NewStringUTF(e?e->gpu->device_name().c_str():"");
}

namespace {
struct GeometryPlane {
    int fd=-1,width=0,height=0,cropX=0,cropY=0,outWidth=0,outHeight=0;
    size_t bytes=0;
    const uint16_t* pixels=nullptr;
    double inverse[9]{};
    ~GeometryPlane(){if(pixels)munmap(const_cast<uint16_t*>(pixels),bytes);if(fd>=0)close(fd);}
};
}
extern "C" JNIEXPORT jlong JNICALL Java_com_spektra_film_GeometryResampler_nativeOpen(
    JNIEnv* env,jobject,jstring path,jint width,jint height,jint frameWidth,jint frameHeight,jdoubleArray matrix,jint cropX,jint cropY,jint outWidth,jint outHeight) {
    try {
        if(width<1 || height<1 || frameWidth<1 || frameHeight<1 || int64_t(width)*height!=int64_t(frameWidth)*frameHeight || !matrix || env->GetArrayLength(matrix)!=9 || cropX<0 || cropY<0 || outWidth<1 || outHeight<1 || int64_t(cropX)+outWidth>frameWidth || int64_t(cropY)+outHeight>frameHeight)
            throw std::runtime_error("Invalid full-resolution geometry plane");
        auto p=std::make_unique<GeometryPlane>();p->width=width;p->height=height;p->cropX=cropX;p->cropY=cropY;p->outWidth=outWidth;p->outHeight=outHeight;
        p->bytes=size_t(width)*height*6;p->fd=open(string(env,path).c_str(),O_RDONLY);
        struct stat info{};if(p->fd<0 || fstat(p->fd,&info)!=0 || size_t(info.st_size)!=p->bytes)throw std::runtime_error("Complete geometry plane is unavailable");
        void* mapped=mmap(nullptr,p->bytes,PROT_READ,MAP_SHARED,p->fd,0);
        if(mapped==MAP_FAILED)throw std::runtime_error("Cannot map complete geometry plane");
        p->pixels=static_cast<const uint16_t*>(mapped);env->GetDoubleArrayRegion(matrix,0,9,p->inverse);
        for(double v:p->inverse)if(!std::isfinite(v))throw std::runtime_error("Invalid geometry matrix");
        return reinterpret_cast<jlong>(p.release());
    }catch(const std::exception& error){fail(env,error.what());return 0;}
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_GeometryResampler_nativeRow(
    JNIEnv* env,jobject,jlong handle,jint row,jshortArray target,jint offset) {
    try {
        auto* p=reinterpret_cast<GeometryPlane*>(handle);
        if(!p || row<0 || row>=p->outHeight || !target || offset<0 || int64_t(offset)+int64_t(p->outWidth)*3>env->GetArrayLength(target))throw std::runtime_error("Invalid geometry output row");
        std::vector<jshort> result(size_t(p->outWidth)*3);const auto& m=p->inverse;const double dy=row+p->cropY;
        for(int x=0;x<p->outWidth;++x) {
            const double dx=x+p->cropX,d=m[6]*dx+m[7]*dy+m[8];
            const double sx=(m[0]*dx+m[1]*dy+m[2])/d,sy=(m[3]*dx+m[4]*dy+m[5])/d;
            if(!std::isfinite(sx) || !std::isfinite(sy) || sx<-.001 || sy<-.001 || sx>p->width-1+.001 || sy>p->height-1+.001)continue;
            const double cx=std::clamp(sx,0.,double(p->width-1)),cy=std::clamp(sy,0.,double(p->height-1));
            const int x0=int(cx),y0=int(cy),x1=std::min(x0+1,p->width-1),y1=std::min(y0+1,p->height-1);
            const double fx=cx-x0,fy=cy-y0;
            for(int c=0;c<3;++c) {
                const double a=p->pixels[(size_t(y0)*p->width+x0)*3+c],b=p->pixels[(size_t(y0)*p->width+x1)*3+c];
                const double q=p->pixels[(size_t(y1)*p->width+x0)*3+c],r=p->pixels[(size_t(y1)*p->width+x1)*3+c];
                result[size_t(x)*3+c]=jshort(std::lround((a+(b-a)*fx)*(1-fy)+(q+(r-q)*fx)*fy));
            }
        }
        env->SetShortArrayRegion(target,offset,jsize(result.size()),result.data());
    }catch(const std::exception& error){fail(env,error.what());}
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_GeometryResampler_nativeClose(JNIEnv*,jobject,jlong handle){delete reinterpret_cast<GeometryPlane*>(handle);}
