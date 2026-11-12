package com.spektra.film

import android.content.Context
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Color
import android.content.res.ColorStateList
import android.view.GestureDetector
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ViewConfiguration
import android.widget.SeekBar
import kotlin.math.abs
import kotlin.math.roundToInt

/** Native direct dragging, plus a deliberate long-press relative fine gesture. */
internal class PrecisionSeekBar(context:Context):SeekBar(context) {
    var resetCurrent:(()->Unit)?=null
    var colorStops:IntArray?=null
        set(value) {field=value;if(value!=null){progressTintList=ColorStateList.valueOf(Color.TRANSPARENT);progressBackgroundTintList=ColorStateList.valueOf(Color.TRANSPARENT)};invalidate()}
    var referenceFraction:Float?=null
    private val trackPaint=Paint(Paint.ANTI_ALIAS_FLAG)
    private val fine=FineSliderGesture(ViewConfiguration.get(context).scaledTouchSlop.toFloat())
    private var listener:OnSeekBarChangeListener?=null
    private var callbacksSuppressed=false
    private var tracking=false
    private var lastTapOnThumb=false
    private var downOnThumb=false
    private var downTime=0L
    private var resetting=false
    private var downX=0f
    private var downY=0f
    private var scrolling=false
    private var downProgress=0
    private val touchSlop=ViewConfiguration.get(context).scaledTouchSlop
    private val detector=GestureDetector(context,object:GestureDetector.SimpleOnGestureListener() {
        override fun onDown(event:MotionEvent)=true
        override fun onLongPress(event:MotionEvent) {
            if(!isEnabled || resetting || !fine.activate(progress))return
            lastTapOnThumb=false
            // Native SeekBar may still be waiting for its scrolling-container
            // slop. Cancel it, then own exactly one tracking session explicitly.
            if(!tracking) {tracking=true;listener?.onStartTrackingTouch(this@PrecisionSeekBar)}
            parent?.requestDisallowInterceptTouchEvent(true);isPressed=true
            performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
            announceForAccessibility("精细调整，当前灵敏度十分之一")
        }
        override fun onDoubleTap(event:MotionEvent):Boolean {
            if(lastTapOnThumb && downOnThumb && !fine.active) {
                resetting=true;lastTapOnThumb=false;fine.end()
                cancelNative(event);stopTracking();resetCurrent?.invoke()
            }
            return resetting
        }
    })
    init {
        tooltipText="长按圆点微调，双击恢复默认值"
        super.setOnSeekBarChangeListener(object:OnSeekBarChangeListener {
            override fun onProgressChanged(slider:SeekBar,value:Int,fromUser:Boolean) {
                if(!callbacksSuppressed)listener?.onProgressChanged(slider,value,fromUser)
            }
            override fun onStartTrackingTouch(slider:SeekBar) {
                if(!callbacksSuppressed && !tracking) {tracking=true;listener?.onStartTrackingTouch(slider)}
            }
            override fun onStopTrackingTouch(slider:SeekBar) {if(!callbacksSuppressed)stopTracking()}
        })
    }
    override fun setOnSeekBarChangeListener(value:OnSeekBarChangeListener?) {listener=value}
    override fun onDraw(canvas:Canvas) {
        val density=resources.displayMetrics.density
        colorStops?.let {colors ->
            trackPaint.shader=LinearGradient(paddingLeft.toFloat(),0f,(width-paddingRight).toFloat(),0f,colors,null,Shader.TileMode.CLAMP)
            trackPaint.alpha=if(isEnabled)255 else 80
            canvas.drawRoundRect(paddingLeft.toFloat(),height/2f-2*density,(width-paddingRight).toFloat(),height/2f+2*density,2*density,2*density,trackPaint)
            trackPaint.shader=null;trackPaint.alpha=255
        }
        referenceFraction?.let {fraction ->
            val x=paddingLeft+(width-paddingLeft-paddingRight)*fraction
            trackPaint.color=UiTheme.muted;trackPaint.strokeWidth=density
            canvas.drawLine(x,height/2f-5*density,x,height/2f+5*density,trackPaint)
        }
        super.onDraw(canvas)
    }
    private fun stopTracking() {
        if(tracking) {tracking=false;listener?.onStopTrackingTouch(this)}
        parent?.requestDisallowInterceptTouchEvent(false);isPressed=false
    }
    private fun cancelNative(event:MotionEvent) {
        val cancel=MotionEvent.obtain(event).apply {action=MotionEvent.ACTION_CANCEL}
        callbacksSuppressed=true
        try {super.onTouchEvent(cancel)} finally {callbacksSuppressed=false;cancel.recycle()}
    }
    private fun onThumb(event:MotionEvent):Boolean {
        val fraction=progress.toFloat()/max.coerceAtLeast(1)
        val x=paddingLeft+(width-paddingLeft-paddingRight)*(if(layoutDirection==LAYOUT_DIRECTION_RTL)1f-fraction else fraction)
        return abs(event.x-x)<=24*resources.displayMetrics.density && abs(event.y-height/2f)<=24*resources.displayMetrics.density
    }
    private fun directProgress(x:Float) {
        var fraction=((x-paddingLeft)/(width-paddingLeft-paddingRight).coerceAtLeast(1)).coerceIn(0f,1f)
        if(layoutDirection==LAYOUT_DIRECTION_RTL)fraction=1f-fraction
        setUserProgress((fraction*max).roundToInt())
    }
    private fun setUserProgress(next:Int) {
        if(next!=progress) {
            callbacksSuppressed=true
            try {progress=next} finally {callbacksSuppressed=false}
            listener?.onProgressChanged(this,next,true)
        }
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(!isEnabled) {fine.end();stopTracking();return false}
        when(event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX=event.x;downY=event.y;downProgress=progress;scrolling=false
                downOnThumb=onThumb(event);downTime=event.eventTime
                fine.begin(event.x,event.y,downOnThumb,max,width-paddingLeft-paddingRight,layoutDirection==LAYOUT_DIRECTION_RTL)
            }
            MotionEvent.ACTION_MOVE -> fine.move(event.x,event.y)
            MotionEvent.ACTION_POINTER_DOWN -> {fine.cancelHold();lastTapOnThumb=false}
        }
        detector.onTouchEvent(event)
        if(resetting) {
            if(event.actionMasked==MotionEvent.ACTION_UP || event.actionMasked==MotionEvent.ACTION_CANCEL) {resetting=false;fine.end();stopTracking()}
            return true
        }
        if(fine.active) {
            when(event.actionMasked) {
                MotionEvent.ACTION_MOVE,MotionEvent.ACTION_UP -> {
                    val next=fine.progressAt(event.x)
                    if(next!=progress) {
                        callbacksSuppressed=true
                        try {progress=next} finally {callbacksSuppressed=false}
                        listener?.onProgressChanged(this,next,true)
                    }
                }
            }
            if(event.actionMasked==MotionEvent.ACTION_UP || event.actionMasked==MotionEvent.ACTION_CANCEL) {fine.end();stopTracking()}
            return true
        }
        when(event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                // SeekBar normally defers its first drag inside a ScrollView.
                // Claim the gesture immediately so a single contact edits it.
                tracking=true;listener?.onStartTrackingTouch(this)
                parent?.requestDisallowInterceptTouchEvent(true);isPressed=true
                if(!downOnThumb)directProgress(event.x)
            }
            MotionEvent.ACTION_MOVE -> {
                val dx=abs(event.x-downX);val dy=abs(event.y-downY)
                if(!downOnThumb && dy>touchSlop && dy>dx*1.4f) {
                    scrolling=true;fine.cancelHold();setUserProgress(downProgress);stopTracking()
                    parent?.requestDisallowInterceptTouchEvent(false)
                } else if(!scrolling)directProgress(event.x)
            }
        }
        if(event.actionMasked==MotionEvent.ACTION_UP) {
            lastTapOnThumb=fine.isTap && event.eventTime-downTime<ViewConfiguration.getLongPressTimeout()
            if(!scrolling && !lastTapOnThumb)directProgress(event.x)
            fine.end();stopTracking();performClick()
        } else if(event.actionMasked==MotionEvent.ACTION_CANCEL) {lastTapOnThumb=false;fine.end();stopTracking()}
        return true
    }
    override fun performClick():Boolean {super.performClick();return true}
    override fun onWindowFocusChanged(hasWindowFocus:Boolean) {
        super.onWindowFocusChanged(hasWindowFocus)
        if(!hasWindowFocus) {fine.end();lastTapOnThumb=false;stopTracking()}
    }
    override fun onDetachedFromWindow() {
        fine.end();lastTapOnThumb=false;stopTracking();super.onDetachedFromWindow()
    }
}
