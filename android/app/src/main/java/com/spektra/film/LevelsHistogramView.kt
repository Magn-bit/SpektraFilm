package com.spektra.film

import android.content.Context
import android.graphics.*
import android.view.MotionEvent
import android.view.View
import kotlin.math.*

/** Input black / midpoint / white and output black / white share one aligned histogram. */
internal class LevelsHistogramView(context:Context):View(context) {
    var value=LevelChannel();set(v){field=v.canonical();invalidate()}
    var histogram=FloatArray(128);set(v){field=v;invalidate()}
    var channel=0;set(v){field=v;invalidate()}
    var onChange:((LevelChannel)->Unit)?=null
    var onStart:(()->Unit)?=null
    var onEnd:(()->Unit)?=null
    private val p=Paint(Paint.ANTI_ALIAS_FLAG);private val path=Path();private var handle=-1
    private val density=resources.displayMetrics.density
    private val pad=24*density
    init {isFocusable=true;contentDescription="色阶直方图，三个输入滑柄与两个输出滑柄；下方数值可精确输入"}
    private fun x(v:Float)=pad+(width-2*pad)*v
    private fun inputY()=height-62*density
    private fun outputY()=height-16*density
    private fun positions()=floatArrayOf(value.black,value.black+(value.white-value.black)*.5f.pow(value.gamma),value.white,value.outputBlack,value.outputWhite)
    override fun onDraw(c:Canvas) {
        super.onDraw(c);val top=12*density;val bottom=inputY()-16*density
        p.color=UiTheme.canvas;c.drawRoundRect(RectF(pad,top,width-pad,bottom),4*density,4*density,p)
        p.color=when(channel){1->0xffac6a60.toInt();2->0xff6f8e72.toInt();3->0xff718ca5.toInt();else->UiTheme.muted};p.alpha=160
        path.reset();path.moveTo(pad,bottom)
        histogram.forEachIndexed {i,v->path.lineTo(pad+(width-2*pad)*i/max(1,histogram.size-1),(bottom-v.coerceIn(0f,1f)*(bottom-top)))}
        path.lineTo(width-pad,bottom);path.close();c.drawPath(path,p);p.alpha=255
        p.color=UiTheme.line;p.strokeWidth=2*density;c.drawLine(pad,inputY(),width-pad,inputY(),p)
        p.shader=LinearGradient(pad,0f,width-pad,0f,Color.BLACK,Color.WHITE,Shader.TileMode.CLAMP)
        c.drawRect(pad,outputY()-5*density,width-pad,outputY()+5*density,p);p.shader=null
        val positions=positions()
        positions.forEachIndexed {i,v->
            val cy=if(i<3)inputY() else outputY()
            if(handle==i){p.color=UiTheme.accent;p.alpha=45;c.drawCircle(x(v),cy,20*density,p);p.alpha=255}
            path.reset();path.moveTo(x(v),cy-7*density);path.lineTo(x(v)-7*density,cy+7*density);path.lineTo(x(v)+7*density,cy+7*density);path.close()
            p.style=Paint.Style.FILL;p.color=when(i){0,3->0xff353630.toInt();2,4->Color.WHITE;else->0xff8b8d80.toInt()};c.drawPath(path,p)
            p.style=Paint.Style.STROKE;p.strokeWidth=1.2f*density;p.color=UiTheme.ink;c.drawPath(path,p);p.style=Paint.Style.FILL
        }
    }
    override fun onTouchEvent(e:MotionEvent):Boolean {
        if(!isEnabled)return false
        when(e.actionMasked) {
            MotionEvent.ACTION_DOWN->{val pts=positions();handle=pts.indices.minByOrNull {i->hypot(e.x-x(pts[i]),e.y-if(i<3)inputY() else outputY())}?:-1
                if(handle<0 || hypot(e.x-x(pts[handle]),e.y-if(handle<3)inputY() else outputY())>28*density){handle=-1;return false}
                parent?.requestDisallowInterceptTouchEvent(true);onStart?.invoke();invalidate();return true}
            MotionEvent.ACTION_MOVE->{if(handle<0)return false;val v=((e.x-pad)/(width-2*pad)).coerceIn(0f,1f)
                value=when(handle){0->value.copy(black=min(v,value.white-.001f));1->value.copy(gamma=(ln(((v-value.black)/(value.white-value.black)).coerceIn(.001f,.999f))/ln(.5f)).coerceIn(.1f,10f));2->value.copy(white=max(v,value.black+.001f));3->value.copy(outputBlack=min(v,value.outputWhite));else->value.copy(outputWhite=max(v,value.outputBlack))}.canonical()
                onChange?.invoke(value);return true}
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL->{if(handle<0)return false;handle=-1;onEnd?.invoke();parent?.requestDisallowInterceptTouchEvent(false);performClick();invalidate();return true}
        };return true
    }
    override fun performClick():Boolean{super.performClick();return true}
}
