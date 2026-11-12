#include "editor_process.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace spk::editor {
namespace {
using gpu::Arg;
constexpr double pi=3.14159265358979323846;
double number(const Json& j,const char* key,double fallback,double lo,double hi){
    const Json& q=j.at(key);if(q.is_null())return fallback;
    if(!q.is_number()||!std::isfinite(q.as_double())||q.as_double()<lo||q.as_double()>hi)
        throw std::runtime_error(std::string("editor: invalid ")+key);
    return q.as_double();
}
bool active(const Json& q,const char* name){return std::abs(q.at(name).as_double())>1e-12;}
std::array<double,2> point(const Json& j,std::array<double,2> d){
    if(j.is_null())return d;
    if(!j.is_array()||j.items().size()!=2)throw std::runtime_error("editor: invalid point");
    for(size_t i=0;i<2;++i){const auto& x=j.items()[i];if(!x.is_number()||!std::isfinite(x.as_double())||x.as_double()<0||x.as_double()>1)throw std::runtime_error("editor: point outside source");d[i]=x.as_double();}return d;
}
std::array<double,3> white(double t,double tint){
    double x=t>4000?-3.0258469e9/(t*t*t)+2.1070379e6/(t*t)+.2226347e3/t+.240390:-.2661239e9/(t*t*t)-.2343580e6/(t*t)+.8776956e3/t+.179910;
    double y=t<=2222?-1.1063814*x*x*x-1.34811020*x*x+2.18555832*x-.20219683:t<=4000?-.9549476*x*x*x-1.37418593*x*x+2.09137015*x-.16748867:3.081758*x*x*x-5.8733867*x*x+3.75112997*x-.37001483;
    y=std::clamp(y+tint*.000045,.30,.36);return {x/y,1.,(1-x-y)/y};
}
Mat3 pre_matrix(const Colour& colour,const Json& s,const std::string& source){
    Mat3 convert;if(source!="sRGB"){std::string error;if(!colour.matrix_RGB_to_RGB(source,"sRGB","CAT02",convert,error))throw std::runtime_error(error);}
    const double t=number(s,"temperature",6500,2000,10000),tint=number(s,"tint",0,-100,100);
    Mat3 adaptation;
    if(t!=6500||tint!=0){
        const double b[]={.8951,.2664,-.1614,-.7502,1.7135,.0367,.0389,-.0685,1.0296};
        const double rgb[]={.4124564,.3575761,.1804375,.2126729,.7151522,.072175,.0193339,.119192,.9503041};
        Mat3 bradford=Mat3::from_row_major(b),xyz=Mat3::from_row_major(rgb);auto a=white(6500,0),z=white(t,tint);double ba[3],bz[3];bradford.apply(a.data(),ba);bradford.apply(z.data(),bz);
        adaptation=xyz.inverse()*bradford.inverse()*Mat3::diag(bz[0]/ba[0],bz[1]/ba[1],bz[2]/ba[2])*bradford*xyz;
    }
    Mat3 calibration;const char* names[]={"red","green","blue"};
    for(size_t i=0;i<3;++i){std::string h="calibration_"+std::string(names[i])+"_hue",v="calibration_"+std::string(names[i])+"_saturation";
        double angle=number(s,h.c_str(),0,-100,100)*.006283185307179586,scale=1+number(s,v.c_str(),0,-100,100)/100.;
        const double axis=1/std::sqrt(3.);double c[3]={-1./3,-1./3,-1./3};c[i]+=1;double cross[3]={axis*(c[2]-c[1]),axis*(c[0]-c[2]),axis*(c[1]-c[0])};
        for(size_t r=0;r<3;++r)calibration.m[r][i]=1./3+scale*(c[r]*std::cos(angle)+cross[r]*std::sin(angle));
    }
    // Row normalisation keeps every neutral grey neutral even when each primary
    // has a different calibration. A near-zero denominator is rejected rather
    // than creating an unbounded colour transform.
    for(size_t r=0;r<3;++r){double sum=calibration.m[r][0]+calibration.m[r][1]+calibration.m[r][2];if(std::abs(sum)>.05)for(double& v:calibration.m[r])v/=sum;}
    return calibration*adaptation*convert;
}
std::vector<std::array<double,2>> curve_points(const Json& q){
    const Json& j=q.is_object()?q.at("points"):q;if(j.is_null())return {{0,0},{1,1}};
    if(!j.is_array()||j.items().size()<2||j.items().size()>256)throw std::runtime_error("editor: curves need 2..256 ordered points");
    std::vector<std::array<double,2>> out;for(const auto& x:j.items()){auto p=point(x,{0,0});if(!out.empty()&&p[0]<=out.back()[0])throw std::runtime_error("editor: curve x must increase");out.push_back(p);}
    return out;
}
// PCHIP (weighted harmonic interior derivatives, one-sided endpoint limiting),
// matching shared/color_tools.py without importing an interpreter.
void curve_table(const std::vector<std::array<double,2>>& p,float* out,bool fritsch=false,const float* inputs=nullptr){
    size_t n=p.size();std::vector<double> h(n-1),d(n-1),m(n);
    for(size_t i=0;i+1<n;++i){h[i]=p[i+1][0]-p[i][0];d[i]=(p[i+1][1]-p[i][1])/h[i];}
    if(n==2)m[0]=m[1]=d[0];else if(fritsch){
        m[0]=d[0];m[n-1]=d[n-2];
        for(size_t i=1;i+1<n;++i)m[i]=d[i-1]*d[i]<=0?0:(d[i-1]+d[i])*.5;
        for(size_t i=0;i+1<n;++i)if(d[i]!=0){double a=m[i]/d[i],b=m[i+1]/d[i],s=a*a+b*b;if(s>9){double t=3/std::sqrt(s);m[i]=t*a*d[i];m[i+1]=t*b*d[i];}}
    }else{
        for(size_t i=1;i+1<n;++i){if(d[i-1]*d[i]<=0)m[i]=0;else{double w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1];m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i]);}}
        auto end=[](double h1,double h2,double d1,double d2){double v=((2*h1+h2)*d1-h1*d2)/(h1+h2);if(v*d1<=0)return 0.;return d1*d2<0&&std::abs(v)>3*std::abs(d1)?3*d1:v;};
        m[0]=end(h[0],h[1],d[0],d[1]);m[n-1]=end(h[n-2],h[n-3],d[n-2],d[n-3]);
    }
    size_t j=0;for(size_t x=0;x<4096;++x){double q=inputs?inputs[x]:double(x)/4095;if(q<=p.front()[0]){out[x]=float(p.front()[1]);continue;}if(q>=p.back()[0]){out[x]=float(p.back()[1]);continue;}while(j+2<n&&q>p[j+1][0])++j;double t=(q-p[j][0])/h[j],t2=t*t,t3=t2*t;out[x]=float(std::clamp((2*t3-3*t2+1)*p[j][1]+(t3-2*t2+t)*h[j]*m[j]+(-2*t3+3*t2)*p[j+1][1]+(t3-t2)*h[j]*m[j+1],0.,1.));}
}
std::vector<std::array<double,2>> parametric_points(const Json& q){
    if(q.is_null())return {};if(!q.is_object())throw std::runtime_error("editor: parametric curve must be an object");
    const char* keys[]={"shadows","darks","lights","highlights"};double amounts[4],offsets[4];bool wanted=false;
    for(size_t i=0;i<4;++i){amounts[i]=number(q,keys[i],0,-100,100);wanted|=amounts[i]!=0;}
    if(!wanted)return {};
    double splits[]={0,number(q,"shadow_split",.25,.05,.95),number(q,"midtone_split",.5,.05,.95),number(q,"highlight_split",.75,.05,.95),1};
    for(size_t i=0;i<4;++i)if(splits[i+1]-splits[i]<.049999)throw std::runtime_error("editor: parametric split gap must be at least .05");
    for(size_t i=0;i<4;++i)offsets[i]=amounts[i]/100*(splits[i+1]-splits[i])*.5;
    std::vector<std::array<double,2>> out={{0,0}};
    for(size_t i=0;i<4;++i){double mid=(splits[i]+splits[i+1])*.5;out.push_back({mid,mid+offsets[i]});if(i<3)out.push_back({splits[i+1],splits[i+1]+(offsets[i]+offsets[i+1])*.5});}out.push_back({1,1});
    double floor=0;for(auto& p:out){p[1]=std::max(floor,std::clamp(p[1],0.,1.));floor=p[1];}return out;
}
std::array<double,3> wheel(double h){
    double k=h/60.;int i=int(k)%6;double x=1-std::abs(std::fmod(k,2.)-1.);double c[3];
    switch(i){case 0:c[0]=1;c[1]=x;c[2]=0;break;case 1:c[0]=x;c[1]=1;c[2]=0;break;case 2:c[0]=0;c[1]=1;c[2]=x;break;case 3:c[0]=0;c[1]=x;c[2]=1;break;case 4:c[0]=x;c[1]=0;c[2]=1;break;default:c[0]=1;c[1]=0;c[2]=x;}
    for(double& v:c)v=v<=.04045?v/12.92:std::pow((v+.055)/1.055,2.4);
    double l=std::cbrt(.4122214708*c[0]+.5363325363*c[1]+.0514459929*c[2]),m=std::cbrt(.2119034982*c[0]+.6806995451*c[1]+.1073969566*c[2]),s=std::cbrt(.0883024619*c[0]+.2817188376*c[1]+.6299787005*c[2]);
    double a=1.9779984951*l-2.428592205*m+.4505937099*s,b=.0259040371*l+.7827717662*m-.808675766*s,n=std::hypot(a,b);return {0,a/std::max(n,1e-6),b/std::max(n,1e-6)};
}
struct Mask { std::array<float,24> u{};uint32_t kind=0;std::vector<float> segments; };
std::vector<Mask> masks(const Json& list,uint32_t fw,uint32_t fh){
    std::vector<Mask> result;if(list.is_null())return result;if(!list.is_array()||list.items().size()>32)throw std::runtime_error("editor: at most 32 masks");
    for(const auto& j:list.items()){
        if(!j.is_object()||!j.at("enabled").as_bool(true)||number(j,"opacity",1,0,1)==0)continue;
        if(!active(j,"exposure")&&!active(j,"temperature")&&!active(j,"tint")&&!active(j,"contrast")&&!active(j,"saturation")&&!active(j,"highlights")&&!active(j,"shadows"))continue;
        Mask q;std::string kind=j.at("kind").as_string();q.kind=kind=="linear"?1:kind=="radial"?2:0;
        auto& u=q.u;double sx=std::max(1u,fw-1),sy=std::max(1u,fh-1);auto start=point(j.at("start"),{.25,.5}),end=point(j.at("end"),{.75,.5}),center=point(j.at("center"),{.5,.5});
        if(q.kind==1){u[4]=float(start[0]*sx);u[5]=float(start[1]*sy);u[6]=float(end[0]*sx);u[7]=float(end[1]*sy);}
        if(q.kind==2){u[4]=float(center[0]*sx);u[5]=float(center[1]*sy);u[6]=float(std::max(.5,number(j,"radius_x",.25,.002,2)*sx));u[7]=float(std::max(.5,number(j,"radius_y",.25,.002,2)*sy));double angle=number(j,"rotation",0,-360,360)*pi/180;u[8]=float(std::cos(angle));u[9]=float(std::sin(angle));u[10]=float(std::max(.001,number(j,"feather",.75,0,1)));}
        u[11]=j.at("inverted").as_bool()?1:0;u[12]=float(number(j,"opacity",1,0,1));u[13]=float(number(j,"exposure",0,-3,3));
        double t=number(j,"temperature",0,-100,100),g=number(j,"tint",0,-100,100);double gain[]={std::exp2(t*.004+g*.0015),std::exp2(-g*.0015),std::exp2(-t*.004+g*.0015)},normal=gain[0]*.2126+gain[1]*.7152+gain[2]*.0722;
        for(size_t c=0;c<3;++c)u[14+c]=float(gain[c]/normal);u[17]=float(number(j,"contrast",0,-100,100)/100);u[18]=float(number(j,"saturation",0,-100,100)/100);u[19]=float(number(j,"highlights",0,-100,100)/100);u[20]=float(number(j,"shadows",0,-100,100)/100);
        const Json& strokes=j.at("strokes");if(q.kind==0&&strokes.is_array()){
            if(strokes.items().size()>4096)throw std::runtime_error("editor: too many brush strokes");uint32_t stroke=0;
            for(const auto& st:strokes.items()){
                const Json& points=st.at("points");double flow=number(st,"flow",1,0,1);if(!points.is_array()||points.items().empty()||flow==0){++stroke;continue;}if(points.items().size()>8192)throw std::runtime_error("editor: too many brush points");
                double radius=std::max(.5,number(st,"radius",.06,.002,.5)*std::min(fw,fh)),inner=radius*(1-number(st,"feather",.75,0,1)),soft=std::max(.5,radius-inner);
                auto first=point(points.items()[0],{0,0});for(size_t k=points.items().size()==1?0:1;k<points.items().size();++k){auto last=point(points.items()[k],{0,0});float a[]={float(first[0]*sx),float(first[1]*sy),float(last[0]*sx),float(last[1]*sy),float(inner),float(soft),float(flow),st.at("erase").as_bool()?1.f:0.f,float(stroke),float(radius),0,0};q.segments.insert(q.segments.end(),a,a+12);first=last;if(q.segments.size()/12>262144)throw std::runtime_error("editor: brush data exceeds budget");}++stroke;
            }
        }
        result.push_back(std::move(q));
    }return result;
}
std::vector<uint32_t> bins(const Mask& mask,uint32_t width,uint32_t height,double ox,double oy,double scale_x,double scale_y){
    uint32_t cols=(width+63)/64,rows=(height+63)/64;size_t count=size_t(cols)*rows;std::vector<std::vector<uint32_t>> cells(count);size_t refs=0;
    for(uint32_t i=0;i<mask.segments.size()/12;++i){const float* s=mask.segments.data()+12*i;double r=s[9];int left=int(std::floor((std::min(s[0],s[2])-r-ox)/scale_x/64)),right=int(std::floor((std::max(s[0],s[2])+r-ox)/scale_x/64));int top=int(std::floor((std::min(s[1],s[3])-r-oy)/scale_y/64)),bottom=int(std::floor((std::max(s[1],s[3])+r-oy)/scale_y/64));
        if(right<0||bottom<0||left>=int(cols)||top>=int(rows))continue;left=std::max(0,left);right=std::min(int(cols)-1,right);top=std::max(0,top);bottom=std::min(int(rows)-1,bottom);
        for(int y=top;y<=bottom;++y)for(int x=left;x<=right;++x){cells[size_t(y)*cols+x].push_back(i);if(++refs>16000000)throw std::runtime_error("editor: brush spatial index exceeds budget");}
    }
    std::vector<uint32_t> result(2*count+refs);size_t offset=0;for(size_t i=0;i<count;++i){result[2*i]=uint32_t(offset);result[2*i+1]=uint32_t(cells[i].size());std::copy(cells[i].begin(),cells[i].end(),result.begin()+2*count+offset);offset+=cells[i].size();}return result;
}
}

bool defringe(gpu::Gpu* gpu,const spk_image& input,float* output,uint64_t& changed_pixels,double& elapsed_ms,std::string& error){
    auto begin=std::chrono::steady_clock::now();changed_pixels=0;
    if(!gpu||!input.data||!output||!input.width||!input.height||input.channels!=3){error="defringe: packed RGB input/output required";return false;}
    std::vector<float> saved,host;uint32_t saved_top=0;
    for(uint32_t top=0;top<input.height;top+=512){
        uint32_t end=std::min(input.height,top+512),y0=top>4?top-4:0,y1=std::min(input.height,end+4),height=y1-y0;size_t count=size_t(input.width)*height,bytes=count*3*sizeof(float);const float* upload=input.data+size_t(y0)*input.width*3;
        if(output==input.data){host.assign(upload,upload+count*3);if(y0<top&&!saved.empty())std::copy(saved.begin()+size_t(y0-saved_top)*input.width*3,saved.end(),host.begin());uint32_t first=end>4?end-4:0;saved.assign(host.begin()+size_t(first-y0)*input.width*3,host.begin()+size_t(end-y0)*input.width*3);saved_top=first;upload=host.data();}
        auto in=gpu->upload(upload,bytes,error),out=gpu->alloc(bytes,error),stats=gpu->alloc_zeroed(sizeof(uint32_t),error);if(!in||!out||!stats)return false;
        uint32_t meta[]={uint32_t(count),input.width,height,top-y0,end-y0};if(!gpu->dispatch("spk_editor_defringe",{Arg::buf(in),Arg::inline_bytes(meta,5),Arg::buf(out),Arg::buf(stats)},count,error)||!gpu->flush(error))return false;
        uint32_t changed=0;if(!gpu->read(stats.get(),0,&changed,sizeof(changed),error)||!gpu->read(out.get(),size_t(top-y0)*input.width*3*sizeof(float),output+size_t(top)*input.width*3,size_t(end-top)*input.width*3*sizeof(float),error))return false;changed_pixels+=changed;
    }
    elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();return true;
}

bool process(gpu::Gpu* gpu,const Colour& colour,const spk_image& input,const Json& req,float* output,double& elapsed_ms,std::string& error,const float* tone_base){
    auto started=std::chrono::steady_clock::now();
    try{
        if(!gpu||!input.data||!output||!input.width||!input.height||input.channels!=3)throw std::runtime_error("editor: expected packed float32 RGB input and output");
        if(!req.is_object())throw std::runtime_error("editor: request must be an object");const Json& s=req.at("settings");if(!s.is_null()&&!s.is_object())throw std::runtime_error("editor: settings must be an object");
        std::string stage=req.at("stage").is_null()?"all":req.at("stage").as_string();if(stage!="pre"&&stage!="post"&&stage!="all")throw std::runtime_error("editor: stage must be pre, post or all");
        bool pre=stage!="post",post=stage!="pre";uint32_t fw=uint32_t(number(req,"source_width",input.width,1,1000000)),fh=uint32_t(number(req,"source_height",input.height,1,1000000));
        double ox=number(req,"origin_x",0,-1000000,1000000),oy=number(req,"origin_y",0,-1000000,1000000),scale_x=number(req,"pixel_scale_x",1,1e-6,1000000),scale_y=number(req,"pixel_scale_y",1,1e-6,1000000);
        std::array<float,128> u{};u[0]=pre;u[1]=post;u[2]=req.at("clamp_output").as_bool(post)?1:0;u[3]=float(std::exp2(number(req,"exposure_ev",stage=="all"?number(s,"exposure",0,-20,20):0,-20,20)));
        std::string cs=req.at("source_color_space").is_null()?"sRGB":req.at("source_color_space").as_string();Mat3 matrix=pre?pre_matrix(colour,s,cs):Mat3{};
        for(size_t r=0;r<3;++r)for(size_t c=0;c<3;++c)u[4+r*3+c]=float(matrix.m[r][c]);
        if(req.at("source_linear").as_bool())u[13]=1;else if(cs=="sRGB"||cs=="Display P3")u[13]=0;else if(cs=="ProPhoto RGB")u[13]=2;else if(cs=="Adobe RGB (1998)")u[13]=3;else if(pre)throw std::runtime_error("editor: unsupported source transfer; supply a linear source");
        u[20]=float(number(s,"contrast",0,-100,100)/100);u[21]=float(number(s,"warmth",0,-50,50)*.0025);u[22]=float(number(s,"saturation",0,-100,100)/100);u[23]=float(number(s,"vibrance",0,-100,100)/100);
        u[24]=float(number(s,"highlights",0,-100,100)/100);u[25]=float(number(s,"shadows",0,-100,100)/100);u[26]=float(number(s,"black_point",0,0,20)/100*.12);u[27]=float(1-(100-number(s,"white_point",100,80,100))/100*.12);u[28]=float(number(s,"gamma",1,.5,2));u[29]=float(number(s,"vignette",0,0,100)/100);
        u[32]=float(ox);u[33]=float(oy);u[34]=float(scale_x);u[35]=float(scale_y);u[36]=float(number(s,"dehaze",0,-100,100)/100);u[37]=float(number(s,"calibration_shadow_tint",number(s,"shadow_tint",0,-100,100),-100,100)/100);
        u[38]=float(number(s,"whites",0,-100,100)/100);u[39]=float(number(s,"blacks",0,-100,100)/100);
        u[40]=float(number(s,"brightness",0,-100,100)/100);
        u[112]=tone_base?1.f:0.f;
        const Json& levels=s.at("levels");if(!levels.is_null()&&!levels.is_object())throw std::runtime_error("editor: levels must be an object");
        const char* level_names[]={"master","red","green","blue"};
        for(size_t ch=0;ch<4;++ch){const auto& q=levels.at(level_names[ch]);if(!q.is_null()&&!q.is_object())throw std::runtime_error("editor: level channel must be an object");
            double v[]={number(q,"black",0,0,1),number(q,"white",1,0,1),number(q,"gamma",1,.1,10),number(q,"output_black",0,0,1),number(q,"output_white",1,0,1)};
            if(v[1]-v[0]<.000099)throw std::runtime_error("editor: level white must exceed black");
            for(size_t k=0;k<5;++k)u[88+5*ch+k]=float(v[k]);u[108+ch]=(v[0]!=0||v[1]!=1||v[2]!=1||v[3]!=0||v[4]!=1)?1.f:0.f;
        }
        std::array<float,5*4096> curves{};const char* channels[]={"master","red","green","blue","luma"};for(size_t row=0;row<5;++row){auto p=curve_points(s.at("curves").at(channels[row]));auto parametric=parametric_points(s.at("curves").at("parametric").at(channels[row]));u[14+row]=(p.size()!=2||p[0]!=std::array<double,2>{0,0}||p[1]!=std::array<double,2>{1,1}||!parametric.empty())?1:0;if(parametric.empty())curve_table(p,curves.data()+4096*row);else{std::array<float,4096> inputs{};curve_table(parametric,inputs.data(),true);curve_table(p,curves.data()+4096*row,false,inputs.data());}}
        const Json& grading=s.at("grading");const char* zones[]={"shadows","midtones","highlights"};for(size_t z=0;z<3;++z){const auto& g=grading.at(zones[z]);double saturation=number(g,"saturation",0,0,100),l=number(g,"luminance",0,-100,100);auto v=wheel(number(g,"hue",0,0,360));u[50+3*z]=float(l*.0015);u[51+3*z]=float(v[1]*saturation*.0012);u[52+3*z]=float(v[2]*saturation*.0012);if(saturation||l)u[19]=1;}u[59]=float(number(grading,"balance",0,-100,100)*.0025);u[60]=float(.16+.24*number(grading,"blending",50,0,100)/100);
        {const auto& g=grading.at("master");double saturation=number(g,"saturation",0,0,100),l=number(g,"luminance",0,-100,100);auto v=wheel(number(g,"hue",0,0,360));u[114]=float(l*.0015);u[115]=float(v[1]*saturation*.0012);u[116]=float(v[2]*saturation*.0012);if(saturation||l)u[19]=1;}
        const char* rgb_channels[]={"red","green","blue"};for(size_t row=0;row<3;++row)for(size_t col=0;col<3;++col){double offset=number(s.at("channel_mixer").at(rgb_channels[row]),rgb_channels[col],0,-100,100);u[41+3*row+col]=float((row==col?1.:0.)+offset/100);if(offset!=0)u[113]=1;}
        const char* bands[]={"red","orange","yellow","green","aqua","blue","purple","magenta"};const char* keys[]={"hue","saturation","luminance"};for(size_t b=0;b<8;++b)for(size_t k=0;k<3;++k){u[64+3*b+k]=float(number(s.at("hsl").at(bands[b]),keys[k],0,-100,100));if(u[64+3*b+k]!=0)u[61]=1;}
        auto local=post?masks(s.at("masks"),fw,fh):std::vector<Mask>{};
        const float output_clamp=u[2];if(!local.empty())u[2]=0;
        // Restoration belongs to capture-side development, before the film
        // simulation. post never denoises/sharpens simulated grain. all runs
        // it once between source WB/calibration and display-side colour.
        float restore[]={float(number(s,"sharpening",0,0,100)/100),
                         float(number(s,"noise_luminance",0,0,100)/100),
                         float(number(s,"noise_color",0,0,100)/100),
                         float(scale_x),float(scale_y),0,0};
        const bool denoise=pre&&(restore[1]!=0||restore[2]!=0),sharpen=pre&&restore[0]!=0;
        const bool restoration=denoise||sharpen;
        float detail[]={float(number(s,"texture",0,-100,100)/100),float(number(s,"clarity",0,-100,100)/100),float(scale_x),float(scale_y),u[2]};
        const bool hdr_spatial=post&&!tone_base&&(u[24]!=0||u[25]!=0);
        const bool detail_spatial=post&&(detail[0]!=0||detail[1]!=0),spatial=restoration||detail_spatial||hdr_spatial;
        // Serial spatial operators need the sum of their support. Additional
        // rows cover the bilinear restoration samples at fractional proxies.
        const double support=(denoise?2.:0.)+(sharpen?1.:0.)+(detail_spatial?48.:0.)+(hdr_spatial?48.:0.);
        uint32_t halo=spatial?uint32_t(std::ceil(support/std::max(1e-6,scale_y)))+2:0;halo=std::min(halo,input.height);
        // Keep GPU scratch bounded on 61/100/150 MP frames. Only two RGB strips
        // and small tables are live; this also permits caller-owned mapped output.
        size_t budget=size_t(number(req,"memory_budget_bytes",128*1024*1024,16*1024*1024,1024.*1024*1024));uint32_t rows=uint32_t(std::max<size_t>(1,std::min<size_t>(512,budget/(size_t(input.width)*3*sizeof(float)*3))));
        auto table=gpu->upload(curves.data(),sizeof(curves),error);if(!table)return false;
        std::vector<float> preserved,upload_host;uint32_t preserved_top=0;
        for(uint32_t top=0;top<input.height;top+=rows){
            uint32_t end=std::min(input.height,top+rows),y0=top>halo?top-halo:0,y1=std::min(input.height,end+halo),height=y1-y0;size_t count=size_t(input.width)*height,bytes=count*3*sizeof(float);if(count>std::numeric_limits<uint32_t>::max())throw std::runtime_error("editor: region exceeds shader address range");
            const float* upload_data=input.data+size_t(y0)*input.width*3;
            if(spatial&&output==input.data){
                upload_host.assign(upload_data,upload_data+count*3);
                if(y0<top&&!preserved.empty())std::copy(preserved.begin()+size_t(y0-preserved_top)*input.width*3,preserved.end(),upload_host.begin());
                uint32_t saved_top=end>halo?end-halo:0;preserved.assign(upload_host.begin()+size_t(saved_top-y0)*input.width*3,upload_host.begin()+size_t(end-y0)*input.width*3);preserved_top=saved_top;upload_data=upload_host.data();
            }
            auto input_gpu=gpu->upload(upload_data,bytes,error),next=gpu->alloc(bytes,error);if(!input_gpu||!next)return false;
            float unused_base=0;
            auto base_gpu=gpu->upload(tone_base?tone_base+size_t(y0)*input.width:&unused_base,
                tone_base?count*sizeof(float):sizeof(float),error);if(!base_gpu)return false;
            u[33]=float(oy+y0*scale_y);uint32_t meta[]={uint32_t(count),input.width,height,fw,fh};
            auto first_colour=u;if(restoration){first_colour[1]=0;first_colour[2]=0;}
            // A local mask must see the float HDR result before the final
            // output clamp. The last mask applies that clamp after all local
            // layers have been composited (mu[21]); a no-mask pass keeps the
            // existing color-shader clamp contract.
            if(!local.empty())first_colour[2]=0;
            if(!gpu->dispatch("spk_editor_color",{Arg::buf(input_gpu),Arg::inline_bytes(first_colour.data(),first_colour.size()),Arg::inline_bytes(meta,5),Arg::buf(table),Arg::buf(next),Arg::buf(base_gpu)},count,error)||!gpu->flush(error))return false;
            auto current=std::move(next);input_gpu.reset();
            if(restoration){
                for(int pass=0;pass<2;++pass){
                    if((pass==0&&!denoise)||(pass==1&&!sharpen))continue;
                    restore[5]=float(pass);restore[6]=!post&&u[2]!=0&&(pass==1||!sharpen)?1.f:0.f;
                    next=gpu->alloc(bytes,error);if(!next)return false;
                    if(!gpu->dispatch("spk_editor_restore",{Arg::buf(current),Arg::inline_bytes(restore,7),Arg::inline_bytes(meta,3),Arg::buf(next)},count,error)||!gpu->flush(error))return false;current=std::move(next);
                }
                if(post){
                    auto post_colour=u;post_colour[0]=0;post_colour[3]=1;
                    next=gpu->alloc(bytes,error);if(!next)return false;
                    if(!gpu->dispatch("spk_editor_color",{Arg::buf(current),Arg::inline_bytes(post_colour.data(),post_colour.size()),Arg::inline_bytes(meta,5),Arg::buf(table),Arg::buf(next),Arg::buf(base_gpu)},count,error)||!gpu->flush(error))return false;current=std::move(next);
                }
            }
            if(detail_spatial){next=gpu->alloc(bytes,error);if(!next)return false;if(!gpu->dispatch("spk_editor_detail",{Arg::buf(current),Arg::inline_bytes(detail,5),Arg::inline_bytes(meta,3),Arg::buf(next)},count,error)||!gpu->flush(error))return false;current=std::move(next);}
            for(size_t mask_index=0;mask_index<local.size();++mask_index){
                const auto& mask=local[mask_index];
                auto mu=mask.u;mu[0]=float(ox);mu[1]=float(oy+y0*scale_y);mu[2]=float(scale_x);mu[3]=float(scale_y);mu[21]=(output_clamp!=0&&mask_index+1==local.size())?1.f:0.f;auto index=bins(mask,input.width,height,ox,oy+y0*scale_y,scale_x,scale_y);
                float dummy=0;auto segments=gpu->upload(mask.segments.empty()?&dummy:mask.segments.data(),std::max(sizeof(float),mask.segments.size()*sizeof(float)),error);auto spatial_index=gpu->upload(index.data(),index.size()*sizeof(uint32_t),error);next=gpu->alloc(bytes,error);if(!segments||!spatial_index||!next)return false;
                uint32_t mm[]={uint32_t(count),input.width,height,fw,fh,mask.kind,(input.width+63)/64,(height+63)/64};if(!gpu->dispatch("spk_editor_mask",{Arg::buf(current),Arg::inline_bytes(mu.data(),mu.size()),Arg::inline_bytes(mm,8),Arg::buf(segments),Arg::buf(spatial_index),Arg::buf(next)},count,error)||!gpu->flush(error))return false;current=std::move(next);
            }
            if(!gpu->read(current.get(),size_t(top-y0)*input.width*3*sizeof(float),output+size_t(top)*input.width*3,size_t(end-top)*input.width*3*sizeof(float),error))return false;
        }
        elapsed_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();return true;
    }catch(const std::exception& e){error=e.what();return false;}
}
}
