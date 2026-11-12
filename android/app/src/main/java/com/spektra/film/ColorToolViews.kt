package com.spektra.film

import android.content.Context
import android.graphics.*
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import kotlin.math.*

/** Editable PCHIP point curve; the displayed interpolation matches the shared renderer. */
class CurveEditorView(context:Context):View(context) {
    var histogram:FloatArray?=null
    var points:List<CurvePoint> = listOf(CurvePoint(0f,0f),CurvePoint(1f,1f))
        set(value) { field=value;selected=selected.coerceAtMost(value.lastIndex);invalidate() }
    var curveColor=Color.rgb(37,47,40)
    var onChange:((List<CurvePoint>)->Unit)?=null
    var onGestureStart:(()->Unit)?=null
    var onGestureEnd:(()->Unit)?=null
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG)
    private val plot=RectF()
    private var selected=-1
    private val density=resources.displayMetrics.density
    init { isFocusable=true;contentDescription="色彩曲线，轻点增加控制点，拖动调整；方向键微调所选点" }
    private fun bounds() { val p=22*density;plot.set(p,p,width-p,height-p) }
    override fun onDraw(canvas:Canvas) {
        bounds();paint.color=Color.rgb(247,249,247);paint.style=Paint.Style.FILL
        canvas.drawRoundRect(plot,6*density,6*density,paint)
        histogram?.takeIf {it.isNotEmpty()}?.let {bins ->
            val path=Path().apply {moveTo(plot.left,plot.bottom)}
            bins.forEachIndexed {i,value ->path.lineTo(plot.left+(i+.5f)/bins.size*plot.width(),plot.bottom-value.coerceIn(0f,1f)*plot.height()*.72f)}
            path.lineTo(plot.right,plot.bottom);path.close();paint.color=0x346b7768;canvas.drawPath(path,paint)
        }
        paint.style=Paint.Style.STROKE;paint.strokeWidth=density;paint.color=Color.rgb(222,228,222)
        for(i in 1..3) { val f=i/4f;canvas.drawLine(plot.left+plot.width()*f,plot.top,plot.left+plot.width()*f,plot.bottom,paint);canvas.drawLine(plot.left,plot.top+plot.height()*f,plot.right,plot.top+plot.height()*f,paint) }
        paint.color=Color.rgb(206,214,206);canvas.drawLine(plot.left,plot.bottom,plot.right,plot.top,paint)
        val path=Path()
        for(i in 0..160) { val x=i/160f;val y=interpolate(points,x).coerceIn(0f,1f);if(i==0)path.moveTo(plot.left,plot.bottom-y*plot.height()) else path.lineTo(plot.left+x*plot.width(),plot.bottom-y*plot.height()) }
        paint.color=curveColor;paint.strokeWidth=1.75f*density;canvas.drawPath(path,paint)
        points.forEachIndexed { index,p ->
            val x=plot.left+p.x*plot.width();val y=plot.bottom-p.y*plot.height()
            paint.style=Paint.Style.FILL;paint.color=Color.WHITE;canvas.drawCircle(x,y,(if(index==selected)6f else 4.5f)*density,paint)
            paint.style=Paint.Style.STROKE;paint.color=curveColor;paint.strokeWidth=1.5f*density;canvas.drawCircle(x,y,(if(index==selected)6f else 4.5f)*density,paint)
        }
        paint.style=Paint.Style.FILL
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(!isEnabled)return false
        bounds()
        when(event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if(!RectF(plot).apply { inset(-22*density,-22*density) }.contains(event.x,event.y))return false
                onGestureStart?.invoke();parent?.requestDisallowInterceptTouchEvent(true)
                selected=points.indices.minByOrNull { hypot(plot.left+points[it].x*plot.width()-event.x,plot.bottom-points[it].y*plot.height()-event.y) } ?: -1
                if(selected>=0 && hypot(plot.left+points[selected].x*plot.width()-event.x,plot.bottom-points[selected].y*plot.height()-event.y)>22*density && points.size<16) {
                    val p=CurvePoint(((event.x-plot.left)/plot.width()).coerceIn(.015f,.985f),((plot.bottom-event.y)/plot.height()).coerceIn(0f,1f))
                    if(points.none { abs(it.x-p.x)<.015f }) { points=(points+p).sortedBy { it.x };selected=points.indexOf(p);onChange?.invoke(points) }
                }
                requestFocus();move(event.x,event.y);return true
            }
            MotionEvent.ACTION_MOVE -> { move(event.x,event.y);return true }
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL -> { parent?.requestDisallowInterceptTouchEvent(false);onGestureEnd?.invoke();performClick();return true }
        }
        return true
    }
    private fun move(x:Float,y:Float) {
        if(selected !in points.indices)return
        val p=points[selected]
        val nx=if(selected==0 || selected==points.lastIndex)p.x else ((x-plot.left)/plot.width()).coerceIn(points[selected-1].x+.005f,points[selected+1].x-.005f)
        val ny=((plot.bottom-y)/plot.height()).coerceIn(0f,1f)
        val changed=points.toMutableList().apply { set(selected,CurvePoint(nx,ny)) }.toList()
        if(changed!=points) { points=changed;onChange?.invoke(changed) }
    }
    fun removeSelected():Boolean {
        if(selected<=0 || selected>=points.lastIndex)return false
        points=points.filterIndexed { index,_ -> index!=selected };selected=-1;onChange?.invoke(points);return true
    }
    override fun onKeyDown(keyCode:Int,event:KeyEvent):Boolean {
        if(selected !in points.indices)selected=0
        val p=points[selected]
        val dx=when(keyCode) { KeyEvent.KEYCODE_DPAD_LEFT->-.01f;KeyEvent.KEYCODE_DPAD_RIGHT->.01f;else->0f }
        val dy=when(keyCode) { KeyEvent.KEYCODE_DPAD_UP->.01f;KeyEvent.KEYCODE_DPAD_DOWN->-.01f;else->0f }
        if(dx!=0f || dy!=0f) { bounds();move(plot.left+(p.x+dx)*plot.width(),plot.bottom-(p.y+dy)*plot.height());return true }
        return super.onKeyDown(keyCode,event)
    }
    override fun performClick():Boolean { super.performClick();return true }
    companion object {
        internal fun interpolate(points:List<CurvePoint>,x:Float):Float {
            if(points.size<2)return x
            val n=points.size;val h=FloatArray(n-1) { points[it+1].x-points[it].x };val d=FloatArray(n-1) { (points[it+1].y-points[it].y)/h[it] }
            val m=FloatArray(n)
            if(n==2) { m[0]=d[0];m[1]=d[0] } else {
                fun endpoint(a:Float,b:Float,da:Float,db:Float):Float {
                    val v=((2*a+b)*da-a*db)/(a+b)
                    return if(v*da<=0f)0f else if(da*db<0f && abs(v)>3*abs(da))3*da else v
                }
                m[0]=endpoint(h[0],h[1],d[0],d[1]);m[n-1]=endpoint(h[n-2],h[n-3],d[n-2],d[n-3])
                for(i in 1 until n-1) { if(d[i-1]*d[i]>0f) { val w1=2*h[i]+h[i-1];val w2=h[i]+2*h[i-1];m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i]) } }
            }
            val i=(0 until n-1).lastOrNull { x>=points[it].x } ?: 0
            val t=((x-points[i].x)/h[i]).coerceIn(0f,1f);val t2=t*t;val t3=t2*t
            return (2*t3-3*t2+1)*points[i].y+(t3-2*t2+t)*h[i]*m[i]+(-2*t3+3*t2)*points[i+1].y+(t3-t2)*h[i]*m[i+1]
        }
    }
}

/** One tonal wheel at a time; angle is hue and distance from centre is saturation. */
class GradingWheelView(context:Context):View(context) {
    var grade=TonalGrade()
        set(value) { field=value;invalidate() }
    var onChange:((TonalGrade)->Unit)?=null
    var onGestureStart:(()->Unit)?=null
    var onGestureEnd:(()->Unit)?=null
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG)
    private val density=resources.displayMetrics.density
    private var radius=1f
    init { isFocusable=true;contentDescription="色轮：圆周方向选择色相，离圆心越远饱和度越高" }
    override fun onDraw(canvas:Canvas) {
        val cx=width/2f;val cy=height/2f;radius=max(1f,min(width,height)/2f-14*density)
        paint.shader=SweepGradient(cx,cy,intArrayOf(Color.RED,Color.YELLOW,Color.GREEN,Color.CYAN,Color.BLUE,Color.MAGENTA,Color.RED),null)
        canvas.drawCircle(cx,cy,radius,paint)
        paint.shader=RadialGradient(cx,cy,radius,intArrayOf(Color.rgb(246,247,245),Color.TRANSPARENT),null,Shader.TileMode.CLAMP)
        canvas.drawCircle(cx,cy,radius,paint);paint.shader=null
        val angle=grade.hue*PI/180;val r=grade.saturation/100*radius
        val x=cx+cos(angle).toFloat()*r;val y=cy+sin(angle).toFloat()*r
        paint.color=Color.WHITE;paint.style=Paint.Style.STROKE;paint.strokeWidth=3*density;canvas.drawCircle(x,y,6*density,paint)
        paint.color=Color.rgb(34,42,36);paint.strokeWidth=density;canvas.drawCircle(x,y,7.5f*density,paint);paint.style=Paint.Style.FILL
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(!isEnabled)return false
        when(event.actionMasked) {
            MotionEvent.ACTION_DOWN -> { onGestureStart?.invoke();parent?.requestDisallowInterceptTouchEvent(true);choose(event.x,event.y);return true }
            MotionEvent.ACTION_MOVE -> { choose(event.x,event.y);return true }
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL -> { parent?.requestDisallowInterceptTouchEvent(false);onGestureEnd?.invoke();performClick();return true }
        }
        return true
    }
    private fun choose(x:Float,y:Float) {
        val dx=x-width/2f;val dy=y-height/2f
        val hue=((atan2(dy,dx)*180/PI+360)%360).toFloat();val saturation=(hypot(dx,dy)/radius*100).coerceIn(0f,100f)
        grade=grade.copy(hue=hue,saturation=saturation);onChange?.invoke(grade)
    }
    override fun performClick():Boolean { super.performClick();return true }
}
