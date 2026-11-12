package com.spektra.film

import android.content.res.AssetManager
import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.security.MessageDigest

/** A style deliberately excludes capture settings, film development, geometry and local edits. */
data class StyleSettings(
    val contrast:Float=0f,
    val saturation:Float=0f,
    val vibrance:Float=0f,
    val highlights:Float=0f,
    val shadows:Float=0f,
    val blackPoint:Float=0f,
    val whitePoint:Float=100f,
    val gamma:Float=1f,
    val curves:CurveSet=CurveSet(),
    val grading:ColorGrading=ColorGrading(),
    val lookLut:String="",
    val lookStrength:Float=100f,
    val hsl:HslSettings=HslSettings(),
) {
    fun applyTo(a:Adjustments)=a.copy(contrast=contrast,saturation=saturation,vibrance=vibrance,
        highlights=highlights,shadows=shadows,blackPoint=blackPoint,whitePoint=whitePoint,gamma=gamma,
        curves=curves,grading=grading,lookLut=lookLut,lookStrength=lookStrength,hsl=hsl)
    fun toJson()=JSONObject().put("contrast",contrast).put("saturation",saturation).put("vibrance",vibrance)
        .put("highlights",highlights).put("shadows",shadows).put("black_point",blackPoint).put("white_point",whitePoint)
        .put("gamma",gamma).put("curves",curves.toJson()).put("grading",grading.toJson()).put("look_lut",lookLut).put("look_strength",lookStrength).put("hsl",hsl.toJson())
    companion object {
        fun from(a:Adjustments)=StyleSettings(a.contrast,a.saturation,a.vibrance,a.highlights,a.shadows,
            a.blackPoint,a.whitePoint,a.gamma,a.curves,a.grading,a.lookLut,a.lookStrength,a.hsl)
        fun fromJson(j:JSONObject)=StyleSettings(
            j.number("contrast",0f,-100f,100f),j.number("saturation",0f,-100f,100f),j.number("vibrance",0f,-100f,100f),
            j.number("highlights",0f,-100f,100f),j.number("shadows",0f,-100f,100f),j.number("black_point",0f,0f,20f),
            j.number("white_point",100f,80f,100f),j.number("gamma",1f,.5f,2f),
            CurveSet.fromJson(j.optJSONObject("curves") ?: JSONObject()),ColorGrading.fromJson(j.optJSONObject("grading") ?: JSONObject()),j.optString("look_lut",""),j.number("look_strength",100f,0f,100f),HslSettings.fromJson(j.optJSONObject("hsl") ?: JSONObject()))
    }
}

data class StylePreset(val id:String,val name:String,val description:String,val author:String,val kind:String,
                       val source:String,val settings:StyleSettings,val warnings:List<String> = emptyList(),val category:String="general") {
    fun toJson()=JSONObject().put("id",id).put("name",name).put("description",description).put("author",author)
        .put("kind",kind).put("source",source).put("settings",settings.toJson()).put("warnings",JSONArray(warnings)).put("category",category)
    companion object {
        fun fromJson(j:JSONObject)=StylePreset(j.getString("id"),j.getString("name"),j.optString("description"),
            j.optString("author"),j.optString("kind","original"),j.optString("source"),StyleSettings.fromJson(j.getJSONObject("settings")),
            j.optJSONArray("warnings")?.let {a->(0 until a.length()).map {a.optString(it)}} ?: emptyList(),
            j.optString("category","general").takeIf {it in setOf("portrait","landscape","general")} ?: "general")
        fun load(assets:AssetManager):List<StylePreset> {
            val root=JSONObject(assets.open("styles/presets.json").bufferedReader().use {it.readText()})
            val list=root.getJSONArray("presets")
            return (0 until list.length()).map {fromJson(list.getJSONObject(it))}
        }
    }
}

/** Imports retain parameter documents only; they never copy the user's photographs. */
internal class ImportedStyleStore(context:Context) {
    private val directory=File(context.filesDir,"styles")
    private fun file(id:String):AtomicFile {
        val name=MessageDigest.getInstance("SHA-256").digest(id.toByteArray(Charsets.UTF_8)).joinToString("") {"%02x".format(it)}
        return AtomicFile(File(directory,"$name.json"))
    }
    fun load():List<StylePreset> = directory.listFiles {f->f.isFile && f.extension=="json"}?.sortedBy {it.name}?.take(128)?.mapNotNull {
        runCatching {require(it.length()<=2*1024*1024);StylePreset.fromJson(JSONObject(it.readText(Charsets.UTF_8)))}.getOrNull()
    } ?: emptyList()
    fun save(preset:StylePreset) {
        directory.mkdirs();val target=file(preset.id);val stream=target.startWrite()
        try {stream.write(preset.toJson().toString().toByteArray(Charsets.UTF_8));target.finishWrite(stream)}
        catch(error:Exception) {target.failWrite(stream);throw error}
    }
    internal fun remove(id:String)=file(id).delete()
}

/** A batch application is one undo unit, keyed by URI so removal/reordering cannot retarget it. */
internal class StyleHistory(private val capacity:Int=16) {
    data class Change(val uri:String,val before:StyleSettings,val after:StyleSettings)
    private val past=java.util.ArrayDeque<List<Change>>()
    val canUndo get()=past.isNotEmpty()
    fun remember(changes:List<Change>) {
        if(changes.isEmpty())return
        past.addLast(changes);while(past.size>capacity)past.removeFirst()
    }
    fun undo():List<Change>?=past.pollLast()
    fun forget(uri:String) {
        val remaining=past.map {changes ->changes.filterNot {it.uri==uri}}.filter {it.isNotEmpty()}
        past.clear();remaining.forEach {past.addLast(it)}
    }
}
