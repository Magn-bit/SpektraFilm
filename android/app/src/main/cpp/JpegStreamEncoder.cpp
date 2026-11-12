#include <jni.h>
#include <cstdio>
#include <jpeglib.h>
#include <cstdlib>
#include <cstring>
#include <climits>
#include <new>
#include <setjmp.h>
#include <vector>
#include <cstdint>
#include <algorithm>

struct JpegError {
    jpeg_error_mgr base;
    jmp_buf jump;
    char message[JMSG_LENGTH_MAX];
};

struct JpegContext {
    jpeg_compress_struct compressor{};
    JpegError error{};
    FILE* file = nullptr;
    bool created = false;
    int width = 0;
    int height = 0;
    std::vector<JSAMPLE> row;
    std::vector<jshort> rgb16;
    std::vector<jint> argb;
};

static void failJpeg(j_common_ptr common) {
    auto* error = reinterpret_cast<JpegError*>(common->err);
    (*common->err->format_message)(common, error->message);
    longjmp(error->jump, 1);
}

static void destroy(JpegContext* context) {
    if (!context) return;
    if (context->created) jpeg_destroy_compress(&context->compressor);
    if (context->file) fclose(context->file);
    delete context;
}

static void throwState(JNIEnv* env, const char* message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    if (type) env->ThrowNew(type, message && message[0] ? message : "JPEG 编码失败");
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeBegin(
        JNIEnv* env, jobject, jstring outputPath, jint width, jint height, jint quality) {
    if (width <= 0 || height <= 0 || width > (INT_MAX / 3)) {
        throwState(env, "无效的 JPEG 尺寸");
        return 0;
    }
    const char* path = env->GetStringUTFChars(outputPath, nullptr);
    if (!path) return 0;
    auto* context = new (std::nothrow) JpegContext();
    if (!context) {
        env->ReleaseStringUTFChars(outputPath, path);
        throwState(env, "无法创建 JPEG 编码器");
        return 0;
    }
    context->width = width;
    context->height = height;
    context->file = fopen(path, "wb");
    env->ReleaseStringUTFChars(outputPath, path);
    if (!context->file) {
        destroy(context);
        throwState(env, "无法创建 JPG 暂存文件");
        return 0;
    }
    context->compressor.err = jpeg_std_error(&context->error.base);
    context->error.base.error_exit = failJpeg;
    if (setjmp(context->error.jump)) {
        const char* message = context->error.message;
        char copy[JMSG_LENGTH_MAX];
        std::strncpy(copy, message, sizeof(copy));
        copy[sizeof(copy) - 1] = '\0';
        destroy(context);
        throwState(env, copy);
        return 0;
    }
    jpeg_create_compress(&context->compressor);
    context->created = true;
    jpeg_stdio_dest(&context->compressor, context->file);
    context->compressor.image_width = static_cast<JDIMENSION>(width);
    context->compressor.image_height = static_cast<JDIMENSION>(height);
    context->compressor.input_components = 3;
    context->compressor.in_color_space = JCS_RGB;
    jpeg_set_defaults(&context->compressor);
    jpeg_set_quality(&context->compressor, quality, TRUE);
    if (quality >= 100) {
        for (int component = 0; component < context->compressor.num_components; ++component) {
            context->compressor.comp_info[component].h_samp_factor = 1;
            context->compressor.comp_info[component].v_samp_factor = 1;
        }
    }
    // Standard Huffman tables encode the identical quantised coefficients in
    // one pass. Optimising tables requires retaining a whole image of DCT
    // blocks and doing a second entropy pass -- costly for 61-150 MP RAWs.
    // Only compressed byte size changes; quality, 4:4:4 and pixels do not.
    context->compressor.optimize_coding = FALSE;
    try {
        context->row.resize(static_cast<size_t>(width) * 3);
    } catch (const std::bad_alloc&) {
        destroy(context);
        throwState(env, "无法分配 JPG 行缓冲区");
        return 0;
    }
    jpeg_start_compress(&context->compressor, TRUE);
    return reinterpret_cast<jlong>(context);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeIcc(JNIEnv* env,jobject,jlong handle,jbyteArray profile) {
    auto* context=reinterpret_cast<JpegContext*>(handle);
    const int size=profile?env->GetArrayLength(profile):0;
    if(!context || size<128 || size>16*1024*1024 || context->compressor.next_scanline!=0) {
        throwState(env,"无效的 JPG 色彩配置或写入时机");return JNI_FALSE;
    }
    constexpr int payload=65519;
    const int count=(size+payload-1)/payload;
    if(count>255){throwState(env,"JPG 色彩配置过大");return JNI_FALSE;}
    std::vector<JOCTET> marker;
    try {marker.resize(14+std::min(size,payload));}
    catch(const std::bad_alloc&){throwState(env,"色彩配置缓冲不足");return JNI_FALSE;}
    std::memcpy(marker.data(),"ICC_PROFILE",12);
    if(setjmp(context->error.jump)){throwState(env,context->error.message);return JNI_FALSE;}
    for(int part=0;part<count;++part) {
        const int length=std::min(payload,size-part*payload);
        marker[12]=JOCTET(part+1);marker[13]=JOCTET(count);
        env->GetByteArrayRegion(profile,part*payload,length,reinterpret_cast<jbyte*>(marker.data()+14));
        if(env->ExceptionCheck())return JNI_FALSE;
        jpeg_write_marker(&context->compressor,JPEG_APP0+2,marker.data(),unsigned(length+14));
    }
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeWriteRow(
        JNIEnv* env, jobject, jlong handle, jintArray pixels) {
    auto* context = reinterpret_cast<JpegContext*>(handle);
    if (!context || !pixels || env->GetArrayLength(pixels) < context->width ||
        context->compressor.next_scanline >= static_cast<JDIMENSION>(context->height)) {
        throwState(env, "JPEG 行数据与目标尺寸不匹配");
        return JNI_FALSE;
    }
    try { context->argb.resize(size_t(context->width)); }
    catch(const std::bad_alloc&) {throwState(env,"无法分配 JPG 行缓冲区");return JNI_FALSE;}
    env->GetIntArrayRegion(pixels, 0, context->width, context->argb.data());
    if (env->ExceptionCheck()) return JNI_FALSE;
    for(int x=0;x<context->width;++x) {
        const auto p=uint32_t(context->argb[size_t(x)]);
        context->row[size_t(x)*3]=JSAMPLE(p>>16);
        context->row[size_t(x)*3+1]=JSAMPLE(p>>8);
        context->row[size_t(x)*3+2]=JSAMPLE(p);
    }
    if (setjmp(context->error.jump)) {
        char copy[JMSG_LENGTH_MAX];
        std::strncpy(copy, context->error.message, sizeof(copy));
        copy[sizeof(copy) - 1] = '\0';
        throwState(env, copy);
        return JNI_FALSE;
    }
    JSAMPROW row = context->row.data();
    if (jpeg_write_scanlines(&context->compressor, &row, 1) != 1) {
        throwState(env, "JPEG 行写入失败");
        return JNI_FALSE;
    }
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeWriteRows16(
        JNIEnv* env, jobject, jlong handle, jshortArray pixels, jint offset, jint rows) {
    auto* context = reinterpret_cast<JpegContext*>(handle);
    const int64_t samples=context ? int64_t(context->width)*3 : 0;
    if(!context || !pixels || rows<=0 || rows>32 || offset<0 ||
       int64_t(offset)+samples*rows>env->GetArrayLength(pixels) ||
       int64_t(context->compressor.next_scanline)+rows>context->height) {
        throwState(env,"JPEG 行数据与目标尺寸不匹配");return JNI_FALSE;
    }
    // Copy only this bounded batch, never GetShortArrayElements on a whole
    // output band: ART may otherwise duplicate a >100 MiB array per call.
    try {context->rgb16.resize(size_t(samples)*rows);context->row.resize(size_t(samples)*rows);}
    catch(const std::bad_alloc&) {throwState(env,"无法分配 JPG 行缓冲区");return JNI_FALSE;}
    env->GetShortArrayRegion(pixels,offset,jsize(samples*rows),context->rgb16.data());
    if(env->ExceptionCheck())return JNI_FALSE;
    for(size_t i=0;i<size_t(samples)*rows;++i)
        context->row[i]=JSAMPLE((uint32_t(uint16_t(context->rgb16[i]))+128u)/257u);
    if(setjmp(context->error.jump)) {throwState(env,context->error.message);return JNI_FALSE;}
    JSAMPROW scanlines[32];
    for(int y=0;y<rows;++y)scanlines[y]=context->row.data()+size_t(y)*size_t(samples);
    JDIMENSION written=0;
    while(written<JDIMENSION(rows)) {
        const auto count=jpeg_write_scanlines(&context->compressor,scanlines+written,JDIMENSION(rows)-written);
        if(!count){throwState(env,"JPEG 行写入失败");return JNI_FALSE;}
        written+=count;
    }
    return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeFinish(
        JNIEnv* env, jobject, jlong handle) {
    auto* context = reinterpret_cast<JpegContext*>(handle);
    if (!context) return JNI_FALSE;
    if (setjmp(context->error.jump)) {
        char copy[JMSG_LENGTH_MAX];
        std::strncpy(copy, context->error.message, sizeof(copy));
        copy[sizeof(copy) - 1] = '\0';
        throwState(env, copy);
        return JNI_FALSE;
    }
    if (context->compressor.next_scanline != static_cast<JDIMENSION>(context->height)) {
        throwState(env, "JPEG 行数不足，文件未完成");
        return JNI_FALSE;
    }
    jpeg_finish_compress(&context->compressor);
    const bool ok = fflush(context->file) == 0;
    if (!ok) { throwState(env, "无法写入完整 JPG 文件");return JNI_FALSE; }
    destroy(context);
    return ok ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT void JNICALL
Java_com_spektra_film_JpegStreamEncoder_nativeAbort(JNIEnv*, jobject, jlong handle) {
    destroy(reinterpret_cast<JpegContext*>(handle));
}
