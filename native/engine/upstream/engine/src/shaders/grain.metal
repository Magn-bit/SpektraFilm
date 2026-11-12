// grain.metal -- film grain and print glare, verbatim from
// `src/spektrafilm/backends/metal/grain.py`.
//
// Grain is the RFC-002 model unchanged: Poisson-thinned particle counts per
// sub-layer, `X ~ Poisson(n / sat * p)`, drawn by an *exact* sampler. Its
// randomness is Philox keyed on (pixel, stream, seed), which is tile-invariant
// -- so a chunked render has no seam in the draws themselves. The *blurs* do
// seam, which is why nothing here tiles (AGENTS.md traps 1 and 9).
#include "spk_common.h"

// Product morphology in film-density space, matching spk_grain_texture.comp.
// The upstream Poisson kernels below remain available as texture=0.
uint texture_hash(uint2 v, uint seed) {
    uint h=v.x*374761393u+v.y*668265263u+seed*1442695041u;
    h=(h^(h>>13u))*1274126177u;
    return h^(h>>16u);
}
float texture_random(int2 at,uint seed) {
    return (float(texture_hash(uint2(at),seed)>>8u)+.5f)*(2.f/16777216.f)-1.f;
}
float texture_field(float2 at,uint seed) {
    int2 cell=int2(floor(at));float2 f=at-floor(at);
    f=f*f*f*(f*(f*6.f-15.f)+10.f);
    return mix(mix(texture_random(cell,seed),texture_random(cell+int2(1,0),seed),f.x),
        mix(texture_random(cell+int2(0,1),seed),texture_random(cell+int2(1,1),seed),f.x),f.y);
}
float texture_particles(float2 at,uint seed) {
    int2 cell=int2(floor(at));float total=0.f;
    for(int y=-1;y<=1;++y)for(int x=-1;x<=1;++x) {
        int2 c=cell+int2(x,y);float weight=texture_random(c,seed);
        if(abs(weight)<.38f)continue;
        float2 center=float2(c)+.5f+float2(texture_random(c,seed+19u),texture_random(c,seed+37u))*.28f;
        float2 offset=at-center;float radius=.20f+.09f*(texture_random(c,seed+53u)+1.f);
        total+=sign(weight)*exp(-dot(offset,offset)/(2.f*radius*radius));
    }
    return total*2.2f;
}
kernel void spk_grain_texture(device const float* src [[buffer(0)]],
                              device const float* p [[buffer(1)]],
                              device const uint* meta [[buffer(2)]],
                              device float* dst [[buffer(3)]],
                              uint3 position [[thread_position_in_grid]]) {
    uint i=position.x;if(i>=meta[0])return;
    float2 xy=float2(float(int(meta[3]))+float(i%meta[1]),float(int(meta[4]))+float(i/meta[1]))+.5f;
    float2 q=xy/max(.65f,p[1]);uint seed=meta[5];float field;
    if(meta[2]==1u) {
        field=(texture_field(q*1.7f,seed)*.62f+texture_field(q*.8f+float2(17.3f,8.1f),seed+13u)*.38f)*1.8f;
    } else if(meta[2]==3u) {
        field=texture_particles(q*.62f+float2(5.7f,9.2f),seed);
    } else if(meta[2]==4u) {
        float clump=texture_field(q*.25f+float2(21.8f,5.4f),seed+31u)*1.65f;
        float detail=texture_field(q*1.3f,seed)*1.65f;
        field=clump*.85f+detail*.35f*(.55f+.8f*abs(clump));
    } else {
        field=(texture_field(q,seed)*.78f+texture_field(q*2.4f+float2(9.1f,3.4f),seed+7u)*.22f)*1.8f;
    }
    float maximum=max(.1f,p[3]);
    float density=clamp((src[i*3u]+src[i*3u+1u]+src[i*3u+2u])/3.f+.03f,.005f,maximum*.98f);
    float sigma=sqrt(max(0.f,density*(maximum-density*p[4])*p[0]))*p[2]*.10f;
    float delta=field*sigma;
    for(uint c=0u;c<3u;++c)dst[i*3u+c]=src[i*3u+c]+delta;
}

// Fused sub-layer grain: per pixel, 3 channels x 3 sub-layers. ``xa`` is the
// (K, 3) per-channel density axis (negated for positive film, as the
// reference negates both axis and query), ``ylay`` is (K, 9) = [ch*3 + sl].
kernel void spk_grain_layers(device const float* cmy [[buffer(0)]],
                             device const float* xa [[buffer(1)]],
                             device const float* inv [[buffer(2)]],
                             device const float* ylay [[buffer(3)]],
                             device const float* lp [[buffer(4)]],
                             device const uint* streams [[buffer(5)]],
                             device const uint* meta [[buffer(6)]],
                             device float* out [[buffer(7)]],
                             uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    uint K = meta[0], n = meta[1], positive = meta[2], seed = meta[3];
    if (i >= n) return;
    for (uint ch = 0u; ch < 3u; ++ch) {
        float v = cmy[3u * i + ch];
        if (positive != 0u) v = -v;
        // shared search for the three sub-layer columns (fast_interp on a common axis)
        float x0 = xa[ch], xN = xa[(K - 1u) * 3u + ch];
        uint low = 0u; float t = 0.0f; int mode;
        if (v <= x0) mode = 0; else if (v >= xN) mode = 1; else {
            uint idx = search_right(xa, 3u, ch, K, v);
            low = idx - 1u; t = (v - xa[low * 3u + ch]) * inv[low * 3u + ch]; mode = 2;
        }
        float acc = 0.0f;
        for (uint sl = 0u; sl < 3u; ++sl) {
            uint col = ch * 3u + sl;
            float d;
            if (mode == 0) d = ylay[col];
            else if (mode == 1) d = ylay[(K - 1u) * 9u + col];
            else { float y0 = ylay[low * 9u + col], y1 = ylay[(low + 1u) * 9u + col]; d = y0 + t * (y1 - y0); }
            d += lp[4u * col];                       // density_min_layers[sl, ch]
            Rng rng(i, streams[col], seed);
            acc += layer_draw(rng, d, lp[4u * col + 1u], lp[4u * col + 2u], lp[4u * col + 3u]);
        }
        out[3u * i + ch] = acc;
    }
}

// Simple (non-sub-layer) grain: n_sub draws per channel on the density itself.
kernel void spk_grain_simple(device const float* cmy [[buffer(0)]],
                             device const float* lp [[buffer(1)]],
                             device const uint* streams [[buffer(2)]],
                             device const uint* meta [[buffer(3)]],
                             device float* out [[buffer(4)]],
                             uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    uint n = meta[0], nsub = meta[1], seed = meta[2];
    if (i >= n) return;
    for (uint ch = 0u; ch < 3u; ++ch) {
        float d = cmy[3u * i + ch] + lp[4u * ch];     // += density_min
        float acc = 0.0f;
        for (uint sl = 0u; sl < nsub; ++sl) {
            Rng rng(i, streams[ch] + sl * 10u, seed);
            acc += layer_draw(rng, d, lp[4u * ch + 1u], lp[4u * ch + 2u], lp[4u * ch + 3u]);
        }
        out[3u * i + ch] = acc;
    }
}

// Lognormal field with linear-space mean m and std s
// (fast_lognormal_from_mean_std). Carries grain's micro-structure clumping and
// the print's veiling glare.
kernel void spk_lognormal_field(device const float* p [[buffer(0)]],
                                device const uint* meta [[buffer(1)]],
                                device float* out [[buffer(2)]],
                                uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    uint n = meta[0], seed = meta[1], stream0 = meta[2], per_channel = meta[3];
    if (i >= n) return;
    float m = p[0], s = p[1];
    float sig = sqrt(log(1.0f + (s * s) / (m * m)));
    float mu = log(m) - 0.5f * sig * sig;
    if (per_channel != 0u) {
        for (uint ch = 0u; ch < 3u; ++ch) { Rng rng(i, stream0 + ch, seed); out[3u * i + ch] = exp(mu + sig * rng.normal()); }
    } else {
        Rng rng(i, stream0, seed);
        float v = exp(mu + sig * rng.normal());
        out[3u * i] = v; out[3u * i + 1u] = v; out[3u * i + 2u] = v;
    }
}

// One sub-layer's contribution, for all three channels.
//
// The fused `spk_grain_layers` above accumulates the three sub-layers inside
// the kernel, which is what makes grain one dispatch at the shipped defaults.
// It cannot do that when the *dye-cloud* blur is active, because the reference
// blurs each sub-layer's draw before accumulating it
// (`grain.layer_particle_model`, `blur_particle` branch) -- so this emits one
// sub-layer, the host blurs it with that sub-layer's per-channel sigma, and
// the host accumulates.
//
// When it fires: `sigma_particle = blur_dye_clouds_um * sqrt(dmax / n)` above
// 0.4 px. At 35 mm and 45 MP it is 0.29 px and this never runs -- but
// `camera.film_format_mm` goes down to 4 mm on the wire, and at 4 mm it is
// 0.51 px. Which is exactly why the branch is here rather than an error: an
// unreachable-looking path that the wire can in fact reach.
kernel void spk_grain_layer_one(device const float* cmy [[buffer(0)]],
                                device const float* xa [[buffer(1)]],
                                device const float* inv [[buffer(2)]],
                                device const float* ylay [[buffer(3)]],
                                device const float* lp [[buffer(4)]],
                                device const uint* streams [[buffer(5)]],
                                device const uint* meta [[buffer(6)]],
                                device float* out [[buffer(7)]],
                                uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    uint K = meta[0], n = meta[1], positive = meta[2], seed = meta[3], sl = meta[4];
    if (i >= n) return;
    for (uint ch = 0u; ch < 3u; ++ch) {
        float v = cmy[3u * i + ch];
        if (positive != 0u) v = -v;
        float x0 = xa[ch], xN = xa[(K - 1u) * 3u + ch];
        uint low = 0u; float t = 0.0f; int mode;
        if (v <= x0) mode = 0; else if (v >= xN) mode = 1; else {
            uint idx = search_right(xa, 3u, ch, K, v);
            low = idx - 1u; t = (v - xa[low * 3u + ch]) * inv[low * 3u + ch]; mode = 2;
        }
        uint col = ch * 3u + sl;
        float d;
        if (mode == 0) d = ylay[col];
        else if (mode == 1) d = ylay[(K - 1u) * 9u + col];
        else { float y0 = ylay[low * 9u + col], y1 = ylay[(low + 1u) * 9u + col]; d = y0 + t * (y1 - y0); }
        d += lp[4u * col];
        Rng rng(i, streams[col], seed);
        out[3u * i + ch] = layer_draw(rng, d, lp[4u * col + 1u], lp[4u * col + 2u], lp[4u * col + 3u]);
    }
}
