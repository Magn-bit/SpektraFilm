#include "raw_decoder.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <exception>

#if defined(_WIN32)
#define SPK_OPTICS_API __declspec(dllexport)
#else
#define SPK_OPTICS_API __attribute__((visibility("default")))
#endif
namespace {
struct Point {double x,y;};
Point orient(Point p,uint32_t w,uint32_t h,uint32_t orientation){
    switch(orientation){case 2:return {w-1-p.x,p.y};case 3:return {w-1-p.x,h-1-p.y};case 4:return {p.x,h-1-p.y};case 5:return {p.y,p.x};case 6:return {h-1-p.y,p.x};case 7:return {h-1-p.y,w-1-p.x};case 8:return {p.y,w-1-p.x};default:return p;}
}
Point polynomial(Point p,const double* m){double r=p.x*p.x+p.y*p.y,f=1+r*(m[4]+r*(m[5]+r*m[6]))+2*(m[7]*p.y+m[8]*p.x);return {p.x*f+m[8]*r,p.y*f+m[7]*r};}
Point mapping(Point p,const double* models,bool chrom,uint32_t channel,double zoom,uint32_t w,uint32_t h){
    const double* base=models;p={((p.x-w/2.)/zoom+w/2.-base[2])/base[0],((p.y-h/2.)/zoom+h/2.-base[3])/base[1]};p=polynomial(p,base);p={p.x*base[0]+base[2],p.y*base[1]+base[3]};
    if(chrom&&channel!=1){const double* green=models+10;const double* model=models+(channel==0?20:30);p=polynomial({(p.x-green[2])/green[0],(p.y-green[3])/green[1]},model);p={p.x*model[9]*model[0]+model[2],p.y*model[9]*model[1]+model[3]};}return p;
}
template<class T> float sample(const T* source,uint32_t width,uint32_t height,Point p,uint32_t c,double norm){
    p.x=std::clamp(p.x,0.,double(width-1));p.y=std::clamp(p.y,0.,double(height-1));uint32_t x=uint32_t(p.x),y=uint32_t(p.y),x1=std::min(x+1,width-1),y1=std::min(y+1,height-1);double fx=p.x-x,fy=p.y-y;
    double a=double(source[(size_t(y)*width+x)*3+c])*(1-fx)+double(source[(size_t(y)*width+x1)*3+c])*fx,b=double(source[(size_t(y1)*width+x)*3+c])*(1-fx)+double(source[(size_t(y1)*width+x1)*3+c])*fx;return float((a*(1-fy)+b*fy)*norm);
}
template<class T> void correct(const T* source,uint32_t width,uint32_t height,uint32_t orientation,const double* models,bool chrom,double zoom,float* output,double norm){
    uint32_t rw=orientation>=5?height:width,rh=orientation>=5?width:height,inv=orientation==6?8:orientation==8?6:orientation;
    #pragma omp parallel for schedule(static)
    for(int64_t y=0;y<int64_t(height);++y)for(uint32_t x=0;x<width;++x){Point raw=orient({double(x),double(y)},width,height,inv);for(uint32_t c=0;c<3;++c){Point p=mapping(raw,models,chrom,c,zoom,rw,rh);p=orient(p,rw,rh,orientation);output[(size_t(y)*width+x)*3+c]=sample(source,width,height,p,c,norm);}}
}
}
extern "C" SPK_OPTICS_API int32_t spk_lens_correct(const void* input,uint32_t width,uint32_t height,uint32_t sample_type,uint32_t orientation,const double* models,int32_t chromatic,double zoom,float* output,double* elapsed_ms){
    try{
        if(!input||!output||!models||width<2||height<2||orientation<1||orientation>8||!std::isfinite(zoom)||zoom<.5||zoom>2)return 1;
        for(size_t i=0;i<40;++i)if(!std::isfinite(models[i]))return 1;for(size_t i=0;i<(chromatic?4u:1u);++i)if(models[10*i]<=0||models[10*i+1]<=0)return 1;
        spk::io::RawDecodeThreadScope workers;auto begin=std::chrono::steady_clock::now();
        if(sample_type==1)correct(static_cast<const uint8_t*>(input),width,height,orientation,models,chromatic!=0,zoom,output,1./255.);
        else if(sample_type==2)correct(static_cast<const uint16_t*>(input),width,height,orientation,models,chromatic!=0,zoom,output,1./65535.);
        else if(sample_type==3)correct(static_cast<const float*>(input),width,height,orientation,models,chromatic!=0,zoom,output,1.);
        else return 1;
        if(elapsed_ms)*elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();return 0;
    }catch(...){return 1;}
}
