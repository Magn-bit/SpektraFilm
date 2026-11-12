package com.spektra.film

import android.content.res.AssetManager
import android.content.Context
import android.app.ActivityManager
import android.graphics.Bitmap
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.LinkedHashMap
import kotlin.math.*

data class FilmStock(
    val id:String,val name:String,val family:String,val file:String,
    val maker:String="",val type:String=family,val category:String=type,
    val description:String="",val modelStatus:String="upstream_original",
) {
    val isExtendedModel:Boolean get() = modelStatus.lowercase(java.util.Locale.ROOT) !in
        setOf("upstream_original","upstream-original","upstream","original")
    val sourceLabel:String get() = if(isExtendedModel)"扩展光谱 · 估计模型" else "上游原版 · 完整光谱"
    val makerLabel:String get() = maker.ifBlank {
        when {
            id.startsWith("fujifilm",true) || name.startsWith("Fujifilm ",true) -> "Fujifilm"
            id.startsWith("kodak",true) || name.startsWith("Kodak ",true) -> "Kodak"
            else -> "胶片档案"
        }
    }
    val shortName:String get() =
        (if(name.startsWith("$makerLabel ",true))name.substring(makerLabel.length+1) else name).trim().ifEmpty {name}
    val categoryLabel:String get() {
        val tags=listOf(type,category,family).joinToString(" ").lowercase(java.util.Locale.ROOT)
        return when {
            "cinema" in tags || "cine" in tags -> "电影负片"
            "positive" in tags || "slide" in tags || "reversal" in tags -> "反转片"
            "black" in tags || "mono" in tags || "b&w" in tags -> "黑白胶片"
            "negative" in tags -> "彩色负片"
            else -> category.ifBlank {family}
        }
    }
    companion object {
        fun fromJson(json:JSONObject):FilmStock {
            fun value(key:String)=json.optString(key,"").takeUnless {it=="null"}.orEmpty().trim()
            val type=value("type").ifBlank {value("family").ifBlank {"negative"}}
            return FilmStock(json.getString("id"),json.getString("name"),value("family").ifBlank {type},json.getString("file"),
                maker=value("maker"),type=type,category=value("category").ifBlank {type},description=value("description"),
                modelStatus=value("model_status").ifBlank {"upstream_original"})
        }
    }
}
data class Adjustments(
    val exposure: Float = 0f,
    val temperature: Float = 6500f,
    val tint: Float = 0f,
    val contrast: Float = 0f,
    val warmth: Float = 0f,
    val texture:Float=0f, val clarity:Float=0f, val dehaze:Float=0f, val shadowTint:Float=0f,
    val sharpening:Float=0f,val noiseLuminance:Float=0f,val noiseColor:Float=0f,
    val sceneLatitude:Float=0f, val halationHeadroom:Float=0f,
    val sceneLatitudeParams:String="",val meterMethod:String="balanced",
    val neutralC:Float?=null,val neutralM:Float?=null,val neutralY:Float?=null,
    val saturation: Float = 0f,
    val vibrance: Float = 0f,
    val highlights: Float = 0f,
    val shadows: Float = 0f,
    val whites:Float=0f,val blacks:Float=0f,val levels:LevelsSettings=LevelsSettings(),
    val blackPoint: Float = 0f,
    val whitePoint: Float = 100f,
    val gamma: Float = 1f,
    val redHue: Float = 0f,
    val redSaturation: Float = 0f,
    val greenHue: Float = 0f,
    val greenSaturation: Float = 0f,
    val blueHue: Float = 0f,
    val blueSaturation: Float = 0f,
    val grain: Float = .18f,
    val grainSize: Float = 1f,
    val grainType: String = "classic",
    val halation: Float = .12f,
    val vignette: Float = 0f,
    val strength: Float = 1f,
    val filmEnabled: Boolean = false,
    val paper:String="auto",
    val filmFormatMm:Float=35f,
    val printExposure:Float=0f,
    val printY:Float=0f,
    val printM:Float=0f,
    val glare:Float=0f,
    val masks: List<MaskLayer> = emptyList(),
    val curves:CurveSet=CurveSet(),
    val grading:ColorGrading=ColorGrading(),
    val geometry:Geometry=Geometry(),
    val lookLut:String="",
    val lookStrength:Float=100f,
    val hsl:HslSettings=HslSettings(),
) {
    /** One canonical state for preview, undo, persistence and final output. */
    fun filmOnly(): Adjustments {
        fun b(v:Float,d:Float,lo:Float,hi:Float)=if(v.isFinite())v.coerceIn(lo,hi) else d
        return copy(
            exposure=b(exposure,0f,-5f,5f), temperature=b(temperature,6500f,2000f,10000f),tint=b(tint,0f,-100f,100f),
            contrast=b(contrast,0f,-100f,100f),warmth=b(warmth,0f,-50f,50f),saturation=b(saturation,0f,-100f,100f),vibrance=b(vibrance,0f,-100f,100f),
            texture=b(texture,0f,-100f,100f),clarity=b(clarity,0f,-100f,100f),dehaze=b(dehaze,0f,-100f,100f),shadowTint=b(shadowTint,0f,-100f,100f),
            sharpening=b(sharpening,0f,0f,100f),noiseLuminance=b(noiseLuminance,0f,0f,100f),noiseColor=b(noiseColor,0f,0f,100f),
            sceneLatitudeParams=SceneLatitudeEdit.canonical(sceneLatitudeParams),meterMethod=meterMethod.takeIf {it in setOf("balanced","center","protect_highlights","protect_shadows")} ?: "balanced",
            neutralC=neutralC?.let {b(it,0f,0f,200f)},neutralM=neutralM?.let {b(it,0f,0f,200f)},neutralY=neutralY?.let {b(it,0f,0f,200f)},
            sceneLatitude=b(sceneLatitude,0f,0f,6f),halationHeadroom=b(halationHeadroom,0f,0f,6f),
            highlights=b(highlights,0f,-100f,100f),shadows=b(shadows,0f,-100f,100f),blackPoint=b(blackPoint,0f,0f,20f),whitePoint=b(whitePoint,100f,80f,100f),gamma=b(gamma,1f,.5f,2f),
            whites=b(whites,0f,-100f,100f),blacks=b(blacks,0f,-100f,100f),levels=LevelsSettings.fromJson(levels.toJson()),
            redHue=b(redHue,0f,-100f,100f),redSaturation=b(redSaturation,0f,-100f,100f),greenHue=b(greenHue,0f,-100f,100f),greenSaturation=b(greenSaturation,0f,-100f,100f),blueHue=b(blueHue,0f,-100f,100f),blueSaturation=b(blueSaturation,0f,-100f,100f),
            grain=b(grain,.18f,0f,1f),grainSize=b(grainSize,1f,.25f,2.5f),grainType=grainType.takeIf {it in setOf("fine","classic","coarse","clustered")} ?: "classic",
            halation=b(halation,.12f,0f,1f),vignette=b(vignette,0f,0f,1f),strength=b(strength,1f,0f,1f),
            paper=paper.takeIf {it=="auto" || it in setOf("kodak_portra_endura","kodak_endura_premier","kodak_ektacolor_edge","kodak_supra_endura","kodak_ultra_endura","fujifilm_crystal_archive_typeii","kodak_2383","kodak_2393","ilford_multigrade_iv_rc")} ?: "auto",
            filmFormatMm=b(filmFormatMm,35f,16f,120f),printExposure=b(printExposure,0f,-3f,3f),printY=b(printY,0f,-100f,100f),printM=b(printM,0f,-100f,100f),glare=b(glare,0f,0f,30f),
            geometry=Geometry.fromJson(geometry.toJson()),curves=CurveSet.fromJson(curves.toJson()),grading=ColorGrading.fromJson(grading.toJson()),hsl=HslSettings.fromJson(hsl.toJson()),
            lookStrength=b(lookStrength,100f,0f,100f),masks=masks.take(32),
        )
    }

}

/** Preview and export share the native spectral model, with separate bounded caches. */
class FilmEngine(context: Context) {
    private val appContext = context.applicationContext
    private val assets: AssetManager = appContext.assets
    private val nativePreviewDelegate=lazy { NativeSpectral(appContext) }
    private val nativePreview by nativePreviewDelegate
    private val nativeInteractiveDelegate=lazy {NativeSpectral(appContext)}
    private val nativeInteractive by nativeInteractiveDelegate
    private val nativeExportDelegate=lazy { NativeSpectral(appContext) }
    private val nativeExport by nativeExportDelegate
    internal val materials:List<PrintMaterial> by lazy {
        val rows=JSONObject(assets.open("darkroom.json").bufferedReader().use {it.readText()}).getJSONArray("papers")
        (0 until rows.length()).map {rows.getJSONObject(it).let {p->PrintMaterial(p.getString("id"),p.getString("name"),p.getString("kind"))}}
    }
    internal fun materialsFor(stock:FilmStock)=materials.filter {it.kind==if(stock.categoryLabel=="黑白胶片")"bw" else "color"}
    fun close() {if(nativeInteractiveDelegate.isInitialized())nativeInteractive.close();if(nativePreviewDelegate.isInitialized())nativePreview.close();if(nativeExportDelegate.isInitialized())nativeExport.close()}
    internal fun analyze(input:Bitmap,stock:FilmStock,a:Adjustments,target:String):JSONObject=nativePreview.analyze(input,stock,a.filmOnly(),target)
    internal fun nativeDevice()=nativeExport.device
    internal fun nativeMemoryPeak()=nativeExport.memoryPeak()
    internal fun releasePreviewMemory() {if(nativeInteractiveDelegate.isInitialized())nativeInteractive.trim();if(nativePreviewDelegate.isInitialized())nativePreview.trim()}
    internal fun releaseExportMemory() {if(nativeExportDelegate.isInitialized())nativeExport.trim()}
    internal fun spatialHalo(stock:FilmStock,a:Adjustments,width:Int,height:Int)=nativeExport.spatialHalo(stock,a.filmOnly(),width,height)
    internal fun exportTileCapacity():Long {
        val manager=appContext.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
            ?: error("无法确认原生显影可用内存；原片未缩小")
        val info=ActivityManager.MemoryInfo();manager.getMemoryInfo(info)
        check(!info.lowMemory) {"设备可用内存不足；请释放内存后重试，原片未缩小"}
        val memoryBudget=minOf((info.availMem*.60).toLong(),info.totalMem/4)
        // Covers transient float32 GPU planes, input/readback and pooled buffers;
        // Java owns only the final RGB16 core and a bounded output band.
        // Device probe measured about 73 GPU-resident + 24 host bytes/pixel.
        // 128 retains >30% variable headroom; the fixed reserve covers staging,
        // output bands and previews. It never shortens the spatial halo.
        val memoryPixels=((memoryBudget-256L*1024*1024)/128).coerceAtLeast(0)
        return minOf(nativeExport.tileCapacity(),memoryPixels)
    }
    internal fun renderFileRegion(path:String,width:Int,height:Int,stock:FilmStock,a:Adjustments,
                                  sourceWidth:Int,sourceHeight:Int,originX:Int,originY:Int,
                                  coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int,cancelled:()->Boolean):ShortArray? {
        if(cancelled())return null
        val result=nativeExport.renderFile(path,width,height,stock,a.filmOnly(),sourceWidth,sourceHeight,originX,originY,coreX,coreY,coreWidth,coreHeight)
        return if(cancelled())null else result
    }
    internal fun renderBitmapRegion(bitmap:Bitmap,stock:FilmStock,a:Adjustments,
                                    sourceWidth:Int,sourceHeight:Int,originX:Int,originY:Int,
                                    coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int,cancelled:()->Boolean):ShortArray? {
        if(cancelled())return null
        val result=nativeExport.renderBitmap(bitmap,stock,a.filmOnly(),sourceWidth,sourceHeight,originX,originY,coreX,coreY,coreWidth,coreHeight)
        return if(cancelled())null else result
    }
    fun render16(input:FloatArray,width:Int,height:Int,stock:FilmStock,adjustments:Adjustments,
                 sourceWidth:Int=width,sourceHeight:Int=height,originX:Int=0,originY:Int=0,preview:Boolean=false,
                 interactive:Boolean=false,cancelled:()->Boolean={false}):ShortArray? {
        if(cancelled())return null
        val result=(if(interactive)nativeInteractive else if(preview)nativePreview else nativeExport).render(input,width,height,stock,adjustments.filmOnly(),sourceWidth,sourceHeight,originX,originY,preview)
        return if(cancelled())null else result
    }
    val stocks: List<FilmStock>
    val size: Int
    init {
        val json = JSONObject(assets.open("luts/manifest.json").bufferedReader().use { it.readText() })
        size = json.getInt("size")
        require(size in 2..129) { "Invalid LUT size" }
        val items = json.getJSONArray("stocks")
        stocks = (0 until items.length()).map {FilmStock.fromJson(items.getJSONObject(it))}
    }
    fun render(input: Bitmap, stock: FilmStock, adjustments: Adjustments, previewMode:Boolean = false,
               sourceWidth:Int=input.width, sourceHeight:Int=input.height, seedOffset:Int=0,
               originX:Int=0, originY:Int=0,
               interactive:Boolean=false,cancelled: () -> Boolean = { false }): Bitmap? {
        val a=adjustments.filmOnly()
        if (cancelled()) return null
        val pixels=IntArray(input.width*input.height)
        input.getPixels(pixels,0,input.width,0,0,input.width,input.height)
        val linear=FloatArray(pixels.size*3)
        for(i in pixels.indices){val p=pixels[i];linear[i*3]=(p ushr 16 and 255)/255f;linear[i*3+1]=(p ushr 8 and 255)/255f;linear[i*3+2]=(p and 255)/255f}
        val rgb=render16(linear,input.width,input.height,stock,a,sourceWidth,sourceHeight,originX,originY,previewMode,interactive,cancelled) ?: return null
        for(i in pixels.indices){
            fun c(n:Int)=((rgb[n].toInt() and 65535)+128)/257
            pixels[i]=(0xff shl 24) or (c(i*3) shl 16) or (c(i*3+1) shl 8) or c(i*3+2)
        }
        val bitmap=Bitmap.createBitmap(pixels,input.width,input.height,Bitmap.Config.ARGB_8888)
        val corrected=PhotoGeometry.preview(bitmap,a.geometry)
        if(corrected!==bitmap)bitmap.recycle()
        return corrected

    }
    /** Both preview lanes use the same native model and current paper. */
    fun renderLut(input:Bitmap,stock:FilmStock,adjustments:Adjustments,originX:Int=0,originY:Int=0,
                  sourceWidth:Int=input.width,sourceHeight:Int=input.height,cancelled:()->Boolean={false}):Bitmap? =
        render(input,stock,adjustments,previewMode=true,sourceWidth=sourceWidth,sourceHeight=sourceHeight,originX=originX,originY=originY,cancelled=cancelled)
    fun renderInteractive(input:Bitmap,stock:FilmStock,adjustments:Adjustments,cacheIdentity:Bitmap=input,cancelled:()->Boolean={false}):Bitmap? =
        render(input,stock,adjustments,previewMode=true,cancelled=cancelled,interactive=true)
}
