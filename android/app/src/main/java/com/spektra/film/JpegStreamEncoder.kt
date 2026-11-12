package com.spektra.film

import java.io.Closeable

/** JPEG encoder; a small bounded RGB16 batch is handed to the native codec. */
internal class JpegStreamEncoder(
    path: String,
    private val width: Int,
    private val height: Int,
    quality: Int,
    profile:ByteArray?=null,
) : Closeable {
    companion object {
        init { System.loadLibrary("spektra_stream_jpeg") }
    }

    private var handle = nativeBegin(path, width, height, quality)
    private var rows = 0

    init {
        check(handle != 0L) { "无法启动 JPG 编码器" }
        if(profile!=null)try {check(nativeIcc(handle,profile)){"无法写入 JPG 色彩配置"}}
        catch(error:Throwable){close();throw error}
    }

    fun writeRow(pixels: IntArray) {
        check(handle != 0L && rows < height) { "JPEG 编码器未启动或行数超出图像高度" }
        require(pixels.size >= width)
        check(nativeWriteRow(handle, pixels)) { "JPG 行编码失败" }
        rows++
    }

    /**
     * Feeds several RGB16 rows directly to libjpeg-turbo.  The previous path
     * converted every pixel through Short -> Int ARGB -> ByteArray in Kotlin
     * and crossed JNI once per row.  Keeping the final 16->8 quantisation in
     * the native encoder preserves the exact output values while removing two
     * large temporary arrays and most JNI calls.
     */
    fun writeRows16(pixels: ShortArray, offset: Int, rowCount: Int) {
        check(handle != 0L && rows + rowCount <= height) { "JPEG 编码器未启动或行数超出图像高度" }
        require(rowCount > 0 && offset >= 0 && offset.toLong() + width.toLong() * 3 * rowCount <= pixels.size)
        check(nativeWriteRows16(handle, pixels, offset, rowCount)) { "JPG 行编码失败" }
        rows += rowCount
    }

    fun finish() {
        check(handle != 0L) { "JPEG 编码器未启动" }
        check(rows == height) { "JPG 行数不完整" }
        check(nativeFinish(handle)) { "JPG 文件未完成" }
        handle = 0L
    }

    override fun close() {
        if (handle != 0L) {
            nativeAbort(handle)
            handle = 0L
        }
    }

    private external fun nativeBegin(path: String, width: Int, height: Int, quality: Int): Long
    private external fun nativeIcc(handle:Long,profile:ByteArray):Boolean
    private external fun nativeWriteRow(handle: Long, pixels: IntArray): Boolean
    private external fun nativeWriteRows16(handle: Long, pixels: ShortArray, offset: Int, rowCount: Int): Boolean
    private external fun nativeFinish(handle: Long): Boolean
    private external fun nativeAbort(handle: Long)
}
