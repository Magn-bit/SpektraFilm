#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 inverseX;
    vec4 inverseY;
    vec4 inverseW;
    vec4 maskPoints;
    vec4 maskShape;
    vec4 maskSpace;
    vec4 tint;
} ubuf;

void main() {
    vec3 p = vec3(qt_TexCoord0, 1.0);
    float divisor = dot(ubuf.inverseW.xyz, p);
    if (abs(divisor) < 0.000001) { fragColor = vec4(0.0); return; }
    vec2 source = vec2(dot(ubuf.inverseX.xyz, p), dot(ubuf.inverseY.xyz, p)) / divisor;
    if (any(lessThan(source, vec2(0.0))) || any(greaterThan(source, vec2(1.0)))) {
        fragColor = vec4(0.0); return;
    }
    float alpha;
    if (ubuf.maskSpace.z < 0.5) {
        vec2 delta = (ubuf.maskPoints.zw - ubuf.maskPoints.xy) * ubuf.maskSpace.xy;
        float length2 = dot(delta, delta);
        float t = length2 > 0.000000001 ? clamp(dot((source - ubuf.maskPoints.xy) * ubuf.maskSpace.xy, delta) / length2, 0.0, 1.0) : 0.0;
        alpha = t * t * (3.0 - 2.0 * t);
    } else {
        vec2 delta = (source - ubuf.maskPoints.xy) * ubuf.maskSpace.xy;
        float c = cos(ubuf.maskShape.z), s = sin(ubuf.maskShape.z);
        vec2 local = vec2(delta.x*c + delta.y*s, -delta.x*s + delta.y*c);
        float distance = length(local / max(vec2(0.5), ubuf.maskShape.xy * ubuf.maskSpace.xy));
        float feather = max(0.001, ubuf.maskShape.w);
        float t = clamp((distance - (1.0 - feather)) / feather, 0.0, 1.0);
        alpha = 1.0 - t * t * (3.0 - 2.0 * t);
    }
    if (ubuf.maskSpace.w > 0.5) alpha = 1.0 - alpha;
    alpha *= ubuf.tint.a * ubuf.qt_Opacity;
    fragColor = vec4(ubuf.tint.rgb * alpha, alpha);
}
