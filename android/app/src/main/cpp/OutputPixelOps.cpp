#include <jni.h>
#include <array>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <new>

namespace {
struct Tables {
    std::array<float,65536> decode{},srgb{},prophoto{};
    Tables() {
        for(int i=0;i<65536;++i) {
            const double x=i/65535.0;
            decode[i]=float(x<=.04045?x/12.92:std::pow((x+.055)/1.055,2.4));
            srgb[i]=float(x<=.0031308?12.92*x:1.055*std::pow(x,1.0/2.4)-.055);
            prophoto[i]=float(x<=1.0/512?16*x:std::pow(x,1.0/1.8));
        }
    }
};
const Tables& tables(){static const Tables result;return result;}
uint16_t encode(float value,int transfer) {
    const float v=std::clamp(value,0.f,1.f);
    if(transfer==2)return uint16_t(std::lround(v*65535.f));
    const auto& lut=transfer==1?tables().prophoto:tables().srgb;
    const float x=v*65535.f;const unsigned i=unsigned(x);const unsigned j=std::min(65535u,i+1);
    return uint16_t(std::clamp(std::lround((lut[i]+(lut[j]-lut[i])*(x-i))*65535.f),0l,65535l));
}
void error(JNIEnv* env,const char* message){env->ThrowNew(env->FindClass("java/lang/IllegalArgumentException"),message);}
struct Resize {
    int sourceWidth,outputWidth;
    std::vector<jshort> row;
    std::vector<double> sums;
    Resize(int source,int output):sourceWidth(source),outputWidth(output),row(size_t(source)*3),sums(size_t(output)*3,0){}
};
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_OutputPixelOps_transform(
    JNIEnv* env,jobject,jshortArray data,jint offset,jint count,jfloatArray coefficients,jint transfer) {
    if(!data || !coefficients || offset<0 || count<0 || count%3 || int64_t(offset)+count>env->GetArrayLength(data) || env->GetArrayLength(coefficients)!=9 || transfer<0 || transfer>2){error(env,"无效的输出色彩转换参数");return;}
    float m[9];env->GetFloatArrayRegion(coefficients,0,9,m);
    if(env->ExceptionCheck())return;
    const auto& lut=tables().decode;
    auto* pixels=static_cast<jshort*>(env->GetPrimitiveArrayCritical(data,nullptr));if(!pixels)return;
    for(int i=offset;i<offset+count;i+=3) {
        const float r=lut[uint16_t(pixels[i])],g=lut[uint16_t(pixels[i+1])],b=lut[uint16_t(pixels[i+2])];
        pixels[i]=jshort(encode(m[0]*r+m[1]*g+m[2]*b,transfer));
        pixels[i+1]=jshort(encode(m[3]*r+m[4]*g+m[5]*b,transfer));
        pixels[i+2]=jshort(encode(m[6]*r+m[7]*g+m[8]*b,transfer));
    }
    env->ReleasePrimitiveArrayCritical(data,pixels,0);
}
extern "C" JNIEXPORT jlong JNICALL Java_com_spektra_film_OutputPixelOps_beginResize(JNIEnv* env,jobject,jint source,jint output) {
    if(source<=0 || source>100000 || output<=0 || output>source){error(env,"无效的输出尺寸");return 0;}
    try {tables();return reinterpret_cast<jlong>(new Resize(source,output));}
    catch(const std::bad_alloc&){error(env,"输出缩放行缓冲不足");return 0;}
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_OutputPixelOps_accumulateResize(JNIEnv* env,jobject,jlong handle,jshortArray pixels,jdouble weight) {
    auto* r=reinterpret_cast<Resize*>(handle);
    if(!r || !pixels || env->GetArrayLength(pixels)<r->sourceWidth*3 || !std::isfinite(weight) || weight<=0){error(env,"无效的输出行");return;}
    env->GetShortArrayRegion(pixels,0,r->sourceWidth*3,r->row.data());if(env->ExceptionCheck())return;
    const auto& lut=tables().decode;const double scale=double(r->sourceWidth)/r->outputWidth;
    for(int x=0;x<r->outputWidth;++x) {
        const double left=x*scale,right=(x+1)*scale;
        const int first=int(std::floor(left)),last=std::min(r->sourceWidth-1,int(std::ceil(right))-1);
        double rgb[3]={0,0,0};
        for(int sx=first;sx<=last;++sx) {
            const double w=std::min(right,sx+1.0)-std::max(left,double(sx));
            for(int c=0;c<3;++c)rgb[c]+=lut[uint16_t(r->row[size_t(sx)*3+c])]*w;
        }
        for(int c=0;c<3;++c)r->sums[size_t(x)*3+c]+=rgb[c]*weight/scale;
    }
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_OutputPixelOps_finishResizeRow(JNIEnv* env,jobject,jlong handle,jshortArray pixels,jdouble totalWeight) {
    auto* r=reinterpret_cast<Resize*>(handle);
    if(!r || !pixels || env->GetArrayLength(pixels)<r->outputWidth*3 || !std::isfinite(totalWeight) || totalWeight<=0){error(env,"无效的输出行");return;}
    for(int i=0;i<r->outputWidth*3;++i){r->row[i]=jshort(encode(float(r->sums[i]/totalWeight),0));r->sums[i]=0;}
    env->SetShortArrayRegion(pixels,0,r->outputWidth*3,r->row.data());
}
extern "C" JNIEXPORT void JNICALL Java_com_spektra_film_OutputPixelOps_closeResize(JNIEnv*,jobject,jlong handle){delete reinterpret_cast<Resize*>(handle);}
