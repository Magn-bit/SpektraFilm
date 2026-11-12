package com.spektra.film

import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.*

internal data class CreativePhoto(val uri:Uri,val name:String,val stock:Int,val adjustments:Adjustments,val width:Int=0,val height:Int=0)
internal data class CreativeSlot(val source:Int,val panX:Float=.5f,val panY:Float=.5f,val zoom:Float=1f)
internal data class CreativeSpec(val columns:Int=2,val cellAspect:Float=1f,val gap:Float=.016f,val border:Float=.04f,val background:Int=0xfff4f1e9.toInt(),val date:String="",val slots:List<CreativeSlot>) {
    fun toJson()=JSONObject().put("columns",columns).put("cell_aspect",cellAspect).put("gap",gap).put("border",border).put("background",background).put("date",date)
        .put("slots",JSONArray().apply {slots.forEach {put(JSONObject().put("source",it.source).put("pan_x",it.panX).put("pan_y",it.panY).put("zoom",it.zoom))}})
}
internal data class CreativeRect(val left:Int,val top:Int,val width:Int,val height:Int,val slot:CreativeSlot)
internal data class CreativePlan(val width:Int,val height:Int,val cells:List<CreativeRect>,val footer:Int)
internal object CreativeLayout {
    fun plan(sizes:List<Pair<Int,Int>>,spec:CreativeSpec,previewWidth:Int=0):CreativePlan {
        require(sizes.isNotEmpty() && spec.slots.size in 1..9 && spec.columns in 1..3 && spec.cellAspect in .2f..5f)
        val columns=min(spec.columns,spec.slots.size);val rows=(spec.slots.size+columns-1)/columns
        val natural=spec.slots.minOf {slot->val (w,h)=sizes[slot.source];floor(min(w.toDouble(),h*spec.cellAspect.toDouble())/slot.zoom).toInt().coerceAtLeast(1)}
        val unit=if(previewWidth>0)previewWidth.toDouble()/(columns+(columns-1)*spec.gap+2*spec.border) else natural.toDouble()
        val cellW=max(1,floor(unit).toInt());val cellH=max(1,(cellW/spec.cellAspect).roundToInt())
        val gap=(cellW*spec.gap).roundToInt();val border=(cellW*spec.border).roundToInt();val footer=if(spec.date.isBlank())0 else max((cellH*.045f).roundToInt(),border)
        val width=columns*cellW+(columns-1)*gap+border*2;val height=rows*cellH+(rows-1)*gap+border*2+footer
        require(width<=65500 && height<=65500){"拼图尺寸超过格式上限；请减少列数或照片数量"}
        return CreativePlan(width,height,spec.slots.mapIndexed {i,slot->CreativeRect(border+i%columns*(cellW+gap),border+i/columns*(cellH+gap),cellW,cellH,slot)},footer)
    }
    /** Crop in each developed photo, so preview and full output take the identical field of view. */
    fun sourceRect(width:Int,height:Int,aspect:Float,slot:CreativeSlot):DoubleArray {
        val w=min(width.toDouble(),height*aspect.toDouble())/slot.zoom.coerceIn(1f,4f);val h=w/aspect
        return doubleArrayOf((width-w)*slot.panX.coerceIn(0f,1f),(height-h)*slot.panY.coerceIn(0f,1f),w,h)
    }
}
