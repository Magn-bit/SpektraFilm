package com.spektra.film

import android.content.Context
import android.graphics.Typeface

/** Shared asset preserves Chinese Fangsong and Latin serif glyphs on Android 8+. */
object InterfaceTypography {
    private var editorialFace:Typeface?=null

    @Synchronized fun load(context:Context):Typeface {
        editorialFace?.let { return it }
        return Typeface.createFromAsset(context.assets,"fonts/SpektraBilingualSerif-Regular.ttf").also { editorialFace=it }
    }

    fun heading(context:Context):Typeface = load(context)
    fun emphasis(context:Context):Typeface = load(context)
    fun editorial(context:Context):Typeface = load(context)

    /** Use the approved pairing in controls as well as titles. The supplied
     * regular face stays intact instead of synthesizing heavier Fangsong. */
    fun forText(context:Context,text:CharSequence,size:Float,bold:Boolean=false):Typeface {
        return load(context)
    }

    fun description(context:Context):String {
        load(context)
        return "中文朱雀仿宋 · 英文与数字 Noto Serif SC"
    }
}
