package com.spektra.film

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View
import org.json.JSONObject
import kotlin.math.*

internal class LatitudeHistogramView(context:Context,histogram:JSONObject,private val low:Double,private val high:Double):View(context) {
    private val lo=histogram.optDouble("lo_ev",-16.0)
    private val hi=histogram.optDouble("hi_ev",16.0)
    private val bins=histogram.optJSONArray("fractions")?.let {j ->DoubleArray(j.length()){j.optDouble(it,0.0)}} ?: doubleArrayOf()
    private val p=Paint(Paint.ANTI_ALIAS_FLAG)
    init {contentDescription="场景亮度分布，胶片有效范围从${String.format(java.util.Locale.US,"%.1f",low)}到${String.format(java.util.Locale.US,"%.1f",high)} EV"}
    override fun onDraw(c:Canvas) {
        val d=resources.displayMetrics.density;val left=8*d;val top=8*d;val right=width-8*d;val bottom=height-26*d
        fun x(ev:Double)=(left+(ev-lo)/(hi-lo)*(right-left)).toFloat().coerceIn(left,right)
        p.color=UiTheme.canvas;c.drawRoundRect(left,top,right,bottom,6*d,6*d,p)
        p.color=UiTheme.selection;c.drawRect(x(low),top,x(high),bottom,p)
        val peak=(bins.maxOrNull() ?: 1.0).coerceAtLeast(1e-12)
        val path=Path().apply {moveTo(left,bottom)}
        bins.forEachIndexed {i,v ->path.lineTo(left+(i+.5f)/max(1,bins.size)*(right-left),(bottom-sqrt(v/peak)*(bottom-top-8*d)).toFloat())}
        path.lineTo(right,bottom);path.close();p.color=0x99687a60.toInt();c.drawPath(path,p)
        p.color=UiTheme.accent;p.strokeWidth=d
        c.drawLine(x(low),top,x(low),bottom,p);c.drawLine(x(high),top,x(high),bottom,p)
        p.typeface=InterfaceTypography.load(context);p.textSize=11*resources.displayMetrics.scaledDensity;p.color=UiTheme.muted
        for(ev in -12..12 step 6)if(ev>=lo && ev<=hi){p.textAlign=Paint.Align.CENTER;c.drawText("${if(ev>0)"+" else ""}$ev",x(ev.toDouble()),height-7*d,p)}
    }
}
