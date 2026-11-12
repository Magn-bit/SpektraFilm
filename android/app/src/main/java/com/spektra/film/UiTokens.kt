package com.spektra.film

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable

/** Four typography roles shared by controls; sizes are scaled pixels. */
object UiTokens {
    const val display=24f
    const val heading=18f
    const val body=14f
    const val caption=12f
    fun fontSize(requested:Float)=when {
        requested>=22f -> display
        requested>=17f -> heading
        requested>=13f -> body
        else -> caption
    }
}

/** Shared cool neutral surfaces and sage interaction states. */
object UiTheme {
    val background=0xFFFCFCFB.toInt()
    val surface=0xFFFFFFFF.toInt()
    val ink=0xFF252725.toInt()
    val muted=0xFF555E54.toInt()
    val line=0xFFD8DDD2.toInt()
    val accent=0xFF667C65.toInt()
    val accentText=0xFF66745E.toInt()
    val canvas=0xFFEBEEE9.toInt()
    val selection=0xFFEAF0E6.toInt()

    fun textColors(normal:Int=ink)=ColorStateList(
        arrayOf(intArrayOf(-android.R.attr.state_enabled),intArrayOf()),intArrayOf(muted,normal))
    fun toggleColors()=ColorStateList(
        arrayOf(intArrayOf(-android.R.attr.state_enabled),intArrayOf(android.R.attr.state_checked),intArrayOf()),
        intArrayOf(line,accentText,muted))
    fun accentColors()=ColorStateList(
        arrayOf(intArrayOf(-android.R.attr.state_enabled),intArrayOf()),intArrayOf(line,accent))
    fun trackColors()=ColorStateList(
        arrayOf(intArrayOf(-android.R.attr.state_enabled),intArrayOf(android.R.attr.state_checked),intArrayOf()),
        intArrayOf(line,accent,line))
    fun choiceTextColors()=ColorStateList(
        arrayOf(intArrayOf(android.R.attr.state_checked),intArrayOf()),intArrayOf(accentText,ink))

    fun controlBackground(context:Context,color:Int=surface,radius:Float=9f,border:Int=line,selected:Boolean=false):RippleDrawable {
        val density=context.resources.displayMetrics.density
        fun shape(fill:Int,stroke:Int,strokeDp:Float=1f)=GradientDrawable().apply {
            setColor(fill);cornerRadius=radius*density
            if(stroke!=Color.TRANSPARENT)setStroke((strokeDp*density+.5f).toInt(),stroke)
        }
        val states=StateListDrawable().apply {
            addState(intArrayOf(-android.R.attr.state_enabled),shape(canvas,line))
            addState(intArrayOf(android.R.attr.state_focused),shape(if(selected)selection else color,accentText,2f))
            addState(intArrayOf(android.R.attr.state_checked),shape(selection,Color.TRANSPARENT))
            addState(intArrayOf(android.R.attr.state_selected),shape(selection,accent))
            addState(intArrayOf(),shape(if(selected)selection else color,if(selected)accent else border))
        }
        return RippleDrawable(ColorStateList.valueOf(0x26667C65),states,null)
    }
}
