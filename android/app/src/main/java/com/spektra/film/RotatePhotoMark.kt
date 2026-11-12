package com.spektra.film

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View

/** Lightweight native vector mark, with the same stroke as crop and app-bar symbols. */
internal class RotatePhotoMark(context:Context,private val clockwise:Boolean):View(context) {
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG).apply {style=Paint.Style.STROKE;strokeCap=Paint.Cap.ROUND;strokeJoin=Paint.Join.ROUND}
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas)
        val s=minOf(width,height)/24f;canvas.save();canvas.translate((width-24*s)/2,(height-24*s)/2);canvas.scale(s,s)
        if(!clockwise){canvas.translate(24f,0f);canvas.scale(-1f,1f)}
        paint.color=UiTheme.ink;paint.alpha=if(isEnabled)255 else 100;paint.strokeWidth=1.5f
        canvas.drawRoundRect(RectF(7f,10f,17f,19f),1.5f,1.5f,paint)
        canvas.drawArc(RectF(4f,3f,20f,19f),200f,215f,false,paint)
        val tip=Path().apply {moveTo(20.5f,7f);lineTo(20.1f,12f);lineTo(15.4f,10.9f)}
        canvas.drawPath(tip,paint);canvas.restore()
    }
}
