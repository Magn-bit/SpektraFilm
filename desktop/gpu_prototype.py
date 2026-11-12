"""Experimental WebGPU kernels for validating native spectral acceleration."""
from __future__ import annotations

import numpy as np

from pathlib import Path

_INTERPOLATE_SHADER = (Path(__file__).resolve().parents[1] / "native/shaders/density_curve.wgsl").read_text(encoding="utf-8")


class SpectralGpuPrototype:
    def __init__(self, *, backend="Vulkan"):
        import wgpu

        self._wgpu = wgpu
        adapters = wgpu.gpu.enumerate_adapters_sync()
        matches = [
            item for item in adapters
            if str(item.info.get("backend_type", "")).lower() == backend.lower()
        ]
        if not matches:
            available = sorted({item.info.get("backend_type", "unknown") for item in adapters})
            raise RuntimeError(f"{backend} backend unavailable; adapters: {available}")
        self.adapter = next(
            (item for item in matches if item.info.get("adapter_type") == "DiscreteGPU"),
            matches[0],
        )
        self.device = self.adapter.request_device_sync()
        shader = self.device.create_shader_module(code=_INTERPOLATE_SHADER)
        self.pipeline = self.device.create_compute_pipeline(
            layout="auto",
            compute={"module": shader, "entry_point": "main"},
        )

    def interpolate_density(self, image, x_axis, y_values):
        wgpu = self._wgpu
        source = np.ascontiguousarray(image, dtype=np.float32)
        axis = np.ascontiguousarray(x_axis, dtype=np.float32)
        curves = np.ascontiguousarray(y_values, dtype=np.float32)
        if source.ndim != 3 or source.shape[-1] != 3 or not source.shape[0] or not source.shape[1]:
            raise ValueError("image must have shape (height, width, 3)")
        if axis.ndim == 1:
            axis = np.repeat(axis[:, None], 3, axis=1)
        if axis.shape != curves.shape or axis.ndim != 2 or axis.shape[1] != 3 or len(axis)<2:
            raise ValueError("axis and curves must have matching (curve_count, 3) shapes")
        if not np.all(np.diff(axis, axis=0) >= 0):
            raise ValueError("each interpolation axis must be monotonic")
        if not np.isfinite(source).all() or not np.isfinite(axis).all() or not np.isfinite(curves).all():
            raise ValueError("prototype requires finite input and curve values")

        # Bound work buffers to the adapter binding limit. A 61MP source is
        # not one giant storage binding, and output dimensions never change.
        max_pixels = min(4_194_304, int(self.device.limits["max-storage-buffer-binding-size"]) // 12)
        if source.shape[0] * source.shape[1] > max_pixels:
            output = np.empty_like(source)
            flat_source=source.reshape(-1,3)
            flat_output=output.reshape(-1,3)
            for start in range(0, len(flat_source), max_pixels):
                stop = min(start + max_pixels, len(flat_source))
                flat_output[start:stop] = self.interpolate_density(
                    flat_source[start:stop][None,:,:], axis, curves
                )[0]
            return output
        flat = source.reshape(-1)
        pixel_count = source.shape[0] * source.shape[1]
        usage = wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        input_buffer = self.device.create_buffer_with_data(
            data=flat, usage=usage | wgpu.BufferUsage.COPY_SRC
        )
        axis_buffer = self.device.create_buffer_with_data(
            data=axis.reshape(-1), usage=usage
        )
        curve_buffer = self.device.create_buffer_with_data(
            data=curves.reshape(-1), usage=usage
        )
        output_buffer = self.device.create_buffer(
            size=flat.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        params = np.asarray([pixel_count, len(axis)], dtype=np.uint32)
        params_buffer = self.device.create_buffer_with_data(
            data=params, usage=wgpu.BufferUsage.UNIFORM
        )
        bind_group = self.device.create_bind_group(
            layout=self.pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": input_buffer, "offset": 0, "size": input_buffer.size}},
                {"binding": 1, "resource": {"buffer": axis_buffer, "offset": 0, "size": axis_buffer.size}},
                {"binding": 2, "resource": {"buffer": curve_buffer, "offset": 0, "size": curve_buffer.size}},
                {"binding": 3, "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size}},
                {"binding": 4, "resource": {"buffer": params_buffer, "offset": 0, "size": params_buffer.size}},
            ],
        )

        groups_x = min(65535, (pixel_count + 255) // 256)
        groups_y = (pixel_count + groups_x * 256 - 1) // (groups_x * 256)
        encoder = self.device.create_command_encoder()
        compute = encoder.begin_compute_pass()
        compute.set_pipeline(self.pipeline)
        compute.set_bind_group(0, bind_group)
        compute.dispatch_workgroups(groups_x, groups_y, 1)
        compute.end()
        self.device.queue.submit([encoder.finish()])
        output = np.frombuffer(
            self.device.queue.read_buffer(output_buffer), dtype=np.float32
        ).reshape(source.shape).copy()

        for buffer in (input_buffer, axis_buffer, curve_buffer, output_buffer, params_buffer):
            buffer.destroy()
        return output
