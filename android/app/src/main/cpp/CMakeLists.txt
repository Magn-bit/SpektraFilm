cmake_minimum_required(VERSION 3.22.1)
project(spektra_stream_jpeg LANGUAGES C CXX)

set(ENABLE_SHARED OFF CACHE BOOL "" FORCE)
set(ENABLE_STATIC ON CACHE BOOL "" FORCE)
if(ANDROID AND ANDROID_ABI STREQUAL "arm64-v8a")
    # AArch64 guarantees NEON; use turbo's vector colour/DCT/entropy kernels.
    # This changes execution only, not JPEG quality, subsampling or precision.
    set(WITH_SIMD ON CACHE BOOL "" FORCE)
    set(REQUIRE_SIMD ON CACHE BOOL "" FORCE)
else()
    set(WITH_SIMD OFF CACHE BOOL "" FORCE)
endif()
set(WITH_TURBOJPEG OFF CACHE BOOL "" FORCE)
set(WITH_TOOLS OFF CACHE BOOL "" FORCE)
set(WITH_TESTS OFF CACHE BOOL "" FORCE)
set(WITH_JAVA OFF CACHE BOOL "" FORCE)
set(WITH_FUZZ OFF CACHE BOOL "" FORCE)
set(SPEKTRA_EMBED_LIBJPEG ON)

add_subdirectory(third_party/libjpeg-turbo)
if(TARGET simd)
    target_compile_options(simd PRIVATE -O3)
    set_target_properties(simd PROPERTIES POSITION_INDEPENDENT_CODE ON)
endif()

if(ANDROID)
    target_compile_options(jpeg-static PRIVATE -O3)
    add_library(spektra_stream_jpeg SHARED JpegStreamEncoder.cpp OutputPixelOps.cpp)
    target_compile_features(spektra_stream_jpeg PRIVATE cxx_std_17)
    target_compile_options(spektra_stream_jpeg PRIVATE -O3 -fno-fast-math)
    target_include_directories(spektra_stream_jpeg PRIVATE
        third_party/libjpeg-turbo/src
        ${CMAKE_CURRENT_BINARY_DIR}/third_party/libjpeg-turbo
    )
    target_link_libraries(spektra_stream_jpeg PRIVATE jpeg-static)
endif()

# LibRaw is vendored under its original CDDL-1.0 / LGPL-2.1 dual license.
# Keep the full decoder + postprocessing implementation, excluding upstream's
# mutually exclusive no-processing placeholders. Proprietary SDKs are
# disabled; JPEG and zlib support remain available for
# formats such as lossy/compressed DNG.
file(GLOB_RECURSE SPEKTRA_LIBRAW_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/third_party/libraw/src/*.cpp")
list(FILTER SPEKTRA_LIBRAW_SOURCES EXCLUDE REGEX "/(preprocessing|postprocessing|write)/.*_ph\\.cpp$")
add_library(spektra_libraw STATIC ${SPEKTRA_LIBRAW_SOURCES})
set_target_properties(spektra_libraw PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(spektra_libraw PRIVATE cxx_std_17)
target_compile_definitions(spektra_libraw PUBLIC LIBRAW_NODLL PRIVATE USE_JPEG USE_ZLIB)
target_include_directories(spektra_libraw PUBLIC third_party/libraw PRIVATE
    third_party/libjpeg-turbo/src
    ${CMAKE_CURRENT_BINARY_DIR}/third_party/libjpeg-turbo)
target_link_libraries(spektra_libraw PRIVATE jpeg-static z)

add_library(spektra_raw_core STATIC RawDecoder.cpp)
set_target_properties(spektra_raw_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(spektra_raw_core PRIVATE cxx_std_17)
target_include_directories(spektra_raw_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(spektra_raw_core PUBLIC spektra_libraw)
if(ANDROID)
    # Personal delivery uses a debug signature, but RAW pixel loops must still
    # ship optimized. AHD's upstream OpenMP path keeps its original arithmetic.
    target_compile_options(spektra_libraw PRIVATE -O3 -fno-fast-math -fopenmp)
    target_compile_options(spektra_raw_core PRIVATE -O3 -fno-fast-math)
    add_library(spektra_raw SHARED RawImageDecoderJni.cpp)
    target_compile_features(spektra_raw PRIVATE cxx_std_17)
    target_link_libraries(spektra_raw PRIVATE spektra_raw_core)
    target_compile_options(spektra_raw PRIVATE -O3 -fno-fast-math -fopenmp)
    target_link_options(spektra_raw PRIVATE -fopenmp -static-openmp)
endif()

option(SPEKTRA_RAW_BUILD_PROBE "Build the optional native RAW diagnostic program" OFF)
if(SPEKTRA_RAW_BUILD_PROBE)
    add_executable(spektra_raw_probe tests/RawDecoderProbe.cpp)
    target_compile_features(spektra_raw_probe PRIVATE cxx_std_17)
    target_include_directories(spektra_raw_probe PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
    target_link_libraries(spektra_raw_probe PRIVATE spektra_raw_core)
    add_executable(spektra_raw_validation tests/RawDecoderValidation.cpp)
    target_compile_features(spektra_raw_validation PRIVATE cxx_std_17)
    target_link_libraries(spektra_raw_validation PRIVATE spektra_raw_core)
endif()

if(ANDROID)
    # Same scientific core and float32 Vulkan kernels as the Windows build.
    # SPIR-V is baked once by scripts/prepare_android_native.py, never on-device.
    get_filename_component(SPEKTRA_REPO "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
    set(SPEKTRA_ENGINE "${SPEKTRA_REPO}/native/engine/upstream/engine")
    file(GLOB SPEKTRA_CORE CONFIGURE_DEPENDS "${SPEKTRA_ENGINE}/src/core/*.cpp")
    add_library(spektra_android_core STATIC ${SPEKTRA_CORE})
    target_compile_features(spektra_android_core PUBLIC cxx_std_20)
    target_compile_definitions(spektra_android_core PUBLIC SPK_VULKAN_BACKEND=1)
    target_include_directories(spektra_android_core PUBLIC "${SPEKTRA_ENGINE}/src/core")
    set_target_properties(spektra_android_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
    set(SPEKTRA_PIPELINE_SOURCES blur pipeline scene_latitude windows_unported overscan imprint_raster view_process editor_process editor_analyze)
    foreach(source ${SPEKTRA_PIPELINE_SOURCES})
        list(APPEND SPEKTRA_PIPELINE "${SPEKTRA_ENGINE}/src/pipeline/${source}.cpp")
    endforeach()
    set(SPEKTRA_FONTS "${SPEKTRA_ENGINE}/resources_product/fonts")
    file(READ "${SPEKTRA_FONTS}/LiberationSans-Regular.ttf" regular HEX)
    file(READ "${SPEKTRA_FONTS}/LiberationSans-Bold.ttf" bold HEX)
    file(READ "${SPEKTRA_FONTS}/DejaVuSansMono-Bold.ttf" mono_bold HEX)
    foreach(font regular bold mono_bold)
        string(REGEX REPLACE "(..)" "0x\\1," ${font} "${${font}}")
    endforeach()
    file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/generated/spk_imprint_fonts.hpp"
        CONTENT "#pragma once\nnamespace spk::imprint::font_data {\nconst unsigned char regular[]={${regular}};\nconst unsigned char bold[]={${bold}};\nconst unsigned char mono_bold[]={${mono_bold}};\n}\n")
    add_library(spektra_spectral SHARED NativeSpectralJni.cpp ${SPEKTRA_PIPELINE}
        "${SPEKTRA_ENGINE}/src/gpu/vulkan_gpu.cpp" "${SPEKTRA_ENGINE}/third_party/volk/volk.c")
    target_compile_features(spektra_spectral PRIVATE cxx_std_20)
    target_compile_definitions(spektra_spectral PRIVATE SPK_VULKAN_BACKEND=1)
    target_include_directories(spektra_spectral PRIVATE "${SPEKTRA_ENGINE}/src" "${SPEKTRA_ENGINE}/include"
        "${SPEKTRA_ENGINE}/third_party/volk" "${CMAKE_CURRENT_BINARY_DIR}/generated")
    target_link_libraries(spektra_spectral PRIVATE spektra_android_core dl log jnigraphics)
    target_compile_options(spektra_spectral PRIVATE -O3 -fno-fast-math)
    target_compile_options(spektra_android_core PRIVATE -O3 -fno-fast-math)
endif()
