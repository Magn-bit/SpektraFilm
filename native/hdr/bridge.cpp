// Small owned-memory C boundary around Google's real Ultra HDR codec.
#include "ultrahdr_api.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <cstdint>

#if defined(_WIN32)
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif

namespace {
thread_local std::string failure;
void require(uhdr_error_info_t e) {
    if(e.error_code!=UHDR_CODEC_OK)
        throw std::runtime_error(e.has_detail ? e.detail : "Ultra HDR codec refused the image");
}
uhdr_compressed_image_t compressed(const void* data,size_t size,int gamut) {
    return {const_cast<void*>(data),size,size,static_cast<uhdr_color_gamut_t>(gamut),UHDR_CT_SRGB,UHDR_CR_FULL_RANGE};
}
struct EncoderDelete {void operator()(uhdr_codec_private_t* p) const {if(p)uhdr_release_encoder(p);}};
struct DecoderDelete {void operator()(uhdr_codec_private_t* p) const {if(p)uhdr_release_decoder(p);}};
}

API const char* spk_hdr_version(){return UHDR_LIB_VERSION_STR;}
API const char* spk_hdr_error(){return failure.c_str();}
API void spk_hdr_free(void* p){std::free(p);}

API int spk_hdr_encode(const void* base,size_t base_size,const void* map,size_t map_size,
                      float headroom,int gamut,void** output,size_t* output_size) {
    if(output)*output=nullptr;if(output_size)*output_size=0;
    try {
        if(!output || !output_size || !base || !map || !base_size || !map_size ||
            !std::isfinite(headroom) || headroom<=1 || headroom>16.8 || (gamut!=0 && gamut!=1))
            throw std::runtime_error("Invalid HDR base, gain map, headroom, or gamut");
        std::unique_ptr<uhdr_codec_private_t,EncoderDelete> encoder(uhdr_create_encoder());
        if(!encoder)throw std::runtime_error("Cannot allocate HDR encoder");
        auto b=compressed(base,base_size,gamut),m=compressed(map,map_size,gamut);
        uhdr_gainmap_metadata_t metadata{};
        for(int c=0;c<3;c++){
            metadata.max_content_boost[c]=headroom;metadata.min_content_boost[c]=1;
            metadata.gamma[c]=1;metadata.offset_sdr[c]=0;metadata.offset_hdr[c]=0;
        }
        metadata.hdr_capacity_min=1;metadata.hdr_capacity_max=headroom;metadata.use_base_cg=1;
        require(uhdr_enc_set_compressed_image(encoder.get(),&b,UHDR_BASE_IMG));
        require(uhdr_enc_set_gainmap_image(encoder.get(),&m,&metadata));
        require(uhdr_encode(encoder.get()));
        const auto encoded=uhdr_get_encoded_stream(encoder.get());
        if(!encoded || !encoded->data || !encoded->data_sz)throw std::runtime_error("HDR encoder returned no file");
        void* p=std::malloc(encoded->data_sz);if(!p)throw std::bad_alloc();
        std::memcpy(p,encoded->data,encoded->data_sz);*output=p;*output_size=encoded->data_sz;
        failure.clear();return 0;
    }catch(const std::exception& e){failure=e.what();return -1;}
}

// Independent standards decoder. Owned packed little-endian RGBA half floats
// are returned only for checks/preview callers, never to create a file's map.
API int spk_hdr_decode(const void* data,size_t size,float display_boost,void** output,
                      size_t* output_size,unsigned* width,unsigned* height,
                      unsigned* map_width,unsigned* map_height,float* map_headroom) {
    if(output)*output=nullptr;if(output_size)*output_size=0;
    try {
        if(!data || !size || !output || !output_size || !width || !height || !map_width || !map_height || !map_headroom)
            throw std::runtime_error("Invalid HDR decoder arguments");
        std::unique_ptr<uhdr_codec_private_t,DecoderDelete> decoder(uhdr_create_decoder());
        if(!decoder)throw std::runtime_error("Cannot allocate HDR decoder");
        auto image=compressed(data,size,-1);
        require(uhdr_dec_set_image(decoder.get(),&image));
        require(uhdr_dec_set_out_img_format(decoder.get(),UHDR_IMG_FMT_64bppRGBAHalfFloat));
        require(uhdr_dec_set_out_color_transfer(decoder.get(),UHDR_CT_LINEAR));
        require(uhdr_dec_set_out_max_display_boost(decoder.get(),display_boost));
        require(uhdr_dec_probe(decoder.get()));
        auto metadata=uhdr_dec_get_gainmap_metadata(decoder.get());
        if(!metadata)throw std::runtime_error("File has no real gain map");
        *map_width=uhdr_dec_get_gainmap_width(decoder.get());
        *map_height=uhdr_dec_get_gainmap_height(decoder.get());
        *map_headroom=metadata->hdr_capacity_max;
        require(uhdr_decode(decoder.get()));
        auto pixels=uhdr_get_decoded_image(decoder.get());
        if(!pixels || !pixels->planes[0])throw std::runtime_error("HDR decoder returned no pixels");
        *width=pixels->w;*height=pixels->h;const size_t row=static_cast<size_t>(pixels->w)*8;
        if(pixels->h>SIZE_MAX/row)throw std::runtime_error("HDR image size overflow");
        const size_t bytes=row*pixels->h;
        auto p=static_cast<unsigned char*>(std::malloc(bytes));if(!p)throw std::bad_alloc();
        const auto source=static_cast<const unsigned char*>(pixels->planes[0]);
        for(unsigned y=0;y<pixels->h;y++)std::memcpy(p+y*row,source+static_cast<size_t>(y)*pixels->stride[0]*8,row);
        *output=p;*output_size=bytes;failure.clear();return 0;
    }catch(const std::exception& e){failure=e.what();return -1;}
}
