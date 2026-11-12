package com.spektra.film

import org.json.JSONArray
import org.json.JSONObject

data class CurvePoint(val x:Float,val y:Float)
data class HslBand(val hue:Float=0f,val saturation:Float=0f,val luminance:Float=0f) {
    fun isActive()=hue!=0f || saturation!=0f || luminance!=0f
    fun toJson()=JSONObject().put("hue",hue).put("saturation",saturation).put("luminance",luminance)
    companion object {
        fun fromJson(j:JSONObject)=HslBand(j.number("hue",0f,-100f,100f),j.number("saturation",0f,-100f,100f),j.number("luminance",0f,-100f,100f))
    }
}
data class HslSettings(val red:HslBand=HslBand(),val orange:HslBand=HslBand(),val yellow:HslBand=HslBand(),
                       val green:HslBand=HslBand(),val aqua:HslBand=HslBand(),val blue:HslBand=HslBand(),
                       val purple:HslBand=HslBand(),val magenta:HslBand=HslBand()) {
    fun band(index:Int)=when(index) {0->red;1->orange;2->yellow;3->green;4->aqua;5->blue;6->purple;else->magenta}
    fun withBand(index:Int,value:HslBand)=when(index) {0->copy(red=value);1->copy(orange=value);2->copy(yellow=value);3->copy(green=value);4->copy(aqua=value);5->copy(blue=value);6->copy(purple=value);else->copy(magenta=value)}
    fun isActive()=(0..7).any {band(it).isActive()}
    fun toJson()=JSONObject().apply {names.forEachIndexed {index,name ->put(name,band(index).toJson())}}
    companion object {
        val names=listOf("red","orange","yellow","green","aqua","blue","purple","magenta")
        fun fromJson(j:JSONObject):HslSettings {var result=HslSettings();names.forEachIndexed {index,name ->result=result.withBand(index,HslBand.fromJson(j.optJSONObject(name) ?: JSONObject()))};return result}
    }
}
private val identityCurve=listOf(CurvePoint(0f,0f),CurvePoint(1f,1f))
data class CurveSet(
    val master:List<CurvePoint> = identityCurve,
    val red:List<CurvePoint> = identityCurve,
    val green:List<CurvePoint> = identityCurve,
    val blue:List<CurvePoint> = identityCurve,
    val luma:List<CurvePoint> = identityCurve,
) {
    fun channel(index:Int)=when(index) { 1->red;2->green;3->blue;4->luma;else->master }
    fun withChannel(index:Int,points:List<CurvePoint>)=when(index) {
        1->copy(red=points);2->copy(green=points);3->copy(blue=points);4->copy(luma=points);else->copy(master=points)
    }
    fun isIdentity()=(0..4).all { channel(it)==identityCurve }
    fun toJson()=JSONObject().apply {
        listOf("master","red","green","blue","luma").forEachIndexed { index,name ->
            put(name,JSONArray().apply { channel(index).forEach { put(JSONArray().put(it.x).put(it.y)) } })
        }
    }
    companion object {
        fun fromJson(json:JSONObject)=CurveSet(
            points(json.optJSONArray("master")),points(json.optJSONArray("red")),points(json.optJSONArray("green")),
            points(json.optJSONArray("blue")),points(json.optJSONArray("luma")))
        private fun points(array:JSONArray?):List<CurvePoint> {
            if(array==null)return identityCurve
            val entries=sortedMapOf<Float,Float>()
            for(index in 0 until minOf(32,array.length())) {
                val point=array.optJSONArray(index) ?: continue
                val x=point.optDouble(0,Double.NaN);val y=point.optDouble(1,Double.NaN)
                if(x.isFinite() && y.isFinite())entries[x.toFloat().coerceIn(0f,1f)]=y.toFloat().coerceIn(0f,1f)
            }
            if(entries.size<2)return identityCurve
            if(!entries.containsKey(0f))entries[0f]=entries.values.first()
            if(!entries.containsKey(1f))entries[1f]=entries.values.last()
            return entries.map { CurvePoint(it.key,it.value) }
        }
    }
}

data class TonalGrade(val hue:Float=0f,val saturation:Float=0f,val luminance:Float=0f) {
    fun toJson()=JSONObject().put("hue",hue).put("saturation",saturation).put("luminance",luminance)
    fun isActive()=saturation!=0f || luminance!=0f
    companion object {
        fun fromJson(j:JSONObject)=TonalGrade(j.number("hue",0f,0f,360f),j.number("saturation",0f,0f,100f),j.number("luminance",0f,-100f,100f))
    }
}
data class ColorGrading(
    val shadows:TonalGrade=TonalGrade(),val midtones:TonalGrade=TonalGrade(),val highlights:TonalGrade=TonalGrade(),
    val balance:Float=0f,val blending:Float=50f,
) {
    fun zone(index:Int)=when(index) { 1->midtones;2->highlights;else->shadows }
    fun withZone(index:Int,grade:TonalGrade)=when(index) { 1->copy(midtones=grade);2->copy(highlights=grade);else->copy(shadows=grade) }
    fun isActive()=(0..2).any { zone(it).isActive() }
    fun toJson()=JSONObject().put("shadows",shadows.toJson()).put("midtones",midtones.toJson()).put("highlights",highlights.toJson())
        .put("balance",balance).put("blending",blending)
    companion object {
        fun fromJson(j:JSONObject)=ColorGrading(
            TonalGrade.fromJson(j.optJSONObject("shadows") ?: JSONObject()),TonalGrade.fromJson(j.optJSONObject("midtones") ?: JSONObject()),
            TonalGrade.fromJson(j.optJSONObject("highlights") ?: JSONObject()),j.number("balance",0f,-100f,100f),j.number("blending",50f,0f,100f))
    }
}

data class CropBounds(val left:Float=0f,val top:Float=0f,val right:Float=1f,val bottom:Float=1f) {
    fun toJson()=JSONArray().put(left).put(top).put(right).put(bottom)
    fun isFull()=this==CropBounds()
    companion object {
        fun fromJson(a:JSONArray?):CropBounds {
            if(a==null)return CropBounds()
            val values=FloatArray(4) { index ->val n=a.optDouble(index,if(index<2)0.0 else 1.0);if(n.isFinite())n.toFloat().coerceIn(0f,1f) else if(index<2)0f else 1f}
            val left=minOf(values[0],values[2]).coerceAtMost(.99f);val top=minOf(values[1],values[3]).coerceAtMost(.99f)
            return CropBounds(left,top,maxOf(values[0],values[2]).coerceAtLeast(left+.001f),maxOf(values[1],values[3]).coerceAtLeast(top+.001f))
        }
    }
}
data class Geometry(
    val rotation:Float=0f,val vertical:Float=0f,val horizontal:Float=0f,val aspect:Float=0f,val scale:Float=100f,
    val flipHorizontal:Boolean=false,val flipVertical:Boolean=false,val autoCrop:Boolean=true,
    val crop:CropBounds=CropBounds(),
    val quarterTurns:Int=0,
) {
    fun isNeutral()=quarterTurns%4==0 && rotation==0f && vertical==0f && horizontal==0f && aspect==0f && scale==100f && !flipHorizontal && !flipVertical && crop.isFull()
    fun toJson()=JSONObject().put("rotation",rotation).put("vertical",vertical).put("horizontal",horizontal).put("aspect",aspect).put("scale",scale)
        .put("flip_horizontal",flipHorizontal).put("flip_vertical",flipVertical).put("auto_crop",autoCrop).put("crop",crop.toJson()).put("quarter_turns",quarterTurns.mod(4))
    companion object {
        fun fromJson(j:JSONObject)=Geometry(j.number("rotation",0f,-45f,45f),j.number("vertical",0f,-100f,100f),
            j.number("horizontal",0f,-100f,100f),j.number("aspect",0f,-100f,100f),j.number("scale",100f,100f,200f),
            j.optBoolean("flip_horizontal"),j.optBoolean("flip_vertical"),j.optBoolean("auto_crop",true),CropBounds.fromJson(j.optJSONArray("crop")),j.optInt("quarter_turns",0).mod(4))
    }
}

internal fun Adjustments.colorJson(lookPath:String="")=JSONObject().put("curves",curves.toJson()).put("grading",grading.toJson())
    .put("hsl",hsl.toJson())
    .put("look_lut_path",lookPath).put("look_strength",lookStrength.coerceIn(0f,100f)).toString()
internal fun JSONObject.number(key:String,default:Float,low:Float,high:Float):Float {
    val value=optDouble(key,default.toDouble())
    return if(value.isFinite())value.toFloat().coerceIn(low,high) else default
}
