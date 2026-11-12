package com.spektra.film

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import kotlin.math.*

/** Same pixel-centre homography as shared/geometry.py; crop is in the rotated output frame. */
internal object PhotoGeometry {
    fun requiresResample(g:Geometry)=!g.copy(crop=CropBounds()).isNeutral()
    fun frameSize(width:Int,height:Int,g:Geometry)=if(g.quarterTurns.mod(2)==1)height to width else width to height
    private val identity=doubleArrayOf(1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0)
    private fun multiply(a:DoubleArray,b:DoubleArray)=DoubleArray(9) {i ->val r=i/3;val c=i%3;(0..2).sumOf {k->a[r*3+k]*b[k*3+c]}}
    private fun translate(x:Double,y:Double)=doubleArrayOf(1.0,0.0,x,0.0,1.0,y,0.0,0.0,1.0)
    private fun scale(x:Double,y:Double)=doubleArrayOf(x,0.0,0.0,0.0,y,0.0,0.0,0.0,1.0)
    fun inverse(a:DoubleArray):DoubleArray {
        val q=doubleArrayOf(a[4]*a[8]-a[5]*a[7],a[2]*a[7]-a[1]*a[8],a[1]*a[5]-a[2]*a[4],a[5]*a[6]-a[3]*a[8],a[0]*a[8]-a[2]*a[6],a[2]*a[3]-a[0]*a[5],a[3]*a[7]-a[4]*a[6],a[1]*a[6]-a[0]*a[7],a[0]*a[4]-a[1]*a[3])
        val determinant=a[0]*q[0]+a[1]*q[3]+a[2]*q[6];require(abs(determinant)>1e-15)
        return DoubleArray(9){q[it]/determinant}
    }
    fun point(m:DoubleArray,x:Double,y:Double):Pair<Double,Double> {val d=m[6]*x+m[7]*y+m[8];return (m[0]*x+m[1]*y+m[2])/d to (m[3]*x+m[4]*y+m[5])/d}
    fun matrix(width:Int,height:Int,g:Geometry):DoubleArray {
        if(!requiresResample(g))return identity.copyOf()
        val q=g.quarterTurns.mod(4)
        if(q!=0) {
            val turn=when(q) {
                1->doubleArrayOf(0.0,-1.0,height-1.0,1.0,0.0,0.0,0.0,0.0,1.0)
                2->doubleArrayOf(-1.0,0.0,width-1.0,0.0,-1.0,height-1.0,0.0,0.0,1.0)
                else->doubleArrayOf(0.0,1.0,0.0,-1.0,0.0,width-1.0,0.0,0.0,1.0)
            }
            val (w,h)=frameSize(width,height,g)
            return multiply(matrix(w,h,g.copy(quarterTurns=0)),turn)
        }
        val cx=(width-1)/2.0;val cy=(height-1)/2.0;val a=g.rotation*PI/180.0;val c=cos(a);val s=sin(a)
        val rotation=doubleArrayOf(c,-s,0.0,s,c,0.0,0.0,0.0,1.0)
        val aspect=2.0.pow(g.aspect/100.0)
        val shape=scale(aspect*if(g.flipHorizontal)-1.0 else 1.0,(if(g.flipVertical)-1.0 else 1.0)/aspect)
        val perspective=doubleArrayOf(1.0,0.0,0.0,0.0,1.0,0.0,g.horizontal*.003/max(cx,.5),g.vertical*.003/max(cy,.5),1.0)
        val core=multiply(multiply(multiply(rotation,shape),perspective),translate(-cx,-cy))
        fun at(zoom:Double)=multiply(multiply(translate(cx,cy),scale(zoom,zoom)),core)
        fun fits(zoom:Double):Boolean {val inv=inverse(at(zoom));return listOf(0.0 to 0.0,(width-1.0) to 0.0,0.0 to (height-1.0),(width-1.0) to (height-1.0)).all {val (x,y)=point(inv,it.first,it.second);x>=-1e-8 && y>=-1e-8 && x<=width-1+1e-8 && y<=height-1+1e-8}}
        var zoom=g.scale/100.0
        if(g.autoCrop && !fits(zoom)){var lo=zoom;var hi=16.0;repeat(40){val mid=(lo+hi)/2;if(fits(mid))hi=mid else lo=mid};zoom=hi*(1+1e-8)}
        return at(zoom)
    }
    fun preview(source:Bitmap,g:Geometry):Bitmap {
        if(!requiresResample(g))return source
        val m=matrix(source.width,source.height,g)
        val edges=multiply(multiply(translate(.5,.5),m),translate(-.5,-.5))
        val canvasMatrix=Matrix().apply {setValues(FloatArray(9){edges[it].toFloat()})}
        val (width,height)=frameSize(source.width,source.height,g)
        return Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888).also {bitmap ->Canvas(bitmap).drawBitmap(source,canvasMatrix,Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))}
    }
}
