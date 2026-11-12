package com.spektra.film

import org.json.JSONObject
import java.util.Locale

/** Portable schema shared with shared/output_recipes.py. Zero long edge always means original size. */
internal data class OutputRecipe(
    val id:String="jpg-high",val name:String="高品质 JPG",val format:String="jpeg",val bitDepth:Int=8,
    val colorSpace:String="sRGB",val quality:Int=100,val longEdge:Int=0,val naming:String="{name}_{film}",
    val subfolder:String="高品质 JPG",val conflict:String="rename",val openAfter:Boolean=false,
) {
    val raw get()=format=="raw"
    val extension get()=when(format){"jpeg"->"jpg";"tiff"->"tif";"png"->"png";"dng"->"dng";else->""}
    val mime get()=when(format){"jpeg"->"image/jpeg";"tiff"->"image/tiff";"png"->"image/png";"dng"->"image/x-adobe-dng";else->"application/octet-stream"}
    val detail get()=when {
        raw->"相机原片另存 · 不包含调整"
        format=="dng"->"处理后的线性 RGB · 16 bit · ${sizeLabel()}"
        else->"${sizeLabel()} · $bitDepth bit · $colorSpace"+(if(format=="jpeg")" · 质量 $quality" else "")
    }
    private fun sizeLabel()=if(longEdge==0)"原尺寸" else "长边 $longEdge px"
    fun toJson()=JSONObject().put("id",id).put("name",name).put("format",format).put("bit_depth",bitDepth)
        .put("color_space",colorSpace).put("quality",quality).put("long_edge",longEdge).put("naming",naming)
        .put("subfolder",subfolder).put("conflict",conflict).put("open_after",openAfter)
    fun validated():OutputRecipe {
        require(id.matches(Regex("[a-zA-Z0-9_-]{1,80}")) && name.isNotBlank()) {"导出配方名称无效"}
        require(format in listOf("jpeg","png","tiff","dng","raw") && bitDepth in listOf(8,16)) {"导出格式或位深不支持"}
        require(colorSpace in COLOR_SPACES && quality in 1..100 && longEdge in 0..32000) {"导出参数超出范围"}
        require(format!="jpeg" || bitDepth==8) {"JPG 仅支持 8 位"}
        require(format!="dng" || bitDepth==16 && colorSpace=="sRGB") {"线性 DNG 使用 16 位线性 sRGB 原色"}
        require(!raw || longEdge==0) {"RAW 原片不能缩放"}
        require(subfolder.isNotBlank() && subfolder !in listOf(".","..") && subfolder.none {it in "/\\:"}) {"导出子文件夹不能包含路径"}
        val fields=Regex("\\{([^{}]*)}").findAll(naming).toList()
        require(fields.isNotEmpty() && fields.all {it.groupValues[1] in listOf("name","film","index")} &&
            Regex("\\{[^{}]*}").replace(naming,"").none {it=='{' || it=='}'}) {"命名仅支持 {name}、{film}、{index}"}
        require(conflict in listOf("rename","skip")) {"同名文件处理方式无效"}
        return this
    }
    fun filename(sourceName:String,film:String,index:Int,rawExtension:String?=null):String {
        val stem=naming.replace("{name}",sourceName.substringBeforeLast('.',sourceName))
            .replace("{film}",film).replace("{index}",index.toString())
        return safeFilename(stem)+"."+if(raw)requireNotNull(rawExtension) else extension
    }
    companion object {
        val COLOR_SPACES=listOf("sRGB","Display P3","ProPhoto RGB")
        val DEFAULTS=listOf(OutputRecipe(),OutputRecipe(id="jpg-share",name="分享 JPG",quality=85,subfolder="分享 JPG"),
            OutputRecipe(id="tiff",name="无损 TIFF",format="tiff",bitDepth=16,subfolder="无损 TIFF"),
            OutputRecipe(id="png",name="无损 PNG",format="png",bitDepth=16,subfolder="无损 PNG"),
            OutputRecipe(id="dng",name="线性 DNG",format="dng",bitDepth=16,subfolder="线性 DNG"),
            OutputRecipe(id="raw",name="RAW 原片",format="raw",bitDepth=16,subfolder="RAW 原片"))
        fun fromJson(j:JSONObject)=OutputRecipe(id=j.optString("id","jpg-high"),name=j.optString("name","高品质 JPG"),
            format=j.optString("format","jpeg"),bitDepth=j.optInt("bit_depth",8),colorSpace=j.optString("color_space","sRGB"),
            quality=j.optInt("quality",100),longEdge=j.optInt("long_edge",0),naming=j.optString("naming","{name}_{film}"),
            subfolder=j.optString("subfolder","高品质 JPG"),conflict=j.optString("conflict","rename"),openAfter=j.optBoolean("open_after",false)).validated()
        fun safeFilename(value:String):String {
            var text=value.map {if(it.code<32 || it in "<>:\"/\\|?*")'_' else it}.joinToString("").trim(' ','.').ifEmpty {"照片"}
            val base=text.substringBefore('.').uppercase(Locale.ROOT)
            if(base in setOf("CON","PRN","AUX","NUL") || base.matches(Regex("(COM|LPT)[1-9]")))text="_"+text
            return text.take(180)
        }
    }
}
