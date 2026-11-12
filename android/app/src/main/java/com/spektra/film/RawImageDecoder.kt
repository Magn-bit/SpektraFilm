package com.spektra.film

import java.io.Closeable
import java.util.concurrent.CancellationException

/** LibRaw runs locally; both full and preview results are developed sRGB RGB16LE, never embedded JPEGs. */
internal object RawImageDecoder {
    init { System.loadLibrary("spektra_raw") }

    fun interface ProgressCallback {
        /** Return false to cancel the native operation. */
        fun onProgress(stage: String, fraction: Double): Boolean
    }

    class Session : Closeable {
        private val handle = nativeCreate().also { check(it != 0L) { "无法创建 RAW 解码器" } }
        @Volatile private var closed = false
        fun info(path: String): IntArray { check(!closed);return nativeInfo(handle, path) }
        fun develop(path: String, output: String, callback: ProgressCallback): IntArray {
            if (closed) throw CancellationException("RAW 显影已取消")
            return nativeDevelop(handle, path, output, false, callback)
        }
        fun developPreview(path: String, output: String, callback: ProgressCallback): IntArray {
            if (closed) throw CancellationException("RAW 预览已取消")
            return nativeDevelop(handle, path, output, true, callback)
        }
        @Synchronized fun cancel() { if (!closed) nativeCancel(handle) }
        @Synchronized override fun close() { if (!closed) { closed = true;nativeClose(handle) } }
    }

    @JvmStatic external fun nativeCreate(): Long
    @JvmStatic external fun nativeInfo(handle: Long, sourcePath: String): IntArray
    @JvmStatic external fun nativeDevelop(handle: Long, sourcePath: String, rgb16Path: String, halfSize: Boolean, callback: ProgressCallback?): IntArray
    @JvmStatic external fun nativeProgress(handle: Long): Int
    @JvmStatic external fun nativeCancel(handle: Long)
    @JvmStatic external fun nativeClear(handle: Long): Boolean
    @JvmStatic external fun nativeLastError(handle: Long): String
    @JvmStatic external fun nativeClose(handle: Long)
    @JvmStatic external fun nativeVersion(): String
}
