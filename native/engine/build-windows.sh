#!/usr/bin/env bash
# Run inside Ubuntu/WSL. Dependencies: cmake ninja-build mingw-w64-posix,
# glslang-tools libvulkan-dev. No interpreter is embedded in the output DLL.
set -euo pipefail
engine_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$engine_root/../.." && pwd)"
native_build="${SPEKTRAFILM_NATIVE_BUILD:-/var/tmp/spektra-native-win}"
vulkan_headers="$native_build/host-vulkan-headers"
mkdir -p "$vulkan_headers"
# Only Vulkan headers are shared with the cross compiler. Passing /usr/include
# would accidentally select glibc's stdint.h instead of MinGW's Windows one.
cp -r /usr/include/vulkan /usr/include/vk_video "$vulkan_headers/"
cmake -S "$engine_root" -B "$native_build" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$engine_root/mingw-toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSPEKTRALAB_VULKAN_HEADERS="$vulkan_headers" \
  -DSPEKTRALAB_GLSLANG=/usr/bin/glslangValidator
cmake --build "$native_build" --target spektralab_engine_shared spektrafilm_raw --parallel "${SPEKTRAFILM_BUILD_JOBS:-4}"
mkdir -p "$engine_root/runtime/resources"
cp "$native_build/upstream/engine/spektrafilm_engine.dll" "$engine_root/runtime/"
cp "$native_build/spektrafilm_raw.dll" "$engine_root/runtime/"
mkdir -p "$engine_root/runtime/third-party/LibRaw"
cp "$native_build/third-party/LibRaw/"* "$engine_root/runtime/third-party/LibRaw/"
cp -r "$native_build/upstream/engine/resources/." "$engine_root/runtime/resources/"
# Product extensions are data overlays, never edits to preserved upstream data.
cp "$repo_root/vendor/spektrafilm/data/profiles/"*.json "$engine_root/runtime/resources/profiles/"
# Product profile overlays predate EDR. Preserve each paper's own measured
# calibration from the canonical native resource rather than dropping it.
python3 - "$engine_root" <<'PY_STAGE_EDR'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
for source in (root / "upstream/engine/resources/profiles").glob("*.json"):
    original = json.loads(source.read_text(encoding="utf-8"))
    calibration = original.get("data", {}).get("edr_tone_map")
    if not calibration:
        continue
    target = root / "runtime/resources/profiles" / source.name
    record = json.loads(target.read_text(encoding="utf-8"))
    record["data"]["edr_tone_map"] = calibration
    target.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
PY_STAGE_EDR

cp "$repo_root/LICENSE" "$engine_root/runtime/LICENSE-GPL-3.0.txt"
cp "$engine_root/UPSTREAM.json" "$engine_root/runtime/UPSTREAM.json"
cp "$engine_root/upstream/license/SPEKTRAFILM_LICENSE.txt" "$engine_root/runtime/resources/SPEKTRAFILM_LICENSE.txt"
cp "$engine_root/upstream/engine/third_party/volk/LICENSE.md" "$engine_root/runtime/volk-LICENSE.md"
printf 'Staged native engine: %s\n' "$engine_root/runtime"
