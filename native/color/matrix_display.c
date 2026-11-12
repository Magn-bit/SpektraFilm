/* Standard matrix/TRC display fast path. Source pixels stay float32; these
 * one-dimensional transfer tables evaluate ICC curves, never film colour.
 * Tables/matrix belong to the caller and this function owns no global state. */
#include <stdint.h>
#include <math.h>
#ifdef _WIN32
#define SPK_DISPLAY_API __declspec(dllexport)
#else
#define SPK_DISPLAY_API
#endif

static float table_value(const float* table,uint32_t size,float value){
    if(value<=0.f)return table[0];
    if(value>=1.f)return table[size-1];
    float position=value*(float)(size-1);
    uint32_t left=(uint32_t)position;
    float weight=position-(float)left;
    return table[left]+(table[left+1]-table[left])*weight;
}

SPK_DISPLAY_API int spk_matrix_display_srgb(const float* source,float* output,uint32_t pixels,
        const float* decoding,const float* encoding,uint32_t table_size,
        const float* matrix,const float* curve){
    if(!source||!output||!decoding||!encoding||!matrix||!curve||table_size<2)return 1;
    for(uint32_t i=0;i<pixels;++i){
        float linear[3];
        for(uint32_t c=0;c<3;++c){
            float value=source[3*i+c];
            if(!isfinite(value))return 2;
            /* Preserve scene headroom and negative float values before the
             * matrix; only the target display TRC clamps its finite gamut. */
            linear[c]=(value<0.f||value>1.f)?
                (value<curve[4]?curve[3]*value+curve[6]:
                    powf(fmaxf(curve[1]*value+curve[2],0.f),curve[0])+curve[5]):
                table_value(decoding,table_size,value);
        }
        for(uint32_t c=0;c<3;++c){
            const float* row=matrix+3*c;
            float value=row[0]*linear[0]+row[1]*linear[1]+row[2]*linear[2];
            output[3*i+c]=table_value(encoding+c*table_size,table_size,value);
        }
    }
    return 0;
}
