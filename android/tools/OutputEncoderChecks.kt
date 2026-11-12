package com.spektra.film

import java.io.File

/** Write real container data once; the host runner independently decodes and verifies pixels/metadata. */
fun main(args:Array<String>) {
    val out=File(args[0]);out.mkdirs()
    val root=File(args[1]);val profile=File(root,"assets/color/sRGB.icc").readBytes()
    val w=64;val h=48
    val reader={y:Int,row:ShortArray->for(i in row.indices)row[i]=((y*w*3+i)*113 and 65535).toShort()}
    File(out,"rgb16.png").outputStream().use {PngStreamEncoder.write(it,w,h,16,profile,reader)}
    File(out,"rgb8.png").outputStream().use {PngStreamEncoder.write(it,w,h,8,profile,reader)}
    File(out,"linear.dng").outputStream().use {LinearDngEncoder.write(it,w,h,reader)}
    File(out,"rgb16.tif").outputStream().use {TiffEncoder.write16(it,w,h,profile,out){y,row->reader(y,row)}}
    println("Wrote RGB8/16 PNG, RGB16 TIFF and LinearRaw DNG without bitmap quantisation")
}
