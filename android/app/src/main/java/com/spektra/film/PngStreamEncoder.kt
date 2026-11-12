package com.spektra.film

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.OutputStream
import java.util.zip.CRC32
import java.util.zip.Deflater
import java.util.zip.DeflaterOutputStream

/** Real RGB8/16 PNG, bounded to one source row and a 64 KiB compressed chunk. */
internal object PngStreamEncoder {
    private fun chunk(out:DataOutputStream,type:String,data:ByteArray,length:Int=data.size) {
        val kind=type.toByteArray(Charsets.US_ASCII);val crc=CRC32()
        crc.update(kind);crc.update(data,0,length)
        out.writeInt(length);out.write(kind);out.write(data,0,length);out.writeInt(crc.value.toInt())
    }
    fun write(target:OutputStream,width:Int,height:Int,depth:Int,icc:ByteArray,read:(Int,ShortArray)->Unit) {
        require(width>0 && height>0 && width<=Int.MAX_VALUE/6 && depth in listOf(8,16) && icc.size>=128)
        val out=DataOutputStream(target);out.write(byteArrayOf(137.toByte(),80,78,71,13,10,26,10))
        val header=ByteArrayOutputStream().apply {DataOutputStream(this).apply {writeInt(width);writeInt(height);writeByte(depth);writeByte(2);writeByte(0);writeByte(0);writeByte(0)}}
        chunk(out,"IHDR",header.toByteArray())
        val profile=ByteArrayOutputStream().apply {
            write("SpektraFilm".toByteArray(Charsets.US_ASCII));write(0);write(0)
            DeflaterOutputStream(this).use {it.write(icc)}
        }
        chunk(out,"iCCP",profile.toByteArray())
        val idat=object:OutputStream() {
            val buffer=ByteArray(65536);var size=0
            override fun write(value:Int) {buffer[size++]=value.toByte();if(size==buffer.size)flush()}
            override fun write(bytes:ByteArray,offset:Int,length:Int) {
                var start=offset;var remaining=length
                while(remaining>0) {val n=minOf(remaining,buffer.size-size);System.arraycopy(bytes,start,buffer,size,n);size+=n;start+=n;remaining-=n;if(size==buffer.size)flush()}
            }
            override fun flush() {if(size>0){chunk(out,"IDAT",buffer,size);size=0}}
            override fun close()=flush()
        }
        val deflater=Deflater(1)
        try {
            DeflaterOutputStream(idat,deflater,65536).use {compressed ->
                val pixels=ShortArray(width*3);val row=ByteArray(1+width*3*(depth/8));row[0]=1 // Sub filter.
                for(y in 0 until height) {
                    read(y,pixels)
                    for(i in pixels.indices) {
                        val v=pixels[i].toInt() and 65535
                        if(depth==16) {row[1+i*2]=(v ushr 8).toByte();row[2+i*2]=v.toByte()}
                        else row[1+i]=((v+128)/257).toByte()
                    }
                    val stride=3*(depth/8)
                    for(i in row.lastIndex downTo 1+stride)row[i]=(row[i].toInt()-row[i-stride].toInt()).toByte()
                    compressed.write(row)
                }
            }
        } finally {deflater.end()}
        chunk(out,"IEND",ByteArray(0));out.flush()
    }
}
