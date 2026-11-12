package com.spektra.film

import android.content.res.AssetManager
import org.json.JSONObject
import java.io.Closeable

/** Converts the rendered sRGB result into actual target samples; cannot recover previously clipped gamut. */
internal class OutputColorTransform(assets:AssetManager,space:String,linear:Boolean=false) {
    private val transfer=if(linear)2 else if(space=="ProPhoto RGB")1 else 0
    private val identity=space=="sRGB" && !linear
    private val matrix=if(space=="sRGB")floatArrayOf(1f,0f,0f,0f,1f,0f,0f,0f,1f) else {
        val j=JSONObject(assets.open("color/output-matrices.json").bufferedReader().use {it.readText()})
        val a=j.getJSONArray(space);FloatArray(9){a.getDouble(it).toFloat()}
    }
    fun apply(pixels:ShortArray,offset:Int=0,count:Int=pixels.size-offset) {
        require(count%3==0 && offset>=0 && count>=0 && offset.toLong()+count<=pixels.size)
        if(!identity)OutputPixelOps.transform(pixels,offset,count,matrix,transfer)
    }
}

internal object OutputPixelOps {
    init {System.loadLibrary("spektra_stream_jpeg")}
    external fun transform(pixels:ShortArray,offset:Int,count:Int,matrix:FloatArray,transfer:Int)
    external fun beginResize(sourceWidth:Int,outputWidth:Int):Long
    external fun accumulateResize(handle:Long,pixels:ShortArray,weight:Double)
    external fun finishResizeRow(handle:Long,pixels:ShortArray,totalWeight:Double)
    external fun closeResize(handle:Long)
}

/** Linear-light area reduction, only when the recipe explicitly asks for a smaller long edge. */
internal class ReducedExportRows(private val source:ExportRows16,longEdge:Int):ExportRows16,Closeable {
    private val factor=minOf(1.0,longEdge.toDouble()/maxOf(source.outputWidth,source.outputHeight))
    override val outputWidth=maxOf(1,kotlin.math.round(source.outputWidth*factor).toInt())
    override val outputHeight=maxOf(1,kotlin.math.round(source.outputHeight*factor).toInt())
    private var handle=OutputPixelOps.beginResize(source.outputWidth,outputWidth)
    private val row=ShortArray(source.outputWidth*3)
    private val result=ShortArray(outputWidth*3)
    private var loaded=-1
    private var next=0
    init {check(handle!=0L){"无法创建缩放行缓冲区"}}
    override fun copyRow16(y:Int,destination:ShortArray,destinationOffset:Int) {
        check(y==next && y<outputHeight && handle!=0L)
        val top=y.toDouble()*source.outputHeight/outputHeight
        val bottom=(y+1.0)*source.outputHeight/outputHeight
        val first=kotlin.math.floor(top).toInt();val last=kotlin.math.ceil(bottom).toInt()-1
        for(sy in first..last) {
            while(loaded<sy){source.copyRow16(loaded+1,row);loaded++}
            val weight=minOf(bottom,sy+1.0)-maxOf(top,sy.toDouble())
            if(weight>0)OutputPixelOps.accumulateResize(handle,row,weight)
        }
        OutputPixelOps.finishResizeRow(handle,result,bottom-top)
        System.arraycopy(result,0,destination,destinationOffset,result.size);next++
    }
    override fun reportEncodedRows(rows:Int) {source.reportEncodedRows(((rows.toLong()*source.outputHeight)/outputHeight).toInt())}
    override fun close() {if(handle!=0L){OutputPixelOps.closeResize(handle);handle=0};source.close()}
}
