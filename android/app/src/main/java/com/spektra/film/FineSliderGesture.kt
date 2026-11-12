package com.spektra.film

import kotlin.math.abs
import kotlin.math.roundToInt

/** Pure gesture state used by the Android View and checked on the host. */
internal class FineSliderGesture(private val slop:Float) {
    var active=false
        private set
    private var held=false
    private var thumb=false
    private var moved=false
    private var downX=0f
    private var downY=0f
    private var latestX=0f
    private var anchorX=0f
    private var anchorProgress=0
    private var maximum=1
    private var trackWidth=1f
    private var direction=1f
    val isTap:Boolean get()=held && thumb && !moved && !active
    fun begin(x:Float,y:Float,onThumb:Boolean,max:Int,width:Int,rtl:Boolean) {
        end();held=true;thumb=onThumb;downX=x;downY=y;latestX=x
        maximum=max.coerceAtLeast(1);trackWidth=width.coerceAtLeast(1).toFloat();direction=if(rtl)-1f else 1f
    }
    fun move(x:Float,y:Float) {
        latestX=x
        if(abs(x-downX)>slop || abs(y-downY)>slop)moved=true
    }
    fun activate(currentProgress:Int):Boolean {
        if(!held || !thumb || moved || active)return false
        active=true;anchorX=latestX;anchorProgress=currentProgress.coerceIn(0,maximum)
        return true
    }
    fun progressAt(x:Float):Int =
        (anchorProgress+(x-anchorX)/trackWidth*maximum*.1f*direction).roundToInt().coerceIn(0,maximum)
    fun cancelHold() {thumb=false;moved=true}
    fun end() {active=false;held=false;thumb=false;moved=false}
}
