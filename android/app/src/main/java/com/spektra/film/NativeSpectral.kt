package com.spektra.film

import android.content.Context
import android.graphics.Bitmap
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import kotlin.math.pow

/** Complete float32 spectral development; RGB16 is quantized only after scanning. */
internal class NativeSpectral(context: Context) : Closeable {
    companion object {
        init { System.loadLibrary("spektra_spectral") }
        private val extractionLock=Any()
        private fun resources(context:Context):File=synchronized(extractionLock) {
            val root=File(context.filesDir,"native-spectral-040")
            val stamp=context.packageManager.getPackageInfo(context.packageName,0).lastUpdateTime.toString()
            val marker=File(root,".complete")
            if(!marker.exists() || marker.readText()!=stamp) {
                root.mkdirs()
                fun extract(path:String) {
                    val children=context.assets.list("native_engine/$path").orEmpty()
                    if(children.isNotEmpty()) children.forEach {extract(if(path.isEmpty())it else "$path/$it")}
                    else {
                        val target=File(root,path);target.parentFile?.mkdirs()
                        context.assets.open("native_engine/$path").use {source->target.outputStream().use {source.copyTo(it)}}
                    }
                }
                extract("");marker.writeText(stamp)
            }
            root
        }
    }
    private val root=resources(context.applicationContext)
    private val extensions=JSONObject(File(root,"profile_extensions.json").readText()).getJSONObject("profiles")
    private val neutral=JSONObject(File(root,"neutral_print_filters.json").readText())
    private val handle=nativeCreate(root.absolutePath).also {check(it!=0L)}
    val device:String get()=nativeDevice(handle)
    private val targetPapers=mutableMapOf<String,String>()
    private var closed=false
    @Synchronized fun render(input:FloatArray,width:Int,height:Int,stock:FilmStock,a:Adjustments,
                             sourceWidth:Int=width,sourceHeight:Int=height,originX:Int=0,originY:Int=0,preview:Boolean=false):ShortArray {
        check(!closed)
        val request=parameters(stock,a)
        return nativeRender(handle,input,width,height,request.first,request.second,a.strength,a.vignette,originX,originY,sourceWidth,sourceHeight,preview)
    }
    @Synchronized fun renderFile(path:String,width:Int,height:Int,stock:FilmStock,a:Adjustments,
                                 sourceWidth:Int,sourceHeight:Int,originX:Int,originY:Int,
                                 coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int):ShortArray {
        check(!closed)
        val request=parameters(stock,a)
        return nativeRenderFile(handle,path,width,height,request.first,request.second,a.strength,a.vignette,originX,originY,sourceWidth,sourceHeight,coreX,coreY,coreWidth,coreHeight)
    }
    @Synchronized fun renderBitmap(bitmap:Bitmap,stock:FilmStock,a:Adjustments,
                                   sourceWidth:Int,sourceHeight:Int,originX:Int,originY:Int,
                                   coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int):ShortArray {
        check(!closed)
        val request=parameters(stock,a)
        return nativeRenderBitmap(handle,bitmap,bitmap.width,bitmap.height,request.first,request.second,a.strength,a.vignette,originX,originY,sourceWidth,sourceHeight,coreX,coreY,coreWidth,coreHeight)
    }
    @Synchronized fun analyze(input:Bitmap,stock:FilmStock,a:Adjustments,target:String):JSONObject {
        check(!closed)
        return JSONObject(nativeAnalyze(handle,input,parameters(stock,a).first,target,"{}"))
    }
    @Synchronized fun spatialHalo(stock:FilmStock,a:Adjustments,width:Int,height:Int):Int {
        check(!closed)
        val spectral=if(a.filmEnabled)nativeTileHalo(handle,parameters(stock,a).first,width,height) else 0
        val restoration=if(a.sharpening>0 || a.noiseLuminance>0 || a.noiseColor>0)5 else 0
        val detail=if(a.texture!=0f || a.clarity!=0f)64 else 0
        // Capture restoration, film optics, and post detail run serially: their context adds.
        return maxOf(1,spectral+restoration+detail)
    }
    fun tileCapacity():Long=11_000_000L // RGB32 plane fits Vulkan's guaranteed 128 MiB storage range.
    @Synchronized fun memoryPeak():LongArray {check(!closed);return nativeMemoryPeak(handle)}
    @Synchronized fun trim() {if(!closed)nativeTrim(handle)}
    private fun parameters(stock:FilmStock,a:Adjustments):Pair<String,String> {
        val extra=extensions.optJSONObject(stock.id)
        val paper=if(a.paper=="auto" && stock.categoryLabel!="黑白胶片") {
            extra?.optString("paper")?.takeIf {it.isNotBlank()} ?:
                targetPapers.getOrPut(stock.id) {JSONObject(File(root,"profiles/${stock.id}.json").readText()).getJSONObject("info").optString("target_print").takeIf {it.isNotBlank() && it!="null"} ?: "kodak_portra_endura"}
        } else resolvePaper(stock,a.paper)
        var light="TH-KG3"
        var filters=neutral.optJSONObject(paper)?.optJSONObject(light)?.optJSONArray(stock.id)
        if(extra?.optString("paper")==paper && !extra.isNull("neutral_filters_cmy")) {
            filters=extra.getJSONArray("neutral_filters_cmy");light=extra.getString("illuminant")
        }
        // Keep strength, morphology and physical granularity independent;
        // the density-domain kernel uses a shared neutral random field.
        val kind=when(a.grainType){"fine"->floatArrayOf(1f,.42f,2.2f);"coarse"->floatArrayOf(3f,2.1f,6f);"clustered"->floatArrayOf(4f,1.35f,4.5f);else->floatArrayOf(2f,1f,4f)}
        val black=stock.categoryLabel=="黑白胶片"
        val p=JSONObject().apply {
            put("film_stock",stock.id);put("print_stock",paper);put("editor_settings",a.nativeEditorSettings());put("editor_film_enabled",a.filmEnabled);put("editor_capture_active",a.hasCaptureEdits());put("editor_post_active",a.hasPostEdits());put("editor_active",a.hasCaptureEdits() || a.hasPostEdits() || a.exposure!=0f)
            put("input_color_space","sRGB");put("input_cctf_decoding",true);put("output_color_space","sRGB");put("output_cctf_encoding",true)
            put("auto_exposure",false);put("auto_exposure_method",a.meterMethod);put("exposure_baseline_ev",0);put("exposure_compensation_ev",a.exposure)
            put("film_format_mm",a.filmFormatMm);put("scan_film",stock.categoryLabel=="反转片")
            put("grain_active",a.grain>0);put("grain_sublayers_active",true);put("grain_amount",a.grain*2)
            put("grain_particle_area_um2",maxOf(.000001,.8*a.grainSize.pow(2)*kind[1]))
            put("grain_texture",kind[0].toInt());put("grain_texture_scale_um",kind[2]*a.grainSize)
            put("grain_uniformity_r",.992);put("grain_uniformity_g",.992);put("grain_uniformity_b",.992);put("grain_blur",0);put("grain_cloud_blur_um",0)
            put("halation_active",a.halation>0);put("halation_amount",a.halation*4);put("halation_scatter_amount",minOf(1f,a.halation*4));put("halation_headroom_ev",a.halationHeadroom)
            put("dir_couplers_active",!black && extra==null);put("neutral_filters_from_database",false)
            put("c_filter_neutral",if(black)0.0 else a.neutralC?.toDouble() ?: filters?.optDouble(0) ?: 0.0)
            put("m_filter_neutral",if(black)0.0 else a.neutralM?.toDouble() ?: filters?.optDouble(1) ?: 65.0)
            put("y_filter_neutral",if(black)68.0 else a.neutralY?.toDouble() ?: filters?.optDouble(2) ?: 55.0);put("enlarger_illuminant",light)
            put("print_exposure",2.0.pow(a.printExposure.toDouble()));put("m_filter_shift",a.printM/100);put("y_filter_shift",a.printY/100);put("filter_shift_scale",60)
            put("glare_active",a.glare>0);put("glare_amount",1);put("glare_percent",a.glare)
            put("scanner_white_correction",false);put("scanner_black_correction",false)
            if(a.sceneLatitudeParams.isNotBlank())JSONObject(a.sceneLatitudeParams).let {j ->j.keys().forEach {key ->put(key,j.get(key))}}
        }
        val shoot=JSONObject(p.toString()).apply {listOf("editor_settings","editor_film_enabled","editor_capture_active","editor_post_active","editor_active","print_stock","print_exposure","m_filter_shift","y_filter_shift","filter_shift_scale","glare_active","glare_amount","glare_percent","c_filter_neutral","m_filter_neutral","y_filter_neutral","enlarger_illuminant").forEach {remove(it)}}
        return p.toString() to shoot.toString()
    }
    override fun close()=synchronized(this) {if(!closed){closed=true;nativeClose(handle)}}
    private external fun nativeAnalyze(handle:Long,input:Bitmap,parameters:String,target:String,request:String):String
    private external fun nativeCreate(root:String):Long
    private external fun nativeRender(handle:Long,input:FloatArray,width:Int,height:Int,parameters:String,shoot:String,strength:Float,vignette:Float,originX:Int,originY:Int,sourceWidth:Int,sourceHeight:Int,preview:Boolean):ShortArray
    private external fun nativeRenderFile(handle:Long,path:String,width:Int,height:Int,parameters:String,shoot:String,strength:Float,vignette:Float,originX:Int,originY:Int,sourceWidth:Int,sourceHeight:Int,coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int):ShortArray
    private external fun nativeRenderBitmap(handle:Long,bitmap:Bitmap,width:Int,height:Int,parameters:String,shoot:String,strength:Float,vignette:Float,originX:Int,originY:Int,sourceWidth:Int,sourceHeight:Int,coreX:Int,coreY:Int,coreWidth:Int,coreHeight:Int):ShortArray
    private external fun nativeTileHalo(handle:Long,parameters:String,width:Int,height:Int):Int
    private external fun nativeMemoryPeak(handle:Long):LongArray
    private external fun nativeTrim(handle:Long)
    private external fun nativeClose(handle:Long)
    private external fun nativeDevice(handle:Long):String
}

internal data class PrintMaterial(val id:String,val name:String,val kind:String)
internal fun resolvePaper(stock:FilmStock,paper:String):String {
    if(stock.categoryLabel=="黑白胶片")return "ilford_multigrade_iv_rc"
    if(paper!="auto" && paper!="ilford_multigrade_iv_rc")return paper
    return when(stock.id){"kodak_5219","kodak_5207","kodak_5203","kodak_5213"->"kodak_2383";else->"kodak_portra_endura"}
}
