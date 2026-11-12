package com.spektra.film

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.os.Bundle
import android.view.GestureDetector
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.animation.PathInterpolator
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.Executors
import kotlin.math.*

/** Oriented photo preview with zoom, pan and a draggable before/after divider. */
class PhotoCanvas(context: Context, private val bookTypeface: Typeface) : View(context) {
    /** Normalized crop in the oriented source image; shared with full-resolution export. */
    var crop:CropBounds=CropBounds()
        set(value) {field=value;resetZoom()}
    var geometry=Geometry()
        set(value) {if(field!=value){field=value;requestOverlay();invalidate()}}
    private var mappingGeometry=Geometry()
    private var mappingWidth=0
    private var mappingHeight=0
    private var forwardMap=doubleArrayOf(1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0)
    private var inverseMap=forwardMap.copyOf()
    private fun updateMapping(w:Int,h:Int) {
        if(mappingWidth!=w || mappingHeight!=h || mappingGeometry!=geometry) {
            mappingWidth=w;mappingHeight=h;mappingGeometry=geometry
            forwardMap=PhotoGeometry.matrix(w,h,geometry);inverseMap=PhotoGeometry.inverse(forwardMap)
        }
    }
    private var correctedOriginal:Bitmap?=null
    private var originalIdentity:Bitmap?=null
    private var originalGeometry=Geometry()
    var originalOnly=false
    var original: Bitmap?=null
    var processed: Bitmap?=null
    var comparing=false
        set(value) {
            field=value
            contentDescription=if(value)"前后对比，左侧原图、右侧显影；左右滑动调整分界线" else "照片预览；单击收起或显示调整面板，双指缩放和移动，双击复位"
            if(Build.VERSION.SDK_INT>=30)stateDescription=if(value)"对比线 ${(split*100).roundToInt()}%" else null
            invalidate()
        }
    var brushMode=false
    var gradientMode=false
    var maskToolsVisible=false
    var brushErase=false
    var brushRadius=.05f
    var brushFeather=.7f
    var brushFlow=1f
    var overlayColor=0xffef6554.toInt();set(value){field=value;invalidate()}
    var overlayAlpha=.48f;set(value){field=value.coerceIn(.1f,.85f);invalidate()}
    var onStrokeFinished: ((MaskStroke)->Unit)?=null
    var onGradientStart:(()->Unit)?=null
    var onGradientChange:((MaskLayer)->Unit)?=null
    var onGradientEnd:(()->Unit)?=null
    var overlayMotionEnabled=true
        set(value) {
            field=value
            if(!value)fadeOverlayTo(if(showMaskOverlay && overlay!=null && maskLayer!=null)1f else 0f)
        }
    var showMaskOverlay=true
        set(value) { if(field!=value) {
            field=value
            if(value)requestOverlay()
            fadeOverlayTo(if(value && overlay!=null && maskLayer!=null)1f else 0f)
        } }
    var maskLayer: MaskLayer?=null
        set(value) { if(field!=value) {
            val previous=field
            if(field?.id!=value?.id) {
                overlayAnimator?.cancel();overlayAnimator=null;overlayOpacity=0f
                overlay?.recycle();overlay=null
            }
            field=value
            if(previous?.id!=value?.id)pending.clear()
            if(previous==null || value==null || !sameCoverage(previous,value))requestOverlay()
            invalidate()
        } }
    private fun sameCoverage(a:MaskLayer,b:MaskLayer)=a.kind==b.kind && a.strokes==b.strokes && a.inverted==b.inverted && a.start==b.start && a.end==b.end && a.center==b.center && a.radiusX==b.radiusX && a.radiusY==b.radiusY && a.rotation==b.rotation && a.feather==b.feather
    private val overlayWorker=Executors.newSingleThreadExecutor()
    private val main=Handler(Looper.getMainLooper())
    @Volatile private var overlayRevision=0
    private var overlay: Bitmap?=null
    private var overlayBoundary:Bitmap?=null
    private var cachedCoverage:FloatArray?=null
    private var cachedLayer:MaskLayer?=null
    private var cachedWidth=0;private var cachedHeight=0
    private var overlayOpacity=0f
    private var overlayAnimator:ValueAnimator?=null
    private var overlayRunning=false
    private var overlayQueued=false
    private var split=.5f
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val frame=RectF()
    private val fitted=RectF()
    private var zoom=1f
    private var panX=0f
    private var panY=0f
    private var lastX=0f
    private var lastY=0f
    private var moved=false
    private var navigating=false
    private val pending=mutableListOf<MaskPoint>()
    private var gradientHandle:String?=null
    private var gradientStart:MaskLayer?=null
    private var gradientPoint:MaskPoint?=null
    private val scaleDetector=ScaleGestureDetector(context,object:ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector:ScaleGestureDetector):Boolean {
            val previous=zoom;zoom=(zoom*detector.scaleFactor).coerceIn(1f,8f)
            val factor=zoom/previous
            panX=detector.focusX+(width/2f+panX-detector.focusX)*factor-width/2f
            panY=detector.focusY+(height/2f+panY-detector.focusY)*factor-height/2f
            moved=true;clampPan();invalidate();return true
        }
    })
    private val gestureDetector=GestureDetector(context,object:GestureDetector.SimpleOnGestureListener() {
        override fun onDown(event:MotionEvent)=true
        override fun onSingleTapConfirmed(event:MotionEvent):Boolean {
            if(brushMode || gradientMode || comparing || scaleDetector.isInProgress)return false
            performClick();return true
        }
        override fun onDoubleTap(event:MotionEvent):Boolean {
            if(brushMode || gradientMode || comparing)return false
            if(zoom>1.01f)resetZoom() else { zoom=2f;panX=width/2f-event.x;panY=height/2f-event.y;clampPan() }
            invalidate();return true
        }
    })
    init { contentDescription="照片细节预览；单击收起或显示调整面板，双指缩放和移动，双击复位；对比时可拖动分界线";isFocusable=true }
    fun resetZoom() { pending.clear();zoom=1f;panX=0f;panY=0f;requestOverlay();invalidate() }
    private fun sourceRect(image:Bitmap):Rect {
        val left=(crop.left*image.width).roundToInt().coerceIn(0,image.width-1)
        val top=(crop.top*image.height).roundToInt().coerceIn(0,image.height-1)
        val right=(crop.right*image.width).roundToInt().coerceIn(left+1,image.width)
        val bottom=(crop.bottom*image.height).roundToInt().coerceIn(top+1,image.height)
        return Rect(left,top,right,bottom)
    }
    private fun displayPoint(p:MaskPoint):PointF {
        val image=original ?: processed
        val w=image?.width ?: 1;val h=image?.height ?: 1
        updateMapping(w,h)
        val (fw,fh)=PhotoGeometry.frameSize(w,h,geometry)
        val q=PhotoGeometry.point(forwardMap,p.u*(w-1.0),p.v*(h-1.0))
        return PointF(((q.first/max(1,fw-1)-crop.left)/max(.001f,crop.right-crop.left)).toFloat(),((q.second/max(1,fh-1)-crop.top)/max(.001f,crop.bottom-crop.top)).toFloat())
    }
    private fun sourcePoint(u:Float,v:Float):MaskPoint {
        val image=original ?: processed;val w=image?.width ?: 1;val h=image?.height ?: 1
        val (fw,fh)=PhotoGeometry.frameSize(w,h,geometry)
        val x=(crop.left+u.coerceIn(0f,1f)*(crop.right-crop.left))*(fw-1.0)
        val y=(crop.top+v.coerceIn(0f,1f)*(crop.bottom-crop.top))*(fh-1.0)
        updateMapping(w,h)
        val q=PhotoGeometry.point(inverseMap,x,y)
        return MaskPoint((q.first/max(1,w-1)).toFloat().coerceIn(0f,1f),(q.second/max(1,h-1)).toFloat().coerceIn(0f,1f))
    }
    fun cancelStroke() {
        pending.clear();gradientHandle=null;gradientStart=null;gradientPoint=null
        parent?.requestDisallowInterceptTouchEvent(false);invalidate()
    }
    private fun fitRect(image:Bitmap):RectF {
        val padding=10*resources.displayMetrics.density
        val source=sourceRect(image)
        val ratio=min(max(1f,width-2*padding)/source.width(),max(1f,height-2*padding)/source.height())
        val w=source.width()*ratio;val h=source.height()*ratio
        fitted.set((width-w)/2,(height-h)/2,(width+w)/2,(height+h)/2)
        return fitted
    }
    private fun updateFrame(): Boolean {
        val image=processed ?: original ?: return false
        if(image.isRecycled)return false
        val base=fitRect(image);val w=base.width()*zoom;val h=base.height()*zoom
        frame.set(width/2f+panX-w/2f,height/2f+panY-h/2f,width/2f+panX+w/2f,height/2f+panY+h/2f)
        return true
    }
    internal fun normalizedPoint(x:Float,y:Float):MaskPoint? {
        if(!updateFrame() || !frame.contains(x,y))return null
        val u=((x-frame.left)/frame.width()).coerceIn(0f,1f);val v=((y-frame.top)/frame.height()).coerceIn(0f,1f)
        return sourcePoint(u,v)
    }
    private fun clampPan() {
        val image=processed ?: original ?: return
        val base=fitRect(image)
        val maxX=max(0f,(base.width()*zoom-width)/2f);val maxY=max(0f,(base.height()*zoom-height)/2f)
        panX=panX.coerceIn(-maxX,maxX);panY=panY.coerceIn(-maxY,maxY)
    }
    private fun requestOverlay() {
        overlayRevision++
        if(!showMaskOverlay || overlayWorker.isShutdown)return
        if(overlayRunning) { overlayQueued=true;return }
        val layer=maskLayer
        val image=original ?: processed
        if(layer==null || image==null) { overlay?.recycle();overlay=null;return }
        if(layer.kind!="brush"){overlay?.recycle();overlay=null;overlayBoundary?.recycle();overlayBoundary=null;return}
        val request=overlayRevision;val requestedGeometry=geometry
        val factor=min(1f,640f/max(image.width,image.height))
        val w=max(1,(image.width*factor).roundToInt());val h=max(1,(image.height*factor).roundToInt())
        overlayRunning=true
        overlayWorker.execute {
            val before=cachedLayer;val previous=cachedCoverage
            val alpha=if(previous!=null && before!=null && before.id==layer.id && cachedWidth==w && cachedHeight==h &&
                layer.strokes.size==before.strokes.size+1 && layer.strokes.dropLast(1)==before.strokes) {
                val stroke=layer.strokes.last()
                MaskOverlayRasterizer.alpha(layer.copy(strokes=listOf(stroke.copy(erase=false)),inverted=false,opacity=1f),w,h){request!=overlayRevision}?.let {coverage->
                    FloatArray(coverage.size){i->if(stroke.erase)previous[i]*(1-coverage[i]) else previous[i]+(1-previous[i])*coverage[i]}
                }
            } else MaskOverlayRasterizer.alpha(layer.copy(inverted=false,opacity=1f),w,h) { request!=overlayRevision }
            if(alpha!=null){cachedCoverage=alpha;cachedLayer=layer;cachedWidth=w;cachedHeight=h}
            val coverage=alpha?.let {FloatArray(it.size){i->if(layer.inverted)1-it[i] else it[i]}}
            val bitmap=coverage?.let { values ->
                val raw=Bitmap.createBitmap(IntArray(w*h) { i -> ((values[i]*255).roundToInt().coerceIn(0,255) shl 24) or 0x00ffffff },w,h,Bitmap.Config.ARGB_8888)
                PhotoGeometry.preview(raw,requestedGeometry).also {if(it!==raw)raw.recycle()}
            }
            val boundary=coverage?.let {values->
                val pixels=IntArray(w*h)
                for(y in 1 until h-1)for(x in 1 until w-1){val i=y*w+x;val hit=values[i]>=.5f
                    if((values[i-1]>=.5f)!=hit || (values[i+1]>=.5f)!=hit || (values[i-w]>=.5f)!=hit || (values[i+w]>=.5f)!=hit)pixels[i]=if(hit)0xf2ffffff.toInt() else 0xc530332d.toInt()}
                val raw=Bitmap.createBitmap(pixels,w,h,Bitmap.Config.ARGB_8888);PhotoGeometry.preview(raw,requestedGeometry).also {if(it!==raw)raw.recycle()}
            }
            main.post {
                if(request==overlayRevision) {
                    val first=overlay==null
                    overlay?.recycle();overlay=bitmap
                    overlayBoundary?.recycle();overlayBoundary=boundary
                    if(first)fadeOverlayTo(if(showMaskOverlay && bitmap!=null)1f else 0f)
                    invalidate()
                } else {bitmap?.recycle();boundary?.recycle()}
                overlayRunning=false
                if(overlayQueued) { overlayQueued=false;requestOverlay() }
            }
        }
    }
    /** Animate only the cached alpha surface; stroke feedback and handle geometry remain direct. */
    private fun fadeOverlayTo(target:Float) {
        overlayAnimator?.cancel();overlayAnimator=null
        if(!overlayMotionEnabled || !ValueAnimator.areAnimatorsEnabled() || abs(overlayOpacity-target)<.001f) {
            overlayOpacity=target;invalidate();return
        }
        val animator=ValueAnimator.ofFloat(overlayOpacity,target).apply {
            duration=140
            interpolator=PathInterpolator(.2f,.8f,.2f,1f)
            addUpdateListener { overlayOpacity=it.animatedValue as Float;invalidate() }
            addListener(object:AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation:Animator) {if(overlayAnimator===animation)overlayAnimator=null}
            })
        }
        overlayAnimator=animator;animator.start()
    }
    override fun onDraw(c:Canvas) {
        super.onDraw(c)
        val image=processed ?: original
        if(image==null || image.isRecycled) {
            val density=resources.displayMetrics.density
            paint.color=UiTheme.muted;paint.textSize=UiTokens.body*resources.displayMetrics.scaledDensity
            paint.typeface=InterfaceTypography.forText(context,"",14f);paint.textAlign=Paint.Align.CENTER
            c.drawText(if(originalOnly)"RAW 原片 · 可另存" else "轻点，导入你的照片",width/2f,height/2f+5*density,paint)
            return
        }
        updateFrame();paint.color=UiTheme.surface;paint.alpha=255;paint.style=Paint.Style.FILL
        c.drawBitmap(image,sourceRect(image),frame,paint)
        if(comparing && original!=null) {
            val source=requireNotNull(original)
            if(originalIdentity!==source || originalGeometry!=geometry) {
                correctedOriginal?.takeUnless {it===originalIdentity || it.isRecycled}?.recycle()
                correctedOriginal=PhotoGeometry.preview(source,geometry);originalIdentity=source;originalGeometry=geometry
            }
            val before=correctedOriginal ?: source
            val x=frame.left+frame.width()*split
            c.save();c.clipRect(frame.left,frame.top,x,frame.bottom);c.drawBitmap(before,sourceRect(before),frame,paint);c.restore()
            val density=resources.displayMetrics.density
            if(isPressed) {paint.color=UiTheme.surface;paint.alpha=55;c.drawCircle(x,frame.centerY(),24*density,paint);paint.alpha=255}
            paint.color=UiTheme.surface;paint.strokeWidth=resources.displayMetrics.density;c.drawLine(x,frame.top,x,frame.bottom,paint)
            c.drawCircle(x,frame.centerY(),11*resources.displayMetrics.density,paint)
            paint.color=UiTheme.accentText;paint.strokeWidth=1.5f*resources.displayMetrics.density
            c.drawLine(x,frame.centerY()-4*resources.displayMetrics.density,x,frame.centerY()+4*resources.displayMetrics.density,paint)
            paint.typeface=InterfaceTypography.forText(context,"",12f,true);paint.textSize=12*resources.displayMetrics.scaledDensity
            paint.color=UiTheme.surface;paint.setShadowLayer(2*density,0f,density,0xAA000000.toInt())
            paint.textAlign=Paint.Align.LEFT;c.drawText("原图",frame.left+10*density,frame.top+22*density,paint)
            paint.textAlign=Paint.Align.RIGHT;c.drawText("显影",frame.right-10*density,frame.top+22*density,paint)
            paint.clearShadowLayer();paint.textAlign=Paint.Align.LEFT
        }
        if((showMaskOverlay || overlayOpacity>0f) && maskLayer!=null && !comparing) {
            c.save();c.clipRect(frame)
            if(maskLayer?.kind!="brush" && showMaskOverlay)drawGradientCoverage(c,requireNotNull(maskLayer))
            overlay?.takeUnless { it.isRecycled }?.let {
                paint.alpha=(overlayOpacity*overlayAlpha*255).roundToInt().coerceIn(0,255)
                paint.colorFilter=PorterDuffColorFilter(overlayColor,PorterDuff.Mode.SRC_IN)
                c.drawBitmap(it,sourceRect(it),frame,paint);paint.alpha=255;paint.colorFilter=null
            }
            if(showMaskOverlay)overlayBoundary?.takeUnless {it.isRecycled}?.let {c.drawBitmap(it,sourceRect(it),frame,paint)}
            if(showMaskOverlay && pending.isNotEmpty()) {
                val path=Path()
                pending.forEachIndexed { index,p ->
                    val display=displayPoint(p);val x=frame.left+display.x*frame.width();val y=frame.top+display.y*frame.height()
                    if(index==0)path.moveTo(x,y) else path.lineTo(x,y)
                }
                paint.color=if(brushErase)UiTheme.surface else overlayColor
                paint.style=Paint.Style.STROKE
                paint.strokeCap=Paint.Cap.ROUND;paint.strokeJoin=Paint.Join.ROUND
                // Several low-opacity concentric paths give immediate, soft feedback without an opaque paint ribbon.
                for(ring in 6 downTo 1) {
                    val fraction=(1-brushFeather)+brushFeather*ring/6f
                    paint.alpha=(overlayAlpha*255*brushFlow/6).roundToInt().coerceAtLeast(1)
                    paint.strokeWidth=brushRadius*min(frame.width(),frame.height())*2*fraction
                    if(pending.size==1) { val point=displayPoint(pending[0]);paint.style=Paint.Style.FILL;c.drawCircle(frame.left+point.x*frame.width(),frame.top+point.y*frame.height(),paint.strokeWidth/2,paint);paint.style=Paint.Style.STROKE }
                    else c.drawPath(path,paint)
                }
                paint.style=Paint.Style.STROKE;paint.alpha=235;paint.color=UiTheme.surface;paint.strokeWidth=1.3f*resources.displayMetrics.density
                val end=displayPoint(pending.last());c.drawCircle(frame.left+end.x*frame.width(),frame.top+end.y*frame.height(),brushRadius*min(frame.width(),frame.height()),paint)
                paint.style=Paint.Style.FILL;paint.alpha=255
            }
            c.restore()
        }
        if(maskToolsVisible && maskLayer?.kind!="brush" && !comparing && maskLayer!=null)drawGradient(c,maskLayer!!)
    }
    private fun handles(layer:MaskLayer):Map<String,PointF> {
        fun point(p:MaskPoint):PointF {val display=displayPoint(p);return PointF(frame.left+display.x*frame.width(),frame.top+display.y*frame.height())}
        if(layer.kind=="linear")return linkedMapOf("start" to point(layer.start),"end" to point(layer.end),"center" to point(MaskPoint((layer.start.u+layer.end.u)/2,(layer.start.v+layer.end.v)/2)))
        val center=point(layer.center);val x=point(radialPoint(layer,0.0));val y=point(radialPoint(layer,PI/2))
        val axis=point(radialPoint(layer,-PI/2));val dx=axis.x-center.x;val dy=axis.y-center.y;val length=max(1f,hypot(dx,dy))
        val extra=32*resources.displayMetrics.density
        return linkedMapOf("center" to center,"x" to x,"y" to y,"rotate" to PointF(axis.x+dx/length*extra,axis.y+dy/length*extra))
    }
    /** Analytical gradients draw directly while dragging; no raster job or bitmap allocation per pointer event. */
    private fun drawGradientCoverage(c:Canvas,layer:MaskLayer) {
        val image=original ?: processed ?: return;val w=image.width;val h=image.height
        val (fw,fh)=PhotoGeometry.frameSize(w,h,geometry)
        val m=PhotoGeometry.matrix(w,h,geometry);val sx=frame.width()/max(.001f,crop.right-crop.left)/max(1,fw-1);val sy=frame.height()/max(.001f,crop.bottom-crop.top)/max(1,fh-1)
        val tx=frame.left-crop.left*frame.width()/max(.001f,crop.right-crop.left);val ty=frame.top-crop.top*frame.height()/max(.001f,crop.bottom-crop.top)
        val screen=Matrix().apply {setValues(floatArrayOf((m[0]*sx+tx*m[6]).toFloat(),(m[1]*sx+tx*m[7]).toFloat(),(m[2]*sx+tx*m[8]).toFloat(),(m[3]*sy+ty*m[6]).toFloat(),(m[4]*sy+ty*m[7]).toFloat(),(m[5]*sy+ty*m[8]).toFloat(),m[6].toFloat(),m[7].toFloat(),m[8].toFloat()))}
        val colors=IntArray(17){i->val t=i/16f;val a=if(layer.kind=="linear")t*t*(3-2*t) else {val z=((t-(1-layer.feather))/max(.001f,layer.feather)).coerceIn(0f,1f);1-z*z*(3-2*z)};val v=if(layer.inverted)1-a else a;((v*overlayAlpha*255).roundToInt() shl 24) or (overlayColor and 0xffffff)}
        val stops=FloatArray(17){it/16f}
        val shader=if(layer.kind=="linear")LinearGradient(layer.start.u*(w-1),layer.start.v*(h-1),layer.end.u*(w-1),layer.end.v*(h-1),colors,stops,Shader.TileMode.CLAMP)
        else RadialGradient(0f,0f,1f,colors,stops,Shader.TileMode.CLAMP).apply {setLocalMatrix(Matrix().apply {setScale(max(.5f,layer.radiusX*w),max(.5f,layer.radiusY*h));postRotate(layer.rotation);postTranslate(layer.center.u*(w-1),layer.center.v*(h-1))})}
        paint.shader=shader;paint.style=Paint.Style.FILL;paint.alpha=255;c.save();c.concat(screen);c.drawRect(-w.toFloat()*4,-h.toFloat()*4,w.toFloat()*5,h.toFloat()*5,paint);c.restore();paint.shader=null
    }
    private fun radialPoint(layer:MaskLayer,angle:Double,scale:Float=1f):MaskPoint {
        val image=original ?: processed;val w=max(1,image?.width ?: 1).toFloat();val h=max(1,image?.height ?: 1).toFloat()
        val a=layer.rotation*PI/180;val x=cos(angle)*layer.radiusX*w*scale;val y=sin(angle)*layer.radiusY*h*scale
        return MaskPoint((layer.center.u+(x*cos(a)-y*sin(a))/w).toFloat(),(layer.center.v+(x*sin(a)+y*cos(a))/h).toFloat())
    }
    private fun drawGradient(c:Canvas,layer:MaskLayer) {
        val density=resources.displayMetrics.density;val controls=handles(layer)
        paint.shader=null;paint.style=Paint.Style.STROKE;paint.strokeWidth=.85f*density;paint.color=UiTheme.surface;paint.alpha=195
        if(layer.kind=="linear") {
            val a=controls.getValue("start");val b=controls.getValue("end")
            c.drawLine(a.x,a.y,b.x,b.y,paint)
            val dx=b.x-a.x;val dy=b.y-a.y;val length=max(1f,hypot(dx,dy));val px=-dy/length;val py=dx/length
            for(p in listOf(a,b))c.drawLine(p.x-px*24*density,p.y-py*24*density,p.x+px*24*density,p.y+py*24*density,paint)
        } else {
            val center=controls.getValue("center")
            fun ellipse(scale:Float):Path=Path().apply {
                for(i in 0..96) {
                    val p=displayPoint(radialPoint(layer,2*PI*i/96,scale))
                    val x=frame.left+p.x*frame.width();val y=frame.top+p.y*frame.height()
                    if(i==0)moveTo(x,y) else lineTo(x,y)
                };close()
            }
            c.drawPath(ellipse(1f),paint)
            paint.alpha=100;paint.pathEffect=DashPathEffect(floatArrayOf(3*density,4*density),0f)
            c.drawPath(ellipse(1-layer.feather),paint)
            paint.pathEffect=null
            paint.alpha=150;val rotate=controls.getValue("rotate");c.drawLine(center.x,center.y,rotate.x,rotate.y,paint)
        }
        controls.forEach { (key,p) ->
            paint.style=Paint.Style.FILL;paint.color=UiTheme.surface;paint.alpha=235;c.drawCircle(p.x,p.y,(if(key=="center")4f else 5f)*density,paint)
            paint.style=Paint.Style.STROKE;paint.color=UiTheme.accentText;paint.strokeWidth=.85f*density;c.drawCircle(p.x,p.y,(if(key=="center")4f else 5f)*density,paint)
        }
        paint.style=Paint.Style.FILL;paint.alpha=255
    }
    private fun moveGradient(x:Float,y:Float) {
        val original=gradientStart ?: return;val initial=gradientPoint ?: return
        val p=sourcePoint((x-frame.left)/frame.width(),(y-frame.top)/frame.height())
        val change=if(original.kind=="linear")when(gradientHandle) {
            "start"->original.copy(start=p);"end"->original.copy(end=p)
            else->{val du=(p.u-initial.u).coerceIn(-min(original.start.u,original.end.u),1-max(original.start.u,original.end.u));val dv=(p.v-initial.v).coerceIn(-min(original.start.v,original.end.v),1-max(original.start.v,original.end.v));original.copy(start=MaskPoint(original.start.u+du,original.start.v+dv),end=MaskPoint(original.end.u+du,original.end.v+dv))}
        } else {
            val image=this.original ?: processed;val sw=max(1,image?.width ?: 1).toFloat();val sh=max(1,image?.height ?: 1).toFloat()
            val dx=(p.u-original.center.u)*sw;val dy=(p.v-original.center.v)*sh;val angle=original.rotation*PI/180
            when(gradientHandle) {
                "center"->original.copy(center=MaskPoint((original.center.u+p.u-initial.u).coerceIn(0f,1f),(original.center.v+p.v-initial.v).coerceIn(0f,1f)))
                "x"->original.copy(radiusX=(abs(dx*cos(angle)+dy*sin(angle))/sw).toFloat().coerceIn(.002f,2f))
                "y"->original.copy(radiusY=(abs(-dx*sin(angle)+dy*cos(angle))/sh).toFloat().coerceIn(.002f,2f))
                else->original.copy(rotation=((atan2(dy,dx)*180/PI)+90).toFloat())
            }
        }
        onGradientChange?.invoke(change);invalidate()
    }
    private fun addPoint(x:Float,y:Float) {
        val point=normalizedPoint(x,y) ?: return
        val previous=pending.lastOrNull()
        if(previous==null || hypot(point.u-previous.u,point.v-previous.v)>.0008f)pending.add(point)
    }
    override fun onTouchEvent(event:MotionEvent):Boolean {
        if(!isEnabled)return false
        if(!brushMode && !gradientMode)gestureDetector.onTouchEvent(event)
        scaleDetector.onTouchEvent(event)
        when(event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                isPressed=comparing
                lastX=event.x;lastY=event.y;moved=false;navigating=false;pending.clear()
                gradientHandle=null;gradientStart=null;gradientPoint=null
                if(gradientMode && updateFrame())maskLayer?.let { layer ->
                    val target=handles(layer).entries.minByOrNull {hypot(it.value.x-event.x,it.value.y-event.y)}
                    if(target!=null && hypot(target.value.x-event.x,target.value.y-event.y)<=22*resources.displayMetrics.density) {
                        gradientHandle=target.key;gradientStart=layer;gradientPoint=sourcePoint((event.x-frame.left)/frame.width(),(event.y-frame.top)/frame.height());onGradientStart?.invoke()
                    }
                }
                if(brushMode && maskLayer!=null && !comparing)addPoint(event.x,event.y)
                parent?.requestDisallowInterceptTouchEvent(true);invalidate();return true
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                pending.clear();navigating=true;moved=true
                gradientStart?.let {onGradientChange?.invoke(it)};gradientHandle=null;gradientStart=null
                lastX=(event.getX(0)+event.getX(1))/2;lastY=(event.getY(0)+event.getY(1))/2
                invalidate();return true
            }
            MotionEvent.ACTION_MOVE -> {
                if(event.pointerCount>=2) {
                    val cx=(event.getX(0)+event.getX(1))/2;val cy=(event.getY(0)+event.getY(1))/2
                    panX+=cx-lastX;panY+=cy-lastY;lastX=cx;lastY=cy;clampPan();invalidate()
                } else if(!navigating) {
                    val dx=event.x-lastX;val dy=event.y-lastY
                    if(gradientMode && gradientHandle!=null && !comparing) {moveGradient(event.x,event.y);moved=true}
                    else if(brushMode && maskLayer!=null && !comparing) {
                        for(index in 0 until event.historySize)addPoint(event.getHistoricalX(index),event.getHistoricalY(index))
                        addPoint(event.x,event.y);moved=true;invalidate()
                    } else if(comparing && frame.width()>0) {setSplit((event.x-frame.left)/frame.width());moved=true}
                    else if(zoom>1f) { panX+=dx;panY+=dy;moved=true;clampPan();invalidate() }
                    lastX=event.x;lastY=event.y
                }
                return true
            }
            MotionEvent.ACTION_POINTER_UP -> { navigating=true;return true }
            MotionEvent.ACTION_UP -> {
                isPressed=false;invalidate()
                if(gradientMode && gradientHandle!=null && !navigating) {moveGradient(event.x,event.y);onGradientEnd?.invoke();gradientHandle=null;gradientStart=null}
                else if(brushMode && !navigating && pending.isNotEmpty()) {
                    addPoint(event.x,event.y)
                    val stroke=MaskStroke(pending.toList(),brushRadius.coerceIn(.002f,.5f),brushFeather.coerceIn(0f,1f),brushFlow.coerceIn(0f,1f),brushErase)
                    pending.clear();onStrokeFinished?.invoke(stroke);invalidate()
                }
                parent?.requestDisallowInterceptTouchEvent(false);return true
            }
            MotionEvent.ACTION_CANCEL -> {isPressed=false;pending.clear();gradientStart?.let {onGradientChange?.invoke(it)};gradientHandle=null;gradientStart=null;parent?.requestDisallowInterceptTouchEvent(false);invalidate();return true }
        }
        return true
    }
    override fun performClick():Boolean { super.performClick();return true }
    private fun setSplit(value:Float) {
        split=value.coerceIn(.03f,.97f)
        if(Build.VERSION.SDK_INT>=30)stateDescription="对比线 ${(split*100).roundToInt()}%"
        invalidate()
    }
    override fun onInitializeAccessibilityNodeInfo(info:AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.className=if(comparing)"android.widget.SeekBar" else "android.widget.ImageView"
        if(comparing) {
            info.rangeInfo=AccessibilityNodeInfo.RangeInfo.obtain(AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_FLOAT,3f,97f,split*100)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD)
        }
    }
    override fun performAccessibilityAction(action:Int,arguments:Bundle?):Boolean {
        if(comparing && isEnabled)when(action) {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> {setSplit(split+.05f);return true}
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> {setSplit(split-.05f);return true}
            android.R.id.accessibilityActionSetProgress -> {
                val value=arguments?.getFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE) ?: return false
                setSplit(value/100);return true
            }
        }
        return super.performAccessibilityAction(action,arguments)
    }
    override fun onKeyDown(keyCode:Int,event:KeyEvent):Boolean {
        if(comparing && isEnabled)when(keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT -> {setSplit(split-.02f);return true}
            KeyEvent.KEYCODE_DPAD_RIGHT -> {setSplit(split+.02f);return true}
        }
        return super.onKeyDown(keyCode,event)
    }
    override fun onDetachedFromWindow() {
        overlayAnimator?.cancel();overlayAnimator=null;overlayOpacity=0f
        correctedOriginal?.takeUnless {it===originalIdentity || it.isRecycled}?.recycle();correctedOriginal=null
        overlayRevision++;overlayWorker.shutdown();overlay?.recycle();overlay=null;overlayBoundary?.recycle();overlayBoundary=null;cachedCoverage=null;paint.alpha=255;super.onDetachedFromWindow()
    }
}

/** Bounded overlay raster. Same per-stroke max coverage / per-layer over rule as local_masks.py. */
internal object MaskOverlayRasterizer {
    fun alpha(layer:MaskLayer,width:Int,height:Int,cancelled:()->Boolean={false}):FloatArray? {
        val result=FloatArray(width*height)
        if(layer.kind!="brush") {
            val sx=max(1,width-1).toFloat();val sy=max(1,height-1).toFloat()
            val ax=layer.start.u*sx;val ay=layer.start.v*sy;val dx=(layer.end.u-layer.start.u)*sx;val dy=(layer.end.v-layer.start.v)*sy;val length2=dx*dx+dy*dy
            val angle=layer.rotation*PI/180;val cs=cos(angle).toFloat();val sn=sin(angle).toFloat()
            for(y in 0 until height) {
                if(cancelled())return null
                for(x in 0 until width) {
                    val alpha=if(layer.kind=="linear") {
                        if(length2<=1e-12f)0f else {val t=(((x-ax)*dx+(y-ay)*dy)/length2).coerceIn(0f,1f);t*t*(3-2*t)}
                    } else {
                        val px=x-layer.center.u*sx;val py=y-layer.center.v*sy
                        val distance=hypot((px*cs+py*sn)/max(.5f,layer.radiusX*sx),(-px*sn+py*cs)/max(.5f,layer.radiusY*sy))
                        val t=((distance-(1-layer.feather))/max(.001f,layer.feather)).coerceIn(0f,1f);1-t*t*(3-2*t)
                    }
                    result[y*width+x]=alpha
                }
            }
        }
        for(stroke in if(layer.kind=="brush")layer.strokes else emptyList()) {
            if(cancelled())return null
            if(stroke.points.isEmpty())continue
            val coverage=FloatArray(result.size)
            val radius=max(.5f,stroke.radius*min(width,height));val inner=radius*(1-stroke.feather)
            val points=stroke.points
            for(index in points.indices) {
                if(cancelled())return null
                val a=points[if(index==0)0 else index-1];val b=points[index]
                val ax=a.u*(width-1);val ay=a.v*(height-1);val bx=b.u*(width-1);val by=b.v*(height-1)
                val dx=bx-ax;val dy=by-ay;val square=dx*dx+dy*dy
                val left=floor(min(ax,bx)-radius).toInt().coerceAtLeast(0);val right=ceil(max(ax,bx)+radius).toInt().coerceAtMost(width-1)
                val top=floor(min(ay,by)-radius).toInt().coerceAtLeast(0);val bottom=ceil(max(ay,by)+radius).toInt().coerceAtMost(height-1)
                for(y in top..bottom)for(x in left..right) {
                    val t=if(square==0f)0f else (((x-ax)*dx+(y-ay)*dy)/square).coerceIn(0f,1f)
                    val distance=hypot(x-ax-t*dx,y-ay-t*dy)
                    val weight=if(distance>=radius)0f else if(distance<=inner || radius==inner)1f else {
                        val fade=((radius-distance)/(radius-inner)).coerceIn(0f,1f);fade*fade*(3-2*fade)
                    }
                    val pixel=y*width+x;coverage[pixel]=max(coverage[pixel],weight)
                }
            }
            for(index in result.indices) {
                val opacity=coverage[index]*stroke.flow
                result[index]=if(stroke.erase)result[index]*(1-opacity) else result[index]+(1-result[index])*opacity
            }
        }
        for(index in result.indices)result[index]=(if(layer.inverted)1-result[index] else result[index])*layer.opacity
        return result
    }
}
