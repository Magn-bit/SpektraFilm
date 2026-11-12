package com.spektra.film

import android.app.Dialog
import android.content.Context
import android.graphics.*
import android.os.*
import android.view.*
import android.widget.*
import java.util.concurrent.Executors
import kotlin.math.*

/** A separate composition workspace. Edits are never written back into any photo's development state. */
internal class CreativeWorkspaceDialog(context:Context,private val photos:List<CreativePhoto>,private val load:(Int)->Bitmap?,private val export:(CreativeSpec,OutputRecipe)->Unit):Dialog(context) {
    private val main=Handler(Looper.getMainLooper());private val worker=Executors.newSingleThreadExecutor()
    private val previews=mutableMapOf<Int,Bitmap>();private var disposed=false
    private var spec=CreativeSpec(columns=if(photos.size==1)1 else if(photos.size<=4)2 else 3,cellAspect=if(photos.size==1 && photos[0].width>0)photos[0].width.toFloat()/photos[0].height else 1f,slots=photos.indices.map {CreativeSlot(it)})
    private var selected=0;private lateinit var preview:CompositionView;private lateinit var details:TextView
    private fun d(v:Int)=(v*context.resources.displayMetrics.density+.5f).toInt()
    private fun text(value:String,size:Float=14f)=TextView(context).apply {text=value;textSize=size;setTextColor(UiTheme.ink);typeface=InterfaceTypography.forText(context,value,size);includeFontPadding=false}
    private fun button(label:String,primary:Boolean=false,action:()->Unit)=text(label).apply {gravity=Gravity.CENTER;minimumHeight=d(48);setPadding(d(12),d(8),d(12),d(8));background=UiTheme.controlBackground(context,if(primary)UiTheme.ink else Color.TRANSPARENT,8f,Color.TRANSPARENT);if(primary)setTextColor(UiTheme.surface);isFocusable=true;isClickable=true;contentDescription=label;setOnClickListener {action()}}
    private fun update(){preview.invalidate();val size=photos.map {max(1,it.width) to max(1,it.height)};details.text=runCatching {CreativeLayout.plan(size,spec).let {"${it.width} × ${it.height} · ${selected+1} / ${photos.size}"}}.getOrDefault("正在读取照片尺寸")}
    override fun onCreate(state:Bundle?) {
        super.onCreate(state);requestWindowFeature(Window.FEATURE_NO_TITLE)
        val root=LinearLayout(context).apply {orientation=LinearLayout.VERTICAL;setBackgroundColor(UiTheme.background);setPadding(d(12),d(8),d(12),d(8))}
        val head=LinearLayout(context).apply {gravity=Gravity.CENTER_VERTICAL}
        head.addView(button("‹"){dismiss()},LinearLayout.LayoutParams(d(48),-2));head.addView(text("排版",20f),LinearLayout.LayoutParams(0,-2,1f));head.addView(button("交换"){val next=(selected+1)%spec.slots.size;val slots=spec.slots.toMutableList();val slot=slots[selected];slots[selected]=slots[next];slots[next]=slot;spec=spec.copy(slots=slots);update()}.apply {isEnabled=photos.size>1});root.addView(head)
        preview=CompositionView(context);root.addView(preview,LinearLayout.LayoutParams(-1,0,1f))
        details=text("",12f).apply {gravity=Gravity.CENTER;setPadding(0,d(8),0,d(8))};root.addView(details)
        val options=LinearLayout(context).apply {orientation=LinearLayout.VERTICAL}
        val layouts=LinearLayout(context)
        for(columns in 1..min(3,photos.size))layouts.addView(button("$columns 列"){spec=spec.copy(columns=columns);update()},LinearLayout.LayoutParams(0,-2,1f))
        listOf("方格" to 1f,"横幅" to 1.5f,"竖幅" to 2f/3f).forEach {(name,ratio)->layouts.addView(button(name){spec=spec.copy(cellAspect=ratio);update()},LinearLayout.LayoutParams(0,-2,1f))};options.addView(layouts)
        fun slider(label:String,value:Float,max:Float,onChange:(Float)->Unit){val row=LinearLayout(context).apply {gravity=Gravity.CENTER_VERTICAL};row.addView(text(label,12f),LinearLayout.LayoutParams(d(48),-2));row.addView(SeekBar(context).apply {this.max=1000;progress=(value/max*1000).roundToInt();progressTintList=UiTheme.accentColors();thumbTintList=UiTheme.accentColors();minimumHeight=d(48);contentDescription=label;setOnSeekBarChangeListener(object:SeekBar.OnSeekBarChangeListener{override fun onProgressChanged(v:SeekBar,p:Int,user:Boolean){if(user){onChange(p/1000f*max);update()}};override fun onStartTrackingTouch(v:SeekBar){};override fun onStopTrackingTouch(v:SeekBar){}})},LinearLayout.LayoutParams(0,d(48),1f));options.addView(row)}
        slider("间距",spec.gap,.15f){spec=spec.copy(gap=it)};slider("边框",spec.border,.3f){spec=spec.copy(border=it)}
        val tones=LinearLayout(context)
        listOf("暖白" to 0xfff4f1e9.toInt(),"纯白" to Color.WHITE,"深灰" to 0xff242721.toInt()).forEach {(name,color)->tones.addView(button(name){spec=spec.copy(background=color);update()},LinearLayout.LayoutParams(0,-2,1f))}
        tones.addView(button("日期"){val input=EditText(context).apply {setSingleLine();setText(spec.date.ifBlank {java.text.SimpleDateFormat("yyyy.MM.dd",java.util.Locale.US).format(java.util.Date())})};android.app.AlertDialog.Builder(context).setTitle("日期标记").setView(input).setPositiveButton("应用"){_,_->spec=spec.copy(date=input.text.toString().take(40));update()}.setNeutralButton("移除"){_,_->spec=spec.copy(date="");update()}.setNegativeButton("取消",null).show()},LinearLayout.LayoutParams(0,-2,1f));options.addView(tones)
        val precision=LinearLayout(context)
        precision.addView(button("取景复位"){val slots=spec.slots.toMutableList();slots[selected]=slots[selected].copy(panX=.5f,panY=.5f,zoom=1f);spec=spec.copy(slots=slots);update()},LinearLayout.LayoutParams(0,-2,1f))
        precision.addView(button("导出",true){val recipes=listOf(OutputRecipe.DEFAULTS[0],OutputRecipe.DEFAULTS[2],OutputRecipe.DEFAULTS[3]);android.app.AlertDialog.Builder(context).setTitle("导出排版").setItems(recipes.map {it.name}.toTypedArray()){_,i->export(spec,recipes[i]);dismiss()}.setNegativeButton("取消",null).show()},LinearLayout.LayoutParams(0,-2,1f));options.addView(precision)
        root.addView(ScrollView(context).apply {addView(options)},LinearLayout.LayoutParams(-1,d(240)));setContentView(root)
        setOnDismissListener {disposed=true;worker.shutdownNow();previews.values.forEach {it.recycle()};previews.clear()}
        photos.indices.forEach {i->worker.execute {val bitmap=runCatching {load(i)}.getOrNull();main.post {if(disposed)bitmap?.recycle() else {if(bitmap!=null)previews[i]=bitmap;update()}}}}
        update()
    }
    override fun onStart(){super.onStart();window?.setBackgroundDrawableResource(android.R.color.transparent);window?.setLayout(-1,-1);window?.decorView?.setOnApplyWindowInsetsListener {v,i->v.setPadding(i.systemWindowInsetLeft,i.systemWindowInsetTop,i.systemWindowInsetRight,i.systemWindowInsetBottom);i};window?.decorView?.requestApplyInsets()}
    private inner class CompositionView(context:Context):View(context) {
        private val paint=Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG);private var lastX=0f;private var lastY=0f;private var rects=emptyList<RectF>()
        private val pinch=ScaleGestureDetector(context,object:ScaleGestureDetector.SimpleOnScaleGestureListener(){override fun onScale(detector:ScaleGestureDetector):Boolean{val slots=spec.slots.toMutableList();slots[selected]=slots[selected].copy(zoom=(slots[selected].zoom*detector.scaleFactor).coerceIn(1f,4f));spec=spec.copy(slots=slots);update();return true}})
        init {contentDescription="拼图预览，轻点选择照片，拖动改变取景，双指缩放；交换按钮交换当前与下一张";isFocusable=true}
        override fun onDraw(c:Canvas) {
            val sizes=photos.indices.map {i->previews[i]?.let {it.width to it.height} ?: (max(1,photos[i].width) to max(1,photos[i].height))}
            val plan=CreativeLayout.plan(sizes,spec,1000);val scale=min((width-d(16)).toFloat()/plan.width,(height-d(16)).toFloat()/plan.height);val left=(width-plan.width*scale)/2;val top=(height-plan.height*scale)/2
            c.save();c.translate(left,top);c.scale(scale,scale);paint.color=spec.background;c.drawRect(0f,0f,plan.width.toFloat(),plan.height.toFloat(),paint)
            rects=plan.cells.map {r->RectF(left+r.left*scale,top+r.top*scale,left+(r.left+r.width)*scale,top+(r.top+r.height)*scale)}
            plan.cells.forEachIndexed {i,r->previews[r.slot.source]?.let {image->val source=CreativeLayout.sourceRect(image.width,image.height,spec.cellAspect,r.slot);val dest=RectF(r.left.toFloat(),r.top.toFloat(),(r.left+r.width).toFloat(),(r.top+r.height).toFloat());c.drawBitmap(image,Rect(source[0].toInt(),source[1].toInt(),(source[0]+source[2]).toInt().coerceAtLeast(source[0].toInt()+1),(source[1]+source[3]).toInt().coerceAtLeast(source[1].toInt()+1)),dest,paint)
                if(i==selected){paint.style=Paint.Style.STROKE;paint.strokeWidth=2/scale;paint.color=UiTheme.accent;c.drawRect(dest,paint);paint.style=Paint.Style.FILL}}}
            if(spec.date.isNotBlank()){paint.color=if(Color.red(spec.background)<100)Color.WHITE else UiTheme.ink;paint.typeface=InterfaceTypography.load(context);paint.textSize=max(12f,plan.footer*.4f);paint.textAlign=Paint.Align.RIGHT;c.drawText(spec.date,plan.width-plan.cells.first().left.toFloat(),plan.height-plan.footer*.35f,paint);paint.textAlign=Paint.Align.LEFT}
            c.restore()
        }
        override fun onTouchEvent(e:MotionEvent):Boolean {pinch.onTouchEvent(e);when(e.actionMasked){MotionEvent.ACTION_DOWN->{selected=rects.indexOfFirst {it.contains(e.x,e.y)}.takeIf {it>=0} ?: selected;lastX=e.x;lastY=e.y;update();return true};MotionEvent.ACTION_MOVE->{if(!pinch.isInProgress && e.pointerCount==1){val rect=rects.getOrNull(selected)?:return true;val slots=spec.slots.toMutableList();val current=slots[selected];slots[selected]=current.copy(panX=(current.panX-(e.x-lastX)/max(1f,rect.width())).coerceIn(0f,1f),panY=(current.panY-(e.y-lastY)/max(1f,rect.height())).coerceIn(0f,1f));spec=spec.copy(slots=slots);lastX=e.x;lastY=e.y;update()};return true};MotionEvent.ACTION_UP->{performClick();return true}};return true}
        override fun performClick():Boolean{super.performClick();return true}
    }
}
