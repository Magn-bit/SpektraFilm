package com.spektra.film

import android.content.Context
import android.net.Uri
import android.util.AtomicFile
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID

/** Coordinates are normalized in the EXIF-oriented original, never in preview pixels. */
data class MaskPoint(val u: Float, val v: Float)

data class MaskStroke(
    val points: List<MaskPoint> = emptyList(),
    val radius: Float = .05f,
    val feather: Float = .7f,
    val flow: Float = 1f,
    val erase: Boolean = false,
) {
    fun toJson() = JSONObject().apply {
        put("points", JSONArray().apply { points.forEach { put(JSONArray().put(it.u).put(it.v)) } })
        put("radius", radius);put("feather", feather);put("flow", flow);put("erase", erase)
    }
    companion object {
        fun fromJson(json: JSONObject): MaskStroke {
            val array = json.optJSONArray("points") ?: JSONArray()
            val points = (0 until array.length()).mapNotNull { index ->
                val point = array.optJSONArray(index) ?: return@mapNotNull null
                val u = point.optDouble(0, Double.NaN);val v = point.optDouble(1, Double.NaN)
                if (u.isFinite() && v.isFinite()) MaskPoint(u.toFloat().coerceIn(0f, 1f), v.toFloat().coerceIn(0f, 1f)) else null
            }
            return MaskStroke(points, json.number("radius", .05f, .002f, .5f),
                json.number("feather", .7f, 0f, 1f), json.number("flow", 1f, 0f, 1f), json.optBoolean("erase"))
        }
    }
}

data class MaskLayer(
    val id: String = UUID.randomUUID().toString(),
    val name: String = "蒙版",
    val enabled: Boolean = true,
    val inverted: Boolean = false,
    val opacity: Float = 1f,
    val exposure: Float = 0f,
    val temperature: Float = 0f,
    val tint: Float = 0f,
    val contrast: Float = 0f,
    val saturation: Float = 0f,
    val highlights: Float = 0f,
    val shadows: Float = 0f,
    val strokes: List<MaskStroke> = emptyList(),
    val kind:String="brush",
    val start:MaskPoint=MaskPoint(.25f,.5f),
    val end:MaskPoint=MaskPoint(.75f,.5f),
    val center:MaskPoint=MaskPoint(.5f,.5f),
    val radiusX:Float=.25f,
    val radiusY:Float=.25f,
    val rotation:Float=0f,
    val feather:Float=.75f,
) {
    fun toJson() = JSONObject().apply {
        put("id", id);put("name", name);put("enabled", enabled);put("inverted", inverted);put("opacity", opacity)
        put("exposure", exposure);put("temperature", temperature);put("tint", tint);put("contrast", contrast)
        put("saturation", saturation);put("highlights", highlights);put("shadows", shadows)
        put("strokes", JSONArray().apply { strokes.forEach { put(it.toJson()) } })
        put("kind",kind);put("start",JSONArray().put(start.u).put(start.v));put("end",JSONArray().put(end.u).put(end.v))
        put("center",JSONArray().put(center.u).put(center.v));put("radius_x",radiusX);put("radius_y",radiusY);put("rotation",rotation);put("feather",feather)
    }
    companion object {
        fun fromJson(json: JSONObject) = MaskLayer(
            id = json.optString("id").ifBlank { UUID.randomUUID().toString() },
            name = json.optString("name", "蒙版"), enabled = json.optBoolean("enabled", true),
            inverted = json.optBoolean("inverted"), opacity = json.number("opacity", 1f, 0f, 1f),
            exposure = json.number("exposure", 0f, -3f, 3f), temperature = json.number("temperature", 0f, -100f, 100f),
            tint = json.number("tint", 0f, -100f, 100f), contrast = json.number("contrast", 0f, -100f, 100f),
            saturation = json.number("saturation", 0f, -100f, 100f), highlights = json.number("highlights", 0f, -100f, 100f),
            shadows = json.number("shadows", 0f, -100f, 100f),
            strokes = json.optJSONArray("strokes")?.let { array ->
                (0 until array.length()).mapNotNull { index -> array.optJSONObject(index)?.let { MaskStroke.fromJson(it) } }
            } ?: emptyList(),
            kind=json.optString("kind","brush").takeIf { it in listOf("brush","linear","radial") } ?: "brush",
            start=point(json,"start",MaskPoint(.25f,.5f)),end=point(json,"end",MaskPoint(.75f,.5f)),center=point(json,"center",MaskPoint(.5f,.5f)),
            radiusX=json.number("radius_x",.25f,.002f,2f),radiusY=json.number("radius_y",.25f,.002f,2f),
            rotation=json.number("rotation",0f,-360f,360f),feather=json.number("feather",.75f,0f,1f),
        )
        private fun point(j:JSONObject,key:String,default:MaskPoint):MaskPoint {
            val a=j.optJSONArray(key) ?: return default
            val u=a.optDouble(0,default.u.toDouble());val v=a.optDouble(1,default.v.toDouble())
            return MaskPoint(if(u.isFinite())u.toFloat().coerceIn(0f,1f) else default.u,if(v.isFinite())v.toFloat().coerceIn(0f,1f) else default.v)
        }
        fun encode(layers: List<MaskLayer>) = JSONArray().apply { layers.forEach { put(it.toJson()) } }.toString()
        fun decode(value: String): List<MaskLayer> = JSONArray(value).let { array ->
            (0 until array.length()).mapNotNull { array.optJSONObject(it)?.let(::fromJson) }
        }
    }
}

/** Each photo owns its own bounded undo journal; a completed stroke is one entry. */
internal class MaskHistory(private val capacity:Int=24) {
    private val past=java.util.ArrayDeque<List<MaskLayer>>()
    private val future=java.util.ArrayDeque<List<MaskLayer>>()
    val canUndo get()=past.isNotEmpty()
    val canRedo get()=future.isNotEmpty()
    fun remember(layers:List<MaskLayer>) {
        if(past.peekLast()!=layers) { past.addLast(layers);while(past.size>capacity)past.removeFirst() }
        future.clear()
    }
    fun undo(current:List<MaskLayer>):List<MaskLayer>? {
        if(past.isEmpty())return null
        future.addLast(current);return past.removeLast()
    }
    fun redo(current:List<MaskLayer>):List<MaskLayer>? {
        if(future.isEmpty())return null
        past.addLast(current);return future.removeLast()
    }
}

/** Small private sidecar only: no copied source, thumbnail, catalog, or source-folder write. */
internal class PhotoEditsStore(context: Context) {
    private val directory = File(context.filesDir, "photo-edits")
    data class Saved(val stock: Int, val adjustments: Adjustments)
    private fun file(uri: Uri): AtomicFile {
        val hash = MessageDigest.getInstance("SHA-256").digest(uri.toString().toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return AtomicFile(File(directory, "$hash.json"))
    }
    fun load(uri: Uri): Saved? = runCatching {
        val json = JSONObject(file(uri).openRead().bufferedReader().use { it.readText() })
        Saved(json.optInt("stock", 0), adjustmentsFromJson(json.getJSONObject("adjustments"),json.optInt("version",1)))
    }.getOrNull()
    internal fun remove(uri:Uri) { file(uri).delete() }
    fun save(uri: Uri, stock: Int, adjustments: Adjustments) {
        directory.mkdirs()
        val file = file(uri);val stream = file.startWrite()
        try {
            val json = JSONObject().put("version", 3).put("stock", stock).put("adjustments", adjustmentsToJson(adjustments))
            stream.write(json.toString().toByteArray(Charsets.UTF_8));file.finishWrite(stream)
        } catch (error: Exception) { file.failWrite(stream);throw error }
    }
    companion object {
        internal fun adjustmentsToJson(adjustments:Adjustments)=adjustments.toEditorJson()
        internal fun adjustmentsFromJson(json:JSONObject,version:Int=3)=decodeAdjustments(json,version)
    }
}
