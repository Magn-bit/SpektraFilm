package com.spektra.film

import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.json.JSONObject

fun main(args:Array<String>) {
    val out=File(args[0]);val root=File(args[1])
    val config=JSONObject(File(root,"android/app/src/main/assets/color/output-matrices.json").readText())
    val input=ShortArray(256*3) {i->((i*421+1777) and 65535).toShort()}
    fun save(name:String,row:ShortArray) {File(out,name).writeBytes(ByteBuffer.allocate(row.size*2).order(ByteOrder.LITTLE_ENDIAN).apply {asShortBuffer().put(row)}.array())}
    save("input.rgb16",input)
    for((space,name,transfer) in listOf(Triple("Display P3","p3",0),Triple("ProPhoto RGB","prophoto",1))) {
        val matrix=config.getJSONArray(space);val pixels=input.copyOf()
        OutputPixelOps.transform(pixels,0,pixels.size,FloatArray(9){matrix.getDouble(it).toFloat()},transfer)
        save(name+".rgb16",pixels)
    }
    val resize=OutputPixelOps.beginResize(4,2)
    try {
        val first=shortArrayOf(0,0,0,-1,-1,-1,0,0,0,-1,-1,-1)
        OutputPixelOps.accumulateResize(resize,first,1.0);OutputPixelOps.accumulateResize(resize,first,1.0)
        val row=ShortArray(6);OutputPixelOps.finishResizeRow(resize,row,2.0);save("area.rgb16",row)
        OutputPixelOps.accumulateResize(resize,ShortArray(12),1.0)
        OutputPixelOps.finishResizeRow(resize,row,1.0);check(row.all {it==0.toShort()})
    } finally {OutputPixelOps.closeResize(resize)}
    println("OK: actual JNI output conversion and area row accumulator executed")
}
