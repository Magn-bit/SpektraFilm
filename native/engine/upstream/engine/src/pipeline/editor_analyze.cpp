#include "editor_analyze.hpp"
#include "latitude_fit.hpp"
#include "digital_intermediate.hpp"
#include <algorithm>
#include <cmath>
#include <exception>

namespace spk::editor {
namespace {
Json array(const std::vector<double>& v){Json j=Json::array();for(double x:v)j.push(Json(x));return j;}
Json side(const slm::Side& s){Json j=Json::object();j.set("on",Json(s.on));j.set("pull_back",Json(s.pull_back));j.set("minimum_pull_back",Json(s.minimum));j.set("scene_extreme_ev",Json(s.extreme));j.set("medium_boundary_ev",Json(s.boundary));if(s.on){j.set("knee",Json(s.knee));j.set("room",Json(s.room));}j.set("landing_ev",Json(s.landing));j.set("slope_at_extreme",Json(s.slope));return j;}
Json issues(const std::vector<slm::FitIssue>& v){Json list=Json::array();for(const auto& x:v){Json j=Json::object();j.set("code",Json(x.code));j.set("side",Json(x.side));j.set("message",Json(x.message));list.push(std::move(j));}return list;}
bool medium(gpu::Gpu* gpu,Colour* colour,Blob* blob,SetupCache* cache,const Params& source,slm::Medium& out,std::string& error){
    Params p=source;p.camera.auto_exposure=false;p.camera.exposure_baseline_ev=0;p.camera.scene_latitude.active=false;p.film_render.grain.active=false;p.film_render.grain.sublayers_active=false;p.film_render.halation.active=false;p.film_render.overscan.active=false;p.film_render.date_imprint.active=false;p.print_render.glare.active=false;p.print_render.contrast_mask.active=false;p.print_render.edr_enabled=false;p.io.geometry=GeometryParams{};p.io.input_cctf_decoding=false;p.io.output_cctf_encoding=false;p.settings.striped=false;
    Mat3 xyz;if(!colour->matrix_RGB_to_XYZ(p.io.output_color_space,nullptr,"CAT02",xyz,error))return false;
    constexpr uint32_t samples=1024,rows=8;std::vector<float> ramp(size_t(samples)*rows*3);out.ev.resize(samples);
    for(uint32_t x=0;x<samples;++x){out.ev[x]=-12.+24.*x/(samples-1.);float light=float(slm::kMidgray*std::exp2(out.ev[x]));for(uint32_t y=0;y<rows;++y)for(uint32_t c=0;c<3;++c)ramp[(size_t(y)*samples+x)*3+c]=light;}
    Pipeline pipeline(gpu,colour,blob,cache);if(!pipeline.build(p,error))return false;pipeline.set_source_long_edge(samples,samples);
    Image in,negative,rgb;in.w=samples;in.h=rows;in.c=3;in.buf=gpu->upload(ramp.data(),ramp.size()*sizeof(float),error);
    if(!in.valid()||!pipeline.run_film(in,negative,nullptr,error)||!pipeline.run_print(negative,rgb,nullptr,error)||!gpu->flush(error))return false;
    std::vector<float> pixels(rgb.elements());if(!gpu->read(rgb.buf.get(),0,pixels.data(),rgb.bytes(),error))return false;
    bool di=p.io.digital_intermediate&&!p.io.scan_film&&!p.film.info.is_positive();auto light=[di](float v){return di?std::pow(10.,(v*kDiCineonMax-kDiCineonWhite)/kDiCineonPerDecade):double(v);};out.y.assign(samples,0.);
    for(uint32_t y=0;y<rgb.h;++y)for(uint32_t x=0;x<rgb.w&&x<samples;++x){const float* q=pixels.data()+(size_t(y)*rgb.w+x)*rgb.c;out.y[x]+=(xyz.m[1][0]*light(q[0])+xyz.m[1][1]*light(q[1])+xyz.m[1][2]*light(q[2]))/rgb.h;}
    return slm::read_boundaries(out,error);
}
Image proxy(gpu::Gpu* gpu,const spk_image& in,std::string& error){
    Image image;image.c=3;uint32_t edge=std::max(in.width,in.height);double scale=edge>1600?1600./edge:1.;image.w=std::max(1u,uint32_t(std::lround(in.width*scale)));image.h=std::max(1u,uint32_t(std::lround(in.height*scale)));
    if(scale==1){image.buf=gpu->upload(in.data,size_t(in.width)*in.height*3*sizeof(float),error);return image;}
    // A bounded area sample prevents a 100MP photo being uploaded merely for
    // the meter. A 4x4 stratified footprint avoids single-pixel aliasing.
    std::vector<float> small(size_t(image.w)*image.h*3);double sx=double(in.width)/image.w,sy=double(in.height)/image.h;
    for(uint32_t y=0;y<image.h;++y)for(uint32_t x=0;x<image.w;++x){double sum[3]={};for(int yy=0;yy<4;++yy)for(int xx=0;xx<4;++xx){uint32_t px=std::min(in.width-1,uint32_t((x+(xx+.5)/4.)*sx)),py=std::min(in.height-1,uint32_t((y+(yy+.5)/4.)*sy));for(size_t c=0;c<3;++c)sum[c]+=in.data[(size_t(py)*in.width+px)*3+c];}for(size_t c=0;c<3;++c)small[(size_t(y)*image.w+x)*3+c]=float(sum[c]/16.);}
    image.buf=gpu->upload(small.data(),small.size()*sizeof(float),error);return image;
}
}
bool analyze(gpu::Gpu* gpu,Colour* colour,Blob* blob,SetupCache* cache,const Json& neutral_filters,const Params& params,const spk_image& input,const std::string& target,const Json& request,Json& reply,std::string& error){
    try{
        if(!gpu||!colour||!blob||!input.data||!input.width||!input.height||input.channels!=3){error="editor analysis: packed RGB source required";return false;}
        if(target!="exposure"&&target!="filter_pack"&&target!="both"&&target!="scene_latitude"){error="editor analysis: unknown target";return false;}
        if(!request.is_object()){error="editor analysis: request must be an object";return false;}
        reply=Json::object();Params p=params;
        if(target!="scene_latitude"){
            Json solved=Json::object();if(target!="filter_pack"){
                Pipeline pipeline(gpu,colour,blob,cache);if(!pipeline.build(p,error))return false;Image in=proxy(gpu,input,error);ExposureEvs evs;if(!in.valid()||!pipeline.measure_meter_evs(in,evs,error))return false;
                solved.set("exposure_compensation_ev",Json(evs.of(p.camera.auto_exposure_method)));Json ev=Json::object();ev.set("balanced",Json(evs.balanced));ev.set("center",Json(evs.center));ev.set("protect_highlights",Json(evs.protect_highlights));ev.set("protect_shadows",Json(evs.protect_shadows));reply.set("exposure_ev_by_method",std::move(ev));
            }
            if(target!="exposure"){Params fit=p;fit.settings.neutral_print_filters_from_database=true;if(!digest(fit,neutral_filters,error))return false;solved.set("c_filter_neutral",Json(fit.enlarger.c_filter_neutral));solved.set("m_filter_neutral",Json(fit.enlarger.m_filter_neutral));solved.set("y_filter_neutral",Json(fit.enlarger.y_filter_neutral));}
            reply.set("solved_params",std::move(solved));return true;
        }
        auto& base=p.camera.scene_latitude;if(request.at("rolloff").is_number())base.rolloff=request.at("rolloff").as_double();if(request.at("max_lift").is_number())base.max_lift=request.at("max_lift").as_double();if(request.at("norm").is_string())base.norm=request.at("norm").as_string();
        if(base.rolloff<1||base.rolloff>4||base.max_lift<.25||base.max_lift>12||!is_known_scene_latitude_norm(base.norm)){error="scene latitude: invalid curve request";return false;}
        slm::Extremes at;double sp=request.at("shadow_percentile").as_double(.1),hp=request.at("highlight_percentile").as_double(99.9);if((sp!=.1&&sp!=1)||(hp!=99.9&&hp!=99)){error="scene latitude: unsupported percentile";return false;}at.shadow_p1=sp==1;at.highlight_p99=hp==99;
        slm::Medium m;if(!medium(gpu,colour,blob,cache,p,m,error))return false;
        Pipeline pipeline(gpu,colour,blob,cache);if(!pipeline.build(p,error))return false;Image in=proxy(gpu,input,error);if(!in.valid())return false;
        double ev=p.camera.exposure_baseline_ev;if(p.camera.auto_exposure){ExposureEvs meter;if(!pipeline.measure_meter_evs(in,meter,error))return false;ev=meter.of(p.camera.auto_exposure_method);}
        double region[4]={0,0,1,1};bool has_region=request.at("region").is_array()&&request.at("region").items().size()==4;if(has_region)for(size_t i=0;i<4;++i)region[i]=request.at("region").items()[i].as_double(i<2?0:1);
        std::vector<double> E;if(!pipeline.scene_latitude_sample(in,ev,E,error,has_region?region:nullptr))return false;auto scene=slm::scene_stats(std::move(E));if(scene.samples==0){error="scene latitude: no positive pixels";return false;}
        double margin=request.at("margin").as_double(.25);auto suggested=slm::suggest(m,scene,margin,base,at);auto fit=slm::fit(m,scene,request.at("highlight_pull_back").as_double(suggested.highlight_pull_back),request.at("shadow_pull_back").as_double(suggested.shadow_pull_back),base,at);
        Json medium_json=Json::object();medium_json.set("shadow_ev",Json(m.shadow_ev));medium_json.set("highlight_ev",Json(m.highlight_ev));medium_json.set("latitude_stops",Json(m.highlight_ev-m.shadow_ev));medium_json.set("y_black",Json(m.y_black));medium_json.set("y_white",Json(m.y_white));Json ramp_ev=Json::array(),ramp_y=Json::array();for(size_t i=0;i<m.ev.size();i+=8){ramp_ev.push(Json(m.ev[i]));ramp_y.push(Json(m.y[i]));}medium_json.set("ramp_ev",std::move(ramp_ev));medium_json.set("ramp_y",std::move(ramp_y));reply.set("medium",std::move(medium_json));
        Json sj=Json::object();sj.set("norm",Json(base.norm));sj.set("samples",Json(double(scene.samples)));sj.set("p0_1",Json(scene.p01));sj.set("p1",Json(scene.p1));sj.set("p50",Json(scene.p50));sj.set("p99",Json(scene.p99));sj.set("p99_9",Json(scene.p999));Json hist=Json::object();hist.set("lo_ev",Json(slm::SceneStats::kLo));hist.set("hi_ev",Json(slm::SceneStats::kHi));hist.set("fractions",array(scene.histogram));if(fit.valid())hist.set("placed_fractions",array(slm::placed_histogram(scene,fit.params)));sj.set("histogram",std::move(hist));reply.set("scene",std::move(sj));
        Json sg=Json::object();sg.set("highlight_pull_back",Json(suggested.highlight_pull_back));sg.set("shadow_pull_back",Json(suggested.shadow_pull_back));sg.set("margin_used",Json(suggested.margin_used));sg.set("valid",Json(suggested.found));reply.set("suggested",std::move(sg));
        Json fj=Json::object();fj.set("valid",Json(fit.valid()));fj.set("issues",issues(fit.issues));fj.set("warnings",issues(fit.warnings));fj.set("highlight",side(fit.highlight));fj.set("shadow",side(fit.shadow));fj.set("core_stops",fit.core?Json(*fit.core):Json());
        if(fit.valid()){Json d=Json::object();d.set("scene_latitude_active",Json(fit.highlight.on||fit.shadow.on));d.set("scene_latitude_norm",Json(fit.params.norm));d.set("scene_latitude_highlight_knee",Json(fit.params.highlight_knee));d.set("scene_latitude_highlight_room",Json(fit.params.highlight_room));d.set("scene_latitude_shadow_knee",Json(fit.params.shadow_knee));d.set("scene_latitude_shadow_room",Json(fit.params.shadow_room));d.set("scene_latitude_rolloff",Json(fit.params.rolloff));d.set("scene_latitude_max_lift",Json(fit.params.max_lift));fj.set("params_delta",std::move(d));}reply.set("fit",std::move(fj));return true;
    }catch(const std::exception& e){error=std::string("editor analysis: ")+e.what();return false;}
}
}
