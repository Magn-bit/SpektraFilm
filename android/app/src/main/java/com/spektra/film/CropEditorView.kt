package com.spektra.film

import android.content.Context
import android.graphics.*
import android.os.Bundle
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import kotlin.math.*

/** Independent draft in full oriented source coordinates; never edits image pixels. */
class CropEditorView(context:Context,val image:Bitmap,
                     private val sourceWidth:Int=image.width,private val sourceHeight:Int=image.height):View(context) {
    var crop=CropBounds()
        private set
    var onCropChange:((CropBounds)->Unit)?=null
    private var aspect:Float?=null
    private val frame=RectF()
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val density=resources.displayMetrics.density
    private var handle=-1
    private var origin=PointF()
    private var initial=CropBounds()
    init {isFocusable=true;isClickable=true;contentDescription="裁切预览。拖动框内移动，拖动四角和边缘调整范围；方向键移动，加减键缩放。"}
    fun setCrop(value:CropBounds) {
        val left=value.left.coerceIn(0f,.999f);val top=value.top.coerceIn(0f,.999f)
        crop=CropBounds(left,top,value.right.coerceIn(left+.001f,1f),value.bottom.coerceIn(top+.001f,1f))
        invalidate();onCropChange?.invoke(crop)
    }
    private fun normalizedAspect()=aspect?.let {it*sourceHeight/sourceWidth}
    fun setAspect(ratio:Float?) {
        aspect=ratio?.takeIf {it.isFinite() && it>0f}
        val r=normalizedAspect() ?: return
        // Preserve area and center while changing ratios, rather than shrinking
        // the rectangle again on every successive ratio choice.
        val area=(crop.right-crop.left)*(crop.bottom-crop.top)
        var w=sqrt(area*r);var h=w/r;val fit=max(1f,max(w,h));w/=fit;h/=fit
        val cx=(crop.left+crop.right)/2;val cy=(crop.top+crop.bottom)/2
        val x=(cx-w/2).coerceIn(0f,1-w);val y=(cy-h/2).coerceIn(0f,1-h)
        setCrop(CropBounds(x,y,x+w,y+h))
    }
    private fun updateFrame() {
        val p=24*density;val scale=min(max(1f,width-p*2)/sourceWidth,max(1f,height-p*2)/sourceHeight)
        val w=sourceWidth*scale;val h=sourceHeight*scale
        frame.set((width-w)/2,(height-h)/2,(width+w)/2,(height+h)/2)
    }
    private fun cropRect()=RectF(frame.left+crop.left*frame.width(),frame.top+crop.top*frame.height(),frame.left+crop.right*frame.width(),frame.top+crop.bottom*frame.height())
    private fun handles(r:RectF)=listOf(PointF(r.left,r.top),PointF(r.right,r.top),PointF(r.left,r.bottom),PointF(r.right,r.bottom),
        PointF(r.left,r.centerY()),PointF(r.right,r.centerY()),PointF(r.centerX(),r.top),PointF(r.centerX(),r.bottom))
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);if(image.isRecycled)return
        updateFrame();paint.style=Paint.Style.FILL;paint.color=Color.WHITE;paint.alpha=255;canvas.drawBitmap(image,null,frame,paint)
        val r=cropRect();paint.color=Color.BLACK;paint.alpha=132
        canvas.drawRect(frame.left,frame.top,frame.right,r.top,paint);canvas.drawRect(frame.left,r.bottom,frame.right,frame.bottom,paint)
        canvas.drawRect(frame.left,r.top,r.left,r.bottom,paint);canvas.drawRect(r.right,r.top,frame.right,r.bottom,paint)
        paint.color=Color.WHITE;paint.alpha=230;paint.style=Paint.Style.STROKE;paint.strokeWidth=density;canvas.drawRect(r,paint)
        paint.alpha=if(handle>=0)140 else 80;paint.strokeWidth=.75f*density
        for(i in 1..2){val f=i/3f;canvas.drawLine(r.left+r.width()*f,r.top,r.left+r.width()*f,r.bottom,paint);canvas.drawLine(r.left,r.top+r.height()*f,r.right,r.top+r.height()*f,paint)}
        paint.alpha=255;paint.strokeWidth=2.5f*density;paint.strokeCap=Paint.Cap.ROUND
        val arm=min(14*density,min(r.width(),r.height())*.2f)
        handles(r).forEachIndexed {index,p ->
            if(index<4){val dx=if(index%2==0)arm else -arm;val dy=if(index<2)arm else -arm;canvas.drawLine(p.x,p.y,p.x+dx,p.y,paint);canvas.drawLine(p.x,p.y,p.x,p.y+dy,paint)}
            else if(index<6)canvas.drawLine(p.x,p.y-arm*.55f,p.x,p.y+arm*.55f,paint)
            else canvas.drawLine(p.x-arm*.55f,p.y,p.x+arm*.55f,p.y,paint)
            if(index==handle){paint.style=Paint.Style.FILL;paint.alpha=32;canvas.drawCircle(p.x,p.y,22*density,paint);paint.style=Paint.Style.STROKE;paint.alpha=255}
        }
        paint.strokeCap=Paint.Cap.BUTT;paint.style=Paint.Style.FILL
    }
    private fun point(x:Float,y:Float)=PointF(((x-frame.left)/frame.width()).coerceIn(0f,1f),((y-frame.top)/frame.height()).coerceIn(0f,1f))
    private fun resize(p:PointF) {
        val minimum=.015f
        if(handle in 0..3){
            val left=handle%2==0;val top=handle<2
            val ax=if(left)initial.right else initial.left;val ay=if(top)initial.bottom else initial.top
            val availableW=if(left)ax else 1-ax;val availableH=if(top)ay else 1-ay
            var w=(if(left)ax-p.x else p.x-ax).coerceIn(minimum,max(minimum,availableW))
            var h=(if(top)ay-p.y else p.y-ay).coerceIn(minimum,max(minimum,availableH))
            normalizedAspect()?.let {r ->w=max(w,h*r).coerceAtMost(min(availableW,availableH*r));h=w/r}
            val x=if(left)ax-w else ax;val y=if(top)ay-h else ay
            setCrop(CropBounds(x,y,x+w,y+h));return
        }
        val cx=(initial.left+initial.right)/2;val cy=(initial.top+initial.bottom)/2;val r=normalizedAspect()
        if(handle in 4..5){
            val left=handle==4;val anchor=if(left)initial.right else initial.left
            var w=(if(left)anchor-p.x else p.x-anchor).coerceIn(minimum,max(minimum,if(left)anchor else 1-anchor))
            var h=initial.bottom-initial.top
            if(r!=null){w=min(w,2*min(cy,1-cy)*r);h=w/r}
            val x=if(left)anchor-w else anchor;setCrop(CropBounds(x,cy-h/2,x+w,cy+h/2))
        }else{
            val top=handle==6;val anchor=if(top)initial.bottom else initial.top
            var h=(if(top)anchor-p.y else p.y-anchor).coerceIn(minimum,max(minimum,if(top)anchor else 1-anchor))
            var w=initial.right-initial.left
            if(r!=null){h=min(h,2*min(cx,1-cx)/r);w=h*r}
            val y=if(top)anchor-h else anchor;setCrop(CropBounds(cx-w/2,y,cx+w/2,y+h))
        }
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        updateFrame();if(frame.width()<=0 || frame.height()<=0)return false
        val p=point(event.x,event.y)
        when(event.actionMasked){
            MotionEvent.ACTION_DOWN -> {
                val r=cropRect();val targets=handles(r);val nearest=targets.indices.minByOrNull {hypot(targets[it].x-event.x,targets[it].y-event.y)} ?: return false
                handle=if(hypot(targets[nearest].x-event.x,targets[nearest].y-event.y)<=24*density)nearest else if(r.contains(event.x,event.y))8 else -1
                if(handle<0)return false
                initial=crop;origin=p;isPressed=true;parent?.requestDisallowInterceptTouchEvent(true);invalidate();return true
            }
            MotionEvent.ACTION_MOVE -> {
                if(handle==8){val dx=(p.x-origin.x).coerceIn(-initial.left,1-initial.right);val dy=(p.y-origin.y).coerceIn(-initial.top,1-initial.bottom);setCrop(CropBounds(initial.left+dx,initial.top+dy,initial.right+dx,initial.bottom+dy))}
                else if(handle>=0)resize(p)
                return handle>=0
            }
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL -> {
                if(event.actionMasked==MotionEvent.ACTION_CANCEL)setCrop(initial)
                handle=-1;isPressed=false;parent?.requestDisallowInterceptTouchEvent(false);invalidate();performClick();return true
            }
        };return true
    }
    private fun nudge(dx:Float,dy:Float){val x=dx.coerceIn(-crop.left,1-crop.right);val y=dy.coerceIn(-crop.top,1-crop.bottom);setCrop(CropBounds(crop.left+x,crop.top+y,crop.right+x,crop.bottom+y))}
    private fun scaleCrop(factor:Float){
        val cx=(crop.left+crop.right)/2;val cy=(crop.top+crop.bottom)/2
        val previousW=crop.right-crop.left;val previousH=crop.bottom-crop.top
        val effective=max(factor,max(.015f/previousW,.015f/previousH))
        var w=previousW*effective;var h=previousH*effective
        val fit=max(1f,max(w,h));w/=fit;h/=fit;val x=(cx-w/2).coerceIn(0f,1-w);val y=(cy-h/2).coerceIn(0f,1-h)
        setCrop(CropBounds(x,y,x+w,y+h))
    }
    override fun onKeyDown(keyCode:Int,event:KeyEvent):Boolean{
        val step=if(event.isShiftPressed).002f else .02f
        when(keyCode){
            KeyEvent.KEYCODE_DPAD_LEFT ->nudge(-step,0f);KeyEvent.KEYCODE_DPAD_RIGHT ->nudge(step,0f)
            KeyEvent.KEYCODE_DPAD_UP ->nudge(0f,-step);KeyEvent.KEYCODE_DPAD_DOWN ->nudge(0f,step)
            KeyEvent.KEYCODE_PLUS,KeyEvent.KEYCODE_EQUALS ->scaleCrop(.95f);KeyEvent.KEYCODE_MINUS ->scaleCrop(1.05f)
            else ->return super.onKeyDown(keyCode,event)
        };return true
    }
    override fun onInitializeAccessibilityNodeInfo(info:AccessibilityNodeInfo){
        super.onInitializeAccessibilityNodeInfo(info)
        listOf("向左移动裁切框","向右移动裁切框","向上移动裁切框","向下移动裁切框","缩小裁切范围","扩大裁切范围").forEachIndexed {i,label ->info.addAction(AccessibilityNodeInfo.AccessibilityAction(0x01020001+i,label))}
    }
    override fun performAccessibilityAction(action:Int,arguments:Bundle?):Boolean{
        when(action){0x01020001 ->nudge(-.02f,0f);0x01020002 ->nudge(.02f,0f);0x01020003 ->nudge(0f,-.02f);0x01020004 ->nudge(0f,.02f);0x01020005 ->scaleCrop(.95f);0x01020006 ->scaleCrop(1.05f);else ->return super.performAccessibilityAction(action,arguments)};return true
    }
    override fun performClick():Boolean{super.performClick();return true}
}
