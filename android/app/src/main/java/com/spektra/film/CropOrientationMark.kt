package com.spektra.film

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/** Two rectangles communicate swapping aspect, without ambiguous orientation text. */
internal class CropOrientationMark(context:Context):View(context) {
    private val p=Paint(Paint.ANTI_ALIAS_FLAG).apply {style=Paint.Style.STROKE;strokeCap=Paint.Cap.ROUND}
    init {importantForAccessibility=IMPORTANT_FOR_ACCESSIBILITY_NO}
    override fun onDraw(c:Canvas) {
        val u=width/24f;p.strokeWidth=1.45f*u;p.color=UiTheme.ink
        c.drawRoundRect(RectF(2*u,3*u,15*u,12*u),1.5f*u,1.5f*u,p)
        p.color=UiTheme.accent;c.drawRoundRect(RectF(14*u,10*u,22*u,22*u),1.5f*u,1.5f*u,p)
        c.drawLine(5*u,17*u,10*u,17*u,p);c.drawLine(8*u,15*u,10*u,17*u,p);c.drawLine(8*u,19*u,10*u,17*u,p)
    }
}
