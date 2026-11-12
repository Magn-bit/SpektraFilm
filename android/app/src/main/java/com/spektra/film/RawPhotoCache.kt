package com.spektra.film

import android.app.ActivityManager
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.util.UUID
import java.util.concurrent.CancellationException
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import kotlin.math.max
import kotlin.math.roundToInt

/** Readers own a lease so LRU cleanup cannot remove pixels while an export is using them. */
internal interface PhotoPixelSource : Closeable {
    val sourceWidth: Int
    val sourceHeight: Int
    val nativeRgb16Path:String? get()=null
    fun decodeRegion(left: Int, top: Int, width: Int, height: Int): Bitmap
    fun decodeFloatRegion(left:Int,top:Int,width:Int,height:Int):FloatArray
}

internal data class RawMemoryAdmission(val estimatedPeakBytes: Long, val budgetBytes: Long)
internal data class RawPhotoPreview(val bitmap: Bitmap, val sourceWidth: Int, val sourceHeight: Int)

private const val RAW_MEMORY_FAILURE = "当前设备可用内存不足，或无法安全确认 RAW 完整显影所需内存；请释放内存后重试。原片未缩小、未修改，可选择 RAW 原片另存。"

/** Pure admission policy: sensor buffers use native memory, so Java maxMemory is not a budget. */
internal fun rawMemoryAdmission(rawWidth: Long, rawHeight: Long, availableBytes: Long,
                                totalBytes: Long, lowMemory: Boolean): RawMemoryAdmission {
    check(!lowMemory && rawWidth > 0 && rawHeight > 0 && availableBytes > 0 && totalBytes > 0 && availableBytes <= totalBytes) { RAW_MEMORY_FAILURE }
    val estimated = try {
        val rawPixels = Math.multiplyExact(rawWidth, rawHeight)
        val nativePeak = Math.addExact(Math.multiplyExact(rawPixels, 12L), 96L * 1024 * 1024)
        // Keep separate room for the editor's previews and the native colour pipeline.
        Math.addExact(nativePeak, (64L + 128L) * 1024 * 1024)
    } catch (error: ArithmeticException) { throw IllegalStateException(RAW_MEMORY_FAILURE, error) }
    // floor(available * .60), without overflowing when memory metrics are synthetic Long values.
    val availableBudget = (availableBytes / 5) * 3 + (availableBytes % 5) * 3 / 5
    val budget = minOf(availableBudget, totalBytes / 4)
    check(estimated <= budget) { RAW_MEMORY_FAILURE }
    return RawMemoryAdmission(estimated, budget)
}

/** Bounds disk use to 1.5 GiB per active editor; no source copy survives a decode. */
internal class RawPhotoCache(context: Context) : Closeable {
    companion object {
        private const val MAX_BYTES = 1536L * 1024 * 1024
        private const val MAX_SOURCE_BYTES = 512L * 1024 * 1024
        private const val MAX_OUTPUT_BYTES = 1024L * 1024 * 1024
        private const val DISK_RESERVE = 64L * 1024 * 1024
        private val activeDirectories = mutableSetOf<String>()
    }
    private val resolver = context.applicationContext.contentResolver
    private val preferences=context.applicationContext.getSharedPreferences("atelier",Context.MODE_PRIVATE)
    private val budgetBytes:Long get()=preferences.getInt("raw-cache-mb",1536).coerceIn(512,4096)*1024L*1024L
    private val activityManager = try {
        context.applicationContext.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
    } catch (_: RuntimeException) { null }
    private val directory: File
    private data class Entry(val key: String, val uri: Uri, val file: File, val width: Int, val height: Int,
                             val originalWidth: Int, val originalHeight: Int,
                             var readers: Int = 0, var discarded: Boolean = false)
    private data class PixelLease(val pixels: PhotoPixelSource, val originalWidth: Int, val originalHeight: Int)
    private val entries = linkedMapOf<String, Entry>()
    private var activeLeases = 0
    private val buildLock = ReentrantLock()
    @Volatile private var closed = false
    @Volatile private var activeDecoder: RawImageDecoder.Session? = null

    init {
        // v2 changes RAW highlight handling and histogram-derived sRGB white.
        // Never reuse RGB16 pixels developed with the old dark transfer curve.
        val root = File(context.cacheDir, "raw-develop-v2-blend-auto-white")
        synchronized(activeDirectories) {
            check(root.exists() || root.mkdirs()) { "无法建立 RAW 临时目录" }
            // Process-local owners protect overlapping Activities; files left by a killed process are disposable.
            root.listFiles()?.filter { it.isDirectory && it.absolutePath !in activeDirectories }?.forEach { it.deleteRecursively() }
            directory = File(root, UUID.randomUUID().toString())
            check(directory.mkdir()) { "无法建立 RAW 显影缓存" }
            activeDirectories.add(directory.absolutePath)
        }
    }

    /** Full export only looks up the full key and always develops with halfSize=false. */
    fun acquire(uri: Uri, progress: (String, Int) -> Unit = { _, _ -> }, cancelled: () -> Boolean = { false }): PhotoPixelSource =
        acquirePixels(uri, false, progress, cancelled).pixels

    /** Editing can use fewer pixels while retaining the original's complete oriented dimensions. */
    fun preview(uri: Uri, edge: (Int, Int) -> Int, progress: (String, Int) -> Unit = { _, _ -> },
                cancelled: () -> Boolean = { false }): RawPhotoPreview {
        val readyFull = synchronized(this) { if (closed) null else cached(uri, false)?.let { pixelLease(it) } }
        val reader = readyFull ?: acquirePixels(uri, true, progress, cancelled)
        return reader.pixels.use { pixels ->
            RawPhotoPreview(pixels.preview(edge(reader.originalWidth, reader.originalHeight), cancelled),
                            reader.originalWidth, reader.originalHeight)
        }
    }

    private fun acquirePixels(uri: Uri, halfSize: Boolean, progress: (String, Int) -> Unit,
                              cancelled: () -> Boolean): PixelLease {
        fun checkActive() { if (closed || cancelled() || Thread.currentThread().isInterrupted) throw CancellationException("RAW 显影已取消") }
        checkActive()
        synchronized(this) { cached(uri, halfSize)?.let { return pixelLease(it) } }
        while (!buildLock.tryLock(100, TimeUnit.MILLISECONDS)) checkActive()
        var source: File? = null
        var output: File? = null
        try {
            checkActive()
            synchronized(this) { cached(uri, halfSize)?.let { return pixelLease(it) };makeRoom(0) }
            source = File.createTempFile("source-", ".raw", directory)
            val sourceFile = source
            progress("正在读取 RAW 原片", 0)
            resolver.openInputStream(uri).use { input ->
                requireNotNull(input) { "无法打开 RAW 原片" }
                FileOutputStream(sourceFile).use { stream ->
                    val buffer = ByteArray(1024 * 1024)
                    var copied = 0L
                    while (true) {
                        checkActive()
                        val count = input.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        copied += count
                        require(copied <= MAX_SOURCE_BYTES) { "RAW 原片超过本机临时处理上限（512 MiB）；原片未修改" }
                        synchronized(this) { makeRoom(count.toLong()) }
                        stream.write(buffer, 0, count)
                    }
                    require(copied > 0) { "RAW 原片为空" }
                }
            }
            checkActive()
            val decoder = try { RawImageDecoder.Session() } catch (error: LinkageError) {
                throw IllegalStateException("本机 RAW 显影组件未安装或无法加载；可选择 RAW 原片另存", error)
            }
            activeDecoder = decoder
            decoder.use {
                val info = decoder.info(sourceFile.absolutePath)
                require(info.size >= 2 && info[0] > 0 && info[1] > 0) { "RAW 元数据未提供有效全尺寸" }
                // Native info is the complete oriented image size, without DNG DefaultCrop.
                val expectedWidth = info[0];val expectedHeight = info[1]
                // For linear/rotated RAW, LibRaw may retain more than half the dimensions.
                // Reserve full output space; only actual decoded dimensions describe a proxy.
                val expectedBytes = rgb16Bytes(expectedWidth, expectedHeight)
                require(expectedBytes <= MAX_OUTPUT_BYTES) { "RAW 完整像素缓存超过本机处理上限（1 GiB）；原片未缩小" }
                synchronized(this) { makeRoom(expectedBytes) }
                checkActive()
                check(info.size >= 4) { RAW_MEMORY_FAILURE }
                val memory = ActivityManager.MemoryInfo()
                try {
                    val manager = activityManager ?: throw IllegalStateException(RAW_MEMORY_FAILURE)
                    manager.getMemoryInfo(memory)
                } catch (error: RuntimeException) { throw IllegalStateException(RAW_MEMORY_FAILURE, error) }
                rawMemoryAdmission(info[2].toLong(), info[3].toLong(), memory.availMem, memory.totalMem, memory.lowMemory)
                checkActive()
                output = File.createTempFile("pixels-", ".rgb16le", directory)
                val pixels = requireNotNull(output)
                var lastStage = "";var lastPercent = -1
                val callback = RawImageDecoder.ProgressCallback { stage, fraction ->
                    if (closed || cancelled() || Thread.currentThread().isInterrupted) false
                    else {
                        val percent = (fraction.coerceIn(0.0, 1.0) * 100).roundToInt()
                        if(stage != lastStage || percent != lastPercent) { lastStage=stage;lastPercent=percent;progress(stage,percent) }
                        true
                    }
                }
                val size = if (halfSize) decoder.developPreview(sourceFile.absolutePath, pixels.absolutePath, callback)
                           else decoder.develop(sourceFile.absolutePath, pixels.absolutePath, callback)
                checkActive()
                if (halfSize) requireRawPreviewOutput(expectedWidth, expectedHeight, size, pixels.length())
                else requireFullRawOutput(expectedWidth, expectedHeight, size, pixels.length())
                synchronized(this) {
                    checkActive()
                    makeRoom(0)
                    val key = rawCacheKey(uri.toString(), halfSize)
                    val entry = Entry(key, uri, pixels, size[0], size[1], expectedWidth, expectedHeight)
                    entries[key] = entry
                    val result = pixelLease(entry)
                    output = null
                    progress(if (halfSize) "RAW 预览就绪" else "RAW 全尺寸显影完成", 100)
                    return result
                }
            }
        } finally {
            activeDecoder = null
            source?.delete();output?.delete()
            buildLock.unlock()
            synchronized(this) { if (closed) removeIdle() }
        }
    }

    /** Browser thumbnails reuse developed pixels, but never start background RAW jobs. */
    fun cachedPreview(uri: Uri, edge: Int): Bitmap? {
        val reader = synchronized(this) { if (closed) null else (cached(uri, false) ?: cached(uri, true))?.let { lease(it) } } ?: return null
        return reader.use { it.preview(edge) }
    }

    @Synchronized fun discard(uri: Uri) {
        entries.values.filter { it.uri == uri }.toList().forEach { entry ->
            entry.discarded = true
            if (entry.readers == 0) { entry.file.delete();entries.remove(entry.key) }
        }
    }
    fun cancelActive() { activeDecoder?.cancel() }

    private fun cached(uri: Uri, halfSize: Boolean): Entry? {
        val key = rawCacheKey(uri.toString(), halfSize)
        val entry = entries[key] ?: return null
        if (entry.discarded || !entry.file.isFile || entry.file.length() != rgb16Bytes(entry.width, entry.height)) {
            entry.discarded=true
            if(entry.readers==0) {entry.file.delete();entries.remove(key)}
            return null
        }
        entries.remove(key);entries[key] = entry
        return entry
    }
    private fun pixelLease(entry: Entry) = PixelLease(lease(entry), entry.originalWidth, entry.originalHeight)
    private fun lease(entry: Entry): PhotoPixelSource {
        val reader = Rgb16PixelSource(entry.file, entry.width, entry.height) {
            synchronized(this) { entry.readers--;activeLeases--;if (entry.discarded || closed) { if (entry.readers == 0) { entry.file.delete();if(entries[entry.key] === entry)entries.remove(entry.key) } };if(closed)removeIdle() }
        }
        entry.readers++
        activeLeases++
        return reader
    }
    private fun makeRoom(additional: Long) {
        fun used() = directory.listFiles()?.sumOf { it.length() } ?: 0L
        val candidates = entries.values.filter { it.readers == 0 }.toList()
        for (entry in candidates) {
            if (used() + additional <= budgetBytes && directory.usableSpace >= additional + DISK_RESERVE && entries.size < 3) break
            entry.file.delete();entries.remove(entry.key)
        }
        require(used() + additional <= budgetBytes && directory.usableSpace >= additional + DISK_RESERVE) {
            "RAW 全尺寸显影所需临时空间不足，请释放存储空间后重试；原片未缩小、未修改"
        }
    }
    @Synchronized fun trimIdle(all:Boolean=false) {
        if(closed)return
        if(all)entries.values.filter {it.readers==0}.toList().forEach {it.file.delete();entries.remove(it.key)}
        else makeRoom(0)
    }
    private fun removeIdle() {
        entries.values.filter { it.readers == 0 }.toList().forEach { it.file.delete();entries.remove(it.key) }
        if (entries.isEmpty() && activeLeases == 0 && !buildLock.isLocked) {
            directory.deleteRecursively()
            synchronized(activeDirectories) { activeDirectories.remove(directory.absolutePath) }
        }
    }
    override fun close() {
        synchronized(this) { closed = true;entries.values.forEach { it.discarded = true };removeIdle() }
        activeDecoder?.cancel()
    }
}

/** Full and preview entries can never alias, even for the same original URI. */
internal fun rawCacheKey(uri: String, preview: Boolean) = (if (preview) "preview:" else "full:") + uri

internal fun requireRawPreviewOutput(originalWidth: Int, originalHeight: Int, size: IntArray, actualBytes: Long) {
    require(size.size >= 2 && size[0] in 1..originalWidth && size[1] in 1..originalHeight &&
            actualBytes == rgb16Bytes(size[0], size[1])) { "RAW 预览像素缓存或尺寸错误" }
}

internal fun rgb16Bytes(width: Int, height: Int): Long {
    require(width in 1..100_000 && height in 1..100_000 && width.toLong() * height <= Int.MAX_VALUE) { "RAW 全尺寸超出本机像素上限" }
    return width.toLong() * height * 6L
}

/** A self-consistent thumbnail or half-size buffer is still an invalid complete RAW decode. */
internal fun requireFullRawOutput(expectedWidth: Int, expectedHeight: Int, decodedSize: IntArray, actualBytes: Long) {
    val expectedBytes = rgb16Bytes(expectedWidth, expectedHeight)
    require(decodedSize.size >= 2 && decodedSize[0] == expectedWidth && decodedSize[1] == expectedHeight && actualBytes == expectedBytes) {
        "RAW 显影尺寸或像素缓存与完整原片不一致（期望 $expectedWidth × $expectedHeight，$expectedBytes 字节）；拒绝缩小、裁切或缩略图输出。原片未修改，可选择 RAW 原片另存。"
    }
}

/** Export reads all sixteen source bits; only display previews use Bitmap8. */
internal class Rgb16PixelSource(private val file: File, override val sourceWidth: Int, override val sourceHeight: Int,
                                private val released: () -> Unit = {}) : PhotoPixelSource {
    private val input = RandomAccessFile(file, "r")
    private var closed = false
    override val nativeRgb16Path:String get() {check(!closed);return file.absolutePath}
    init { try { require(input.length() == rgb16Bytes(sourceWidth, sourceHeight)) { "RAW 像素缓存长度错误" } } catch(error: Throwable) { input.close();throw error } }
    @Synchronized override fun decodeFloatRegion(left:Int,top:Int,width:Int,height:Int):FloatArray {
        check(!closed);require(width>0 && height>0)
        val xs=IntArray(width){reflectPixel(left.toLong()+it,sourceWidth)}
        val minX=xs.minOrNull()!!;val maxX=xs.maxOrNull()!!
        val bytes=ByteArray((maxX-minX+1)*6);val result=FloatArray(width*height*3)
        for(y in 0 until height) {
            if(Thread.currentThread().isInterrupted)throw CancellationException("RAW 读取已取消")
            input.seek((reflectPixel(top.toLong()+y,sourceHeight).toLong()*sourceWidth+minX)*6);input.readFully(bytes)
            for(x in 0 until width)for(c in 0..2) {
                val i=(xs[x]-minX)*6+c*2
                result[(y*width+x)*3+c]=((bytes[i].toInt() and 255) or ((bytes[i+1].toInt() and 255) shl 8))/65535f
            }
        }
        return result
    }
    @Synchronized override fun decodeRegion(left: Int, top: Int, width: Int, height: Int): Bitmap {
        check(!closed) { "RAW 像素缓存已关闭" }
        require(width > 0 && height > 0)
        val xs = IntArray(width) { reflectPixel(left.toLong() + it, sourceWidth) }
        val minX = xs.minOrNull()!!;val maxX = xs.maxOrNull()!!
        val bytes = ByteArray((maxX - minX + 1) * 6)
        val row = IntArray(width)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        try {
            for (y in 0 until height) {
                if(Thread.currentThread().isInterrupted)throw CancellationException("RAW 读取已取消")
                val sourceY = reflectPixel(top.toLong() + y, sourceHeight)
                input.seek((sourceY.toLong() * sourceWidth + minX) * 6)
                input.readFully(bytes)
                for (x in xs.indices) row[x] = rgb16Color(bytes, (xs[x] - minX) * 6)
                bitmap.setPixels(row, 0, width, 0, y, width, 1)
            }
            return bitmap
        } catch(error: Throwable) { bitmap.recycle();throw error }
    }
    @Synchronized fun preview(maxEdge: Int, cancelled: () -> Boolean = { false }): Bitmap {
        check(!closed)
        require(maxEdge > 0)
        val scale = minOf(1.0, maxEdge.toDouble() / max(sourceWidth, sourceHeight))
        val width = max(1, (sourceWidth * scale).roundToInt());val height = max(1, (sourceHeight * scale).roundToInt())
        val bytes = ByteArray(sourceWidth * 6);val row = IntArray(width)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        try {
            for (y in 0 until height) {
                if(cancelled() || Thread.currentThread().isInterrupted)throw CancellationException("RAW 预览已取消")
                val sy = ((y + .5) * sourceHeight / height).toInt().coerceAtMost(sourceHeight - 1)
                input.seek(sy.toLong() * sourceWidth * 6);input.readFully(bytes)
                for (x in 0 until width) { val sx = ((x + .5) * sourceWidth / width).toInt().coerceAtMost(sourceWidth - 1);row[x] = rgb16Color(bytes, sx * 6) }
                bitmap.setPixels(row, 0, width, 0, y, width, 1)
            }
            return bitmap
        } catch(error: Throwable) { bitmap.recycle();throw error }
    }
    @Synchronized override fun close() { if(!closed) { closed=true;try { input.close() } finally { released() } } }
}

private fun rgb16Color(bytes: ByteArray, offset: Int): Int {
    fun channel(i: Int): Int = (((bytes[i].toInt() and 255) or ((bytes[i + 1].toInt() and 255) shl 8)) + 128) / 257
    return (0xff shl 24) or (channel(offset) shl 16) or (channel(offset + 2) shl 8) or channel(offset + 4)
}
internal fun reflectPixel(value: Long, size: Int): Int {
    if(size <= 1)return 0
    val period = 2L * (size - 1);val folded = ((value % period) + period) % period
    return (if(folded < size) folded else period - folded).toInt()
}
internal fun PhotoPixelSource.preview(maxEdge: Int, cancelled: () -> Boolean = { false }): Bitmap {
    if(this is Rgb16PixelSource)return preview(maxEdge, cancelled)
    throw UnsupportedOperationException("仅 RAW 像素缓存支持此预览入口")
}
