package com.spektra.film

import java.io.Closeable

/** Mapped RGB16 is a bounded temporary plane; no display bitmap is an export input. */
internal class GeometryResampler(path:String,width:Int,height:Int,geometry:Geometry):Closeable {
    companion object {init {System.loadLibrary("spektra_spectral")}}
    private val frame=PhotoGeometry.frameSize(width,height,geometry)
    private val crop=spectralCropRect(geometry.crop,frame.first,frame.second)
    private var handle=nativeOpen(path,width,height,frame.first,frame.second,PhotoGeometry.inverse(PhotoGeometry.matrix(width,height,geometry)),crop.left,crop.top,crop.width(),crop.height())
    init {check(handle!=0L){"无法打开完整像素几何平面"}}
    fun copyRow(y:Int,destination:ShortArray,offset:Int) {check(handle!=0L);nativeRow(handle,y,destination,offset)}
    override fun close() {if(handle!=0L){nativeClose(handle);handle=0L}}
    private external fun nativeOpen(path:String,width:Int,height:Int,frameWidth:Int,frameHeight:Int,inverse:DoubleArray,cropX:Int,cropY:Int,outWidth:Int,outHeight:Int):Long
    private external fun nativeRow(handle:Long,y:Int,destination:ShortArray,offset:Int)
    private external fun nativeClose(handle:Long)
}
