cmake_minimum_required(VERSION 3.20)
project(SpektraFilmNative LANGUAGES C CXX)

# The GPL upstream core is kept intact apart from the documented wire fields.
# No Python interpreter or vendor photo-editor runtime is linked into this DLL.
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(SPEKTRALAB_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)
set(SPEKTRALAB_BUILD_NATIVE_RAW OFF CACHE BOOL "" FORCE)
set(SPEKTRALAB_BUILD_HOST OFF CACHE BOOL "" FORCE)
set(SPEKTRALAB_REQUIRE_VULKAN ON CACHE BOOL "" FORCE)
set(SPEKTRALAB_BUILD_TEST_DLL ON CACHE BOOL "" FORCE)
add_subdirectory(upstream/engine)

if(MINGW)
    target_link_options(spektralab_engine_shared PRIVATE -static-libgcc -static-libstdc++ -static)
endif()

# A separate RAW decoder keeps metadata/thumbnail import independent of GPU
# initialization. Reuse the same current LibRaw source as Android.
set(SPEKTRALAB_LIBRAW_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../android/app/src/main/cpp/third_party/libraw" CACHE PATH "Bundled shared LibRaw source" FORCE)
set(SPEKTRALAB_STATIC_RUNTIME ON)
include(upstream/engine/cmake/LibRaw.cmake)
add_library(spektrafilm_raw SHARED
    upstream/engine/src/io/raw_decoder.cpp upstream/engine/src/io/raw_headroom.cpp
    upstream/engine/src/io/raw_bridge.cpp upstream/engine/src/io/optics_bridge.cpp)
set_target_properties(spektrafilm_raw PROPERTIES OUTPUT_NAME spektrafilm_raw PREFIX "")
target_compile_features(spektrafilm_raw PRIVATE cxx_std_20)
target_include_directories(spektrafilm_raw PRIVATE upstream/engine/include upstream/engine/src)
target_link_libraries(spektrafilm_raw PRIVATE spk_libraw spektralab_core)
if(MINGW)
    target_link_options(spektrafilm_raw PRIVATE -static-libgcc -static-libstdc++ -static)
endif()
