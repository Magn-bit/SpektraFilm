package com.spektra.film

import org.json.JSONArray
import org.json.JSONObject

/** Version 3 stores the complete edit; version 2 deliberately kept film only. */
internal fun Adjustments.toEditorJson():JSONObject {
    val a=filmOnly()
    return JSONObject().apply {
        put("exposure",a.exposure);put("temperature",a.temperature);put("tint",a.tint);put("contrast",a.contrast);put("warmth",a.warmth)
        put("saturation",a.saturation);put("vibrance",a.vibrance);put("highlights",a.highlights);put("shadows",a.shadows)
        put("whites",a.whites);put("blacks",a.blacks);put("levels",a.levels.toJson())
        put("blackPoint",a.blackPoint);put("whitePoint",a.whitePoint);put("gamma",a.gamma)
        put("texture",a.texture);put("clarity",a.clarity);put("dehaze",a.dehaze);put("shadowTint",a.shadowTint)
        put("sharpening",a.sharpening);put("noiseLuminance",a.noiseLuminance);put("noiseColor",a.noiseColor)
        put("redHue",a.redHue);put("redSaturation",a.redSaturation);put("greenHue",a.greenHue);put("greenSaturation",a.greenSaturation);put("blueHue",a.blueHue);put("blueSaturation",a.blueSaturation)
        put("grain",a.grain);put("grainSize",a.grainSize);put("grainType",a.grainType);put("halation",a.halation);put("vignette",a.vignette)
        put("strength",a.strength);put("filmEnabled",a.filmEnabled);put("paper",a.paper);put("filmFormatMm",a.filmFormatMm)
        put("printExposure",a.printExposure);put("printY",a.printY);put("printM",a.printM);put("glare",a.glare)
        put("sceneLatitudeParams",a.sceneLatitudeParams);put("meterMethod",a.meterMethod);put("neutralC",a.neutralC);put("neutralM",a.neutralM);put("neutralY",a.neutralY);
        put("sceneLatitude",a.sceneLatitude);put("halationHeadroom",a.halationHeadroom)
        put("curves",a.curves.toJson());put("grading",a.grading.toJson());put("hsl",a.hsl.toJson());put("geometry",a.geometry.toJson())
        put("masks",JSONArray().apply {a.masks.forEach {put(it.toJson())}})
        put("lookLut",a.lookLut);put("lookStrength",a.lookStrength)
    }
}

internal fun decodeAdjustments(j:JSONObject,version:Int=3):Adjustments {
    val film=Adjustments(exposure=j.number("exposure",0f,-5f,5f),grain=j.number("grain",.18f,0f,1f),grainSize=j.number("grainSize",1f,.25f,2.5f),
        grainType=j.optString("grainType","classic"),halation=j.number("halation",.12f,0f,1f),vignette=j.number("vignette",0f,0f,1f),strength=j.number("strength",1f,0f,1f),
        filmEnabled=if(version<3)true else j.optBoolean("filmEnabled",false),paper=j.optString("paper","auto"),filmFormatMm=j.number("filmFormatMm",35f,16f,120f),
        printExposure=j.number("printExposure",0f,-3f,3f),printY=j.number("printY",0f,-100f,100f),printM=j.number("printM",0f,-100f,100f),glare=j.number("glare",0f,0f,30f),
        geometry=Geometry(crop=CropBounds.fromJson(j.optJSONArray("crop"))))
    if(version<3)return film.filmOnly()
    fun n(k:String,d:Float=0f,lo:Float=-100f,hi:Float=100f)=j.number(k,d,lo,hi)
    return film.copy(temperature=n("temperature",6500f,2000f,10000f),tint=n("tint"),contrast=n("contrast"),warmth=n("warmth"),
        saturation=n("saturation"),vibrance=n("vibrance"),highlights=n("highlights"),shadows=n("shadows"),blackPoint=n("blackPoint",0f,0f,20f),whitePoint=n("whitePoint",100f,80f,100f),gamma=n("gamma",1f,.5f,2f),
        whites=n("whites"),blacks=n("blacks"),levels=LevelsSettings.fromJson(j.optJSONObject("levels")?:JSONObject()),
        texture=n("texture"),clarity=n("clarity"),dehaze=n("dehaze"),shadowTint=n("shadowTint"),
        sharpening=n("sharpening",0f,0f,100f),noiseLuminance=n("noiseLuminance",0f,0f,100f),noiseColor=n("noiseColor",0f,0f,100f),
        redHue=n("redHue"),redSaturation=n("redSaturation"),greenHue=n("greenHue"),greenSaturation=n("greenSaturation"),blueHue=n("blueHue"),blueSaturation=n("blueSaturation"),
        sceneLatitudeParams=j.optString("sceneLatitudeParams",""),meterMethod=j.optString("meterMethod","balanced"),neutralC=if(j.has("neutralC") && !j.isNull("neutralC"))n("neutralC",0f,0f,200f) else null,neutralM=if(j.has("neutralM") && !j.isNull("neutralM"))n("neutralM",0f,0f,200f) else null,neutralY=if(j.has("neutralY") && !j.isNull("neutralY"))n("neutralY",0f,0f,200f) else null,
        sceneLatitude=n("sceneLatitude",0f,0f,6f),halationHeadroom=n("halationHeadroom",0f,0f,6f),
        curves=CurveSet.fromJson(j.optJSONObject("curves") ?: JSONObject()),grading=ColorGrading.fromJson(j.optJSONObject("grading") ?: JSONObject()),hsl=HslSettings.fromJson(j.optJSONObject("hsl") ?: JSONObject()),
        geometry=Geometry.fromJson(j.optJSONObject("geometry") ?: JSONObject()),lookLut=j.optString("lookLut",""),lookStrength=n("lookStrength",100f,0f,100f),
        masks=j.optJSONArray("masks")?.let {array ->(0 until minOf(32,array.length())).mapNotNull {array.optJSONObject(it)?.let(MaskLayer::fromJson)}} ?: emptyList(),
    ).filmOnly()
}

/** Native API receives one schema on every platform, in oriented source coordinates. */
internal fun Adjustments.nativeEditorSettings()=JSONObject().apply {
    val a=this@nativeEditorSettings.filmOnly()
    put("exposure",a.exposure);put("temperature",a.temperature);put("tint",a.tint);put("contrast",a.contrast);put("warmth",a.warmth)
    put("saturation",a.saturation);put("vibrance",a.vibrance);put("highlights",a.highlights);put("shadows",a.shadows)
    put("whites",a.whites);put("blacks",a.blacks);put("levels",a.levels.toJson())
    put("black_point",a.blackPoint);put("white_point",a.whitePoint);put("gamma",a.gamma)
    put("texture",a.texture);put("clarity",a.clarity);put("dehaze",a.dehaze);put("shadow_tint",a.shadowTint);put("vignette",a.vignette*100f)
    put("sharpening",a.sharpening);put("noise_luminance",a.noiseLuminance);put("noise_color",a.noiseColor)
    put("calibration_red_hue",a.redHue);put("calibration_red_saturation",a.redSaturation);put("calibration_green_hue",a.greenHue);put("calibration_green_saturation",a.greenSaturation);put("calibration_blue_hue",a.blueHue);put("calibration_blue_saturation",a.blueSaturation)
    put("curves",a.curves.toJson());put("grading",a.grading.toJson());put("hsl",a.hsl.toJson());put("masks",JSONArray().apply {a.masks.forEach {put(it.toJson())}})
}

internal data class EditorSnapshot(val stock:Int,val values:Adjustments)
internal class EditHistory(private val capacity:Int=40) {
    private val past=java.util.ArrayDeque<EditorSnapshot>()
    private val future=java.util.ArrayDeque<EditorSnapshot>()
    val canUndo get()=past.isNotEmpty()
    val canRedo get()=future.isNotEmpty()
    fun remember(snapshot:EditorSnapshot) {if(past.peekLast()!=snapshot){past.addLast(snapshot);while(past.size>capacity)past.removeFirst()};future.clear()}
    fun undo(current:EditorSnapshot):EditorSnapshot? {if(past.isEmpty())return null;future.addLast(current);return past.removeLast()}
    fun redo(current:EditorSnapshot):EditorSnapshot? {if(future.isEmpty())return null;past.addLast(current);return future.removeLast()}
}

internal fun Adjustments.hasCaptureEdits()=temperature!=6500f || tint!=0f || sharpening!=0f || noiseLuminance!=0f || noiseColor!=0f || redHue!=0f || redSaturation!=0f || greenHue!=0f || greenSaturation!=0f || blueHue!=0f || blueSaturation!=0f
internal fun Adjustments.hasPostEdits()=contrast!=0f || warmth!=0f || saturation!=0f || vibrance!=0f || highlights!=0f || shadows!=0f || whites!=0f || blacks!=0f || levels.active() || blackPoint!=0f || whitePoint!=100f || gamma!=1f || texture!=0f || clarity!=0f || dehaze!=0f || shadowTint!=0f || vignette!=0f || !curves.isIdentity() || grading.isActive() || hsl.isActive() || masks.any {it.enabled && it.opacity>0f && (it.exposure!=0f || it.temperature!=0f || it.tint!=0f || it.contrast!=0f || it.saturation!=0f || it.highlights!=0f || it.shadows!=0f)}

internal object SceneLatitudeEdit {
    fun canonical(value:String):String {
        if(value.isBlank())return ""
        return runCatching {
            val input=JSONObject(value);val out=JSONObject()
            out.put("scene_latitude_active",input.optBoolean("scene_latitude_active",false))
            val norm=input.optString("scene_latitude_norm","power");require(norm in setOf("power","y","max"))
            out.put("scene_latitude_norm",norm)
            listOf("highlight_knee","shadow_knee").forEach {out.put("scene_latitude_$it",input.number("scene_latitude_$it",0f,-24f,24f))}
            listOf("highlight_room","shadow_room").forEach {out.put("scene_latitude_$it",input.number("scene_latitude_$it",0f,0f,24f))}
            out.put("scene_latitude_rolloff",input.number("scene_latitude_rolloff",2f,1f,4f));out.put("scene_latitude_max_lift",input.number("scene_latitude_max_lift",6f,.25f,12f))
            out.toString()
        }.getOrDefault("")
    }
}
