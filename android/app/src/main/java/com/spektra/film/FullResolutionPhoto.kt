package com.spektra.film

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapRegionDecoder
import android.graphics.Rect
import android.media.ExifInterface
import android.net.Uri
import android.os.SystemClock
import android.util.Log
import java.io.Closeable
import java.io.File
import java.io.OutputStream
import java.io.BufferedOutputStream
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.sqrt
import kotlin.math.roundToInt

internal interface ExportRows16:Closeable {val outputWidth:Int;val outputHeight:Int;fun copyRow16(y:Int,destination:ShortArray,destinationOffset:Int=0);fun reportEncodedRows(rows:Int)}

internal data class SpectralTilePlan(
    val maxTilePixels: Long,
    val overlap: Int,
    val core: Int,
    // Independent maxima across rectangular bands, not one tile's dimensions.
    val tileWidth: Int,
    val bandRows: Int,
    val tileHeight: Int,
    val processedPixels: Long,
    val dispatches: Int,
)

/** Largest next core edge that fits the actual clipped halo, in source coordinates. */
internal fun spectralCoreRight(left:Int, right:Int, sourceWidth:Int, overlap:Int, tileHeight:Int, capacity:Long):Int {
    val origin=maxOf(0,left-overlap)
    val available=(capacity/tileHeight).coerceAtMost(sourceWidth.toLong()).toInt()
    val tileRight=minOf(sourceWidth.toLong(),origin.toLong()+available).toInt()
    return minOf(right,if(tileRight==sourceWidth)tileRight else tileRight-overlap)
}

// Leave room for the app's existing preview/runtime allocations, but avoid rejecting a tile
// solely because the spatial-filter halo does not fit the old fixed pixel floor.
internal fun planSpectralTiles(width: Int, height: Int, javaHeapBytes: Long, filmFormatMm:Float=35f, halation:Boolean=true,
                              requiredOverlap:Int?=null,nativeCapacity:Long?=null,
                              sourceWidth:Int=width,sourceHeight:Int=height,originX:Int=0,originY:Int=0): SpectralTilePlan {
    require(width > 0 && height > 0 && javaHeapBytes > 0)
    // CPU's former 320 bytes/pixel budget made halo overlap consume nearly
    // the whole tile. Native float32 planes are bounded separately from Java.
    val overlap = requiredOverlap ?: if(halation)ceil(65.0*sqrt(3.0)*4.0*max(width,height)/(filmFormatMm*1000.0)).toInt()+24 else 48
    val javaBudget=(javaHeapBytes*.32).toLong()
    val budget=nativeCapacity ?: (javaBudget/24).coerceIn(1_000_000L,4_000_000L)
    require(budget>=1024) {"当前设备可用内存不足，无法开始原尺寸显影；原片未缩小"}
    require(overlap>=0 && originX>=0 && originY>=0 && originX.toLong()+width<=sourceWidth && originY.toLong()+height<=sourceHeight)
    // A square assumption wastes the clipped context at image edges and cannot
    // use wider regions when Java memory limits output-band height. Evaluate
    // bounded rectangular bands against the *actual* source/crop boundaries.
    val maxBand=minOf(height,4096,(javaBudget/(width.toLong()*6)).coerceAtLeast(1).toInt())
    var best:SpectralTilePlan?=null
    var bestPixels=Long.MAX_VALUE
    var bestTiles=Int.MAX_VALUE
    val candidates=(sequenceOf(1,maxBand)+generateSequence(32){it+32}.takeWhile{it<=maxBand}).distinct()
    for(rows in candidates) {
        var processed=0L;var tiles=0;var widest=0;var tallest=0;var maxCore=0;var top=0;var valid=true
        while(top<height && valid) {
            val coreHeight=minOf(rows,height-top)
            val sy=originY+top;val oy=maxOf(0,sy-overlap)
            val tileHeight=minOf(sourceHeight,sy+coreHeight+overlap)-oy
            var left=originX
            while(left<originX+width) {
                val end=spectralCoreRight(left,originX+width,sourceWidth,overlap,tileHeight,budget)
                if(end<=left){valid=false;break}
                val tileWidth=minOf(sourceWidth,end+overlap)-maxOf(0,left-overlap)
                processed+=tileWidth.toLong()*tileHeight
                tiles++
                widest=maxOf(widest,tileWidth);tallest=maxOf(tallest,tileHeight);maxCore=maxOf(maxCore,end-left)
                left=end
            }
            top+=coreHeight
        }
        if(valid && (processed<bestPixels || processed==bestPixels && tiles<bestTiles)) {
            bestPixels=processed
            bestTiles=tiles
            best=SpectralTilePlan(budget,overlap,maxCore,widest,rows,tallest,processed,tiles)
        }
    }
    return requireNotNull(best) { "当前片幅与光晕需要的原尺寸分块超出设备内存，原片未缩小；请减小光晕或增大模拟片幅。" }
}

internal fun spectralCropRect(crop:CropBounds,width:Int,height:Int):Rect {
    fun edge(value:Float,limit:Int,fallback:Float)=(if(value.isFinite())value.coerceIn(0f,1f) else fallback).let {(it*limit).roundToInt()}
    val left=edge(crop.left,width,0f).coerceIn(0,width-1)
    val top=edge(crop.top,height,0f).coerceIn(0,height-1)
    return Rect(left,top,edge(crop.right,width,1f).coerceIn(left+1,width),edge(crop.bottom,height,1f).coerceIn(top+1,height))
}

/** Reads oriented source pixels in bounded regions; the editor's proxy is never used here. */
internal class FullResolutionPhoto(
    resolver: ContentResolver,
    uri: Uri,
    private val rawPixels: PhotoPixelSource? = null,
) : Closeable {
    companion object {
        fun open(resolver: ContentResolver, uri: Uri, name: String, cache: RawPhotoCache,
                 progress: (String, Int) -> Unit = { _, _ -> }, cancelled: () -> Boolean = { false }): FullResolutionPhoto {
            if(ExportPreset.rawExtension(name) == null)return FullResolutionPhoto(resolver, uri)
            val pixels = cache.acquire(uri, progress, cancelled)
            try { return FullResolutionPhoto(resolver, uri, pixels) } catch(error: Throwable) { pixels.close();throw error }
        }
    }
    private val stream = if(rawPixels == null) resolver.openInputStream(uri) ?: error("无法打开原始照片") else null
    private val decoder = stream?.let { input ->
        try { BitmapRegionDecoder.newInstance(input, false) ?: error("此图片格式不支持原尺寸区域解码") }
        catch(error: Throwable) { input.close();throw error }
    }
    private val rawWidth = rawPixels?.sourceWidth ?: requireNotNull(decoder).width
    private val rawHeight = rawPixels?.sourceHeight ?: requireNotNull(decoder).height
    private val orientation = if(rawPixels != null) 1 else try {
        resolver.openInputStream(uri).use { ExifInterface(requireNotNull(it)).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1) }
    } catch (_: Exception) { 1 }
    private val swapAxes = orientation in 5..8
    private val flipRawX = orientation in setOf(2, 3, 7, 8)
    private val flipRawY = orientation in setOf(3, 4, 6, 7)
    val sourceWidth = if (swapAxes) rawHeight else rawWidth
    val sourceHeight = if (swapAxes) rawWidth else rawHeight
    val width=sourceWidth
    val height=sourceHeight

    /** All recipes read the original pixel source; a smaller output is an explicit opt-in. */
    fun writeRecipe(engine:FilmEngine,stock:FilmStock,adjustments:Adjustments,target:File,recipe:OutputRecipe,
                    assets:android.content.res.AssetManager,progress:(Int)->Unit={},cancelled:()->Boolean) {
        recipe.validated();require(!recipe.raw)
        val originalRows=outputRows(engine,stock,adjustments.filmOnly(),requireNotNull(target.parentFile),progress,cancelled)
        val rows=if(recipe.longEdge>0 && recipe.longEdge<maxOf(originalRows.outputWidth,originalRows.outputHeight))
            try {ReducedExportRows(originalRows,recipe.longEdge)} catch(error:Throwable){originalRows.close();throw error}
        else originalRows
        try {
            val transform=OutputColorTransform(assets,recipe.colorSpace,recipe.format=="dng")
            val profile=if(recipe.format=="dng")null else assets.open("color/"+when(recipe.colorSpace){"Display P3"->"DisplayP3.icc";"ProPhoto RGB"->"ProPhotoRGB.icc";else->"sRGB.icc"}).use {it.readBytes()}
            val reader={y:Int,row:ShortArray->
                check(!cancelled()) {"导出已取消"};rows.copyRow16(y,row);transform.apply(row)
                if(y==0 || (y+1)%32==0 || y+1==rows.outputHeight)rows.reportEncodedRows(y+1)
            }
            when(recipe.format) {
                "jpeg"->JpegStreamEncoder(target.absolutePath,rows.outputWidth,rows.outputHeight,recipe.quality,profile).use {encoder->
                    val batchRows=8;val batch=ShortArray(rows.outputWidth*3*batchRows);var y=0
                    while(y<rows.outputHeight) {
                        check(!cancelled()) {"导出已取消"};val count=minOf(batchRows,rows.outputHeight-y)
                        for(i in 0 until count)rows.copyRow16(y+i,batch,i*rows.outputWidth*3)
                        transform.apply(batch,0,count*rows.outputWidth*3);encoder.writeRows16(batch,0,count)
                        y+=count;rows.reportEncodedRows(y)
                    }
                    encoder.finish()
                }
                "png"->FileOutputStream(target).buffered(65536).use {PngStreamEncoder.write(it,rows.outputWidth,rows.outputHeight,recipe.bitDepth,requireNotNull(profile),reader)}
                "dng"->FileOutputStream(target).buffered(65536).use {LinearDngEncoder.write(it,rows.outputWidth,rows.outputHeight,reader)}
                "tiff"->FileOutputStream(target).buffered(65536).use {out->
                    if(recipe.bitDepth==16)TiffEncoder.write16(out,rows.outputWidth,rows.outputHeight,requireNotNull(profile),target.parentFile){y,row->reader(y,row)}
                    else {
                        val row16=ShortArray(rows.outputWidth*3)
                        TiffEncoder.write(out,rows.outputWidth,rows.outputHeight,requireNotNull(profile)){y,pixels->
                            reader(y,row16)
                            for(x in pixels.indices)pixels[x]=0xff000000.toInt() or ((((row16[x*3].toInt() and 65535)+128)/257) shl 16) or ((((row16[x*3+1].toInt() and 65535)+128)/257) shl 8) or (((row16[x*3+2].toInt() and 65535)+128)/257)
                        }
                    }
                }
                else->error("不支持的输出格式")
            }
        } catch(error:Throwable){target.delete();throw error}
        finally {rows.close()}
    }

    fun writeJpeg(engine: FilmEngine, stock: FilmStock, adjustments: Adjustments, target: File, quality: Int,
                  progress: (Int) -> Unit = {}, cancelled: () -> Boolean) {
        require(quality in 1..100)
        val rows = outputRows(engine,stock,adjustments.filmOnly(),requireNotNull(target.parentFile),progress,cancelled)
        val start=SystemClock.elapsedRealtime();var encodeMs=0L
        try {
            JpegStreamEncoder(target.absolutePath, rows.outputWidth, rows.outputHeight, quality).use { encoder ->
                // Keep the Java/native boundary coarse enough for a large RAW
                // export while retaining a bounded buffer and cancellation
                // checks. RGB16 is quantised once inside libjpeg-turbo.
                val batchRows = 8
                val batch = ShortArray(rows.outputWidth * 3 * batchRows)
                var y = 0
                while (y < rows.outputHeight) {
                    val count = minOf(batchRows, rows.outputHeight - y)
                    for (index in 0 until count) rows.copyRow16(y + index, batch, index * rows.outputWidth * 3)
                    val encodeStart=SystemClock.elapsedRealtime()
                    encoder.writeRows16(batch, 0, count)
                    encodeMs+=SystemClock.elapsedRealtime()-encodeStart
                    y += count
                    if (y == count || y % 32 == 0 || y == rows.outputHeight) rows.reportEncodedRows(y)
                }
                val finishStart=SystemClock.elapsedRealtime()
                encoder.finish()
                encodeMs+=SystemClock.elapsedRealtime()-finishStart
            }
            Log.i("SpektraExport","jpeg_ms total=${SystemClock.elapsedRealtime()-start} codec=$encodeMs size=${rows.outputWidth}x${rows.outputHeight} quality=$quality bytes=${target.length()}")
        } catch(error:Throwable) {
            target.delete()
            throw error
        } finally { rows.close() }
    }

    fun writeTiff(engine: FilmEngine, stock: FilmStock, adjustments: Adjustments, target: OutputStream,
                  profile: ByteArray, workDirectory:File=File(requireNotNull(System.getProperty("java.io.tmpdir"))), progress: (Int) -> Unit = {}, cancelled: () -> Boolean) {
        val rows = outputRows(engine,stock,adjustments.filmOnly(),workDirectory,progress,cancelled)
        try {
            TiffEncoder.write16(target, rows.outputWidth, rows.outputHeight, profile) { y, row ->
                rows.copyRow16(y, row)
                if (y == 0 || (y + 1) % 32 == 0 || y + 1 == rows.outputHeight) rows.reportEncodedRows(y + 1)
            }
        } finally { rows.close() }
    }

    private fun outputRows(engine:FilmEngine,stock:FilmStock,a:Adjustments,directory:File,progress:(Int)->Unit,cancelled:()->Boolean):ExportRows16 =
        if(PhotoGeometry.requiresResample(a.geometry))CorrectedRows(engine,stock,a,directory,progress,cancelled) else SpectralRows(engine,stock,a,progress,cancelled)

    /** One final geometric resampling, streamed from full precision developed pixels. */
    private inner class CorrectedRows(engine:FilmEngine,stock:FilmStock,a:Adjustments,directory:File,
                                      private val progress:(Int)->Unit,private val cancelled:()->Boolean):ExportRows16 {
        private val frame=PhotoGeometry.frameSize(sourceWidth,sourceHeight,a.geometry)
        private val crop=spectralCropRect(a.geometry.crop,frame.first,frame.second)
        override val outputWidth=crop.width()
        override val outputHeight=crop.height()
        private val temporary:File
        private var sampler:GeometryResampler?=null
        init {
            require(directory.isDirectory || directory.mkdirs()) {"无法创建几何处理临时目录"}
            val bytes=sourceWidth.toLong()*sourceHeight*6
            require(directory.usableSpace>bytes+32L*1024*1024) {"几何处理需要约 ${bytes/(1024*1024)} MB 临时空间；原片未修改"}
            temporary=File.createTempFile("geometry-",".rgb16",directory)
            try {
                SpectralRows(engine,stock,a.copy(geometry=a.geometry.copy(crop=CropBounds())),{progress(it*80/100)},cancelled).use {source ->
                    val row=ShortArray(sourceWidth*3);val bytesRow=ByteBuffer.allocate(sourceWidth*6).order(ByteOrder.LITTLE_ENDIAN)
                    BufferedOutputStream(FileOutputStream(temporary),1024*1024).use {out ->
                        for(y in 0 until sourceHeight) {
                            check(!cancelled()) {"导出已取消"};source.copyRow16(y,row,0)
                            bytesRow.clear();bytesRow.asShortBuffer().put(row);out.write(bytesRow.array())
                            source.reportEncodedRows(y+1)
                        }
                    }
                }
                check(!cancelled()) {"导出已取消"}
                sampler=GeometryResampler(temporary.absolutePath,sourceWidth,sourceHeight,a.geometry)
            } catch(error:Throwable) {temporary.delete();throw error}
        }
        override fun copyRow16(y:Int,destination:ShortArray,destinationOffset:Int) {
            check(!cancelled()) {"导出已取消"};requireNotNull(sampler).copyRow(y,destination,destinationOffset)
        }
        override fun reportEncodedRows(rows:Int) {progress(80+(rows.toLong()*20/outputHeight).toInt())}
        override fun close() {sampler?.close();sampler=null;temporary.delete()}
    }

    private inner class SpectralRows(
        private val engine:FilmEngine,private val stock:FilmStock,adjustments:Adjustments,
        private val progress:(Int)->Unit,private val cancelled:()->Boolean,
    ):ExportRows16 {
        private val a=adjustments.filmOnly()
        private val crop=spectralCropRect(a.geometry.crop,sourceWidth,sourceHeight)
        override val outputWidth=crop.width()
        override val outputHeight=crop.height()
        private val plan=planSpectralTiles(outputWidth,outputHeight,Runtime.getRuntime().maxMemory(),a.filmFormatMm,a.halation>0,
            requiredOverlap=engine.spatialHalo(stock,a,sourceWidth,sourceHeight),nativeCapacity=engine.exportTileCapacity(),
            sourceWidth=sourceWidth,sourceHeight=sourceHeight,originX=crop.left,originY=crop.top)
        init {Log.i("SpektraExport","spectral_plan output=${outputWidth}x${outputHeight} source=${sourceWidth}x${sourceHeight} halo=${plan.overlap} band_rows=${plan.bandRows} dispatches=${plan.dispatches} work_pixels=${plan.processedPixels} tile_capacity=${plan.maxTilePixels}")}
        private var band=ShortArray(0)
        private var bandStart=-1
        private var bandHeight=0
        private var nextY=0
        private var renderedPixels=0L
        private var encodedRows=0
        private var reportedProgress=-1
        private val pixels=outputWidth.toLong()*outputHeight
        override fun copyRow16(y:Int,destination:ShortArray,destinationOffset:Int) {
            check(y==nextY && y<outputHeight && !cancelled()) { "显影已取消或行读取顺序错误" }
            if(y<bandStart || y>=bandStart+bandHeight)fillBand(y)
            System.arraycopy(band,(y-bandStart)*outputWidth*3,destination,destinationOffset,outputWidth*3);nextY++
        }
        private fun reportProgress() {
            val value=(renderedPixels*90/pixels+encodedRows.toLong()*10/outputHeight).coerceIn(0,100).toInt()
            if(value>reportedProgress){reportedProgress=value;progress(value)}
        }
        override fun reportEncodedRows(rows:Int) {encodedRows=maxOf(encodedRows,rows);reportProgress()}
        private fun fillBand(top:Int) {
            check(!cancelled()) { "显影已取消" }
            bandStart=top;bandHeight=minOf(plan.bandRows,outputHeight-top)
            if(band.size!=outputWidth*bandHeight*3)band=ShortArray(outputWidth*bandHeight*3)
            val sourceTop=crop.top+top
            val oy=maxOf(0,sourceTop-plan.overlap)
            val tileHeight=minOf(sourceHeight,sourceTop+bandHeight+plan.overlap)-oy
            var left=crop.left
            while(left<crop.right) {
                check(!cancelled()) { "显影已取消" }
                val end=spectralCoreRight(left,crop.right,sourceWidth,plan.overlap,tileHeight,plan.maxTilePixels)
                check(end>left) {"原尺寸分块计划无效"}
                val coreWidth=end-left
                val ox=maxOf(0,left-plan.overlap)
                val tileWidth=minOf(sourceWidth,end+plan.overlap)-ox
                val path=rawPixels?.nativeRgb16Path
                val result=if(path!=null)engine.renderFileRegion(path,tileWidth,tileHeight,stock,a,sourceWidth,sourceHeight,ox,oy,
                    left-ox,sourceTop-oy,coreWidth,bandHeight,cancelled)
                else {
                    val bitmap=decodeRegion(ox,oy,tileWidth,tileHeight)
                    try {engine.renderBitmapRegion(bitmap,stock,a,sourceWidth,sourceHeight,ox,oy,left-ox,sourceTop-oy,coreWidth,bandHeight,cancelled)}
                    finally {bitmap.recycle()}
                } ?: error("显影已取消")
                require(result.size==coreWidth*bandHeight*3) { "原生显影尺寸不一致" }
                for(y in 0 until bandHeight)System.arraycopy(result,y*coreWidth*3,band,(y*outputWidth+left-crop.left)*3,coreWidth*3)
                renderedPixels+=bandHeight.toLong()*coreWidth
                reportProgress();left+=coreWidth
            }
        }
        override fun close(){band=ShortArray(0);engine.releaseExportMemory()}
    }

    internal fun decodeFloatRegion(left:Int,top:Int,tileWidth:Int,tileHeight:Int):FloatArray {
        rawPixels?.let {return it.decodeFloatRegion(left,top,tileWidth,tileHeight)}
        val bitmap=decodeRegion(left,top,tileWidth,tileHeight)
        try {
            val packed=IntArray(tileWidth*tileHeight);bitmap.getPixels(packed,0,tileWidth,0,0,tileWidth,tileHeight)
            val result=FloatArray(packed.size*3)
            for(i in packed.indices) {val p=packed[i];result[i*3]=(p ushr 16 and 255)/255f;result[i*3+1]=(p ushr 8 and 255)/255f;result[i*3+2]=(p and 255)/255f}
            return result
        } finally {bitmap.recycle()}
    }

    internal fun decodeRegion(left: Int, top: Int, tileWidth: Int, tileHeight: Int): Bitmap {
        rawPixels?.let { return it.decodeRegion(left, top, tileWidth, tileHeight) }
        val outXValues = IntArray(tileWidth) { index -> reflected(left + index, sourceWidth) }
        val outYValues = IntArray(tileHeight) { index -> reflected(top + index, sourceHeight) }
        val rawXValues = if (swapAxes) outYValues else outXValues
        val rawYValues = if (swapAxes) outXValues else outYValues
        var minX = rawXValues.minOrNull()!!
        var maxX = rawXValues.maxOrNull()!!
        var minY = rawYValues.minOrNull()!!
        var maxY = rawYValues.maxOrNull()!!
        if (flipRawX) { val oldMin = minX;minX = rawWidth - 1 - maxX;maxX = rawWidth - 1 - oldMin }
        if (flipRawY) { val oldMin = minY;minY = rawHeight - 1 - maxY;maxY = rawHeight - 1 - oldMin }
        val rawRect = Rect(minX, minY, maxX + 1, maxY + 1)
        val decoded = requireNotNull(decoder).decodeRegion(rawRect, BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.ARGB_8888 })
            ?: error("无法读取原片像素区域")
        if (orientation == 1 && left >= 0 && top >= 0
            && left + tileWidth <= sourceWidth && top + tileHeight <= sourceHeight) {
            return decoded
        }
        var output: Bitmap? = null
        try {
            val rawPixels = IntArray(decoded.width * decoded.height)
            decoded.getPixels(rawPixels, 0, decoded.width, 0, 0, decoded.width, decoded.height)
            output = Bitmap.createBitmap(tileWidth, tileHeight, Bitmap.Config.ARGB_8888)
            val oriented = IntArray(tileWidth)
            for (y in 0 until tileHeight) {
                val outY = reflected(top + y, sourceHeight)
                for (x in 0 until tileWidth) {
                    val outX = reflected(left + x, sourceWidth)
                    var rawX = if (swapAxes) outY else outX
                    var rawY = if (swapAxes) outX else outY
                    if (flipRawX) rawX = rawWidth - 1 - rawX
                    if (flipRawY) rawY = rawHeight - 1 - rawY
                    oriented[x] = rawPixels[(rawY - rawRect.top) * decoded.width + rawX - rawRect.left]
                }
                output.setPixels(oriented, 0, tileWidth, 0, y, tileWidth, 1)
            }
            return output
        } catch (error: Throwable) {
            output?.recycle()
            throw error
        } finally { decoded.recycle() }
    }

    private fun reflected(value: Int, size: Int): Int {
        if (size <= 1) return 0
        val period = 2 * (size - 1)
        val folded = ((value % period) + period) % period
        return if (folded < size) folded else period - folded
    }

    override fun close() {
        rawPixels?.close()
        decoder?.recycle()
        stream?.close()
    }
}
