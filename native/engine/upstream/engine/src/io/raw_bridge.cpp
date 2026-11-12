#include "spektrafilm/spk_raw.h"
#include "raw_decoder.hpp"
#include "json.hpp"
#include <filesystem>
#include <memory>
#include <cstring>
#include <exception>

#if defined(_WIN32)
#define SPK_RAW_API __declspec(dllexport)
#else
#define SPK_RAW_API __attribute__((visibility("default")))
#endif
namespace {
// DLL callers may use MSVC-created Qt/Python threads. Do not register a
// MinGW std::string TLS destructor on those foreign threads: the static
// runtime's detach callbacks can otherwise corrupt the Windows heap.
// Trivially destructible TLS storage keeps the per-thread borrowed contract.
thread_local char last_error[8192]={};
thread_local char probe_reply[65536]={};
void set_error(const std::string& error){size_t n=std::min(error.size(),sizeof(last_error)-1);std::memcpy(last_error,error.data(),n);last_error[n]=0;}
using spk::Json;
struct OwnedRaw {spk::io::DecodedRaw frame;std::string metadata;};
template<class T> Json values(const T& array){Json out=Json::array();for(const auto& v:array)out.push(Json(double(v)));return out;}
Json metadata(const spk::io::RawMetadata& m){
    Json j=Json::object();j.set("make",Json(m.make));j.set("model",Json(m.model));j.set("decoder",Json(m.decoder_name));j.set("libraw_version",Json(m.libraw_version));
    j.set("source_color_space",Json(std::string("ProPhoto RGB")));j.set("source_linear",Json(true));j.set("headroom_enabled",Json(m.headroom_enabled));j.set("white_balance_exposure_restore",Json(m.white_balance_exposure_restore));
    uint32_t w=m.sizes_before_postprocess.width,h=m.sizes_before_postprocess.height;if(m.raw_flip&4)std::swap(w,h);j.set("source_width",Json(double(w)));j.set("source_height",Json(double(h)));j.set("raw_flip",Json(double(m.raw_flip)));
    j.set("camera_whitebalance",values(m.camera_whitebalance));j.set("applied_whitebalance",values(m.post_scale_pre_mul));j.set("camera_from_xyz",values(m.camera_from_xyz));j.set("camera_to_output",values(m.camera_to_output));j.set("rgb_cam",values(m.rgb_cam));
    j.set("black_level",Json(double(m.black)));j.set("black_level_per_channel",values(m.black_level_per_channel));j.set("white_level",Json(double(m.white_level)));j.set("camera_white_level_per_channel",values(m.camera_white_level_per_channel));j.set("as_shot_wb_applied",Json(m.as_shot_wb_applied));j.set("process_warnings",Json(double(m.process_warnings)));
    return j;
}
}
extern "C" {
SPK_RAW_API const char* spk_raw_probe(const char* path_utf8){
    try{if(!path_utf8||!*path_utf8){set_error("RAW metadata: empty path");return nullptr;}spk::io::RawMetadata m;bool supported=false;std::string reason,error;
        if(!spk::io::probe_raw(std::filesystem::u8path(path_utf8),m,supported,reason,error)){set_error(error);return nullptr;}
        Json j=metadata(m);j.set("headroom_supported",Json(supported));j.set("headroom_reason",Json(reason));std::string reply=j.dump();if(reply.size()>=sizeof(probe_reply)){set_error("RAW metadata exceeds response budget");return nullptr;}std::memcpy(probe_reply,reply.c_str(),reply.size()+1);return probe_reply;
    }catch(const std::exception& e){set_error(e.what());return nullptr;}
}
SPK_RAW_API int32_t spk_raw_decode(const char* path_utf8,const char* requested,int32_t half_size,spk_raw_result* out){
    if(!out||!path_utf8||!*path_utf8){set_error("RAW decode: empty path or output");return 1;}
    *out={};try{
        std::string policy=requested?requested:"auto",reason,error;auto source=std::filesystem::u8path(path_utf8);
        if(policy=="auto"){spk::io::RawMetadata m;bool supported=false;if(!spk::io::probe_raw(source,m,supported,reason,error)){set_error(error);return 1;}policy=supported?"headroom":"compatible16";}
        if(policy!="headroom"&&policy!="compatible16"){set_error("RAW decode: unknown development policy");return 1;}
        auto owned=std::make_unique<OwnedRaw>();bool ok=policy=="headroom"?spk::io::decode_raw_headroom(source,nullptr,owned->frame,error,half_size!=0):spk::io::decode_raw_compatible(source,nullptr,owned->frame,error,half_size!=0);
        if(!ok){set_error(error);return 1;}
        Json j=metadata(owned->frame.metadata);j.set("development_policy",Json(policy));j.set("headroom_reason",Json(reason));j.set("preview_proxy",Json(half_size!=0));j.set("decoded_width",Json(double(owned->frame.width)));j.set("decoded_height",Json(double(owned->frame.height)));
        const auto& t=owned->frame.timings;Json timing=Json::object();timing.set("open_ms",Json(t.open_ms));timing.set("unpack_ms",Json(t.unpack_ms));timing.set("process_ms",Json(t.process_ms));timing.set("convert_ms",Json(t.convert_ms));timing.set("total_ms",Json(t.total_ms));timing.set("workers",Json(double(t.workers)));timing.set("openmp",Json(t.openmp_enabled));j.set("timings",std::move(timing));owned->metadata=j.dump();
        out->rgb=owned->frame.rgb.data();out->width=owned->frame.width;out->height=owned->frame.height;out->metadata_json=owned->metadata.c_str();out->owner=owned.release();return 0;
    }catch(const std::exception& e){set_error(std::string("RAW decode: ")+e.what());return 1;}catch(...){set_error("RAW decode: unknown failure");return 1;}
}
SPK_RAW_API void spk_raw_free(spk_raw_result* result){if(!result)return;delete static_cast<OwnedRaw*>(result->owner);*result={};}
SPK_RAW_API const char* spk_raw_last_error(){return last_error;}
}
