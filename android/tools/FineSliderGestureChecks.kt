package com.spektra.film

/** JVM host checks; no Android device, test package or render is required. */
fun main() {
    val gesture=FineSliderGesture(8f)
    fun begin(onThumb:Boolean=true,rtl:Boolean=false) = gesture.begin(100f,24f,onThumb,6000,200,rtl)
    begin()
    check(gesture.isTap && !gesture.active)
    check(gesture.activate(3000))
    check(!gesture.isTap && gesture.active) // A long hold cannot become a reset tap.
    check(gesture.progressAt(100f)==3000) // Activating never jumps the value.
    check(gesture.progressAt(101f)==3003) // Direct travel is 30 ticks; fine is 3.
    check(gesture.progressAt(90f)==2970)
    check(gesture.progressAt(10000f)==6000 && gesture.progressAt(-10000f)==0)
    gesture.end()
    check(!gesture.active && !gesture.isTap && !gesture.activate(3000))
    begin();gesture.move(103f,26f);check(gesture.activate(3007))
    check(gesture.progressAt(103f)==3007) // Jitter before the hold uses the live anchor.
    gesture.end();begin();gesture.move(109f,24f)
    check(!gesture.isTap && !gesture.activate(3000)) // A normal drag cannot become fine.
    gesture.end();begin();gesture.move(100f,33f)
    check(!gesture.activate(3000)) // A vertical scroll cannot become fine.
    gesture.end();begin(onThumb=false);check(!gesture.activate(3000))
    gesture.end();begin(rtl=true);check(gesture.activate(3000))
    check(gesture.progressAt(110f)==2970)
    gesture.end();begin();gesture.cancelHold();check(!gesture.activate(3000))
    gesture.end();begin();check(gesture.isTap)
    println("OK: fine slider anchor, 1/10 sensitivity, endpoints, RTL, tap/hold/drag/scroll/cancel state")
}
