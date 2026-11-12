#!/usr/bin/env bash
set -euo pipefail
hdr_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$hdr_root/../.." && pwd)"
hdr_build="${SPEKTRAFILM_HDR_BUILD:-/var/tmp/spektra-hdr-win}"
jpeg_build="$hdr_build/jpeg"
toolchain="$repo_root/native/engine/mingw-toolchain.cmake"
cmake -S "$repo_root/android/app/src/main/cpp/third_party/libjpeg-turbo" -B "$jpeg_build" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$jpeg_build/install" \
  -DCMAKE_ASM_NASM_COMPILER=/usr/bin/nasm \
  -DENABLE_SHARED=OFF -DENABLE_STATIC=ON -DWITH_TURBOJPEG=OFF
cmake --build "$jpeg_build" --target jpeg-static --parallel 4
cmake -S "$hdr_root" -B "$hdr_build/codec" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DCMAKE_BUILD_TYPE=Release \
  -DJPEG_LIBRARY="$jpeg_build/libjpeg.a" \
  -DJPEG_INCLUDE_DIR="$repo_root/android/app/src/main/cpp/third_party/libjpeg-turbo/src" \
  -DCMAKE_CXX_FLAGS="-I$jpeg_build"
cmake --build "$hdr_build/codec" --target spektrafilm_hdr --parallel 4
mkdir -p "$hdr_root/runtime"
cp "$hdr_build/codec/spektrafilm_hdr.dll" "$hdr_root/runtime/"
cp "$hdr_root/upstream/libultrahdr-2.0.2/LICENSE" "$hdr_root/runtime/libultrahdr-LICENSE.txt"
cp "$hdr_root/upstream/libultrahdr-2.0.2/third_party/image_io/LICENSE" "$hdr_root/runtime/image_io-LICENSE.txt"
cp "$hdr_root/upstream/libultrahdr-2.0.2/adobe-hdr-gain-map-license/NOTICE" "$hdr_root/runtime/adobe-hdr-gain-map-NOTICE.txt"
cp "$hdr_root/UPSTREAM.json" "$hdr_root/runtime/UPSTREAM.json"
cp "$repo_root/android/app/src/main/cpp/third_party/libjpeg-turbo/LICENSE.md" "$hdr_root/runtime/libjpeg-turbo-LICENSE.md"
printf 'Staged Ultra HDR codec: %s\n' "$hdr_root/runtime"
