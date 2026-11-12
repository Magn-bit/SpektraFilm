"""Float32 native GPU CAM16-UCS output gamut stage.

This isolated implementation is used by the gated Windows adapter. The equations
and boundary table follow ``spektrafilm.utils.gamut_compression`` (GPL-3.0,
Andrea Volpato), using the actual Colour 0.4.7 CAM16/Li2017 implementation,
not the different CIECAM16 2022 low/high-response extension. The fixed viewing
setup and Cmax table are prepared on the CPU once; all per-pixel work is WGSL.

CAM16 formula transcription attribution (Colour, BSD-3-Clause):
Copyright 2013 Colour Developers
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""
from __future__ import annotations

import time
import threading

import numpy as np


_SHADER = r"""
// Scalar buffers avoid WGSL vec3 array's 16-byte stride for packed RGB data.
struct Params {
    pixel_count: u32,
    n_l: u32,
    n_h: u32,
    mode: u32,
    knee: vec4<f32>,
    lightness: vec4<f32>,
    table_axis: vec4<f32>,
}
@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(0) @binding(1) var<storage, read> cmax: array<f32>;
@group(0) @binding(2) var<storage, read_write> dst: array<f32>;
@group(0) @binding(3) var<uniform> p: Params;

__CONSTANTS__

fn spow(x: f32, exponent: f32) -> f32 {
    return sign(x) * pow(abs(x), exponent);
}
fn safe_atan2(y: f32, x: f32) -> f32 {
    // D3D12 atan2(0,0) can produce NaN; numpy defines the angle as zero.
    if (x == 0.0 && y == 0.0) { return 0.0; }
    return atan2(y,x);
}
fn finite(x: f32) -> bool {
    return (bitcast<u32>(x) & 0x7f800000u) != 0x7f800000u;
}
// These forms retain dark-value precision and avoid exp/pow overflow at a
// vanishing Cmax. They are algebraically the CPU log1p/expm1/knee operations.
fn log1p_precise(x: f32) -> f32 {
    let u = 1.0 + x;
    if (u == 1.0) { return x; }
    return log(u) * x / (u - 1.0);
}
fn expm1_precise(x: f32) -> f32 {
    if (abs(x) < 0.0001) { return x + x*x*0.5 + x*x*x/6.0; }
    return exp(x) - 1.0;
}
fn knee(x: f32, cfg: vec3<f32>) -> f32 {
    if (x <= cfg.x) { return x; }
    let scale = cfg.y - cfg.x;
    let n = (x - cfg.x) / scale;
    if (n > 1.0) {
        return cfg.x + scale / pow(1.0 + pow(1.0/n, cfg.z), 1.0/cfg.z);
    }
    return cfg.x + scale*n / pow(1.0 + pow(n, cfg.z), 1.0/cfg.z);
}
fn rgb_to_xyz(rgb: vec3<f32>) -> vec3<f32> {
    return vec3<f32>(dot(RGB_X, rgb), dot(RGB_Y, rgb), dot(RGB_Z, rgb));
}
fn xyz_to_rgb(xyz: vec3<f32>) -> vec3<f32> {
    return vec3<f32>(dot(XYZ_R, xyz), dot(XYZ_G, xyz), dot(XYZ_B, xyz));
}
fn cat16(xyz: vec3<f32>) -> vec3<f32> {
    return vec3<f32>(dot(CAT_R, xyz), dot(CAT_G, xyz), dot(CAT_B, xyz));
}
fn inv_cat16(rgb: vec3<f32>) -> vec3<f32> {
    return vec3<f32>(dot(INV_CAT_X, rgb), dot(INV_CAT_Y, rgb), dot(INV_CAT_Z, rgb));
}
fn response(v: f32) -> f32 {
    let f = pow(F_L * abs(v) / 100.0, 0.42);
    return 400.0 * sign(v) * f / (27.13 + f) + 0.1;
}
fn inverse_response(v: f32) -> f32 {
    let x = v - 0.1;
    return sign(x) * 100.0/F_L * spow(27.13*abs(x)/(400.0-abs(x)), 1.0/0.42);
}
fn forward(rgb: vec3<f32>) -> vec3<f32> {
    if (all(rgb == vec3<f32>(0.0))) { return vec3<f32>(0.0); }
    let rc = D_RGB * cat16(rgb_to_xyz(rgb) * 100.0);
    let ra = vec3<f32>(response(rc.x), response(rc.y), response(rc.z));
    let a = ra.x - 12.0*ra.y/11.0 + ra.z/11.0;
    let b = (ra.x + ra.y - 2.0*ra.z)/9.0;
    let h = safe_atan2(b, a);
    let et = 0.25 * (cos(h + 2.0) + 3.8);
    let achromatic = (2.0*ra.x + ra.y + ra.z/20.0 - 0.305)*N_BB;
    let j = 100.0*spow(achromatic/A_W, C_Z);
    let denominator = ra.x + ra.y + 21.0*ra.z/20.0;
    var t = 0.0;
    if (denominator != 0.0) { t = (50000.0/13.0)*N_CB*et*length(vec2<f32>(a,b))/denominator; }
    let chroma = spow(t,0.9)*spow(j/100.0,0.5)*CHROMA_FACTOR;
    let m = chroma*F_L_QUARTER;
    let jp = 1.7*j/(1.0+0.007*j);
    let mp = log1p_precise(0.0228*m)/0.0228;
    return vec3<f32>(jp, mp*cos(h), mp*sin(h));
}
fn inverse(jab: vec3<f32>) -> vec3<f32> {
    let j = jab.x/(1.7-0.007*jab.x);
    let mp = length(jab.yz);
    let m = expm1_precise(mp*0.0228)/0.0228;
    let chroma = m/F_L_QUARTER;
    let h = safe_atan2(jab.z,jab.y);
    let sin_h = sin(h);
    let cos_h = cos(h);
    let t = spow(chroma/(sqrt(max(j,2.220446049250313e-16)/100.0)*CHROMA_FACTOR),1.0/0.9);
    let et = 0.25*(cos(h+2.0)+3.8);
    let achromatic = A_W*spow(j/100.0,1.0/C_Z);
    var p1 = 0.0;
    if (t != 0.0) { p1 = (50000.0/13.0)*N_CB*et/t; }
    let p2 = achromatic/N_BB+0.305;
    let p3 = 21.0/20.0;
    let n = p2*(2.0+p3)*(460.0/1403.0);
    var a = 0.0;
    var b = 0.0;
    if (t != 0.0) {
        if (abs(sin_h) >= abs(cos_h)) {
            let ratio = cos_h/sin_h;
            b = n/(p1/sin_h+(2.0+p3)*(220.0/1403.0)*ratio-27.0/1403.0+p3*(6300.0/1403.0));
            a = b*ratio;
        } else {
            let ratio = sin_h/cos_h;
            a = n/(p1/cos_h+(2.0+p3)*(220.0/1403.0)-(27.0/1403.0-p3*(6300.0/1403.0))*ratio);
            b = a*ratio;
        }
    }
    let ra = vec3<f32>(460.0*p2+451.0*a+288.0*b,
                       460.0*p2-891.0*a-261.0*b,
                       460.0*p2-220.0*a-6300.0*b)/1403.0;
    let rc = vec3<f32>(inverse_response(ra.x),inverse_response(ra.y),inverse_response(ra.z));
    return xyz_to_rgb(inv_cat16(rc/D_RGB)/100.0);
}
fn boundary(jp: f32, h: f32) -> f32 {
    let l_idx = (clamp(jp,p.table_axis.x,p.table_axis.y)-p.table_axis.x)/(p.table_axis.y-p.table_axis.x)*f32(p.n_l-1u);
    let l_lo = min(u32(floor(l_idx)),p.n_l-2u);
    let lf = l_idx-f32(l_lo);
    let h_idx = (h-p.table_axis.z)/p.table_axis.w;
    let hf = h_idx-floor(h_idx);
    let h_lo_signed = i32(floor(h_idx));
    let nh = i32(p.n_h);
    let h_lo = u32(((h_lo_signed%nh)+nh)%nh);
    let h_hi = (h_lo+1u)%p.n_h;
    let v00 = cmax[l_lo*p.n_h+h_lo];
    let v01 = cmax[l_lo*p.n_h+h_hi];
    let v10 = cmax[(l_lo+1u)*p.n_h+h_lo];
    let v11 = cmax[(l_lo+1u)*p.n_h+h_hi];
    return v00*(1.0-lf)*(1.0-hf)+v01*(1.0-lf)*hf+v10*lf*(1.0-hf)+v11*lf*hf;
}
@compute @workgroup_size(256,1,1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>, @builtin(num_workgroups) ng: vec3<u32>) {
    let i = gid.x+gid.y*ng.x*256u;
    if (i >= p.pixel_count) { return; }
    let base = i*3u;
    let rgb = vec3<f32>(src[base],src[base+1u],src[base+2u]);
    var result: vec3<f32>;
    if (p.mode == 2u) {
        result = inverse(rgb);
    } else {
        var jab = forward(rgb);
        if (p.mode == 1u) {
            result = jab;
        } else {
            // Out-of-domain negative colours can have undefined CAM chroma.
            // Colour's inverse safe division/opponent branches yield a=b=0
            // for that case; reproduce it explicitly on both GPU backends.
            if (!finite(jab.y) || !finite(jab.z)) { jab.y=0.0; jab.z=0.0; }
            if (p.lightness.w != 0.0) { jab.x = knee(jab.x/WHITE_JP,p.lightness.xyz)*WHITE_JP; }
            let cp = length(jab.yz);
            let h = safe_atan2(jab.z,jab.y);
            let cm = max(boundary(jab.x,h),1e-9);
            let cn = knee(cp/cm,p.knee.xyz)*cm;
            result = inverse(vec3<f32>(jab.x,cn*cos(h),cn*sin(h)));
        }
    }
    dst[base]=result.x; dst[base+1u]=result.y; dst[base+2u]=result.z;
}
"""


def _setup():
    """Match Colour's normalized XYZ wrapper and the current CPU table."""
    import colour
    from colour.appearance.cam16 import MATRIX_16, MATRIX_INVERSE_16
    from colour.appearance.ciecam02 import (
        achromatic_response_forward,
        degree_of_adaptation,
        post_adaptation_non_linear_response_compression_forward,
        viewing_conditions_dependent_parameters,
    )
    from spektrafilm.utils.gamut_compression import (
        _cam16ucs_white_Jp,
        _get_output_c_max_table,
    )

    cs = colour.RGB_COLOURSPACES["sRGB"]
    xyz_w = colour.xy_to_XYZ(cs.whitepoint)*100
    n, fl, nbb, ncb, z = viewing_conditions_dependent_parameters(20,100,64)
    d = degree_of_adaptation(1,64)
    rgb_w = MATRIX_16 @ xyz_w
    d_rgb = d*100/rgb_w+1-d
    aw = achromatic_response_forward(
        post_adaptation_non_linear_response_compression_forward(d_rgb*rgb_w,fl),nbb
    )
    constants = {
        "F_L": fl, "N_BB": nbb, "N_CB": ncb, "A_W": aw,
        "C_Z": 0.69*z, "CHROMA_FACTOR": (1.64-0.29**n)**0.73,
        "F_L_QUARTER": fl**0.25, "WHITE_JP": _cam16ucs_white_Jp("sRGB"),
        "D_RGB": d_rgb,
    }
    for names, matrix in (
        (("RGB_X","RGB_Y","RGB_Z"),cs.matrix_RGB_to_XYZ),
        (("XYZ_R","XYZ_G","XYZ_B"),cs.matrix_XYZ_to_RGB),
        (("CAT_R","CAT_G","CAT_B"),MATRIX_16),
        (("INV_CAT_X","INV_CAT_Y","INV_CAT_Z"),MATRIX_INVERSE_16),
    ):
        constants.update(zip(names,matrix))
    def number(x):
        value = format(float(x),".17g")
        return value if "." in value or "e" in value else value+".0"
    shader_constants=[]
    for key,value in constants.items():
        if np.ndim(value):
            shader_constants.append(f"const {key}: vec3<f32> = vec3<f32>({', '.join(map(number,value))});")
        else:
            shader_constants.append(f"const {key}: f32 = {number(value)};")
    axes = _get_output_c_max_table("cam16ucs","sRGB")
    return _SHADER.replace("__CONSTANTS__","\n".join(shader_constants)),axes


class GamutGpuPrototype:
    """Standalone experiment for packed linear sRGB, serialized per device.

    Default strips bound temporary GPU transfers to about 48 MiB per RGB
    buffer. The float32 result still has the complete input shape. A zero
    strip limit permits one device-sized buffer for controlled benchmarks.
    Production may lazily create one instance per render worker, use
    ``supports_spec`` before opting in, and call ``compress_for_spec``.
    Unsupported specs raise instead of quietly applying a different model.
    """

    DEFAULT_STRIP_PIXELS = 4 * 1024 * 1024

    @staticmethod
    def supports_spec(spec, *, output_color_space):
        """Only the exact configuration verified against the CPU reference."""
        try:
            return (
                output_color_space == "sRGB"
                and spec.algorithm == "cam16ucs"
                and tuple(spec.knee) == (0.0, 1.0, 6.0)
                and tuple(spec.lightness_compression) == (0.7, 1.0, 2.2)
            )
        except (AttributeError, TypeError, ValueError):
            return False

    def __init__(self, *, backend="Vulkan", max_pixels_per_dispatch=DEFAULT_STRIP_PIXELS):
        import wgpu
        if isinstance(max_pixels_per_dispatch, bool) or not isinstance(max_pixels_per_dispatch, int) or max_pixels_per_dispatch < 0:
            raise ValueError("max_pixels_per_dispatch must be a non-negative integer")
        self._wgpu=wgpu
        self._lock=threading.Lock()
        self._closed=False
        self._table_buffer=None
        self.device=None
        self.max_pixels_per_dispatch=max_pixels_per_dispatch
        adapters=[a for a in wgpu.gpu.enumerate_adapters_sync()
                  if str(a.info.get("backend_type","")).lower()==backend.lower()]
        if not adapters:
            raise RuntimeError(f"Requested {backend} adapter is unavailable")
        self.adapter=next((a for a in adapters if a.info.get("adapter_type")=="DiscreteGPU"),adapters[0])
        try:
            self.device=self.adapter.request_device_sync(required_limits={
                "max-storage-buffer-binding-size":min(int(self.adapter.limits["max-storage-buffer-binding-size"]),1024**3),
                "max-buffer-size":min(int(self.adapter.limits["max-buffer-size"]),1024**3),
            })
            start=time.perf_counter()
            shader,axes=_setup()
            self.setup_seconds=time.perf_counter()-start
            self.l_axis,self.h_axis,table=axes
            self._table_buffer=self.device.create_buffer_with_data(
                data=np.ascontiguousarray(table,dtype=np.float32),usage=wgpu.BufferUsage.STORAGE
            )
            module=self.device.create_shader_module(code=shader)
            self.pipeline=self.device.create_compute_pipeline(layout="auto",compute={"module":module,"entry_point":"main"})
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _validate_knee(value, name):
        try:
            values=tuple(float(x) for x in value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must contain threshold, limit and power") from exc
        if len(values)!=3 or not np.all(np.isfinite(values)) or not (0 <= values[0] < values[1] and values[2] > 0):
            raise ValueError(f"{name} requires finite 0 <= threshold < limit and power > 0")
        return values

    def compress_for_spec(self, image, spec, *, output_color_space, cancelled=None):
        """Eligible production-adapter API; caller owns any CPU routing policy."""
        if not self.supports_spec(spec,output_color_space=output_color_space):
            raise ValueError("GPU prototype only validates default CAM16-UCS in linear sRGB")
        return self.compress_rgb(image,knee=spec.knee,lightness=spec.lightness_compression,cancelled=cancelled)

    def compress_rgb(self, image, *, knee=(0.0,1.0,6.0), lightness=(0.7,1.0,2.2), mode=0, cancelled=None):
        """Return full-size float32 RGB with bounded temporary GPU buffers.

        Mode 1 returns CAM16-UCS; mode 2 interprets input as CAM16-UCS and
        returns RGB. Custom knees/modes are diagnostic, outside the verified
        ``compress_for_spec`` contract. Cancellation is checked between strips
        and raises InterruptedError; already submitted GPU work is completed.
        """
        if isinstance(mode,bool) or mode not in (0,1,2):
            raise ValueError("mode must be 0, 1 or 2")
        knee=self._validate_knee(knee,"knee")
        if lightness is not None:
            lightness=self._validate_knee(lightness,"lightness")
        if cancelled is not None and not callable(cancelled):
            raise ValueError("cancelled must be callable or None")
        source=np.asarray(image)
        if source.ndim<2 or source.shape[-1]!=3 or source.size==0 or source.dtype.kind not in "uif":
            raise ValueError("Expected non-empty real RGB with shape (...,3)")
        with self._lock:
            if self._closed:
                raise RuntimeError("GPU prototype is closed")
            if cancelled is not None and cancelled():
                raise InterruptedError("GPU gamut calculation cancelled")
            buffer_limit=min(self.device.limits["max-storage-buffer-binding-size"],self.device.limits["max-buffer-size"])
            strip_pixels=min(buffer_limit//12,(2**32-1)//3)
            if self.max_pixels_per_dispatch:
                strip_pixels=min(strip_pixels,self.max_pixels_per_dispatch)
            if strip_pixels<1:
                raise RuntimeError("GPU storage buffer cannot contain one RGB pixel")
            result=np.empty(source.shape,dtype=np.float32)
            flat_result=result.reshape(-1)
            offset=0
            # nditer buffers even non-contiguous/float64 inputs in C order,
            # avoiding a full-image float32 conversion before GPU strip upload.
            iterator=np.nditer(source,flags=["external_loop","buffered"],op_flags=["readonly"],
                               op_dtypes=[np.dtype(np.float32)],casting="same_kind",order="C",buffersize=strip_pixels*3)
            with iterator:
                for values in iterator:
                    if cancelled is not None and cancelled():
                        raise InterruptedError("GPU gamut calculation cancelled")
                    if not np.all(np.isfinite(values)):
                        raise ValueError("Input RGB must be finite and representable as float32")
                    if len(values)%3:
                        raise RuntimeError("Internal GPU strip is not a whole RGB pixel")
                    processed=self._dispatch(np.ascontiguousarray(values),knee,lightness,mode)
                    if not np.all(np.isfinite(processed)):
                        raise FloatingPointError("GPU gamut output is non-finite")
                    flat_result[offset:offset+len(values)]=processed
                    offset+=len(values)
            return result

    def _dispatch(self, source, knee, lightness, mode):
        """A complete transfer/dispatch/readback call; caller holds _lock."""
        wgpu=self._wgpu
        count=source.size//3
        config=np.concatenate([
            np.asarray([count,len(self.l_axis),len(self.h_axis),mode],dtype=np.uint32).view(np.float32),
            np.asarray([*knee,0],dtype=np.float32),
            np.asarray([*(lightness or (0,1,1)),int(lightness is not None)],dtype=np.float32),
            np.asarray([self.l_axis[0],self.l_axis[-1],self.h_axis[0],self.h_axis[1]-self.h_axis[0]],dtype=np.float32),
        ])
        buffers=[]
        try:
            source_buffer=self.device.create_buffer_with_data(data=source,usage=wgpu.BufferUsage.STORAGE)
            buffers.append(source_buffer)
            output_buffer=self.device.create_buffer(size=source.nbytes,usage=wgpu.BufferUsage.STORAGE|wgpu.BufferUsage.COPY_SRC)
            buffers.append(output_buffer)
            readback_buffer=self.device.create_buffer(size=source.nbytes,usage=wgpu.BufferUsage.COPY_DST|wgpu.BufferUsage.MAP_READ)
            buffers.append(readback_buffer)
            config_buffer=self.device.create_buffer_with_data(data=config,usage=wgpu.BufferUsage.UNIFORM)
            buffers.append(config_buffer)
            bound=[source_buffer,self._table_buffer,output_buffer,config_buffer]
            group=self.device.create_bind_group(layout=self.pipeline.get_bind_group_layout(0),entries=[
                {"binding":i,"resource":{"buffer":buffer,"offset":0,"size":buffer.size}}
                for i,buffer in enumerate(bound)
            ])
            gx=min(65535,(count+255)//256)
            gy=(count+gx*256-1)//(gx*256)
            encoder=self.device.create_command_encoder()
            compute=encoder.begin_compute_pass()
            compute.set_pipeline(self.pipeline)
            compute.set_bind_group(0,group)
            compute.dispatch_workgroups(gx,gy,1)
            compute.end()
            encoder.copy_buffer_to_buffer(output_buffer,0,readback_buffer,0,source.nbytes)
            self.device.queue.submit([encoder.finish()])
            readback_buffer.map_sync(wgpu.MapMode.READ)
            try:
                return np.frombuffer(readback_buffer.read_mapped(copy=False),dtype=np.float32).copy()
            finally:
                readback_buffer.unmap()
        finally:
            for buffer in buffers:
                buffer.destroy()

    def close(self):
        """Idempotently release the table and device after any in-flight call."""
        with self._lock:
            if not self._closed:
                self._closed=True
                if self._table_buffer is not None:
                    self._table_buffer.destroy()
                if self.device is not None:
                    self.device.destroy()

    def __enter__(self):
        if self._closed:
            raise RuntimeError("GPU prototype is closed")
        return self

    def __exit__(self,exc_type,exc,tb):
        self.close()
