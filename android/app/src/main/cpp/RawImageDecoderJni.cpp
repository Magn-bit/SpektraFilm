#include "RawDecoder.h"

#include <jni.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <omp.h>
#include <unistd.h>

namespace {

struct DecoderContext {
    std::atomic<bool> cancelled{false};
    std::atomic<int> progress{0};
    std::mutex stateMutex;
    bool busy = false;
    bool closed = false;
    std::string error;
};

std::mutex registryMutex;
std::unordered_map<jlong, std::shared_ptr<DecoderContext>> registry;
std::atomic<jlong> nextHandle{1};

void throwJava(JNIEnv* env, const char* type, const char* message) {
    if (env->ExceptionCheck()) return;
    jclass exception = env->FindClass(type);
    if (exception) {
        env->ThrowNew(exception, message);
        env->DeleteLocalRef(exception);
    }
}

std::shared_ptr<DecoderContext> contextFor(JNIEnv* env, jlong handle) {
    std::lock_guard<std::mutex> guard(registryMutex);
    auto it = registry.find(handle);
    if (it == registry.end()) {
        throwJava(env, "java/lang/IllegalStateException", "RAW decoder handle is closed or invalid");
        return {};
    }
    return it->second;
}

class Operation {
public:
    Operation(JNIEnv* env, const std::shared_ptr<DecoderContext>& context) : context_(context) {
        std::lock_guard<std::mutex> lock(context_->stateMutex);
        if (context_->closed) {
            throwJava(env, "java/lang/IllegalStateException", "RAW decoder handle is closed");
            return;
        }
        if (context_->busy) {
            throwJava(env, "java/lang/IllegalStateException", "RAW decoder is already processing a file");
            return;
        }
        context_->busy = true;
        context_->cancelled.store(false);
        context_->progress.store(0);
        context_->error.clear();
        active_ = true;
    }
    ~Operation() {
        if (active_) {
            std::lock_guard<std::mutex> lock(context_->stateMutex);
            context_->busy = false;
        }
    }
    bool active() const { return active_; }
private:
    std::shared_ptr<DecoderContext> context_;
    bool active_ = false;
};

class UtfPath {
public:
    UtfPath(JNIEnv* env, jstring string) : env_(env), string_(string) {
        if (!string_) {
            throwJava(env_, "java/lang/IllegalArgumentException", "RAW path must not be null");
            return;
        }
        value_ = env_->GetStringUTFChars(string_, nullptr);
    }
    ~UtfPath() {
        if (value_) env_->ReleaseStringUTFChars(string_, value_);
    }
    const char* get() const { return value_; }
private:
    JNIEnv* env_;
    jstring string_;
    const char* value_ = nullptr;
};

void recordError(const std::shared_ptr<DecoderContext>& context, const char* message) {
    std::lock_guard<std::mutex> lock(context->stateMutex);
    context->error = message;
}

void translate(JNIEnv* env, const std::shared_ptr<DecoderContext>& context,
               const spektra::RawError& error) {
    recordError(context, error.what());
    const char* type = "java/io/IOException";
    switch (error.kind) {
    case spektra::RawErrorKind::Unsupported: type = "java/lang/UnsupportedOperationException"; break;
    case spektra::RawErrorKind::Cancelled: type = "java/util/concurrent/CancellationException"; break;
    case spektra::RawErrorKind::Invalid: type = "java/lang/IllegalArgumentException"; break;
    case spektra::RawErrorKind::Memory: type = "java/lang/OutOfMemoryError"; break;
    default: break;
    }
    throwJava(env, type, error.what());
}

class JavaProgress {
public:
    JavaProgress(JNIEnv* env, jobject callback, const std::shared_ptr<DecoderContext>& context)
        : env_(env), callback_(callback), context_(context) {
        if (!callback_) return;
        jclass type = env_->GetObjectClass(callback_);
        if (!type) return;
        method_ = env_->GetMethodID(type, "onProgress", "(Ljava/lang/String;D)Z");
        env_->DeleteLocalRef(type);
    }

    bool report(const char* stage, double fraction) const {
        const int value = static_cast<int>(std::clamp(fraction, 0.0, 1.0) * 10000.0);
        context_->progress.store(value, std::memory_order_relaxed);
        if (env_->ExceptionCheck()) return false;
        if (!callback_) return !context_->cancelled.load(std::memory_order_relaxed);
        if (!method_) return false;
        jstring name = env_->NewStringUTF(stage ? stage : "RAW");
        if (!name) return false;
        const jboolean keepGoing = env_->CallBooleanMethod(callback_, method_, name, fraction);
        env_->DeleteLocalRef(name);
        if (env_->ExceptionCheck()) return false;
        return keepGoing == JNI_TRUE && !context_->cancelled.load(std::memory_order_relaxed);
    }
private:
    JNIEnv* env_;
    jobject callback_;
    jmethodID method_ = nullptr;
    std::shared_ptr<DecoderContext> context_;
};

jintArray dimensions(JNIEnv* env, const spektra::RawInfo& result, bool fullInfo) {
    const jint values[] = {result.width, result.height, result.rawWidth, result.rawHeight, result.flip};
    const jsize count = fullInfo ? 5 : 2;
    jintArray array = env->NewIntArray(count);
    if (array) env->SetIntArrayRegion(array, 0, count, values);
    return array;
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_spektra_film_RawImageDecoder_nativeCreate(JNIEnv* env, jobject) {
    try {
        auto context = std::make_shared<DecoderContext>();
        const jlong handle = nextHandle.fetch_add(1);
        std::lock_guard<std::mutex> guard(registryMutex);
        registry.emplace(handle, std::move(context));
        return handle;
    } catch (const std::bad_alloc&) {
        throwJava(env, "java/lang/OutOfMemoryError", "Cannot create native RAW decoder");
        return 0;
    }
}

extern "C" JNIEXPORT jintArray JNICALL
Java_com_spektra_film_RawImageDecoder_nativeInfo(JNIEnv* env, jobject, jlong handle, jstring path) {
    auto context = contextFor(env, handle);
    if (!context) return nullptr;
    Operation operation(env, context);
    if (!operation.active()) return nullptr;
    UtfPath source(env, path);
    if (!source.get()) return nullptr;
    JavaProgress progress(env, nullptr, context);
    try {
        const auto result = spektra::inspectRaw(source.get(), context->cancelled,
            [&progress](const char* stage, double fraction) { return progress.report(stage, fraction); });
        return dimensions(env, result, true);
    } catch (const spektra::RawError& error) {
        translate(env, context, error);
    } catch (const std::bad_alloc&) {
        recordError(context, "Insufficient memory for RAW metadata");
        throwJava(env, "java/lang/OutOfMemoryError", "Insufficient memory for RAW metadata");
    } catch (const std::exception& error) {
        recordError(context, error.what());
        throwJava(env, "java/io/IOException", error.what());
    } catch (...) {
        recordError(context, "Unexpected native RAW metadata error");
        throwJava(env, "java/io/IOException", "Unexpected native RAW metadata error");
    }
    return nullptr;
}

extern "C" JNIEXPORT jintArray JNICALL
Java_com_spektra_film_RawImageDecoder_nativeDevelop(
        JNIEnv* env, jobject, jlong handle, jstring path, jstring outputPath,
        jboolean halfSize, jobject callback) {
    auto context = contextFor(env, handle);
    if (!context) return nullptr;
    Operation operation(env, context);
    if (!operation.active()) return nullptr;
    UtfPath source(env, path);
    UtfPath output(env, outputPath);
    if (!source.get() || !output.get()) return nullptr;
    JavaProgress progress(env, callback, context);
    if (env->ExceptionCheck()) return nullptr;
    try {
        // Bound AHD's 1.6 MiB thread workspaces and leave scheduling room for
        // the UI. OpenMP thread zero owns LibRaw's Java progress callback.
        omp_set_dynamic(0);
        omp_set_num_threads(std::clamp(static_cast<int>(sysconf(_SC_NPROCESSORS_ONLN)),1,6));
        const auto result = spektra::developRaw(source.get(), output.get(), halfSize == JNI_TRUE,
            context->cancelled,
            [&progress](const char* stage, double fraction) { return progress.report(stage, fraction); });
        context->progress.store(10000);
        return dimensions(env, result, false);
    } catch (const spektra::RawError& error) {
        translate(env, context, error);
    } catch (const std::bad_alloc&) {
        recordError(context, "Insufficient memory to develop RAW image");
        throwJava(env, "java/lang/OutOfMemoryError", "Insufficient memory to develop RAW image");
    } catch (const std::exception& error) {
        recordError(context, error.what());
        throwJava(env, "java/io/IOException", error.what());
    } catch (...) {
        recordError(context, "Unexpected native RAW development error");
        throwJava(env, "java/io/IOException", "Unexpected native RAW development error");
    }
    return nullptr;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_spektra_film_RawImageDecoder_nativeProgress(JNIEnv* env, jobject, jlong handle) {
    auto context = contextFor(env, handle);
    return context ? context->progress.load(std::memory_order_relaxed) : 0;
}

extern "C" JNIEXPORT void JNICALL
Java_com_spektra_film_RawImageDecoder_nativeCancel(JNIEnv* env, jobject, jlong handle) {
    auto context = contextFor(env, handle);
    if (!context) return;
    std::lock_guard<std::mutex> lock(context->stateMutex);
    context->cancelled.store(true);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_spektra_film_RawImageDecoder_nativeClear(JNIEnv* env, jobject, jlong handle) {
    auto context = contextFor(env, handle);
    if (!context) return JNI_FALSE;
    std::lock_guard<std::mutex> lock(context->stateMutex);
    if (context->busy) return JNI_FALSE;
    context->cancelled.store(false);
    context->progress.store(0);
    context->error.clear();
    return JNI_TRUE;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_spektra_film_RawImageDecoder_nativeLastError(JNIEnv* env, jobject, jlong handle) {
    auto context = contextFor(env, handle);
    if (!context) return nullptr;
    std::lock_guard<std::mutex> lock(context->stateMutex);
    return env->NewStringUTF(context->error.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_spektra_film_RawImageDecoder_nativeClose(JNIEnv*, jobject, jlong handle) {
    std::shared_ptr<DecoderContext> context;
    {
        std::lock_guard<std::mutex> guard(registryMutex);
        auto it = registry.find(handle);
        if (it == registry.end()) return;
        context = it->second;
        registry.erase(it);
    }
    // Active operations own a shared reference. Mark cancelled without freeing
    // LibRaw from another thread; its worker unwinds and releases normally.
    std::lock_guard<std::mutex> lock(context->stateMutex);
    context->closed = true;
    context->cancelled.store(true);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_spektra_film_RawImageDecoder_nativeVersion(JNIEnv* env, jobject) {
    return env->NewStringUTF(spektra::rawVersion());
}
