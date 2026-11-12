package com.spektra.film

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Rect
import android.os.Bundle
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.roundToInt

/** One UI milestone; no spectral renders, RAW decode loops or hash checks. */
class EditorUiInstrumentation:Instrumentation() {
    private var photoPath=""
    override fun onCreate(arguments:Bundle?) {
        photoPath=arguments?.getString("photo_path").orEmpty();super.onCreate(arguments);start()
    }
    private fun field(activity:MainActivity,name:String)=MainActivity::class.java.getDeclaredField(name).apply {isAccessible=true}
    private fun invoke(activity:MainActivity,name:String)=MainActivity::class.java.getDeclaredMethod(name).apply {isAccessible=true}.invoke(activity)
    private fun tag(root:View,name:String):View=requireNotNull(root.findViewWithTag<View>(name)) {"Missing UI entry $name"}
    private fun views(root:View):List<View> = listOf(root)+if(root is ViewGroup)(0 until root.childCount).flatMap {views(root.getChildAt(it))} else emptyList()
    private fun bounds(root:View,view:View)=Rect(0,0,view.width,view.height).also {(root as ViewGroup).offsetDescendantRectToMyCoords(view,it)}
    private fun measure(root:View,width:Int,height:Int) {
        // Workspace orientation and bounded panel sizes settle on the second pass.
        repeat(2) {root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height)}
        views(root).forEach {it.animate().cancel();it.translationY=0f;it.alpha=1f}
    }
    private fun capture(root:View,path:File) {
        val bitmap=Bitmap.createBitmap(root.width,root.height,Bitmap.Config.ARGB_8888)
        try {root.draw(Canvas(bitmap));path.outputStream().use {check(bitmap.compress(Bitmap.CompressFormat.PNG,100,it))}} finally {bitmap.recycle()}
    }
    override fun onStart() {
        val result=Bundle();val report=JSONObject();val directory=File(targetContext.filesDir,"editor-ui-check").apply {mkdirs()}
        val config=Configuration(targetContext.resources.configuration)
        var activity:MainActivity?=null
        try {
            activity=startActivitySync(Intent(targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            val app=requireNotNull(activity)
            val cases=listOf(Triple(360,800,1f),Triple(393,852,1f),Triple(412,915,1f),Triple(360,800,1.5f),Triple(393,852,2f),Triple(800,360,1f))
            val layouts=JSONArray()
            val supplied=photoPath.takeIf {it.isNotBlank()}?.let {BitmapFactory.decodeFile(it,BitmapFactory.Options().apply {inSampleSize=4})}
            val image=supplied ?: Bitmap.createBitmap(IntArray(768*512) {i ->Color.rgb((i%768)*255/767,(i/768)*255/511,96)},768,512,Bitmap.Config.ARGB_8888)
            runOnMainSync {
                val emptyRoot=field(app,"root").get(app) as View
                check(!tag(emptyRoot,"export-photo").isEnabled && !tag(emptyRoot,"crop-ratio").isEnabled)
                check(tag(emptyRoot,"tab-film").isEnabled)
                report.put("empty_dependencies_disabled",true)
                field(app,"source").set(app,image);field(app,"rendered").set(app,image)
                for((widthDp,heightDp,fontScale) in cases) {
                    @Suppress("DEPRECATION")
                    app.resources.updateConfiguration(Configuration(config).apply {this.fontScale=fontScale},app.resources.displayMetrics)
                    invoke(app,"buildUi")
                    val root=field(app,"root").get(app) as View
                    val density=app.resources.displayMetrics.density
                    val width=(widthDp*density).roundToInt();val height=(heightDp*density).roundToInt()
                    root.setPadding(0,(24*density).roundToInt(),0,(24*density).roundToInt())
                    val preview=tag(root,"photo-preview") as PhotoCanvas;preview.original=image;preview.processed=image
                    (tag(root,"photo-filename") as TextView).text="Sony_A7CR_20261108_very_long_photo_filename_for_crop.ARW"
                    field(app,"fileDimensions").get(app).let {(it as TextView).text="9564 × 6376"}
                    tag(root,"tab-develop").performClick();measure(root,width,height)
                    val footer=bounds(root,tag(root,"export-bar"));val scroll=tag(root,"editor-scroll") as ScrollView
                    val viewport=bounds(root,scroll);val stage=bounds(root,tag(root,"photo-stage"))
                    check(viewport.bottom<=footer.top) {"$widthDp/$fontScale: export covers parameters"}
                    check(stage.width()>100*density && stage.height()>48*density) {"$widthDp/$fontScale: photo preview collapsed"}
                    val name="${widthDp}x${heightDp}-font${fontScale}";capture(root,File(directory,"$name.png"))
                    scroll.scrollTo(0,scroll.getChildAt(0).height)
                    val content=scroll.getChildAt(0) as ViewGroup;val finalRow=content.getChildAt(content.childCount-1)
                    val last=bounds(root,finalRow)
                    check(last.bottom<=viewport.bottom && last.top>=viewport.top) {"$widthDp/$fontScale: final group cannot be reached"}
                    check(tag(root,"tab-develop").isSelected && !tag(root,"tab-film").isSelected)
                    check((tag(root,"photo-filename") as TextView).lineCount==1)
                    capture(root,File(directory,"$name-bottom.png"))
                    layouts.put(JSONObject().put("viewport",name).put("photo_height_dp",stage.height()/density).put("last_group_visible",true))
                }
                report.put("layouts",layouts)
            }
            // Exercise the real GestureDetector confirmation; double tap retains zoom.
            var previousHeight=0
            runOnMainSync {
                val root=field(app,"root").get(app) as View;previousHeight=tag(root,"photo-stage").height
                val preview=tag(root,"photo-preview");val now=SystemClock.uptimeMillis()
                MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,preview.width/2f,preview.height/2f,0).also {preview.dispatchTouchEvent(it);it.recycle()}
                MotionEvent.obtain(now,now+30,MotionEvent.ACTION_UP,preview.width/2f,preview.height/2f,0).also {preview.dispatchTouchEvent(it);it.recycle()}
            }
            SystemClock.sleep((ViewConfiguration.getDoubleTapTimeout()+60).toLong())
            runOnMainSync {
                val root=field(app,"root").get(app) as View;measure(root,root.width,root.height)
                check(tag(root,"editor-panel").visibility==View.GONE) {"Single tap did not hide controls"}
                // Landscape expands horizontally; portrait expands vertically.
                check(tag(root,"photo-stage").height>=previousHeight)
                tag(root,"editor-toggle").performClick();measure(root,root.width,root.height)
                check(tag(root,"editor-panel").visibility==View.VISIBLE)
                report.put("photo_tap_and_explicit_restore",true)
                verifyCrop(app,image,report)
            }
            report.put("ok",true).put("fixture",if(supplied==null)"synthetic UI fixture" else "supplied photo")
            File(directory,"report.json").writeText(report.toString(2));result.putString("stream","OK Android editor UI: $report\n")
            finish(Activity.RESULT_OK,result)
        } catch(error:Throwable) {
            report.put("ok",false).put("error",error.stackTraceToString());File(directory,"report.json").writeText(report.toString(2))
            result.putString("stream",error.stackTraceToString());finish(Activity.RESULT_CANCELED,result)
        } finally {
            @Suppress("DEPRECATION")
            targetContext.resources.updateConfiguration(config,targetContext.resources.displayMetrics)
            activity?.let {app ->runOnMainSync {app.finish()}}
        }
    }
    private fun verifyCrop(activity:Activity,image:Bitmap,report:JSONObject) {
        val sourceWidth=9564;val sourceHeight=6376
        val editor=CropEditorView(activity,image,sourceWidth,sourceHeight)
        val density=activity.resources.displayMetrics.density;val width=(360*density).roundToInt();val height=(480*density).roundToInt()
        editor.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));editor.layout(0,0,width,height)
        editor.setAspect(65f/24f)
        val before=editor.crop;val initial=spectralCropRect(before,sourceWidth,sourceHeight)
        check(abs(initial.width().toFloat()/initial.height()-65f/24f)<.002f) {"XPan export ratio is incorrect"}
        val padding=24*density;val scale=min((width-2*padding)/sourceWidth,(height-2*padding)/sourceHeight)
        val frameLeft=(width-sourceWidth*scale)/2;val frameTop=(height-sourceHeight*scale)/2
        val x=frameLeft+sourceWidth*scale*(before.left+before.right)/2;val y=frameTop+sourceHeight*scale*(before.top+before.bottom)/2
        val now=SystemClock.uptimeMillis()
        listOf(Triple(MotionEvent.ACTION_DOWN,x,y),Triple(MotionEvent.ACTION_MOVE,x,y+30*density),Triple(MotionEvent.ACTION_UP,x,y+30*density)).forEachIndexed {index,event ->
            MotionEvent.obtain(now,now+index*16L,event.first,event.second,event.third,0).also {editor.dispatchTouchEvent(it);it.recycle()}
        }
        val moved=spectralCropRect(editor.crop,sourceWidth,sourceHeight)
        check(moved.top>initial.top && abs(moved.width()-initial.width())<=1 && abs(moved.height()-initial.height())<=1) {"Moving XPan changed size or did not move source origin"}
        val movedBounds=editor.crop
        val cornerX=frameLeft+sourceWidth*scale*movedBounds.left;val cornerY=frameTop+sourceHeight*scale*movedBounds.top
        listOf(Triple(MotionEvent.ACTION_DOWN,cornerX,cornerY),Triple(MotionEvent.ACTION_MOVE,cornerX+40*density,cornerY+20*density),Triple(MotionEvent.ACTION_UP,cornerX+40*density,cornerY+20*density)).forEachIndexed {index,event ->
            MotionEvent.obtain(now+100,now+100+index*16L,event.first,event.second,event.third,0).also {editor.dispatchTouchEvent(it);it.recycle()}
        }
        val resized=spectralCropRect(editor.crop,sourceWidth,sourceHeight)
        check(resized.width()<moved.width() && abs(resized.width().toFloat()/resized.height()-65f/24f)<.002f) {"Corner resize did not preserve XPan ratio"}
        editor.setAspect(null);editor.setCrop(CropBounds(.1f,.2f,.8f,.7f));check(editor.crop==CropBounds(.1f,.2f,.8f,.7f))
        check(movedBounds!=before)
        report.put("crop",JSONObject().put("xpan",true).put("position_drag",true).put("locked_corner_resize",true).put("free_bounds",true).put("source_width",sourceWidth).put("source_height",sourceHeight))
    }
}
