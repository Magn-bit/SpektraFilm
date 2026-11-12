package com.spektra.film

import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Processed, demosaiced linear RGB16 DNG. This is deliberately separate from a camera-RAW copy. */
internal object LinearDngEncoder {
    private data class Tag(val id:Int,val type:Int,val count:Int,val data:ByteArray)
    private fun shorts(vararg values:Int)=ByteBuffer.allocate(values.size*2).order(ByteOrder.LITTLE_ENDIAN).apply {values.forEach {putShort(it.toShort())}}.array()
    private fun longs(vararg values:Int)=ByteBuffer.allocate(values.size*4).order(ByteOrder.LITTLE_ENDIAN).apply {values.forEach {putInt(it)}}.array()
    private fun rationals(values:DoubleArray)=ByteBuffer.allocate(values.size*8).order(ByteOrder.LITTLE_ENDIAN).apply {
        values.forEach {putInt(kotlin.math.round(it*1000000).toInt());putInt(1000000)}
    }.array()
    fun write(target:OutputStream,width:Int,height:Int,readLinear:(Int,ShortArray)->Unit) {
        require(width>0 && height>0 && width<=Int.MAX_VALUE/6)
        val bytes=width.toLong()*height*6
        val tags=mutableListOf<Tag>()
        fun short(id:Int,vararg v:Int){tags.add(Tag(id,3,v.size,shorts(*v)))}
        fun long(id:Int,vararg v:Int){tags.add(Tag(id,4,v.size,longs(*v)))}
        fun ascii(id:Int,v:String){val s=(v+"\u0000").toByteArray(Charsets.US_ASCII);tags.add(Tag(id,2,s.size,s))}
        fun rational(id:Int,v:DoubleArray,signed:Boolean=false){tags.add(Tag(id,if(signed)10 else 5,v.size,rationals(v)))}
        long(256,width);long(257,height);short(258,16,16,16);short(259,1);short(262,34892)
        long(273,0);short(274,1);short(277,3);long(278,height);long(279,bytes.toInt());short(284,1);short(339,1)
        ascii(305,"SpektraFilm")
        tags.add(Tag(50706,1,4,byteArrayOf(1,4,0,0)));tags.add(Tag(50707,1,4,byteArrayOf(1,3,0,0)))
        ascii(50708,"SpektraFilm Linear sRGB")
        short(50713,1,1);rational(50714,doubleArrayOf(0.0));long(50717,65535)
        rational(50718,doubleArrayOf(1.0,1.0));long(50719,0,0);long(50720,width,height)
        // XYZ(D65) -> native linear sRGB, matching CalibrationIlluminant1 D65.
        rational(50721,doubleArrayOf(3.2404542,-1.5371385,-.4985314,-.969266,1.8760108,.041556,.0556434,-.2040259,1.0572252),true)
        rational(50728,doubleArrayOf(1.0,1.0,1.0));rational(50730,doubleArrayOf(0.0),true)
        short(50778,21);ascii(50936,"SpektraFilm processed linear sRGB");long(50829,0,0,height,width)
        tags.sortBy {it.id}
        var offset=8+2+tags.size*12+4
        val locations=mutableMapOf<Int,Int>()
        for(tag in tags)if(tag.data.size>4){locations[tag.id]=offset;offset=(offset+tag.data.size+1) and -2}
        val dataOffset=offset
        require(dataOffset+bytes<=0xffffffffL){"线性 DNG 超过 4 GiB"}
        val h=ByteBuffer.allocate(dataOffset).order(ByteOrder.LITTLE_ENDIAN)
        h.put('I'.code.toByte()).put('I'.code.toByte()).putShort(42).putInt(8).putShort(tags.size.toShort())
        for(tag in tags) {
            h.putShort(tag.id.toShort()).putShort(tag.type.toShort()).putInt(tag.count)
            when {tag.id==273->h.putInt(dataOffset);tag.data.size>4->h.putInt(locations.getValue(tag.id));else->{h.put(tag.data);repeat(4-tag.data.size){h.put(0)}}}
        }
        h.putInt(0)
        for(tag in tags)if(tag.data.size>4){h.position(locations.getValue(tag.id));h.put(tag.data)}
        target.write(h.array())
        val pixels=ShortArray(width*3);val row=ByteArray(width*6)
        for(y in 0 until height) {
            readLinear(y,pixels)
            for(i in pixels.indices){row[i*2]=pixels[i].toByte();row[i*2+1]=(pixels[i].toInt() ushr 8).toByte()}
            target.write(row)
        }
    }
}
