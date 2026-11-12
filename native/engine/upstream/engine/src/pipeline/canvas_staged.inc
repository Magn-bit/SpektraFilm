// Implementation body of run_canvas_bounded. Included inside its restoration
// guard so every exit restores the session and destroys all checkpoint maps.
        uint64_t output_pixels=0;uint32_t regions=0,sweeps=0,point_passes=0,resident_gaussians=0;
        size_t largest_region_pixels=0,largest_source_pixels=0,checkpoint_peak=0;
        std::vector<std::weak_ptr<CanvasPlane>> checkpoints;
        auto track=[&](Plane p){
            checkpoints.push_back(p);size_t bytes=0;
            for(auto it=checkpoints.begin();it!=checkpoints.end();){
                if(auto live=it->lock()){bytes+=live->bytes;++it;}else it=checkpoints.erase(it);
            }
            checkpoint_peak=std::max(checkpoint_peak,bytes);return p;
        };
        auto make_plane=[&](uint32_t w,uint32_t h)->Plane{
            auto p=std::make_shared<CanvasPlane>();File f(canvas_file(error),&std::fclose);
            if(!f||!p->open(std::move(f),w,h,error))return {};return track(std::move(p));
        };
        auto source=std::make_shared<CanvasPlane>();
        if(!source->open(std::move(exposure),in.w,in.h,error))return false;source=track(std::move(source));
        // Upload/read buffers stay below this limit even when one full line
        // is much longer than the requested visual region edge.
        const uint64_t band_pixels=std::max<uint64_t>(std::max(width,height),std::min<uint64_t>(4000000,budget/128));
        const uint32_t rows=std::max(1u,uint32_t(std::min<uint64_t>(512,band_pixels/width)));
        auto stage_started=canvas_started;std::string active_stage="canvas.source_exposure";Json stage_times=Json::object();
        auto phase=[&](double fraction,const char* stage){
            if(active_stage!=stage){const auto now=std::chrono::steady_clock::now();
                stage_times.set(active_stage,Json(std::chrono::duration<double,std::milli>(now-stage_started).count()));
                active_stage=stage;stage_started=now;}
            if(progress){progress->stage=stage;progress->canvas_fraction=std::max(progress->canvas_fraction,fraction);}
        };
        auto origin=[&](uint32_t x,uint32_t y,uint32_t w,uint32_t h){
            canvas_region_={true,x,y,w,h,in.w,in.h,0,0,in.w,in.h};
            params_.settings.tile_origin_x=x;params_.settings.tile_origin_y=y;
            band_row0_=0;strip_plane_h_=height;
        };
        auto read_plane=[&](const Plane& p,uint32_t x,uint32_t y,uint32_t w,uint32_t h,Image& image){
            if(cancelled())return false;
            image.w=w;image.h=h;image.c=3;
            if(x==0&&w==p->w)image.buf=gpu_->upload(p->data+size_t(y)*w*3,image.bytes(),error);
            else{
                host.resize(size_t(w)*h*3);
                for(uint32_t j=0;j<h;++j)std::memcpy(host.data()+size_t(j)*w*3,p->data+(size_t(y+j)*p->w+x)*3,size_t(w)*12);
                image.buf=gpu_->upload(host.data(),image.bytes(),error);
            }
            largest_region_pixels=std::max(largest_region_pixels,image.pixels());return bool(image.buf);
        };
        auto write_plane=[&](const Image& image,const Plane& p,uint32_t x,uint32_t y){
            if(cancelled())return false;
            if(x==0&&image.w==p->w)return gpu_->read(image.buf.get(),0,p->data+size_t(y)*p->w*3,image.bytes(),error);
            host.resize(image.elements());if(!gpu_->read(image.buf.get(),0,host.data(),image.bytes(),error))return false;
            for(uint32_t j=0;j<image.h;++j)std::memcpy(p->data+(size_t(y+j)*p->w+x)*3,host.data()+size_t(j)*image.w*3,size_t(image.w)*12);
            return true;
        };
        using Op=std::function<bool(const std::vector<Image>&,std::vector<Image>&)>;
        auto points=[&](const std::vector<Plane>& inputs,size_t nout,const Op& op,std::vector<Plane>& outputs){
            outputs.clear();for(size_t i=0;i<nout;++i){auto p=make_plane(width,height);if(!p)return false;outputs.push_back(std::move(p));}
            for(uint32_t y=0;y<height;y+=rows){
                if(cancelled())return false;const uint32_t h=std::min(rows,height-y);origin(0,y,width,h);
                std::vector<Image> src(inputs.size()),dst(nout);
                for(size_t i=0;i<inputs.size();++i)if(!read_plane(inputs[i],0,y,width,h,src[i]))return false;
                if(!flush(op(src,dst)))return false;
                for(size_t i=0;i<nout;++i)if(!write_plane(dst[i],outputs[i],0,y))return false;
            }
            ++point_passes;return true;
        };
        auto point=[&](const Plane& input,Plane& output,const std::function<bool(const Image&,Image&)>& op){
            std::vector<Plane> dst;
            if(!points({input},1,[&](const auto& s,auto& d){return op(s[0],d[0]);},dst))return false;
            output=std::move(dst[0]);return true;
        };
        auto combine=[&](const Plane& x,const Plane& y,const double a[3],const double b[3],Plane& out){
            std::vector<Plane> dst;
            if(!points({x,y},1,[&](const auto& s,auto& d){return blur_.lincomb(s[0],s[1],a,b,d[0],error);},dst))return false;
            out=std::move(dst[0]);return true;
        };
        auto sweep=[&](const Plane& input,const double sigma[3],const bool active[3],bool iir,bool horizontal,
                       const Plane& accumulator,const double* weights,Plane& output){
            output=make_plane(width,height);if(!output)return false;
            const uint32_t count=horizontal?height:width;
            // A long recurrence needs enough independent lines to occupy the
            // device. This is bounded by three float planes plus staging,
            // rather than the much heavier spectral pointwise node budget.
            const uint64_t sweep_pixels=std::max<uint64_t>(std::max(width,height),std::min<uint64_t>(16000000,budget/64));
            const uint32_t step=std::max(1u,uint32_t(std::min<uint64_t>(4096,sweep_pixels/(horizontal?width:height))));
            for(uint32_t k=0;k<count;k+=step){
                if(cancelled())return false;
                const uint32_t n=std::min(step,count-k),x=horizontal?0:k,y=horizontal?k:0;
                const uint32_t w=horizontal?width:n,h=horizontal?n:height;
                origin(x,y,w,h);Image band,acc,result;
                if(!read_plane(input,x,y,w,h,band))return false;
                if(accumulator&&!read_plane(accumulator,x,y,w,h,acc))return false;
                if(!flush(blur_.complete_line_pass(band,sigma,active,iir,horizontal,result,error,
                                                  accumulator?&acc:nullptr,weights)))return false;
                if(!write_plane(result,output,x,y))return false;
            }
            ++sweeps;return true;
        };
        std::function<bool(const Plane&,const double*,Plane&,const Plane&,const double*)> gaussian;
        gaussian=[&](const Plane& input,const double* sigma,Plane& output,const Plane& acc,const double* weights){
            bool fir[3],iir[3],any_fir=false,any_iir=false;
            for(int c=0;c<3;++c){fir[c]=Blur::is_fir(sigma[c]);iir[c]=sigma[c]>=3.;any_fir|=fir[c];any_iir|=iir[c];}
            // Admit one complete Gaussian operation when the actual device
            // heap can hold its exact working graph. Disk checkpoints remain
            // the stage boundary, so DIR's retained log and other branches do
            // not inflate the GPU live set. Explicit low budgets are honored.
            const size_t plane_bytes=size_t(width)*height*12;
            const size_t graph_planes=(acc||any_fir)?4:2;
            const size_t admission=plane_bytes*graph_planes+(size_t(128)<<20);
            std::string admission_error;
            if((!request.has("budget_bytes")||admission<=budget)&&!cancelled()){
                if(!gpu_->flush(error))return false;gpu_->trim_pool(0);
                if(gpu_->check_working_set(admission,plane_bytes,admission_error)){
                    Image resident,accumulator,result;
                    if(!read_plane(input,0,0,width,height,resident))return false;
                    if(acc&&!read_plane(acc,0,0,width,height,accumulator))return false;
                    if(!flush(blur_.gaussian(resident,sigma,result,error,3.,acc?&accumulator:nullptr,weights)))return false;
                    output=make_plane(width,height);if(!output||!write_plane(result,output,0,0))return false;
                    resident={};accumulator={};result={};if(!gpu_->flush(error))return false;gpu_->trim_pool(0);
                    sweeps+=((any_fir||(!any_iir&&acc))?2:0)+(any_iir?2:0);++resident_gaussians;return true;
                }
            }
            if(acc&&any_fir&&any_iir){
                Plane blurred;if(!gaussian(input,sigma,blurred,{},nullptr))return false;
                const double one[3]={1,1,1};const double* w=weights?weights:one;
                return combine(acc,blurred,one,w,output);
            }
            Plane current=input,tmp,next;
            if(any_fir||(!any_iir&&acc)){
                if(!sweep(current,sigma,fir,false,false,{},nullptr,tmp)||
                   !sweep(tmp,sigma,fir,false,true,acc,weights,next))return false;
                current=std::move(next);tmp.reset();
            }
            if(any_iir){
                if(!sweep(current,sigma,iir,true,true,{},nullptr,tmp)||
                   !sweep(tmp,sigma,iir,true,false,acc,weights,next))return false;
                current=std::move(next);
            }
            output=std::move(current);return true;
        };
        auto mixture=[&](const Plane& input,const std::vector<Blur::Component>& components,Plane& output){
            if(components.empty()){output=input;return true;}
            Plane acc;
            for(const auto& c:components){
                if(!acc){acc=make_plane(width,height);if(!acc)return false;}
                Plane next;if(!gaussian(input,c.sigma,next,acc,c.weight))return false;acc=std::move(next);
            }
            output=std::move(acc);return true;
        };
        auto blur_scalar=[&](const Plane& input,double sigma,Plane& output){
            const double s[3]={sigma,sigma,sigma};return gaussian(input,s,output,{},nullptr);
        };

        phase(.13,"canvas.exposure_geometry");
        Plane canvas=make_plane(width,height);if(!canvas)return false;
        const uint32_t geometry_width=std::min(width,std::max(core,uint32_t(std::min<uint64_t>(width,band_pixels/std::max(64u,core/2)))));
        const uint32_t geometry_rows=std::max(16u,std::min(core,uint32_t(band_pixels/geometry_width)));
        for(uint32_t y=0;y<height;y+=geometry_rows)for(uint32_t x=0;x<width;x+=geometry_width){
            if(cancelled())return false;
            const uint32_t cw=std::min(geometry_width,width-x),ch=std::min(geometry_rows,height-y);
            uint32_t sx0=x,sy0=y,sx1=x+cw,sy1=y+ch;
            if(overscan_wanted()){
                const auto& L=overscan_;double minx=in.w-1.,miny=in.h-1.,maxx=0,maxy=0;
                auto include=[&](double s,double t){
                    const double fx=L.vertical?(L.gate_t0+L.gate_across-t)/L.px-.5:(s-L.gate_s0)/L.px-.5;
                    const double fy=L.vertical?(s-L.gate_s0)/L.px-.5:(t-L.gate_t0)/L.px-.5;
                    minx=std::min(minx,fx);maxx=std::max(maxx,fx);miny=std::min(miny,fy);maxy=std::max(maxy,fy);
                };
                for(double py:{double(y),double(y+ch-1)})for(double px:{double(x),double(x+cw-1)}){
                    const double u=(px+.5)*L.px-L.cu,v=(py+.5)*L.px-L.cv;
                    const double s=L.A[0]*u+L.A[1]*v+L.cs,t=L.A[2]*u+L.A[3]*v+L.ct;include(s,t);
                    for(int gate=0;gate<(L.pair_adv>0?2:1);++gate){const double shift=gate*L.pair_adv;
                        include(std::clamp(s-shift,L.gate_s0+.12,L.gate_s0+L.gate_along-.12)+shift,
                                std::clamp(t,L.gate_t0+.12,L.gate_t0+L.gate_across-.12));}
                }
                sx0=uint32_t(std::clamp(std::floor(minx)-2.,0.,double(in.w-1)));
                sy0=uint32_t(std::clamp(std::floor(miny)-2.,0.,double(in.h-1)));
                sx1=uint32_t(std::clamp(std::ceil(maxx)+3.,double(sx0+1),double(in.w)));
                sy1=uint32_t(std::clamp(std::ceil(maxy)+3.,double(sy0+1),double(in.h)));
            }
            const uint32_t sw=sx1-sx0,sh=sy1-sy0;Image src;
            largest_source_pixels=std::max(largest_source_pixels,size_t(sw)*sh);
            if(!read_plane(source,sx0,sy0,sw,sh,src))return false;
            canvas_region_={true,x,y,cw,ch,in.w,in.h,sx0,sy0,sw,sh};
            params_.settings.tile_origin_x=x;params_.settings.tile_origin_y=y;band_row0_=0;strip_plane_h_=height;
            Chain exposed,boosted,shaped;exposed.cur=std::move(src);
            if(!flush(film_boost(std::move(exposed),boosted,error))||!flush(film_overscan(std::move(boosted),shaped,error))||
               !write_plane(shaped.cur,canvas,x,y))return false;
            ++regions;
            phase(.13+.09*double(uint64_t(y)*width+uint64_t(x)*ch+uint64_t(cw)*ch)/(double(width)*height),"canvas.exposure_geometry");
        }
        source.reset();
        phase(.23,"canvas.film_optics");
        if(lens_blur_sigma()>0){Plane p;if(!blur_scalar(canvas,lens_blur_sigma(),p))return false;canvas=std::move(p);}
        const auto hal=halation_blurs();const auto& hp=params_.film_render.halation;
        if(!hal.scatter.empty()){
            Plane blurred,mixed;double a[3],b[3];for(int c=0;c<3;++c){a[c]=1-hp.scatter_amount;b[c]=hp.scatter_amount;}
            if(!mixture(canvas,hal.scatter,blurred)||!combine(canvas,blurred,a,b,mixed))return false;canvas=std::move(mixed);
        }
        phase(.34,"canvas.film_halation");
        if(!hal.bounces.empty()){
            Plane blurred,mixed;double a[3],b[3];for(int c=0;c<3;++c){
                const double strength=double(float(hp.halation_strength[c])*float(hp.halation_amount));
                a[c]=hp.halation_renormalize?1./(1.+strength):1.;b[c]=hp.halation_renormalize?strength/(1.+strength):strength;}
            if(!mixture(canvas,hal.bounces,blurred)||!combine(canvas,blurred,a,b,mixed))return false;canvas=std::move(mixed);
        }
        phase(.43,"canvas.film_density");
        std::vector<Plane> developed;
        if(!points({canvas},2,[&](const auto& s,auto& d){
            return flush(node_expose_log(s[0],d[1],error))&&node_film_curves(d[1],d[0],error);
        },developed))return false;
        canvas=std::move(developed[0]);Plane log=std::move(developed[1]);developed.clear();
        if(params_.film_render.dir_couplers.active){
            phase(.47,"canvas.dir_couplers");Plane correction;
            if(!point(canvas,correction,[&](const Image& input,Image& output){
                if(!alloc_like(input,output,error))return false;
                const uint32_t pos[]={params_.film.info.is_positive()?1u:0u},n[]={uint32_t(input.pixels())};
                return gpu_->dispatch("spk_couplers_correction",{gpu::Arg::buf(input.buf),gpu::Arg::buf(baked_.coupler_matrix),
                    gpu::Arg::buf(baked_.coupler_dmax),gpu::Arg::inline_bytes(pos,1),gpu::Arg::buf(baked_.coupler_shift),
                    gpu::Arg::inline_bytes(n,1),gpu::Arg::buf(output.buf)},input.pixels(),error);
            }))return false;
            canvas.reset();Plane diffused;
            if(!mixture(correction,dir_coupler_diffusion(),diffused))return false;correction.reset();
            std::vector<Plane> result;
            if(!points({log,diffused},1,[&](const auto& s,auto& d){
                const double a[3]={1,1,1},b[3]={-1,-1,-1};Image corrected;
                return flush(blur_.lincomb(s[0],s[1],a,b,corrected,error))&&
                    curve_interp(corrected,baked_.coupler_curve_x,baked_.coupler_curve_inv,baked_.coupler_curve_y,baked_.film_curve_k,d[0],error);
            },result))return false;canvas=std::move(result[0]);
        }
        log.reset();phase(.62,"canvas.grain");
        const auto& g=params_.film_render.grain;
        if(g.active&&g.amount>0){
            Plane grained;
            if(g.texture>0){
                if(!point(canvas,grained,[&](const Image& s,Image& d){return node_grain(s,d,error);}))return false;
            }else{
                // The original density-dependent particle model is retained,
                // including dye-cloud and microstructure blurs at any radius.
                const double px=pixel_size_um_;const bool neutral=std::abs(g.uniformity[0]-g.uniformity[1])<1e-9&&std::abs(g.uniformity[1]-g.uniformity[2])<1e-9;
                double scales[3]={g.particle_scale[0],g.particle_scale[1],g.particle_scale[2]};
                if(neutral)scales[0]=scales[1]=scales[2]=1.;
                Plane particles;
                if(g.sublayers_active){
                    const size_t k=params_.film.data.n_exposure;double dmax[3][3],fraction[3][3],total[3]={};
                    for(int sl=0;sl<3;++sl)for(int c=0;c<3;++c){dmax[sl][c]=nanmax(params_.film.data.density_curves_layers.data()+sl*3+c,k,9);total[c]+=dmax[sl][c];}
                    float lp[36];double cloud[3][3];bool clouds=false;
                    for(int c=0;c<3;++c)for(int sl=0;sl<3;++sl){
                        fraction[sl][c]=dmax[sl][c]/total[c];const double dmin=fraction[sl][c]*g.density_min[c];dmax[sl][c]+=dmin;
                        const double n=px*px*fraction[sl][c]/(g.particle_area_um2*scales[c]*g.particle_scale_layers[sl]);
                        cloud[sl][c]=g.blur_dye_clouds_um>0?g.blur_dye_clouds_um*std::sqrt(dmax[sl][c]/n):0;
                        clouds|=cloud[sl][c]>.4;const int i=4*(c*3+sl);
                        lp[i]=float(dmin);lp[i+1]=float(dmax[sl][c]);lp[i+2]=float(n);lp[i+3]=float(g.uniformity[c]);
                    }
                    if(neutral)for(int sl=0;sl<3;++sl){const double v=(cloud[sl][0]+cloud[sl][1]+cloud[sl][2])/3.;cloud[sl][0]=cloud[sl][1]=cloud[sl][2]=v;}
                    auto lpbuf=gpu_->upload(lp,sizeof lp,error);if(!lpbuf)return false;
                    auto streams=baked_.grain_streams;
                    if(neutral){uint32_t values[9];for(int c=0;c<3;++c)for(int sl=0;sl<3;++sl)values[c*3+sl]=sl*10;
                        streams=gpu_->upload_u32(values,9,error);if(!streams)return false;}
                    auto draw=[&](const Plane& input,Plane& output,int sl){return point(input,output,[&](const Image& s,Image& d){
                        if(!alloc_like(s,d,error))return false;const auto& region=params_.settings;
                        const uint32_t m[]={uint32_t(k),uint32_t(s.pixels()),params_.film.info.is_positive()?1u:0u,film_seed_,uint32_t(sl),
                            s.w,uint32_t(region.tile_full_width),uint32_t(region.tile_origin_x),uint32_t(region.tile_origin_y)};
                        const uint32_t all[]={m[0],m[1],m[2],m[3],m[5],m[6],m[7],m[8]};
                        return gpu_->dispatch(sl<0?"spk_grain_layers":"spk_grain_layer_one",{gpu::Arg::buf(s.buf),gpu::Arg::buf(baked_.grain_xa),
                            gpu::Arg::buf(baked_.grain_inv),gpu::Arg::buf(baked_.grain_ylay),gpu::Arg::buf(lpbuf),gpu::Arg::buf(streams),
                            sl<0?gpu::Arg::inline_bytes(all,8):gpu::Arg::inline_bytes(m,9),gpu::Arg::buf(d.buf)},s.pixels(),error);
                    });};
                    if(!clouds){if(!draw(canvas,particles,-1))return false;}
                    else{
                        particles=make_plane(width,height);if(!particles)return false;const double one[3]={1,1,1};
                        for(int sl=0;sl<3;++sl){Plane layer,next;double sigma[3];for(int c=0;c<3;++c)sigma[c]=cloud[sl][c]>.4?cloud[sl][c]:0;
                            if(!draw(canvas,layer,sl)||!gaussian(layer,sigma,next,particles,one))return false;particles=std::move(next);}
                    }
                    const double micro_sigma=g.micro_structure[1]*.001/px;
                    if(micro_sigma>.05){
                        Plane field;if(!point(canvas,field,[&](const Image& s,Image& d){return lognormal_field(s.h,s.w,1.,micro_sigma,film_seed_,100,true,d,error);}))return false;
                        if(g.micro_structure[0]/px>.4){Plane b;if(!blur_scalar(field,g.micro_structure[0]/px,b))return false;field=std::move(b);}
                        std::vector<Plane> multiplied;
                        if(!points({particles,field},1,[&](const auto& s,auto& d){
                            if(!alloc_like(s[0],d[0],error))return false;const uint32_t n[]={uint32_t(s[0].elements())};
                            return gpu_->dispatch("spk_mul",{gpu::Arg::buf(s[0].buf),gpu::Arg::buf(s[1].buf),gpu::Arg::inline_bytes(n,1),gpu::Arg::buf(d[0].buf)},s[0].elements(),error);
                        },multiplied))return false;particles=std::move(multiplied[0]);
                    }
                    Plane shifted;if(!point(particles,shifted,[&](const Image& s,Image& d){const double a[3]={1,1,1},b[3]={-g.density_min[0],-g.density_min[1],-g.density_min[2]};return blur_.affine(s,a,b,d,error);}))return false;
                    particles=std::move(shifted);
                    if(g.blur>0){Plane b;if(!blur_scalar(particles,g.blur,b))return false;particles=std::move(b);}
                }else{
                    const int nsub=std::max(1,g.n_sub_layers);float lp[12];
                    for(int c=0;c<3;++c){lp[c*4]=float(g.density_min[c]);lp[c*4+1]=float(params_.film.density_max[c]+g.density_min[c]);
                        lp[c*4+2]=float(px*px/(g.particle_area_um2*scales[c])/double(nsub));lp[c*4+3]=float(g.uniformity[c]);}
                    auto lpbuf=gpu_->upload(lp,sizeof lp,error);const uint32_t stream[]={0,neutral?0u:1u,neutral?0u:2u};auto streams=gpu_->upload_u32(stream,3,error);
                    if(!lpbuf||!streams)return false;
                    if(!point(canvas,particles,[&](const Image& s,Image& d){
                        Image drawn;if(!alloc_like(s,drawn,error))return false;const auto& r=params_.settings;
                        const uint32_t m[]={uint32_t(s.pixels()),uint32_t(nsub),film_seed_,s.w,uint32_t(r.tile_full_width),uint32_t(r.tile_origin_x),uint32_t(r.tile_origin_y)};
                        if(!flush(gpu_->dispatch("spk_grain_simple",{gpu::Arg::buf(s.buf),gpu::Arg::buf(lpbuf),gpu::Arg::buf(streams),gpu::Arg::inline_bytes(m,7),gpu::Arg::buf(drawn.buf)},s.pixels(),error)))return false;
                        const double a[3]={1./nsub,1./nsub,1./nsub},b[3]={-g.density_min[0],-g.density_min[1],-g.density_min[2]};return blur_.affine(drawn,a,b,d,error);
                    }))return false;
                    if(g.blur>.4){Plane b;if(!blur_scalar(particles,g.blur,b))return false;particles=std::move(b);}
                }
                if(g.amount==1)grained=std::move(particles);else{const double a[3]={1-g.amount,1-g.amount,1-g.amount},b[3]={g.amount,g.amount,g.amount};
                    if(!combine(canvas,particles,a,b,grained))return false;}
            }
            canvas=std::move(grained);
        }
        Plane negative=std::move(canvas);
        auto print_plane=[&](Plane& output){
            Plane current;
            if(!point(negative,current,[&](const Image& s,Image& d){Chain a,b;a.cur=s;if(!print_spectral(std::move(a),b,error))return false;d=std::move(b.cur);return true;}))return false;
            const auto& glare=params_.print_render.glare;const double percent=glare.percent*glare.amount;
            if(!di_active_&&!params_.io.scan_film&&glare.active&&percent>0){
                Plane field;
                if(!point(current,field,[&](const Image& s,Image& d){return lognormal_field(s.h,s.w,percent,glare.roughness*percent,print_seed_,200,false,d,error);}))return false;
                if(glare.blur>0){Plane b;if(!blur_scalar(field,glare.blur*tier_ratio()*std::sqrt(std::max(glare.amount,0.)),b))return false;field=std::move(b);}
                std::vector<Plane> mixed;
                if(!points({current,field},1,[&](const auto& s,auto& d){
                    if(!alloc_like(s[0],d[0],error))return false;const uint32_t n[]={uint32_t(s[0].elements())};
                    return gpu_->dispatch("spk_glare_add",{gpu::Arg::buf(s[0].buf),gpu::Arg::buf(s[1].buf),gpu::Arg::buf(baked_.glare_illuminant),gpu::Arg::inline_bytes(n,1),gpu::Arg::buf(d[0].buf)},s[0].elements(),error);
                },mixed))return false;current=std::move(mixed[0]);
            }
            if(!di_active_){
                Plane linear;if(!point(current,linear,[&](const Image& s,Image& d){Chain a,b;a.cur=s;if(!print_linear(std::move(a),b,error))return false;d=std::move(b.cur);return true;}))return false;current=std::move(linear);
                if(scanner_blur_sigma()>0){Plane b;if(!blur_scalar(current,scanner_blur_sigma(),b))return false;current=std::move(b);}
                if(unsharp_sigma()>0&&params_.scanner.unsharp_mask[1]>0){
                    Plane blurred,mixed;const double strength=params_.scanner.unsharp_mask[1],a[3]={1+strength,1+strength,1+strength},b[3]={-strength,-strength,-strength};
                    if(!blur_scalar(current,unsharp_sigma(),blurred)||!combine(current,blurred,a,b,mixed))return false;current=std::move(mixed);
                }
                Plane encoded;if(!point(current,encoded,[&](const Image& s,Image& d){
                    Image lit=s;if(overscan_wanted()&&!flush(node_overscan_light(s,lit,error)))return false;
                    Chain a,b;a.cur=std::move(lit);if(!print_output(std::move(a),b,error))return false;d=std::move(b.cur);return true;
                }))return false;current=std::move(encoded);
            }
            output=std::move(current);return true;
        };
        phase(.69,"canvas.printing");Plane prints[3];if(!print_plane(prints[0]))return false;
        if(layered)for(int side=0;side<2;++side){
            if(layers[side].printed){apply_live_delta(layers[side].delta);
                if(!refresh_print_constants(error)||!print_plane(prints[side+1]))return false;
                params_.enlarger=saved_enlarger;if(!refresh_print_constants(error))return false;
            }else prints[side+1]=prints[0];
        }
        negative.reset();phase(.9,"canvas.output");
        auto pack=[&](const Image& rgb,Image& packed){
            packed.w=rgb.w;packed.h=rgb.h;packed.c=2;packed.buf=gpu_->alloc(packed.bytes(),error);if(!packed.buf)return false;
            const uint32_t m[]={uint32_t(rgb.pixels()),rgb.w,rgb.w};return flush(gpu_->dispatch("spk_to_rgba16",{
                gpu::Arg::buf(rgb.buf),gpu::Arg::inline_bytes(m,3),gpu::Arg::buf(packed.buf)},rgb.pixels(),error));
        };
        for(uint32_t y=0;y<height;y+=rows){
            const uint32_t h=std::min(rows,height-y);origin(0,y,width,h);Image rgb,packed,final;
            if(!read_plane(prints[0],0,y,width,h,rgb)||!pack(rgb,packed))return false;rgb={};final=packed;
            auto apply_grade=[&](const Image& input,const Json& adjustment,Image& output){
                view::Request q;q.rgba16=true;q.target_space="ProPhoto RGB";q.adjustments=adjustment;
                q.region_full_width=width;q.region_full_height=height;q.region_x=0;q.region_y=y;
                Json transform=Json::object();transform.set("source_color_space",Json(std::string("ProPhoto RGB")));transform.set("target_color_space",Json(std::string("ProPhoto RGB")));
                view::Result result;return flush(view::process(gpu_,input,q,transform,nullptr,0,result,error,{},0,&output));
            };
            if(has_grade||layered){Image graded;if(!apply_grade(packed,grade,graded))return false;final=std::move(graded);}
            if(layered){
                Image holes[2];
                for(int side=0;side<2;++side){
                    const auto& layer=layers[side];if(!layer.printed&&!layer.graded){holes[side]=final;continue;}
                    Image input=packed;if(layer.printed&&(!read_plane(prints[side+1],0,y,width,h,rgb)||!pack(rgb,input)))return false;
                    if(!apply_grade(input,layer.grade,holes[side]))return false;rgb={};
                }
                auto local=rects;for(auto& r:local){r[1]-=y;r[3]-=y;}
                Image mixed;mixed.w=width;mixed.h=h;mixed.c=2;mixed.buf=gpu_->alloc(mixed.bytes(),error);if(!mixed.buf)return false;
                const uint32_t m[]={uint32_t(final.pixels()),width,(layers[0].printed||layers[0].graded)?1u:0u,(layers[1].printed||layers[1].graded)?1u:0u};
                if(!flush(gpu_->dispatch("spk_view_pair",{gpu::Arg::buf(final.buf),gpu::Arg::buf(holes[0].buf),gpu::Arg::buf(holes[1].buf),
                    gpu::Arg::inline_bytes(m,4),gpu::Arg::inline_bytes(local[0].data(),8),gpu::Arg::buf(mixed.buf)},final.pixels(),error)))return false;final=std::move(mixed);
            }
            if(!gpu_->read(final.buf.get(),0,rgba+size_t(y)*width*4,size_t(width)*h*8,error))return false;
            output_pixels+=size_t(width)*h;phase(.9+.1*double(output_pixels)/(double(width)*height),"canvas.output");
        }
        phase(1.,"canvas.complete");report=Json::object();
        report.set("width",Json(double(width)));report.set("height",Json(double(height)));
        report.set("source_bands",Json(double(source_bands)));report.set("regions",Json(double(regions)));
        report.set("region_core",Json(double(core)));report.set("halo_pixels",Json(0.));
        report.set("largest_region_pixels",Json(double(largest_region_pixels)));report.set("largest_source_pixels",Json(double(largest_source_pixels)));
        report.set("exposure_checkpoint_bytes",Json(double(in.pixels()*12)));report.set("checkpoint_peak_bytes",Json(double(checkpoint_peak)));
        report.set("frame_exposure_peak",Json(peak));report.set("frame_boosted_peak",Json(boosted_peak));
        report.set("finite_iir_context",Json(false));report.set("exact_iir_sweeps",Json(true));
        report.set("complete_line_passes",Json(double(sweeps)));report.set("pointwise_passes",Json(double(point_passes)));
        report.set("resident_gaussian_calls",Json(double(resident_gaussians)));
        report.set("stage_ms",std::move(stage_times));
        report.set("pair_layers_applied",Json(layered));report.set("post_adjustments_applied",Json(has_grade||layered));
        Json layout;if(!Json::parse(overscan_geometry_json(),layout,error))return false;report.set("geometry",std::move(layout));
        if(progress)progress->done=true;return true;
