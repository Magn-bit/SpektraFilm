// SPDX-License-Identifier: GPL-3.0-or-later
struct Params {
    pixel_count: u32,
    curve_count: u32,
}

@group(0) @binding(0) var<storage, read> input_values: array<f32>;
@group(0) @binding(1) var<storage, read> x_axis: array<f32>;
@group(0) @binding(2) var<storage, read> y_values: array<f32>;
@group(0) @binding(3) var<storage, read_write> output_values: array<f32>;
@group(0) @binding(4) var<uniform> params: Params;

fn interpolate(value: f32, channel: u32) -> f32 {
    let count = params.curve_count;
    let first = x_axis[channel];
    let last = x_axis[(count - 1u) * 3u + channel];
    if (value <= first) {
        return y_values[channel];
    }
    if (value >= last) {
        return y_values[(count - 1u) * 3u + channel];
    }

    var low = 0u;
    var high = count;
    while (low < high) {
        let middle = low + (high - low) / 2u;
        if (x_axis[middle * 3u + channel] <= value) {
            low = middle + 1u;
        } else {
            high = middle;
        }
    }
    let lower = low - 1u;
    let x0 = x_axis[lower * 3u + channel];
    let x1 = x_axis[low * 3u + channel];
    let dx = x1 - x0;
    if (dx == 0.0) {
        return y_values[lower * 3u + channel];
    }
    let t = (value - x0) / dx;
    let y0 = y_values[lower * 3u + channel];
    let y1 = y_values[low * 3u + channel];
    return y0 + t * (y1 - y0);
}

@compute @workgroup_size(256, 1, 1)
fn main(
    @builtin(global_invocation_id) global_id: vec3<u32>,
    @builtin(num_workgroups) group_count: vec3<u32>,
) {
    let index = global_id.x + global_id.y * group_count.x * 256u;
    if (index >= params.pixel_count) {
        return;
    }
    let base = index * 3u;
    output_values[base] = interpolate(input_values[base], 0u);
    output_values[base + 1u] = interpolate(input_values[base + 1u], 1u);
    output_values[base + 2u] = interpolate(input_values[base + 2u], 2u);
}
