"""Isolated WGSL prototype of Spektrafilm's physical Gaussian approximation.

No production integration. FIR kernel, reflect boundary and YVV coefficients
follow vendor/spektrafilm/utils/fast_gaussian_filter.py (GPL-3.0, Andrea
Volpato). The large-sigma recurrence uses equivalent first/second differences
to avoid the near-cancelling sigma=100 coefficients losing their DC gain.
The input/output plane and three recursive states per line remain float32.
This is not a new blur model.
"""
from __future__ import annotations

import threading
import time

import numpy as np


_FIR_SHADER = r"""
struct Params { shape: vec4<u32>, work: vec4<u32> }
@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(0) @binding(1) var<storage, read> kernel: array<f32>;
@group(0) @binding(2) var<storage, read_write> dst: array<f32>;
@group(0) @binding(3) var<uniform> p: Params;
fn reflected(index: i32, length: u32) -> u32 {
    // Fold negative indices before unsigned modulo. This also avoids
    // backend signed-remainder differences on negative coordinates.
    var positive = index;
    if (positive < 0) { positive = -positive - 1; }
    let period = 2u * length;
    var value = u32(positive) % period;
    if (value >= length) { value = period - 1u - value; }
    return value;
}
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let index = p.work.x + gid.x;
    if (index >= p.work.y) { return; }
    let width = p.shape.x; let height = p.shape.y;
    let x = index % width; let y = index / width;
    let radius = i32(p.shape.z);
    var value = 0.0;
    for (var k = -radius; k <= radius; k++) {
        var position = y * width + reflected(i32(x) + k, width);
        if (p.shape.w == 0u) {
            position = reflected(i32(y) + k, height) * width + x;
        }
        value += src[position] * kernel[u32(k + radius)];
    }
    dst[index] = value;
}
"""


_IIR_SHADER = r"""
struct Params { shape: vec4<u32>, sweep: vec4<u32>, coefficients: vec4<f32> }
@group(0) @binding(0) var<storage, read_write> plane: array<f32>;
@group(0) @binding(1) var<storage, read_write> states: array<f32>;
@group(0) @binding(2) var<uniform> p: Params;

fn sample_index(line: u32, position: u32) -> u32 {
    if (p.sweep.x == 0u) { return line*p.shape.x + position; }
    return position*p.shape.x + line;
}
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let line = gid.x;
    let length = select(p.shape.y, p.shape.x, p.sweep.x == 0u);
    let lines = select(p.shape.x, p.shape.y, p.sweep.x == 0u);
    if (line >= lines) { return; }
    var previous = states[line*3u];
    var difference = states[line*3u+1u];
    var second_difference = states[line*3u+2u];
    if (p.shape.z == 0u) {
        let edge = select(0u, length-1u, p.sweep.y != 0u);
        let first = plane[sample_index(line, edge)];
        previous = first; difference = 0.0; second_difference = 0.0;
    }
    for (var i = 0u; i < p.shape.w; i++) {
        let traversed = p.shape.z + i;
        let position = select(traversed, length-1u-traversed, p.sweep.y != 0u);
        let index = sample_index(line, position);
        // With d1=s1-s2 and d2=s1-2*s2+s3, the upstream recurrence
        // B*x+B1*s1+B2*s2+B3*s3 has the equivalent difference form below.
        // B+B1+B2+B3=1. Small deltas avoid subtracting three large states.
        let next_difference = p.coefficients.x*(plane[index]-previous)
            + p.coefficients.y*difference + p.coefficients.z*second_difference;
        let value = previous + next_difference;
        plane[index] = value;
        second_difference = next_difference-difference;
        difference = next_difference;
        previous = value;
    }
    states[line*3u] = previous;
    states[line*3u+1u] = difference;
    states[line*3u+2u] = second_difference;
}
"""


def _yvv_coeffs(sigma):
    q = 0.98711*sigma - 0.96330 if sigma >= 2.5 else 3.97156 - 4.14554*np.sqrt(1 - .26891*sigma)
    q2, q3 = q*q, q*q*q
    b0 = 1.57825 + 2.44413*q + 1.4281*q2 + .422205*q3
    b1 = 2.44413*q + 2.85619*q2 + 1.26661*q3
    b2 = -(1.4281*q2 + 1.26661*q3)
    b3 = .422205*q3
    return 1-(b1+b2+b3)/b0, b1/b0, b2/b0, b3/b0


class GaussianGpuPrototype:
    """FIR reflect / banded YVV sample-replication blur, explicit backend.

    Each colour channel has a single float32 plane in the IIR path. Forward
    and backward sweeps run in bounded segments, retaining their three states
    per row/column across dispatches. They are not independent tiles: no halo
    approximation, reset at band boundaries or change in recurrence order.
    FIR needs one second plane; separate compute passes provide dependencies.
    """
    def __init__(self, *, backend="Vulkan", segment_length=256):
        import wgpu
        self._wgpu = wgpu
        matches = [item for item in wgpu.gpu.enumerate_adapters_sync()
                   if str(item.info.get('backend_type','')).lower() == backend.lower()]
        if not matches:
            raise RuntimeError(f'{backend} adapter unavailable')
        self.adapter = next((a for a in matches if a.info.get('adapter_type') == 'DiscreteGPU'), matches[0])
        self.device = self.adapter.request_device_sync()
        if not 1 <= int(segment_length) <= 512:
            raise ValueError('segment_length must be within 1..512 for bounded GPU work')
        self.segment_length = int(segment_length)
        self._lock = threading.Lock()
        self._pipelines = {}
        for label, code in (('fir',_FIR_SHADER),('iir',_IIR_SHADER)):
            shader = self.device.create_shader_module(label=f'physical-blur-{label}',code=code)
            self._pipelines[label] = self.device.create_compute_pipeline(
                layout='auto',compute={'module':shader,'entry_point':'main'})
        self.last_timings = {}

    def _buffer(self, data, usage):
        return self.device.create_buffer_with_data(data=data,usage=usage)

    def _bind(self, name, buffers):
        return self.device.create_bind_group(layout=self._pipelines[name].get_bind_group_layout(0),
            entries=[{'binding':i,'resource':{'buffer':b,'offset':0,'size':b.size}}
                     for i,b in enumerate(buffers)])

    def _dispatch(self, encoder, name, bind, groups):
        compute = encoder.begin_compute_pass()
        compute.set_pipeline(self._pipelines[name])
        compute.set_bind_group(0,bind)
        compute.dispatch_workgroups(groups,1,1)
        compute.end()

    def _filter_plane(self, plane, sigma, truncate):
        wgpu = self._wgpu
        height,width = plane.shape
        usage = wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        owned = []
        started = time.perf_counter()
        source = self._buffer(plane,usage); owned.append(source)
        uploaded = time.perf_counter()
        encoder = self.device.create_command_encoder()
        dispatches = 0
        try:
            if sigma < 3:
                radius = int(truncate*sigma + .5)
                coordinates = np.arange(-radius,radius+1,dtype=np.float64)
                kernel = np.exp(-.5*(coordinates/sigma)**2)
                kernel /= kernel.sum()
                weights = self._buffer(kernel.astype(np.float32),wgpu.BufferUsage.STORAGE)
                intermediate = self.device.create_buffer(size=plane.nbytes,usage=usage)
                owned.extend((weights,intermediate))
                for axis,src,dst in ((0,source,intermediate),(1,intermediate,source)):
                    # The storage binding is global, but each dispatch is
                    # bounded to <= 4M samples / maxComputeWorkgroupsPerDimension.
                    count=height*width
                    for start in range(0,count,4_194_304):
                        stop=min(count,start+4_194_304)
                        values=np.asarray([width,height,radius,axis,start,stop,0,0],dtype=np.uint32)
                        params=self._buffer(values,wgpu.BufferUsage.UNIFORM);owned.append(params)
                        self._dispatch(encoder,'fir',self._bind('fir',(src,weights,dst,params)),(stop-start+255)//256)
                        dispatches += 1
            else:
                state=self.device.create_buffer(size=max(width,height)*3*4,usage=usage)
                owned.append(state)
                coefficients=np.asarray(_yvv_coeffs(sigma),dtype=np.float64)
                stable=np.asarray([coefficients[0],-coefficients[2]-2*coefficients[3],coefficients[3],0],dtype=np.float32)
                for axis,length,lines in ((0,width,height),(1,height,width)):
                    for reverse in (0,1):
                        for start in range(0,length,self.segment_length):
                            count=min(self.segment_length,length-start)
                            raw=bytearray(48)
                            np.frombuffer(raw,dtype=np.uint32)[:8]=[width,height,start,count,axis,reverse,0,0]
                            np.frombuffer(raw,dtype=np.float32)[8:]=stable
                            params=self._buffer(raw,wgpu.BufferUsage.UNIFORM);owned.append(params)
                            self._dispatch(encoder,'iir',self._bind('iir',(source,state,params)),(lines+63)//64)
                            dispatches += 1
            self.device.queue.submit([encoder.finish()])
            submitted=time.perf_counter()
            output=np.frombuffer(self.device.queue.read_buffer(source),dtype=np.float32).reshape(plane.shape).copy()
            finished=time.perf_counter()
            return output,{'upload_seconds':uploaded-started,'encode_submit_seconds':submitted-uploaded,
                'wait_readback_seconds':finished-submitted,'upload_dispatch_readback_seconds':finished-started,
                'dispatches':dispatches}
        finally:
            for buffer in owned: buffer.destroy()

    def filter(self, image, sigma, truncate=3.0):
        """Return an independent float32 image with original shape, no scaling.

        The prototype deliberately rejects planes beyond the binding limit.
        Recursive segmentation bounds a dispatch's loop length; it does not
        hide a full-plane GPU allocation or promise phone memory feasibility.
        """
        values=np.asarray(image)
        if values.ndim not in (2,3) or not all(values.shape) or (values.ndim==3 and values.shape[2]!=3):
            raise ValueError('expected nonempty 2D or (height,width,3) image')
        if not np.isfinite(values).all() or not np.isfinite(truncate) or truncate<0:
            raise ValueError('finite input and nonnegative finite truncate required')
        channels=1 if values.ndim==2 else 3
        sigmas=np.asarray(sigma,dtype=np.float64).reshape(-1)
        if sigmas.size==1: sigmas=np.repeat(sigmas,channels)
        if sigmas.size!=channels or not np.isfinite(sigmas).all():
            raise ValueError('sigma must be finite scalar or one value per channel')
        if values.shape[0]*values.shape[1]*4 > self.device.limits['max-storage-buffer-binding-size']:
            raise ValueError('full plane exceeds prototype storage binding; output was not resized')
        if max(values.shape[:2]) > 65535*64:
            raise ValueError('line count exceeds one-dimensional dispatch limit')
        started=time.perf_counter()
        output=np.empty(values.shape,dtype=np.float32)
        records=[]
        with self._lock:
            for channel,s in enumerate(sigmas):
                plane=np.ascontiguousarray(values if channels==1 else values[:,:,channel],dtype=np.float32)
                if s<=0 or (s<3 and int(float(truncate)*s+.5)==0):
                    filtered=plane.copy();record={'identity':True,'dispatches':0}
                else:
                    filtered,record=self._filter_plane(plane,float(s),float(truncate))
                if channels==1: output[:]=filtered
                else: output[:,:,channel]=filtered
                records.append(record)
        self.last_timings={'total_seconds':time.perf_counter()-started,'channels':records,
            'plane_bytes':values.shape[0]*values.shape[1]*4,'segment_length':self.segment_length}
        return output
