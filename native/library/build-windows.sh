#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SPKLIB_BUILD_DIR:-/var/tmp/spektra-library-win}"
CXX="${CXX:-x86_64-w64-mingw32-g++}"
CC="${CC:-x86_64-w64-mingw32-gcc}"
mkdir -p "$BUILD_DIR" "$ROOT/runtime"
SQLITE="$ROOT/third_party/sqlite/sqlite3.c"
if [[ ! -f "$SQLITE" ]]; then
    echo 'Missing pinned SQLite source; see third_party/sqlite/README.md' >&2
    exit 1
fi
"$CC" -O2 -DSQLITE_THREADSAFE=1 -DSQLITE_USE_URI=1 -DSQLITE_OMIT_LOAD_EXTENSION=1 -c "$SQLITE" -o "$BUILD_DIR/sqlite3.o"
"$CXX" -std=c++17 -O2 -DNDEBUG '-DSPKLIB_VERSION="0.3.1-spektrafilm-win1"' \
  -I"$ROOT/include" -I"$ROOT/src" -I"$ROOT/third_party" -I"$ROOT/third_party/sqlite" \
  "$ROOT/src/sqlite.cpp" "$ROOT/src/capture_one.cpp" "$ROOT/src/library.cpp" "$ROOT/src/api.cpp" \
  "$ROOT/host/main.cpp" "$BUILD_DIR/sqlite3.o" \
  -municode -static -static-libgcc -static-libstdc++ -lnormaliz -lwinpthread \
  -o "$BUILD_DIR/spklib-host.exe"
cp "$BUILD_DIR/spklib-host.exe" "$ROOT/runtime/spklib-host.exe"
echo "Built $ROOT/runtime/spklib-host.exe"
