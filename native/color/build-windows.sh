#!/usr/bin/env bash
set -euo pipefail
COLOR_ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$COLOR_ROOT/runtime"
x86_64-w64-mingw32-gcc -O2 -shared -DCMS_DLL_BUILD=1 -DCMS_NO_PTHREADS=1 \
  -I"$COLOR_ROOT/upstream/include" "$COLOR_ROOT"/upstream/src/*.c "$COLOR_ROOT/matrix_display.c" \
  -static-libgcc -Wl,--export-all-symbols,--out-implib,/var/tmp/spektra-lcms2.a -s \
  -o "$COLOR_ROOT/runtime/spektrafilm_lcms2.dll"
