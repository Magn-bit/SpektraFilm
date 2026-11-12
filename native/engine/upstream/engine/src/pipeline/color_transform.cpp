#include "color_transform.hpp"
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace spk::colour_preview {
namespace {
std::vector<float> numbers(const Json& value,size_t count) {
    if(!value.is_array() || value.items().size()!=count)
        throw std::runtime_error("colour preview: invalid setup array");
    std::vector<float> result;result.reserve(count);
    for(const auto& entry:value.items()) {
        double number=entry.as_double();
        if(!std::isfinite(number))throw std::runtime_error("colour preview: non-finite setup");
        result.push_back(float(number));
    }
    return result;
}
}
bool transform(gpu::Gpu* gpu,const float* rgb,uint32_t width,uint32_t height,
               const Json& setup,const float* cmax,uint32_t cmax_count,
               float* output,std::string& error) {
    try {
        const uint64_t pixels=uint64_t(width)*height;
        if(!gpu || !rgb || !output || !pixels || pixels>std::numeric_limits<uint32_t>::max()/3) {
            error="colour preview: invalid RGB dimensions";return false;
        }
        const uint32_t count=uint32_t(pixels),elements=count*3;
        const size_t bytes=size_t(elements)*sizeof(float);
        for(size_t i=0;i<elements;++i)if(!std::isfinite(rgb[i])) {
            error="colour preview: samples must be finite";return false;
        }
        const auto matrix=numbers(setup.at("matrix"),9);
        std::array<float,9> column{};
        for(size_t row=0;row<3;++row)for(size_t col=0;col<3;++col)column[row*3+col]=matrix[col*3+row];
        const auto& gamut=setup.at("gamut_compress");
        const bool compress=gamut.at("algorithm").as_string()=="cam16ucs";
        const uint32_t rows=uint32_t(gamut.at("cmax_rows").as_int()),cols=uint32_t(gamut.at("cmax_cols").as_int());
        std::vector<float> m2x,m2r,k;
        if(compress) {
            if(!cmax || rows<2 || cols<2 || uint64_t(rows)*cols!=cmax_count) {
                error="colour preview: invalid engine C_max table";return false;
            }
            m2x=numbers(gamut.at("m_to_xyz"),9);m2r=numbers(gamut.at("m_to_rgb"),9);k=numbers(gamut.at("k"),22);
        }
        // A matrix between RGB gamuts can yield legitimate negative samples,
        // including tiny roundoff at black. Keep the standalone ABI finite
        // without changing the upstream film pipeline's Adobe pow semantics.
        auto extended_cctf=[](uint32_t mode) { return mode==2u ? 6u : mode; };
        const uint32_t decode[]={elements,extended_cctf(uint32_t(setup.at("source_cctf_mode").as_int()))};
        const uint32_t encode[]={count,extended_cctf(uint32_t(setup.at("target_cctf_mode").as_int()))};
        const float identity[]={1,0,0,0,1,0,0,0,1};
        auto current=gpu->upload(rgb,bytes,error);if(!current)return false;
        auto next=gpu->alloc(bytes,error);if(!next)return false;
        using gpu::Arg;
        if(!gpu->dispatch("spk_cctf_decode",{Arg::buf(current),Arg::inline_bytes(decode,2),Arg::buf(next)},elements,error)
           || !gpu->flush(error))return false;
        current=std::move(next);next=gpu->alloc(bytes,error);if(!next)return false;
        if(!gpu->dispatch("spk_matmul3",{Arg::buf(current),Arg::inline_bytes(column.data(),9),Arg::inline_bytes(&count,1),Arg::buf(next)},count,error)
           || !gpu->flush(error))return false;
        current=std::move(next);
        if(compress) {
            auto table=gpu->upload(cmax,size_t(cmax_count)*sizeof(float),error);if(!table)return false;
            next=gpu->alloc(bytes,error);if(!next)return false;
            const uint32_t meta[]={count,rows,cols,gamut.at("lightness_compression_active").as_bool()?1u:0u};
            if(!gpu->dispatch("spk_cam16ucs_compress",{Arg::buf(current),Arg::inline_bytes(m2x.data(),9),Arg::inline_bytes(m2r.data(),9),Arg::buf(table),Arg::inline_bytes(k.data(),22),Arg::inline_bytes(meta,4),Arg::buf(next)},count,error)
               || !gpu->flush(error))return false;
            current=std::move(next);
        }
        next=gpu->alloc(bytes,error);if(!next)return false;
        if(!gpu->dispatch("spk_cctf_encode_matrix",{Arg::buf(current),Arg::inline_bytes(identity,9),Arg::inline_bytes(encode,2),Arg::buf(next)},count,error)
           || !gpu->flush(error))return false;
        return gpu->read(next.get(),0,output,bytes,error);
    } catch(const std::exception& exception) {error=exception.what();return false;}
}
}
