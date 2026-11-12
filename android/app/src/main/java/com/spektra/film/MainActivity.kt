package com.spektra.film

import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.content.Intent
import android.content.Context
import android.content.res.Configuration
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.*
import android.provider.OpenableColumns
import android.provider.DocumentsContract
import android.view.*
import android.view.animation.PathInterpolator
import android.widget.*
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors
import kotlin.math.*

class MainActivity : Activity() {
    private val bg = UiTheme.background; private val ink = UiTheme.ink; private val accent = UiTheme.accent
    private val muted = UiTheme.muted; private val line = UiTheme.line
    private val bookTypeface:Typeface by lazy { InterfaceTypography.load(this) }
    private val main = Handler(Looper.getMainLooper()); private val worker = Executors.newSingleThreadExecutor()
    private val fastWorker = Executors.newSingleThreadExecutor()
    private val fullWorker = Executors.newSingleThreadExecutor()
    private val editStore by lazy { PhotoEditsStore(this) }
    private val rawCacheDelegate = lazy { RawPhotoCache(this) }
    private val rawCache by rawCacheDelegate
    @Volatile private var activityDisposed = false
    private val persistEdits=Runnable { persistCurrentEdits() }
    private val prefs by lazy { getSharedPreferences("atelier", Context.MODE_PRIVATE) }
    private var engine: FilmEngine? = null; private var source: Bitmap? = null; private var spectralSource: Bitmap? = null; private var rendered: Bitmap? = null
    private var sourceUri: Uri? = null; private var fileName = "尚未导入照片"
    private var stockIndex = 0; private var values = Adjustments(); @Volatile private var generation = 0
    private var exporting = false; private var compare = false; private var favoritesOnly = false
    private data class PhotoEdit(val uri:Uri,val name:String,var stock:Int,var adjustments:Adjustments,var sourceWidth:Int=0,var sourceHeight:Int=0)
    private val photos=mutableListOf<PhotoEdit>()
    private val selectedPhotos=mutableSetOf<Int>()
    private var currentPhoto=-1
    @Volatile private var cancelBatch=false
    private var batchTotal=0
    private var exportProgressDialog:AlertDialog?=null
    private var exportProgressBar:ProgressBar?=null
    private var exportProgressText:TextView?=null
    private var exportCancelButton:TextView?=null
    private var exportStartedAt=0L
    @Volatile private var exportProgressRun=0L
    private var lastProgressPosition=-1
    private var lastPhotoProgress=0
    private var lastOverallProgress=0
    @Volatile private var activeExportRaw=false
    private lateinit var photoButton:TextView
    private var interactionSource:Bitmap?=null
    @Volatile private var dragging=false
    @Volatile private var dragStartGeneration=-1
    private val renderRunning=booleanArrayOf(false,false)
    private val queuedRender=booleanArrayOf(false,false)
    private var publishedGeneration=-1
    private var publishedQuality=0
    @Volatile private var importing = false
    private val favorites = mutableSetOf<String>()
    private lateinit var root: LinearLayout; private lateinit var canvas: PhotoCanvas
    private lateinit var status: TextView; private lateinit var filename: TextView; private lateinit var fileDimensions: TextView
    private lateinit var cropRatioButton: TextView; private lateinit var filmTitle: TextView
    private lateinit var filmRow: LinearLayout; private lateinit var controls: LinearLayout; private lateinit var subtitle: TextView
    private lateinit var filmTab: TextView; private lateinit var adjustTab: TextView; private lateinit var favoriteButton: TextView
    private lateinit var exportButton: TextView; private lateinit var compareButton: TextView
    private lateinit var resetButton:TextView; private lateinit var importButton:TextView
    private lateinit var editorScroll:ScrollView
    private lateinit var editorWorkspace:LinearLayout
    private lateinit var previewPane:LinearLayout
    private lateinit var editorPanel:LinearLayout
    private lateinit var panelToggle:TextView
    private lateinit var previewStage:FrameLayout
    private var panelVisible=true
    private var cropEditor:CropEditorView?=null
    private var cropSnapshot:Bitmap?=null
    private var cropToolbar:LinearLayout?=null
    private lateinit var previewTools:LinearLayout
    private var panelBeforeCrop=true
    private val histories=mutableMapOf<String,EditHistory>()
    private var editClipboard:EditClipboard?=null
    private var gestureSnapshot:EditorSnapshot?=null
    private lateinit var historyButton:TextView
    private var toolGroup=0
    private var hslBand=0
    private var calibrationBand=0
    private var curveChannel=0
    private var levelsChannel=0
    private var maskOverlayColor=0xffef6554.toInt()
    private var maskOverlayAlpha=.48f
    private var gradingZone=0
    private var selectedMask:String?=null
    private var maskErase=false
    private var maskOverlay=true
    private var brushRadius=.05f
    private var brushFeather=.7f
    private var brushFlow=1f
    private val photoControls=mutableListOf<View>()
    private val filmOnlyControls=mutableListOf<View>()
    private var grainTypeSelector:View?=null
    private var currentTab = 1
    private var darkroomExpanded=false
    private var analysisRunning=false
    private var previewPosted=false
    private val pendingRender = Runnable { previewPosted=false;renderPreview(true) }
    private val refineRender = Runnable { renderPreview(false) }
    private fun dp(v: Float) = (v * resources.displayMetrics.density + .5f).toInt()
    private fun d(v: Int) = dp(v.toFloat())
    private fun text(value: String, size: Float, color: Int = ink, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = UiTokens.fontSize(size); setTextColor(UiTheme.textColors(color)); gravity = Gravity.CENTER_VERTICAL
        typeface = InterfaceTypography.forText(this@MainActivity,value,size,bold)
        includeFontPadding = false
    }
    private fun shape(color: Int, radius: Float = 14f, border: Int = Color.TRANSPARENT) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat(); if (border != Color.TRANSPARENT) setStroke(d(1), border)
    }
    private fun button(label: String, action: () -> Unit, primary: Boolean = false): TextView = text(label, 13f, if(primary) UiTheme.surface else ink, true).apply {
        gravity = Gravity.CENTER; setPadding(d(12),d(8),d(12),d(8)); minimumHeight=d(48);minWidth=d(48)
        background = UiTheme.controlBackground(this@MainActivity,if(primary) ink else Color.TRANSPARENT,9f,Color.TRANSPARENT)
        elevation = d(if(primary) 2 else 0).toFloat(); contentDescription = label; isClickable = true; isFocusable = true
        setOnClickListener { if(!exporting && !importing && isEnabled) { haptic(); action() } }
        setOnTouchListener { v, event ->
            if (motionEnabled() && v.isEnabled) when(event.action) {
                MotionEvent.ACTION_DOWN -> v.animate().scaleX(.98f).scaleY(.98f).setDuration(140).start()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> v.animate().scaleX(1f).scaleY(1f).setDuration(240).setInterpolator(PathInterpolator(.2f,.8f,.2f,1f)).start()
            }; false
        }
    }
    private fun motionEnabled() = prefs.getBoolean("motion",true) && android.animation.ValueAnimator.areAnimatorsEnabled()
    private fun updateActions() {
        if(!::exportButton.isInitialized) return
        val rawReady=sourceUri!=null && ExportPreset.rawExtension(fileName)!=null
        val canEdit=!exporting && !importing && source!=null && engine!=null
        val ready=!exporting && !importing && sourceUri!=null && (source!=null && engine!=null || rawReady)
        exportButton.isEnabled=ready
        exportButton.text=if(exporting) "正在保存…" else if(selectedPhotos.size>1)"导出 ${selectedPhotos.size} 张" else "导出照片"
        if(::photoButton.isInitialized) {
            photoButton.text=if(importing)"取消载入" else if(exporting && batchTotal>1)"停止批量" else if(photos.isEmpty())"照片" else "照片 "+(currentPhoto+1).coerceAtLeast(1)+" / "+photos.size
            photoButton.isEnabled=importing || (!exporting && photos.isNotEmpty()) || (exporting && batchTotal>1)
        }
        importButton.isEnabled=!exporting && !importing
        resetButton.isEnabled=canEdit && values.filmOnly()!=Adjustments().filmOnly()
        if(::historyButton.isInitialized)historyButton.isEnabled=canEdit
        cropRatioButton.isEnabled=canEdit
        if(::panelToggle.isInitialized)panelToggle.isEnabled=!exporting && !importing && source!=null
        if(::controls.isInitialized)setControlEnabled(controls,if(currentTab==1)canEdit else !exporting && !importing)
        photoControls.forEach {setControlEnabled(it,canEdit)}
        filmOnlyControls.forEach {setControlEnabled(it,canEdit && values.filmEnabled)}
        exportButton.setTextColor(UiTheme.textColors(UiTheme.surface))
        exportButton.background=UiTheme.controlBackground(this,ink,9f,Color.TRANSPARENT)
        exportButton.elevation=if(ready) d(2).toFloat() else 0f
        compareButton.isEnabled=rendered!=null && !exporting && !importing
        compareButton.isSelected=compare
        compareButton.text=if(compare)"结束" else "对比"
        compareButton.setTextColor(UiTheme.textColors(if(compare)accent else ink))
        if(Build.VERSION.SDK_INT>=30)compareButton.stateDescription=if(compare)"已开启，拖动照片中的分界线" else "未开启"
        grainTypeSelector?.let {selector ->
            selector.isEnabled=canEdit
            if(selector is ViewGroup)for(index in 0 until selector.childCount)selector.getChildAt(index).isEnabled=selector.isEnabled
        }
        if(exporting)window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
    private fun setControlEnabled(view:View,enabled:Boolean) {
        view.isEnabled=enabled
        if(view is ViewGroup)for(index in 0 until view.childCount)setControlEnabled(view.getChildAt(index),enabled)
    }
    private fun haptic() { if (prefs.getBoolean("haptic", true)) root.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        favorites.addAll(prefs.getStringSet("favorites", emptySet()) ?: emptySet())
        window.statusBarColor = bg; window.navigationBarColor = if(Build.VERSION.SDK_INT>=27)bg else ink
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or (if(Build.VERSION.SDK_INT>=27)View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR else 0)
        buildUi()
        try { engine = FilmEngine(this) } catch(e: Exception) { status.text = "胶片资源尚未就绪"; subtitle.text = "请检查完整资源安装" }
        engine?.stocks?.indexOfFirst { it.id == "kodak_portra_400" }?.takeIf { it >= 0 }?.let { stockIndex = it }
        buildFilmCards(); showTab(currentTab)
        if(engine!=null) status.text = "未导入照片"
    }
    private fun buildUi() {
        root=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL;setBackgroundColor(bg);clipToPadding=false
        }
        root.setOnApplyWindowInsetsListener { view,insets ->
            if(Build.VERSION.SDK_INT>=30) {
                val bars=insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                view.setPadding(bars.left,bars.top,bars.right,bars.bottom)
            } else view.setPadding(insets.systemWindowInsetLeft,insets.systemWindowInsetTop,
                insets.systemWindowInsetRight,insets.systemWindowInsetBottom)
            insets
        }
        setContentView(root);root.requestApplyInsets()
        val header=LinearLayout(this).apply {
            gravity=Gravity.CENTER_VERTICAL;minimumHeight=d(56);setPadding(d(8),0,d(8),0)
        }
        header.addView(button("‹",{finish()}).apply {contentDescription="返回";textSize=28f;setPadding(0,0,0,0)},LinearLayout.LayoutParams(d(48),-2))
        header.addView(text("光影暗房",20f).apply {typeface=bookTypeface;maxLines=1;setPadding(d(4),d(6),0,d(6))},LinearLayout.LayoutParams(0,-2,1f))
        val settingsButton=button("设置",{settings()}).apply {text="";contentDescription="设置";setPadding(d(12),d(12),d(12),d(12))}
        header.addView(FrameLayout(this).apply {
            addView(AppBarMark(this@MainActivity,false),FrameLayout.LayoutParams(d(22),d(22),Gravity.CENTER))
            addView(settingsButton,FrameLayout.LayoutParams(-1,-1))
        },LinearLayout.LayoutParams(d(48),d(48)))
        importButton=button("导入",{importPhoto()}).apply {text="";contentDescription="导入照片";setPadding(d(12),d(12),d(12),d(12))}
        header.addView(FrameLayout(this).apply {
            addView(AppBarMark(this@MainActivity,true),FrameLayout.LayoutParams(d(22),d(22),Gravity.CENTER))
            addView(importButton,FrameLayout.LayoutParams(-1,-1))
        },LinearLayout.LayoutParams(d(48),d(48)))
        root.addView(header,LinearLayout.LayoutParams(-1,-2))

        // Photo and parameters have independent, bounded layout space. The photo
        // is never a child of the parameter scroll, even while editing its last row.
        editorWorkspace=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;clipToPadding=false}
        root.addView(editorWorkspace,LinearLayout.LayoutParams(-1,0,1f))
        previewPane=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(12),0,d(12),0)}
        editorWorkspace.addView(previewPane,LinearLayout.LayoutParams(-1,0,1f))
        val fileRow=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL}
        val fileCaption=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(4),d(4),0,d(4))}
        filename=text(fileName,14f,ink).apply {
            tag="photo-filename";maxLines=1;ellipsize=android.text.TextUtils.TruncateAt.MIDDLE
            isClickable=true;isFocusable=true;minimumHeight=d(28)
            contentDescription="文件名，点击查看完整名称";setOnClickListener {showFileInfo()}
        }
        fileDimensions=text("未导入照片",12f,muted).apply {maxLines=1;ellipsize=android.text.TextUtils.TruncateAt.END}
        fileCaption.addView(filename,LinearLayout.LayoutParams(-1,-2));fileCaption.addView(fileDimensions,LinearLayout.LayoutParams(-1,-2))
        fileRow.addView(fileCaption,LinearLayout.LayoutParams(0,-2,1f))
        photoButton=button("照片",{photoPicker()}).apply {
            tag="photo-browser";maxLines=1;maxWidth=d(132);ellipsize=android.text.TextUtils.TruncateAt.END
            setPadding(d(8),d(8),d(8),d(8))
        }
        photoButton.setOnClickListener {if(importing)cancelPhotoImport() else if(exporting && batchTotal>1)requestExportCancel() else if(!exporting)photoPicker()}
        fileRow.addView(photoButton,LinearLayout.LayoutParams(-2,-2));previewPane.addView(fileRow,LinearLayout.LayoutParams(-1,-2))
        previewStage=FrameLayout(this).apply {tag="photo-stage";background=shape(UiTheme.canvas,8f);clipToOutline=true}
        canvas=PhotoCanvas(this,bookTypeface).apply {
            tag="photo-preview"
            setOnClickListener {if(source==null)importPhoto() else if(!exporting && !importing && cropEditor==null)setEditorVisible(!panelVisible,true)}
        }
        previewStage.addView(canvas,FrameLayout.LayoutParams(-1,-1))
        previewPane.addView(previewStage,LinearLayout.LayoutParams(-1,0,1f).apply {topMargin=d(8)})
        val tools=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL};previewTools=tools
        cropRatioButton=button("裁切",{openCropRatios()}).apply {
            tag="crop-ratio";setPadding(d(8),d(6),d(8),d(6));maxLines=1;contentDescription="裁切照片"
        }
        tools.addView(cropRatioButton,LinearLayout.LayoutParams(-2,-2))
        status=text("正在准备…",12f,muted).apply {
            tag="photo-status";maxLines=1;ellipsize=android.text.TextUtils.TruncateAt.END
            setPadding(d(4),0,d(4),0);accessibilityLiveRegion=View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        tools.addView(status,LinearLayout.LayoutParams(0,-2,1f))
        compareButton=button("对比",{
            if(source!=null) {compare=!compare;canvas.comparing=compare;canvas.invalidate();updateActions()}
        }).apply {tag="photo-compare";contentDescription="前后对比，拖动照片中的分界线";setPadding(d(8),d(6),d(8),d(6))}
        tools.addView(compareButton,LinearLayout.LayoutParams(-2,-2))
        panelToggle=button("收起",{setEditorVisible(!panelVisible,true)}).apply {tag="editor-toggle";setPadding(d(8),d(6),d(8),d(6));contentDescription="收起调整面板，扩大照片"}
        tools.addView(panelToggle,LinearLayout.LayoutParams(-2,-2));previewPane.addView(tools,LinearLayout.LayoutParams(-1,-2))

        editorPanel=LinearLayout(this).apply {
            tag="editor-panel";orientation=LinearLayout.VERTICAL;setPadding(d(16),d(8),d(16),0)
            setBackgroundColor(UiTheme.surface)
        }
        editorWorkspace.addView(editorPanel,LinearLayout.LayoutParams(-1,d(280)))
        val editorHeader=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL}
        val tabs=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL;setPadding(d(2),d(2),d(2),d(2));background=shape(UiTheme.canvas,8f)}
        filmTab=button("胶片",{showTab(0)}).apply {tag="tab-film"}
        adjustTab=button("调整",{showTab(1)}).apply {tag="tab-develop"}
        tabs.addView(filmTab,LinearLayout.LayoutParams(0,-2,1f));tabs.addView(adjustTab,LinearLayout.LayoutParams(0,-2,1f))
        editorHeader.addView(tabs,LinearLayout.LayoutParams(0,-2,1f))
        resetButton=button("恢复默认",{
            rememberEdit();values=Adjustments();updateCropUi();showTab(currentTab);scheduleRender();toast("已恢复当前照片全部参数，可撤销")
        }).apply {tag="reset-parameters";setPadding(d(12),d(8),0,d(8));contentDescription="恢复当前照片参数和裁切的默认值，保留胶片选择"}
        resetButton.visibility=View.GONE
        historyButton=button("···",{showEditActions()}).apply {contentDescription="编辑操作，撤销、重做或恢复全部参数";textSize=22f;setPadding(d(12),0,d(4),0)}
        editorHeader.addView(historyButton,LinearLayout.LayoutParams(d(48),-2).apply {leftMargin=d(8)})
        editorPanel.addView(editorHeader,LinearLayout.LayoutParams(-1,-2))
        controls=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(2),d(4),d(2),d(20))}
        editorScroll=ScrollView(this).apply {
            tag="editor-scroll";isFillViewport=false;isVerticalScrollBarEnabled=true;clipToPadding=false
            addView(controls,FrameLayout.LayoutParams(-1,-2))
        }
        editorPanel.addView(editorScroll,LinearLayout.LayoutParams(-1,0,1f))
        // Material identity is rendered once by the compact film selector.
        filmTitle=text("Portra 400",18f,ink);subtitle=text("",12f,muted)
        val footer=LinearLayout(this).apply {
            tag="export-bar";orientation=LinearLayout.VERTICAL;setPadding(d(16),d(8),d(16),d(8))
            setBackgroundColor(UiTheme.surface);elevation=d(3).toFloat()
        }
        exportButton=button("导出照片",{exportOptions()},true).apply {tag="export-photo";contentDescription="导出照片，保留源图像素尺寸，主动裁切除外"}
        footer.addView(exportButton,LinearLayout.LayoutParams(-1,-2));root.addView(footer,LinearLayout.LayoutParams(-1,-2))
        editorWorkspace.addOnLayoutChangeListener {_,left,top,right,bottom,oldLeft,oldTop,oldRight,oldBottom ->
            if(right-left!=oldRight-oldLeft || bottom-top!=oldBottom-oldTop)layoutEditorWorkspace()
        }
        updateActions();editorWorkspace.post {layoutEditorWorkspace()}
    }
    private fun layoutEditorWorkspace() {
        if(!::editorWorkspace.isInitialized || editorWorkspace.height<=0)return
        val landscape=editorWorkspace.width>editorWorkspace.height*1.05f
        editorWorkspace.orientation=if(landscape)LinearLayout.HORIZONTAL else LinearLayout.VERTICAL
        val previewParams=if(landscape)LinearLayout.LayoutParams(0,-1,1f) else LinearLayout.LayoutParams(-1,0,1f)
        previewPane.layoutParams=previewParams
        val panelParams=if(landscape)LinearLayout.LayoutParams(
            (editorWorkspace.width*.40f).roundToInt().coerceIn(d(264),d(380)),-1)
        else LinearLayout.LayoutParams(-1,(editorWorkspace.height*.43f).roundToInt().coerceIn(d(184),d(340)))
        editorPanel.layoutParams=panelParams
    }
    private fun setEditorVisible(visible:Boolean,animate:Boolean=false) {
        if(!::editorPanel.isInitialized || cropEditor!=null)return
        panelVisible=visible;editorPanel.animate().cancel()
        // One explicit layout change; the photo is not faded to hide a size jump.
        editorPanel.visibility=if(visible)View.VISIBLE else View.GONE
        editorPanel.alpha=1f;editorPanel.translationY=0f
        panelToggle.text=if(visible)"收起" else "调整"
        panelToggle.contentDescription=if(visible)"收起调整面板，扩大照片" else "显示调整面板"
        syncMaskTools()
        panelToggle.isSelected=!visible
        if(Build.VERSION.SDK_INT>=30)panelToggle.stateDescription=if(visible)"调整面板已显示" else "调整面板已收起"
        if(visible && animate && motionEnabled()) {
            editorPanel.alpha=.35f;editorPanel.translationY=d(8).toFloat()
            editorPanel.animate().alpha(1f).translationY(0f).setDuration(160).setInterpolator(PathInterpolator(.2f,.8f,.2f,1f)).start()
        }
    }
    override fun onConfigurationChanged(newConfig:Configuration) {
        super.onConfigurationChanged(newConfig);editorWorkspace.post {layoutEditorWorkspace()}
    }
    private fun showTab(tab: Int) {
        currentTab=tab.coerceIn(0,1)
        listOf(filmTab,adjustTab).forEachIndexed {index,tabView ->
            val selected=index==currentTab;tabView.isSelected=selected
            tabView.setTextColor(UiTheme.textColors(if(selected)accent else muted))
            tabView.background=UiTheme.controlBackground(this,if(selected)UiTheme.selection else Color.TRANSPARENT,8f,if(selected)accent else Color.TRANSPARENT)
            tabView.contentDescription=if(index==0)"胶片分组" else "调整分组"
            if(Build.VERSION.SDK_INT>=30)tabView.stateDescription=if(selected)"已选中" else "未选中"
        }
        controls.removeAllViews();grainTypeSelector=null;photoControls.clear();filmOnlyControls.clear()
        syncMaskTools()
        if(currentTab==0) {
            val enabled=Switch(this).apply {text="胶片显影";textSize=14f;typeface=bookTypeface;setTextColor(ink);minimumHeight=d(48);isChecked=values.filmEnabled;contentDescription="启用胶片显影";setOnCheckedChangeListener {_,checked ->rememberEdit();values=values.copy(filmEnabled=checked);scheduleRender()}}
            controls.addView(enabled,LinearLayout.LayoutParams(-1,-2));photoControls.add(enabled)
            val row=LinearLayout(this).apply { gravity=Gravity.CENTER_VERTICAL }
            val visibleCount=engine?.stocks?.count {!favoritesOnly || it.id in favorites} ?: 0
            row.addView(text("胶片 · $visibleCount",12f,muted),LinearLayout.LayoutParams(0,d(40),1f))
            favoriteButton=button(if(favoritesOnly)"全部" else "收藏",{favoritesOnly=!favoritesOnly;showTab(0)}).apply {setPadding(d(12),d(4),0,d(4))}
            row.addView(favoriteButton);controls.addView(row)
            val scroll=HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled=false;clipToPadding=false }
            filmRow=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL }
            scroll.addView(filmRow);controls.addView(scroll,LinearLayout.LayoutParams(-1,-2));buildFilmCards()
            addSlider(controls,"胶片强度","FILM STRENGTH",values.strength,0f,1f,{ values=values.copy(strength=it) },false,
                {String.format(java.util.Locale.US,"%.2f%%",it*100f)},1f)
            filmOnlyControls.add(controls.getChildAt(controls.childCount-1))
        } else {
            val groups=listOf("基础","色彩","校准","曲线","色轮","蒙版","几何","预设","显影")
            val row=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL;setPadding(0,d(4),0,d(8))}
            groups.forEachIndexed {i,label ->
                row.addView(button(label,{toolGroup=i;showTab(1)}).apply {
                    val selected=i==toolGroup;isSelected=selected
                    background=UiTheme.controlBackground(this@MainActivity,if(selected)UiTheme.selection else Color.TRANSPARENT,7f,if(selected)accent else Color.TRANSPARENT)
                    setTextColor(UiTheme.textColors(if(selected)UiTheme.accentText else muted));setPadding(d(12),d(4),d(12),d(4))
                },LinearLayout.LayoutParams(-2,-2).apply {rightMargin=d(4)})
            }
            controls.addView(HorizontalScrollView(this).apply {isHorizontalScrollBarEnabled=false;addView(row)},LinearLayout.LayoutParams(-1,-2))
            buildEditorGroup()
        }
        updateStockLabel();updateActions();controls.animate().cancel()
        if(motionEnabled()) {controls.alpha=0f;controls.translationY=d(5).toFloat();controls.animate().alpha(1f).translationY(0f).setDuration(240).start()}
        else {controls.alpha=1f;controls.translationY=0f}
    }
    private fun snapshot()=EditorSnapshot(stockIndex,values.filmOnly())
    private fun editHistory()=sourceUri?.toString()?.let {histories.getOrPut(it){EditHistory()}}
    private fun rememberEdit() {if(gestureSnapshot==null)editHistory()?.remember(snapshot())}
    private fun beginEditGesture() {if(gestureSnapshot==null)gestureSnapshot=snapshot()}
    private fun endEditGesture() {gestureSnapshot?.let {before ->if(before!=snapshot())editHistory()?.remember(before)};gestureSnapshot=null}
    private fun restoreEdit(state:EditorSnapshot) {stockIndex=state.stock;values=state.values;updateCropUi();showTab(currentTab);scheduleRender()}
    private fun showEditActions() {
        val history=editHistory() ?: return
        val labels=listOf("撤销","重做","恢复全部参数","复制调整…","粘贴调整","同步到所选照片…")
        val panel=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(16),0,d(16),d(12))}
        var dialog:AlertDialog?=null
        labels.forEachIndexed {i,label ->
            val row=button(label,{
                dialog?.dismiss()
                when(i) {0->history.undo(snapshot())?.let(::restoreEdit);1->history.redo(snapshot())?.let(::restoreEdit);
                    2->resetButton.performClick();3->chooseEditCategories(false);4->editClipboard?.let {applyTransferredEdits(it,exportIndices())};5->chooseEditCategories(true)}
            }).apply {isEnabled=when(i){0->history.canUndo;1->history.canRedo;2->resetButton.isEnabled;4->editClipboard!=null;5->selectedPhotos.any {it!=currentPhoto};else->true};gravity=Gravity.START}
            panel.addView(row,LinearLayout.LayoutParams(-1,-2))
        }
        dialog=AlertDialog.Builder(this).setTitle("编辑操作").setView(panel).setNegativeButton("取消",null).create()
        dialog.show();styleDialog(dialog)
    }
    private fun chooseEditCategories(sync:Boolean) {
        val source=snapshot();val categories=EditCategory.entries
        val chosen=categories.map {it.selectedByDefault}.toBooleanArray()
        val dialog=AlertDialog.Builder(this).setTitle(if(sync)"同步调整" else "复制调整")
            .setMultiChoiceItems(categories.map {it.title}.toTypedArray(),chosen) {_,index,checked->chosen[index]=checked}
            .setPositiveButton(if(sync)"同步" else "复制") {_,_->
                val clipboard=EditClipboard(source,categories.filterIndexed {index,_->chosen[index]}.toSet())
                if(clipboard.categories.isEmpty())return@setPositiveButton
                editClipboard=clipboard
                if(sync)applyTransferredEdits(clipboard,selectedPhotos.filter {it!=currentPhoto}) else toast("已复制所选调整")
            }.setNegativeButton("取消",null).create()
        dialog.show();styleDialog(dialog)
    }
    private fun applyTransferredEdits(clipboard:EditClipboard,indices:Collection<Int>) {
        if(exporting || importing)return
        saveSession();var changed=0;val saves=mutableListOf<Triple<Uri,Int,Adjustments>>()
        for(index in indices.distinct().filter {it in photos.indices}) {
            val entry=photos[index];val before=EditorSnapshot(entry.stock,entry.adjustments)
            val after=clipboard.applyTo(before)
            if(before==after)continue
            histories.getOrPut(entry.uri.toString()){EditHistory()}.remember(before)
            entry.stock=after.stock;entry.adjustments=after.values;changed++
            if(index==currentPhoto) {stockIndex=after.stock;values=after.values}
            saves.add(Triple(entry.uri,after.stock,after.values))
        }
        // One bounded worker job rather than one queued task per imported photo.
        if(saves.isNotEmpty())worker.execute {for((uri,stock,a) in saves){if(activityDisposed)break;runCatching {editStore.save(uri,stock,a)}}}
        if(changed>0) {updateCropUi();showTab(currentTab);scheduleRender()}
        toast(if(changed>0)"已应用至 $changed 张，可在各照片中撤销" else "所选照片参数相同")
    }
    private fun field(title:String,labels:List<String>,selected:Int,onSelect:(Int)->Unit) {
        if(labels.isEmpty())return
        val row=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL;minimumHeight=d(48);setPadding(d(12),0,d(10),0);isClickable=true;isFocusable=true;background=UiTheme.controlBackground(this@MainActivity);contentDescription="$title，当前${labels.getOrElse(selected){labels.first()}}"}
        row.addView(text(title,14f),LinearLayout.LayoutParams(0,-2,1f))
        row.addView(text(labels.getOrElse(selected){labels.first()},13f,UiTheme.accentText).apply {gravity=Gravity.END;maxLines=1;ellipsize=android.text.TextUtils.TruncateAt.END},LinearLayout.LayoutParams(-2,-2))
        row.addView(DropdownMark(this),LinearLayout.LayoutParams(d(24),d(48)).apply {leftMargin=d(4)})
        row.setOnClickListener {
            if(source==null || importing || exporting)return@setOnClickListener
            val dialog=AlertDialog.Builder(this).setTitle(title).setSingleChoiceItems(labels.toTypedArray(),selected) {choice,index ->choice.dismiss();onSelect(index)}.setNegativeButton("取消",null).create()
            dialog.show();styleDialog(dialog)
        }
        controls.addView(row,LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(6);bottomMargin=d(8)});photoControls.add(row)
    }
    private fun scalar(title:String,value:Float,minimum:Float=-100f,maximum:Float=100f,default:Float=0f,unit:String="",onChange:(Float)->Unit) {
        val colors=when {
            toolGroup==0 && title=="色温"->intArrayOf(0xff527cab.toInt(),0xffb3b5a2.toInt(),0xffd5aa57.toInt())
            toolGroup==0 && title=="色调"->intArrayOf(0xff63865e.toInt(),0xffb5afa4.toInt(),0xffae7195.toInt())
            toolGroup==2 && title=="阴影色调"->intArrayOf(0xff60845a.toInt(),0xffb5afa4.toInt(),0xffa96c94.toInt())
            toolGroup==2 && title=="色相"->when(calibrationBand){0->intArrayOf(0xffa74e8d.toInt(),0xffb95e54.toInt(),0xffcfb44f.toInt());1->intArrayOf(0xffb9a750.toInt(),0xff6e975c.toInt(),0xff4a9c94.toInt());else->intArrayOf(0xff508a92.toInt(),0xff5d6fa5.toInt(),0xff9f5d9f.toInt())}
            else->null
        }
        addSlider(controls,title,"",value,minimum,maximum,onChange,unit==" EV",{v ->String.format(java.util.Locale.US,if(unit==" K")"%.0f%s" else "%+.2f%s",v,unit)},default,colors)
    }
    private fun buildEditorGroup() {
        when(toolGroup) {
            0->{
                val auto=LinearLayout(this)
                listOf("白平衡" to "white_balance","色阶" to "levels","明暗" to "tone").forEach {(label,kind)->auto.addView(button("自动$label",{proposeAuto(kind,label)}),LinearLayout.LayoutParams(0,-2,1f))}
                controls.addView(auto)
                addSectionLabel(controls,"白平衡")
                scalar("色温",values.temperature,2000f,10000f,6500f," K"){values=values.copy(temperature=it)}
                scalar("色调",values.tint){values=values.copy(tint=it)}
                addSectionLabel(controls,"明暗")
                scalar("曝光",values.exposure,-5f,5f,0f," EV"){values=values.copy(exposure=it)}
                scalar("对比度",values.contrast){values=values.copy(contrast=it)}
                scalar("高光",values.highlights){values=values.copy(highlights=it)}
                scalar("阴影",values.shadows){values=values.copy(shadows=it)}
                scalar("白色",values.whites){values=values.copy(whites=it)}
                scalar("黑色",values.blacks){values=values.copy(blacks=it)}
                buildLevelsControls()
                addSectionLabel(controls,"细节")
                scalar("锐化",values.sharpening,0f,100f){values=values.copy(sharpening=it)}
                scalar("亮度降噪",values.noiseLuminance,0f,100f){values=values.copy(noiseLuminance=it)}
                scalar("彩色降噪",values.noiseColor,0f,100f){values=values.copy(noiseColor=it)}
                scalar("纹理",values.texture){values=values.copy(texture=it)}
                scalar("清晰度",values.clarity){values=values.copy(clarity=it)}
                scalar("去朦胧",values.dehaze){values=values.copy(dehaze=it)}
                addSectionLabel(controls,"色彩")
                scalar("自然饱和度",values.vibrance){values=values.copy(vibrance=it)}
                scalar("饱和度",values.saturation){values=values.copy(saturation=it)}
            }
            1->{
                val names=listOf("红","橙","黄","绿","青","蓝","紫","洋红")
                field("颜色",names,hslBand){hslBand=it;showTab(1)}
                val band=values.hsl.band(hslBand)
                scalar("色相",band.hue){values=values.copy(hsl=values.hsl.withBand(hslBand,values.hsl.band(hslBand).copy(hue=it)))}
                scalar("饱和度",band.saturation){values=values.copy(hsl=values.hsl.withBand(hslBand,values.hsl.band(hslBand).copy(saturation=it)))}
                scalar("明亮度",band.luminance){values=values.copy(hsl=values.hsl.withBand(hslBand,values.hsl.band(hslBand).copy(luminance=it)))}
            }
            2->{
                scalar("阴影色调",values.shadowTint){values=values.copy(shadowTint=it)}
                calibrationBand=0;addSectionLabel(controls,"红原色")
                scalar("色相",values.redHue){values=values.copy(redHue=it)};scalar("饱和度",values.redSaturation){values=values.copy(redSaturation=it)}
                calibrationBand=1;addSectionLabel(controls,"绿原色")
                scalar("色相",values.greenHue){values=values.copy(greenHue=it)};scalar("饱和度",values.greenSaturation){values=values.copy(greenSaturation=it)}
                calibrationBand=2;addSectionLabel(controls,"蓝原色")
                scalar("色相",values.blueHue){values=values.copy(blueHue=it)};scalar("饱和度",values.blueSaturation){values=values.copy(blueSaturation=it)}
            }
            3->{
                field("曲线通道",listOf("RGB","红","绿","蓝","亮度"),curveChannel){curveChannel=it;showTab(1)}
                val editor=CurveEditorView(this).apply {
                    points=values.curves.channel(curveChannel);histogram=curveHistogram();curveColor=listOf(ink,0xffa44c45.toInt(),0xff647b50.toInt(),0xff577a9e.toInt(),accent)[curveChannel]
                    onGestureStart={beginEditGesture();dragging=true;dragStartGeneration=generation}
                    onChange={points ->values=values.copy(curves=values.curves.withChannel(curveChannel,points));scheduleRender()}
                    onGestureEnd={endEditGesture();dragging=false;scheduleRender()}
                }
                controls.addView(editor,LinearLayout.LayoutParams(-1,d(220)));photoControls.add(editor)
                val actions=LinearLayout(this)
                actions.addView(button("删除控制点",{beginEditGesture();editor.removeSelected();endEditGesture()}),LinearLayout.LayoutParams(0,-2,1f))
                actions.addView(button("恢复当前曲线",{rememberEdit();values=values.copy(curves=values.curves.withChannel(curveChannel,CurveSet().master));showTab(1);scheduleRender()}),LinearLayout.LayoutParams(0,-2,1f))
                controls.addView(actions)
            }
            4->{
                field("明暗区域",listOf("阴影","中间调","高光"),gradingZone){gradingZone=it;showTab(1)}
                val wheel=GradingWheelView(this).apply {
                    grade=values.grading.zone(gradingZone)
                    onGestureStart={beginEditGesture();dragging=true;dragStartGeneration=generation}
                    onChange={grade ->values=values.copy(grading=values.grading.withZone(gradingZone,grade));scheduleRender()}
                    onGestureEnd={endEditGesture();dragging=false;showTab(1);scheduleRender()}
                }
                controls.addView(wheel,LinearLayout.LayoutParams(-1,d(216)));photoControls.add(wheel)
                scalar("色相",values.grading.zone(gradingZone).hue,0f,360f,0f,"°"){values=values.copy(grading=values.grading.withZone(gradingZone,values.grading.zone(gradingZone).copy(hue=it)));wheel.grade=values.grading.zone(gradingZone)}
                scalar("饱和度",values.grading.zone(gradingZone).saturation,0f,100f){values=values.copy(grading=values.grading.withZone(gradingZone,values.grading.zone(gradingZone).copy(saturation=it)));wheel.grade=values.grading.zone(gradingZone)}
                scalar("明亮度",values.grading.zone(gradingZone).luminance){values=values.copy(grading=values.grading.withZone(gradingZone,values.grading.zone(gradingZone).copy(luminance=it)))}
                scalar("混合",values.grading.blending,0f,100f,50f){values=values.copy(grading=values.grading.copy(blending=it))}
                scalar("平衡",values.grading.balance){values=values.copy(grading=values.grading.copy(balance=it))}
            }
            5->buildMaskControls()
            6->{
                controls.addView(button("自动拉直",{proposeAuto("geometry","拉直")}),LinearLayout.LayoutParams(-1,-2))
                controls.addView(button("裁切与构图",{openCropRatios()}).apply {gravity=Gravity.START;background=UiTheme.controlBackground(this@MainActivity)},LinearLayout.LayoutParams(-1,-2))
                val turns=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL}
                turns.addView(text("旋转 90°",14f),LinearLayout.LayoutParams(0,-2,1f))
                for(clockwise in listOf(false,true)) {
                    val hit=button("",{rotatePhoto(if(clockwise)1 else -1)}).apply {
                        contentDescription=if(clockwise)"向右旋转 90 度" else "向左旋转 90 度";tooltipText=contentDescription
                    }
                    turns.addView(FrameLayout(this).apply {
                        addView(RotatePhotoMark(this@MainActivity,clockwise),FrameLayout.LayoutParams(d(24),d(24),Gravity.CENTER))
                        addView(hit,FrameLayout.LayoutParams(-1,-1))
                    },LinearLayout.LayoutParams(d(48),d(48)))
                }
                controls.addView(turns);photoControls.add(turns)
                scalar("拉直",values.geometry.rotation,-45f,45f,0f,"°"){values=values.copy(geometry=values.geometry.copy(rotation=it))}
                scalar("垂直透视",values.geometry.vertical){values=values.copy(geometry=values.geometry.copy(vertical=it))}
                scalar("水平透视",values.geometry.horizontal){values=values.copy(geometry=values.geometry.copy(horizontal=it))}
                scalar("宽高",values.geometry.aspect){values=values.copy(geometry=values.geometry.copy(aspect=it))}
                scalar("缩放",values.geometry.scale,100f,200f,100f,"%"){values=values.copy(geometry=values.geometry.copy(scale=it))}
                val row=LinearLayout(this)
                row.addView(button("水平翻转",{rememberEdit();values=values.copy(geometry=values.geometry.copy(flipHorizontal=!values.geometry.flipHorizontal));showTab(1);scheduleRender()}).apply {isSelected=values.geometry.flipHorizontal},LinearLayout.LayoutParams(0,-2,1f))
                row.addView(button("垂直翻转",{rememberEdit();values=values.copy(geometry=values.geometry.copy(flipVertical=!values.geometry.flipVertical));showTab(1);scheduleRender()}).apply {isSelected=values.geometry.flipVertical},LinearLayout.LayoutParams(0,-2,1f));controls.addView(row)
            }
            7->buildPresetControls()
            else->{
                if(!values.filmEnabled) {controls.addView(button("启用胶片显影",{rememberEdit();values=values.copy(filmEnabled=true);showTab(1);scheduleRender()}),LinearLayout.LayoutParams(-1,-2));return}
                addSectionLabel(controls,"颗粒");addGrainTypeSelector();addFilmFormatSelector()
                addSlider(controls,"颗粒","",values.grain,0f,1f,{values=values.copy(grain=it)},false,{String.format(java.util.Locale.US,"%.2f%%",it*100)},.18f)
                addSlider(controls,"颗粒大小","",values.grainSize,.25f,2.5f,{values=values.copy(grainSize=it)},false,{String.format(java.util.Locale.US,"%.3f×",it)},1f)
                addSectionLabel(controls,"光学")
                addSlider(controls,"高光光晕","",values.halation,0f,1f,{values=values.copy(halation=it)},false,{String.format(java.util.Locale.US,"%.2f%%",it*100)},.12f)
                addSlider(controls,"暗角","",values.vignette,0f,1f,{values=values.copy(vignette=it)},false,{String.format(java.util.Locale.US,"%.2f%%",it*100)},0f)
                scalar("光晕高光余量",values.halationHeadroom,0f,6f,0f," EV"){values=values.copy(halationHeadroom=it)}
                addDarkroomControls()
            }
        }
    }
    private fun curveHistogram():FloatArray? {
        val image=(rendered ?: interactionSource ?: source)?.takeUnless {it.isRecycled} ?: return null
        val bins=IntArray(128);val row=IntArray(image.width)
        val yStep=max(1,image.height/160);val xStep=max(1,image.width/200)
        for(y in 0 until image.height step yStep) {
            image.getPixels(row,0,image.width,0,y,image.width,1)
            for(x in 0 until image.width step xStep) {
                val p=row[x];val r=p ushr 16 and 255;val g=p ushr 8 and 255;val b=p and 255
                val value=when(curveChannel){1->r;2->g;3->b;else->(.2126*r+.7152*g+.0722*b).roundToInt()}
                bins[(value/2).coerceIn(0,127)]++
            }
        }
        val peak=bins.maxOrNull()?.coerceAtLeast(1) ?: 1
        return FloatArray(128){sqrt(bins[it].toFloat()/peak)}
    }
    private fun activeMask()=values.masks.firstOrNull {it.id==selectedMask}
    private fun proposeAuto(kind:String,title:String) {
        val image=source ?: return;if(importing || exporting || analysisRunning)return
        val scale=min(1f,320f/max(image.width,image.height));val proxy=Bitmap.createScaledBitmap(image,max(2,(image.width*scale).roundToInt()),max(2,(image.height*scale).roundToInt()),true).copy(Bitmap.Config.ARGB_8888,false)
        val before=values;val uri=sourceUri;val revision=generation;analysisRunning=true;status.text="正在分析…"
        fullWorker.execute {
            val result=runCatching {AutoAdjust.analyze(proxy,kind,before)};proxy.recycle()
            main.post {
                analysisRunning=false;if(activityDisposed || uri!=sourceUri || revision!=generation)return@post
                result.onSuccess {proposal->
                    status.text=if(proposal.values==null)"保留当前调整" else "分析完成"
                    val dialog=AlertDialog.Builder(this).setTitle("自动$title").setMessage(proposal.reason).setNegativeButton("取消",null)
                    if(proposal.values!=null)dialog.setPositiveButton("应用"){_,_->if(uri==sourceUri && revision==generation){rememberEdit();values=proposal.values;updateCropUi();showTab(currentTab);scheduleRender()}}
                    styleDialog(dialog.show())
                }.onFailure {status.text="分析未完成";showError(it.message ?: "自动调整失败")}
            }
        }
    }
    private fun buildLevelsControls() {
        addSectionLabel(controls,"色阶")
        field("通道",listOf("RGB","红","绿","蓝"),levelsChannel){levelsChannel=it;showTab(1)}
        val levels=LevelsHistogramView(this).apply {
            tag="levels-histogram";channel=levelsChannel;value=values.levels.channel(levelsChannel)
            histogram=channelHistogram(levelsChannel)
            onStart={beginEditGesture();dragging=true;dragStartGeneration=generation}
            onChange={next->values=values.copy(levels=values.levels.withChannel(levelsChannel,next));scheduleRender()}
            onEnd={endEditGesture();dragging=false;showTab(currentTab);scheduleRender()}
        }
        controls.addView(levels,LinearLayout.LayoutParams(-1,d(168)));photoControls.add(levels)
        val a=values.levels.channel(levelsChannel)
        val row=LinearLayout(this)
        listOf("输入黑" to a.black,"中间调" to a.gamma,"输入白" to a.white,"输出黑" to a.outputBlack,"输出白" to a.outputWhite).forEachIndexed {i,(label,v)->
            row.addView(button(label+"\n"+String.format(java.util.Locale.US,if(i==1)"%.2f" else "%.3f",v),{
                val input=EditText(this).apply {setSingleLine();setText(v.toString());selectAll();inputType=android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL}
                val dialog=AlertDialog.Builder(this).setTitle(label).setView(input).setPositiveButton("应用",null).setNeutralButton("默认"){_,_->rememberEdit();val n=LevelChannel();val next=when(i){0->a.copy(black=n.black);1->a.copy(gamma=n.gamma);2->a.copy(white=n.white);3->a.copy(outputBlack=n.outputBlack);else->a.copy(outputWhite=n.outputWhite)};values=values.copy(levels=values.levels.withChannel(levelsChannel,next.canonical()));showTab(currentTab);scheduleRender()}.setNegativeButton("取消",null).create()
                dialog.show();styleDialog(dialog);dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val n=input.text.toString().toFloatOrNull();if(n==null || !n.isFinite() || n<(if(i==1).1f else 0f) || n>(if(i==1)10f else 1f))input.error="请输入有效范围" else {
                        rememberEdit();val next=when(i){0->a.copy(black=n);1->a.copy(gamma=n);2->a.copy(white=n);3->a.copy(outputBlack=n);else->a.copy(outputWhite=n)}
                        values=values.copy(levels=values.levels.withChannel(levelsChannel,next.canonical()));dialog.dismiss();showTab(currentTab);scheduleRender()
                    }
                }
            }).apply {textSize=11f;setPadding(0,d(8),0,d(8));contentDescription="$label $v，点击精确输入"},LinearLayout.LayoutParams(0,-2,1f))
        };controls.addView(row)
    }
    private fun channelHistogram(channel:Int):FloatArray {
        val image=(source ?: return FloatArray(128)).takeUnless {it.isRecycled} ?: return FloatArray(128)
        val bins=IntArray(128);val row=IntArray(image.width)
        for(y in 0 until image.height step max(1,image.height/120)) {image.getPixels(row,0,image.width,0,y,image.width,1)
            for(x in 0 until image.width step max(1,image.width/180)){val p=row[x];val r=p ushr 16 and 255;val g=p ushr 8 and 255;val b=p and 255;val v=when(channel){1->r;2->g;3->b;else->(.2126*r+.7152*g+.0722*b).roundToInt()};bins[v/2]++}}
        val peak=max(1,bins.maxOrNull()?:1);return FloatArray(128){sqrt(bins[it].toFloat()/peak)}
    }
    private fun updateMask(change:(MaskLayer)->MaskLayer) {
        val id=selectedMask ?: return
        values=values.copy(masks=values.masks.map {if(it.id==id)change(it) else it});syncMaskTools();scheduleRender()
    }
    private fun syncMaskTools() {
        if(!::canvas.isInitialized)return
        val mask=activeMask();val editing=panelVisible && currentTab==1 && toolGroup==5 && cropEditor==null
        canvas.maskLayer=if(editing)mask else null;canvas.maskToolsVisible=editing
        canvas.brushMode=editing && mask?.kind=="brush";canvas.gradientMode=editing && mask!=null && mask.kind!="brush"
        canvas.brushErase=maskErase;canvas.brushRadius=brushRadius;canvas.brushFeather=brushFeather;canvas.brushFlow=brushFlow
        canvas.showMaskOverlay=maskOverlay;canvas.overlayMotionEnabled=motionEnabled()
        canvas.overlayColor=maskOverlayColor;canvas.overlayAlpha=maskOverlayAlpha
        canvas.onStrokeFinished={stroke ->rememberEdit();updateMask {it.copy(strokes=it.strokes+stroke)}}
        canvas.onGradientStart={beginEditGesture();dragging=true;dragStartGeneration=generation}
        canvas.onGradientChange={draft ->updateMask {draft}}
        canvas.onGradientEnd={endEditGesture();dragging=false;scheduleRender()}
    }
    private fun buildMaskControls() {
        val row=LinearLayout(this)
        row.addView(button("新建蒙版",{
            val names=arrayOf("画笔","线性渐变","径向渐变")
            val dialog=AlertDialog.Builder(this).setTitle("新建蒙版").setItems(names){_,i ->rememberEdit();val mask=MaskLayer(name="${names[i]} ${values.masks.size+1}",kind=listOf("brush","linear","radial")[i]);values=values.copy(masks=values.masks+mask);selectedMask=mask.id;showTab(1);scheduleRender()}.setNegativeButton("取消",null).create()
            dialog.show();styleDialog(dialog)
        }),LinearLayout.LayoutParams(0,-2,1f))
        row.addView(button(if(maskOverlay)"隐藏叠层" else "显示叠层",{maskOverlay=!maskOverlay;syncMaskTools();showTab(1)}),LinearLayout.LayoutParams(0,-2,1f));controls.addView(row)
        if(activeMask()==null)selectedMask=values.masks.lastOrNull()?.id
        val mask=activeMask() ?: return
        field("当前蒙版",values.masks.map {it.name},values.masks.indexOf(mask)){selectedMask=values.masks[it].id;showTab(1)}
        val overlayColors=listOf("朱红" to 0xffef6554.toInt(),"青绿" to 0xff4bc9a1.toInt(),"天蓝" to 0xff65b5f5.toInt(),"洋红" to 0xffda72d2.toInt())
        field("叠层颜色",overlayColors.map {it.first},overlayColors.indexOfFirst {it.second==maskOverlayColor}.coerceAtLeast(0)){maskOverlayColor=overlayColors[it].second;syncMaskTools()}
        addSlider(controls,"叠层可见度","",maskOverlayAlpha,.1f,.85f,{maskOverlayAlpha=it;syncMaskTools()},false,{String.format(java.util.Locale.US,"%.0f%%",it*100)},.48f)
        val actions=LinearLayout(this)
        actions.addView(button(if(mask.enabled)"停用" else "启用",{rememberEdit();updateMask {it.copy(enabled=!it.enabled)};showTab(1)}),LinearLayout.LayoutParams(0,-2,1f))
        actions.addView(button("反选",{rememberEdit();updateMask {it.copy(inverted=!it.inverted)};showTab(1)}).apply {isSelected=mask.inverted},LinearLayout.LayoutParams(0,-2,1f))
        actions.addView(button("删除",{rememberEdit();values=values.copy(masks=values.masks.filterNot {it.id==selectedMask});selectedMask=null;showTab(1);scheduleRender()}),LinearLayout.LayoutParams(0,-2,1f));controls.addView(actions)
        if(mask.kind=="brush") {
            controls.addView(button(if(maskErase)"画笔 · 擦除" else "画笔 · 绘制",{maskErase=!maskErase;showTab(1)}),LinearLayout.LayoutParams(-1,-2))
            addSlider(controls,"画笔大小","",brushRadius,.002f,.2f,{brushRadius=it;syncMaskTools()},false,{String.format(java.util.Locale.US,"%.1f%%",it*100)},.05f)
            addSlider(controls,"羽化","",brushFeather,0f,1f,{brushFeather=it;syncMaskTools()},false,null,.7f)
            addSlider(controls,"流量","",brushFlow,.01f,1f,{brushFlow=it;syncMaskTools()},false,null,1f)
        } else addSlider(controls,"羽化","",mask.feather,0f,1f,{updateMask {m->m.copy(feather=it)}},false,null,.75f)
        addSectionLabel(controls,"局部调整")
        addSlider(controls,"不透明度","",mask.opacity,0f,1f,{updateMask {m->m.copy(opacity=it)}},false,null,1f)
        scalar("曝光",mask.exposure,-3f,3f,0f," EV"){updateMask {m->m.copy(exposure=it)}}
        scalar("色温",mask.temperature){updateMask {m->m.copy(temperature=it)}}
        scalar("色调",mask.tint){updateMask {m->m.copy(tint=it)}}
        scalar("对比度",mask.contrast){updateMask {m->m.copy(contrast=it)}}
        scalar("饱和度",mask.saturation){updateMask {m->m.copy(saturation=it)}}
        scalar("高光",mask.highlights){updateMask {m->m.copy(highlights=it)}}
        scalar("阴影",mask.shadows){updateMask {m->m.copy(shadows=it)}}
        syncMaskTools()
    }
    private fun buildPresetControls() {
        val store=ImportedStyleStore(this)
        controls.addView(button("导入参数风格",{
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {type="application/json";addCategory(Intent.CATEGORY_OPENABLE)},102)
        }).apply {gravity=Gravity.START},LinearLayout.LayoutParams(-1,-2))
        val presets=runCatching {StylePreset.load(assets)}.getOrDefault(emptyList()).filter {it.settings.lookLut.isBlank()}+store.load().filter {it.settings.lookLut.isBlank()}
        controls.addView(button("保存当前风格",{
            val name=EditText(this).apply {setSingleLine();setText("我的风格");selectAll();setPadding(d(16),d(8),d(16),d(8))}
            val dialog=AlertDialog.Builder(this).setTitle("保存风格").setView(name).setPositiveButton("保存"){_,_ ->
                val label=name.text.toString().trim().take(60).ifBlank {"我的风格"}
                store.save(StylePreset("user-${System.currentTimeMillis()}",label,"","","personal","",StyleSettings.from(values)));showTab(1)
            }.setNegativeButton("取消",null).create();dialog.show();styleDialog(dialog)
        }),LinearLayout.LayoutParams(-1,-2))
        presets.forEach {preset ->
            controls.addView(button(preset.name,{
                rememberEdit();values=preset.settings.applyTo(values);showTab(1);scheduleRender()
            }).apply {gravity=Gravity.START;contentDescription="应用风格 ${preset.name}"},LinearLayout.LayoutParams(-1,-2))
        }
    }
    private fun addSectionLabel(parent:ViewGroup,title:String) {
        parent.addView(text(title,12f,muted,true).apply {setPadding(d(2),d(20),0,d(8));contentDescription="$title 参数"},LinearLayout.LayoutParams(-1,-2))
    }
    private fun formatRows():List<Pair<String,Float>> {
        val json=org.json.JSONObject(assets.open("darkroom.json").bufferedReader().use {it.readText()})
        val formats=json.getJSONArray("formats")
        return (0 until formats.length()).map { formats.getJSONObject(it).getString("name") to formats.getJSONObject(it).getDouble("mm").toFloat() }
    }
    private fun addFilmFormatSelector() {
        val rows=formatRows();val selected=rows.indexOfFirst {abs(it.second-values.filmFormatMm)<.1}.coerceAtLeast(0)
        val row=button("模拟片幅  ·  ${rows[selected].first}",{
            val dialog=AlertDialog.Builder(this).setTitle("模拟片幅").setSingleChoiceItems(rows.map {it.first}.toTypedArray(),selected) {choice,index ->
                rememberEdit();values=values.copy(filmFormatMm=rows[index].second);choice.dismiss();showTab(1);scheduleRender()
            }.setNegativeButton("取消",null).create()
            dialog.show();styleDialog(dialog)
        }).apply {gravity=Gravity.START or Gravity.CENTER_VERTICAL;background=UiTheme.controlBackground(this@MainActivity);contentDescription="模拟片幅，当前${rows[selected].first}，打开选项"}
        controls.addView(row,LinearLayout.LayoutParams(-1,-2).apply {bottomMargin=d(8)})
    }
    private fun addDarkroomControls() {
        val stock=engine?.stocks?.getOrNull(stockIndex) ?: return
        val toggle=button(if(darkroomExpanded)"收起暗房" else "暗房",{darkroomExpanded=!darkroomExpanded;showTab(1)})
        controls.addView(toggle,LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(16);bottomMargin=d(8)})
        if(!darkroomExpanded)return
        fun choice(title:String,labels:List<String>,selected:Int,onSelect:(Int)->Unit) {
            val row=button("$title  ·  ${labels.getOrElse(selected){labels.first()}}",{
                val dialog=AlertDialog.Builder(this).setTitle(title).setSingleChoiceItems(labels.toTypedArray(),selected) {dialog,index->
                    rememberEdit();onSelect(index);dialog.dismiss();showTab(1);scheduleRender()
                }.setNegativeButton("取消",null).create()
                dialog.show();styleDialog(dialog)
            })
            controls.addView(row,LinearLayout.LayoutParams(-1,-2).apply {bottomMargin=d(8)})
        }
        val meterNames=listOf("balanced","center","protect_highlights","protect_shadows")
        choice("测光方式",listOf("平衡","中央","保护高光","保护阴影"),meterNames.indexOf(values.meterMethod).coerceAtLeast(0)){values=values.copy(meterMethod=meterNames[it])}
        val analysisActions=LinearLayout(this)
        analysisActions.addView(button("自动配光",{analyzeDarkroom(if(stock.categoryLabel=="黑白胶片")"exposure" else "both")}),LinearLayout.LayoutParams(0,-2,1f))
        analysisActions.addView(button("宽容度",{analyzeDarkroom("scene_latitude")}),LinearLayout.LayoutParams(0,-2,1f));controls.addView(analysisActions)
        if(values.sceneLatitudeParams.isNotBlank())controls.addView(button("关闭宽容度映射",{rememberEdit();values=values.copy(sceneLatitudeParams="");showTab(1);scheduleRender()}),LinearLayout.LayoutParams(-1,-2))
        if(stock.categoryLabel=="反转片")return
        val papers=engine!!.materialsFor(stock)
        choice("印相材料",listOf("随胶片")+papers.map {it.name},(papers.indexOfFirst {it.id==values.paper}+1).coerceAtLeast(0)) {index->values=values.copy(paper=if(index==0)"auto" else papers[index-1].id,neutralC=null,neutralM=null,neutralY=null)}
        addSlider(controls,"印相曝光","PRINT",values.printExposure,-3f,3f,{values=values.copy(printExposure=it)},true,
            {String.format(java.util.Locale.US,"%+.3f EV",it)},0f)
        if(stock.categoryLabel!="黑白胶片") {
            addSlider(controls,"黄色滤镜","Y",values.printY,-100f,100f,{values=values.copy(printY=it)},false,
                {String.format(java.util.Locale.US,"%+.2f",it)},0f)
            addSlider(controls,"品红滤镜","M",values.printM,-100f,100f,{values=values.copy(printM=it)},false,
                {String.format(java.util.Locale.US,"%+.2f",it)},0f)
        }
        addSlider(controls,"眩光","GLARE",values.glare,0f,30f,{values=values.copy(glare=it)},false,
            {String.format(java.util.Locale.US,"%.2f%%",it)},0f)
    }
    private fun analyzeDarkroom(target:String) {
        if(analysisRunning || importing || exporting || !values.filmEnabled)return
        val e=engine ?: return;val stock=e.stocks.getOrNull(stockIndex) ?: return
        val input=(interactionSource ?: source)?.copy(Bitmap.Config.ARGB_8888,false) ?: return
        val uri=sourceUri;val request=generation;val settings=values.filmOnly()
        analysisRunning=true;status.text=if(target=="scene_latitude")"正在分析宽容度…" else "正在配光…"
        fullWorker.execute {
            val result=runCatching {e.analyze(input,stock,settings,target)};input.recycle()
            main.post {
                analysisRunning=false
                if(activityDisposed || uri!=sourceUri || request!=generation || exporting || importing)return@post
                status.text=""
                result.onFailure {showError(it.message ?: "分析未完成")}.onSuccess {reply ->
                    val panel=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(20),d(4),d(20),d(12))}
                    var valid=true
                    val title=if(target=="scene_latitude")"场景宽容度" else "自动配光"
                    if(target=="scene_latitude") {
                        val scene=reply.getJSONObject("scene");val medium=reply.getJSONObject("medium");val fit=reply.getJSONObject("fit")
                        valid=fit.optBoolean("valid",false)
                        panel.addView(text(String.format(java.util.Locale.US,"胶片范围 %+.1f 至 %+.1f EV",medium.optDouble("shadow_ev"),medium.optDouble("highlight_ev")),14f),LinearLayout.LayoutParams(-1,-2))
                        panel.addView(LatitudeHistogramView(this,scene.getJSONObject("histogram"),medium.optDouble("shadow_ev"),medium.optDouble("highlight_ev")),LinearLayout.LayoutParams(-1,d(144)).apply {topMargin=d(12)})
                        panel.addView(text(if(valid)"可将场景高光与阴影映射到胶片范围" else "当前场景无法得到有效映射，参数保持不变",12f,muted).apply {setPadding(0,d(8),0,d(8))},LinearLayout.LayoutParams(-1,-2))
                    } else {
                        val solved=reply.getJSONObject("solved_params")
                        panel.addView(text(String.format(java.util.Locale.US,"曝光 %+.3f EV",solved.optDouble("exposure_compensation_ev",settings.exposure.toDouble()).coerceIn(-5.0,5.0)),15f),LinearLayout.LayoutParams(-1,-2))
                        if(solved.has("m_filter_neutral"))panel.addView(text(String.format(java.util.Locale.US,"印相滤色  C %.1f · M %.1f · Y %.1f",solved.optDouble("c_filter_neutral"),solved.optDouble("m_filter_neutral"),solved.optDouble("y_filter_neutral")),12f,muted),LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(8)})
                    }
                    val dialog=AlertDialog.Builder(this).setTitle(title).setView(panel).setNegativeButton("取消",null).setPositiveButton("应用"){_,_ ->
                        if(uri==sourceUri && generation==request && !exporting && !importing) {
                            rememberEdit()
                            values=if(target=="scene_latitude")values.copy(sceneLatitudeParams=SceneLatitudeEdit.canonical(reply.getJSONObject("fit").getJSONObject("params_delta").toString()))
                            else reply.getJSONObject("solved_params").let {solved ->values.copy(exposure=solved.optDouble("exposure_compensation_ev",values.exposure.toDouble()).toFloat().coerceIn(-5f,5f),
                                neutralC=if(solved.has("c_filter_neutral"))solved.getDouble("c_filter_neutral").toFloat() else values.neutralC,
                                neutralM=if(solved.has("m_filter_neutral"))solved.getDouble("m_filter_neutral").toFloat() else values.neutralM,
                                neutralY=if(solved.has("y_filter_neutral"))solved.getDouble("y_filter_neutral").toFloat() else values.neutralY)}
                            showTab(currentTab);scheduleRender()
                        }
                    }.create()
                    dialog.show();styleDialog(dialog);dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled=valid
                }
            }
        }
    }
    private fun addGrainTypeSelector() {
        val kinds=listOf("fine" to "细腻","classic" to "经典","coarse" to "粗粝","clustered" to "团簇")
        fun currentLabel()=kinds.firstOrNull {it.first==values.grainType}?.second ?: "经典"
        val row=LinearLayout(this).apply {
            gravity=Gravity.CENTER_VERTICAL;setPadding(d(12),0,d(12),0)
            minimumHeight=d(48);isClickable=true;isFocusable=true;isEnabled=!importing && !exporting
            background=UiTheme.controlBackground(this@MainActivity)
            contentDescription="颗粒类型，当前${currentLabel()}，打开选项"
        }
        row.addView(text("颗粒类型",13f,ink,true).apply {setPadding(0,d(12),0,d(12));importantForAccessibility=View.IMPORTANT_FOR_ACCESSIBILITY_NO},LinearLayout.LayoutParams(0,-2,1f))
        val value=text(currentLabel(),13f,UiTheme.accentText,true).apply {
            gravity=Gravity.END or Gravity.CENTER_VERTICAL;isSingleLine=true;importantForAccessibility=View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        row.addView(value,LinearLayout.LayoutParams(-2,-2))
        row.addView(DropdownMark(this),LinearLayout.LayoutParams(d(24),d(48)).apply {leftMargin=d(6)})
        row.setOnClickListener {
            if(!importing && !exporting) {
                haptic()
                val selected=kinds.indexOfFirst {it.first==values.grainType}.coerceAtLeast(0)
                val dialog=AlertDialog.Builder(this).setTitle("颗粒类型")
                    .setSingleChoiceItems(kinds.map {it.second}.toTypedArray(),selected) {choice,index ->
                        if(!importing && !exporting) {
                            rememberEdit();values=values.copy(grainType=kinds[index].first)
                            value.text=kinds[index].second
                            row.contentDescription="颗粒类型，当前${kinds[index].second}，打开选项"
                            scheduleRender()
                        }
                        choice.dismiss()
                    }.setNegativeButton("取消",null).create()
                dialog.show();styleDialog(dialog)
            }
        }
        for(index in 0 until row.childCount)row.getChildAt(index).isEnabled=row.isEnabled
        grainTypeSelector=row
        controls.addView(row,LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(4);bottomMargin=d(8)})
    }
    private fun addSlider(parent:LinearLayout,title:String,english:String,initial:Float,min:Float,max:Float,onChange:(Float)->Unit,ev:Boolean,formatter:((Float)->String)?=null,defaultValue:Float=initial,colors:IntArray?=null) {
        // One progress unit equals one displayed unit. This keeps touch,
        // keyboard, precise entry and accessibility on the same value grid.
        val percentage=!ev && max<=1f
        val unitScale=when {percentage -> 10000f;ev || (min>=.25f && max<=2.5f) -> 1000f;else -> 100f}
        val steps=((max-min)*unitScale).roundToInt().coerceAtLeast(1)
        fun position(v:Float)=((v-min)*unitScale).roundToInt().coerceIn(0,steps)
        fun amount(p:Int)=((min*unitScale).roundToInt()+p)/unitScale
        fun precise(v:Float)=(v*unitScale).roundToInt()/unitScale
        val block=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(0,d(8),0,d(4))}
        val label=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL;minimumHeight=d(28)}
        label.addView(text(title,14f,ink),LinearLayout.LayoutParams(0,-2,1f))
        fun formatted(v:Float)=formatter?.invoke(v) ?: if(ev)String.format(java.util.Locale.US,"%+.3f EV",v) else String.format(java.util.Locale.US,"%.2f%%",v*100)
        val value=text(formatted(initial),13f,ink,true).apply {
            gravity=Gravity.END or Gravity.CENTER_VERTICAL;fontFeatureSettings="tnum";minWidth=d(88);setPadding(d(8),0,0,0)
            contentDescription="$title，${formatted(initial)}";importantForAccessibility=View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        label.addView(value,LinearLayout.LayoutParams(-2,-2));block.addView(label)
        var currentValue=initial
        val slider=PrecisionSeekBar(this).apply {
            this.max=steps;progress=position(initial)
            if(min<0f && max>0f)referenceFraction=-min/(max-min)
            progressTintList=UiTheme.accentColors();progressBackgroundTintList=android.content.res.ColorStateList.valueOf(line)
            thumbTintList=UiTheme.textColors(UiTheme.accentText);splitTrack=false;minimumHeight=d(48);keyProgressIncrement=1
            // Thumb bounds remain fully inside the view at both endpoints.
            val edge=max(d(16),(thumb?.intrinsicWidth ?: d(20))/2+d(3))
            setPadding(edge,0,edge,0);colorStops=colors;contentDescription="$title，长按圆点以十分之一灵敏度微调，双击恢复默认值"
            if(Build.VERSION.SDK_INT>=30)stateDescription=formatted(initial)
            setOnSeekBarChangeListener(object:SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(s:SeekBar,p:Int,fromUser:Boolean) {
                    if(fromUser && s.isEnabled && !exporting && !importing) {
                        if(gestureSnapshot==null)rememberEdit()
                        val v=amount(p);currentValue=v;onChange(v);value.text=formatted(v)
                        value.contentDescription="$title，${formatted(v)}，点击精确输入"
                        if(Build.VERSION.SDK_INT>=30) {s.stateDescription=formatted(v)}
                        scheduleRender()
                    }
                }
                override fun onStartTrackingTouch(s:SeekBar) {
                    beginEditGesture()
                    dragging=true
                    dragStartGeneration=generation
                    main.removeCallbacks(refineRender)
                    s.parent?.requestDisallowInterceptTouchEvent(true)
                }
                override fun onStopTrackingTouch(s:SeekBar) {
                    endEditGesture()
                    dragging=false
                    s.parent?.requestDisallowInterceptTouchEvent(false)
                    haptic()
                    main.removeCallbacks(refineRender);main.postDelayed(refineRender,140)
                }
            })
            resetCurrent={
                if(isEnabled && !exporting && !importing) {
                    rememberEdit();currentValue=defaultValue;onChange(defaultValue)
                    progress=position(defaultValue)
                    value.text=formatted(defaultValue)
                    value.contentDescription="$title，${formatted(defaultValue)}，点击精确输入"
                    if(Build.VERSION.SDK_INT>=30)stateDescription=formatted(defaultValue)
                    scheduleRender();haptic()
                }
            }
        }
        value.apply {
            minimumHeight=d(48);isClickable=true;isFocusable=true
            importantForAccessibility=View.IMPORTANT_FOR_ACCESSIBILITY_YES
            contentDescription="$title，${formatted(initial)}，点击精确输入；双击调节圆点恢复默认值"
            background=UiTheme.controlBackground(this@MainActivity,Color.TRANSPARENT,5f,Color.TRANSPARENT)
            setOnClickListener {
                if(!slider.isEnabled || exporting || importing)return@setOnClickListener
                val scale=if(percentage)100f else 1f
                val decimals=if(unitScale==1000f)3 else 2
                val editor=EditText(this@MainActivity).apply {
                    inputType=android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL or android.text.InputType.TYPE_NUMBER_FLAG_SIGNED
                    typeface=InterfaceTypography.forText(this@MainActivity,"",14f)
                    setText(String.format(java.util.Locale.US,"%.$decimals"+"f",currentValue*scale));selectAll()
                    setPadding(d(16),d(12),d(16),d(12));setSingleLine()
                }
                val dialog=AlertDialog.Builder(this@MainActivity).setTitle(title).setView(editor)
                    .setNegativeButton("取消",null).setNeutralButton("恢复默认",null).setPositiveButton("应用",null).create()
                fun commitPrecise(v:Float) {
                    val committed=precise(v).coerceIn(min,max)
                    rememberEdit();currentValue=committed;onChange(committed);slider.progress=position(committed)
                    value.text=formatted(committed);value.contentDescription="$title，${formatted(committed)}，点击精确输入"
                    if(Build.VERSION.SDK_INT>=30)slider.stateDescription=formatted(committed)
                    scheduleRender();dialog.dismiss()
                }
                dialog.show();styleDialog(dialog)
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val parsed=editor.text.toString().trim().toFloatOrNull()?.div(scale)
                    if(parsed==null || !parsed.isFinite() || parsed<min || parsed>max)editor.error="范围 ${formatted(min)} 至 ${formatted(max)}"
                    else commitPrecise(parsed)
                }
                dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {commitPrecise(defaultValue)}
            }
        }
        block.addView(slider,LinearLayout.LayoutParams(-1,d(48)));photoControls.add(block);parent.addView(block)
    }
    private fun buildFilmCards() {
        if(!::filmRow.isInitialized) return
        filmRow.removeAllViews()
        val stocks=engine?.stocks ?: return
        stocks.forEachIndexed { index,stock ->
            if(favoritesOnly && stock.id !in favorites) return@forEachIndexed
            val card=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;minimumHeight=d(84);setPadding(d(12),d(4),d(4),d(10));background=UiTheme.controlBackground(this@MainActivity,UiTheme.surface,8f,line,index==stockIndex);isSelected=index==stockIndex;isClickable=true;isFocusable=true}
            val top=LinearLayout(this).apply { gravity=Gravity.CENTER_VERTICAL }
            val brand=stock.makerLabel.uppercase(java.util.Locale.ROOT)
            top.addView(text(brand,12f,muted,false).apply {maxLines=2},LinearLayout.LayoutParams(0,-2,1f))
            val star=FavoriteMark(this,stock.id in favorites,accent,muted).apply { contentDescription="收藏 ${stock.name}";setOnClickListener {
                if(!favorites.add(stock.id)) favorites.remove(stock.id);prefs.edit().putStringSet("favorites",favorites.toSet()).apply();haptic();buildFilmCards()
            } };top.addView(star,LinearLayout.LayoutParams(d(48),d(48)));card.addView(top)
            card.addView(text(stock.shortName,18f,ink).apply {typeface=bookTypeface;maxLines=2;setPadding(0,0,d(8),0)},LinearLayout.LayoutParams(-1,-2).apply {topMargin=0;bottomMargin=d(4)})
            card.contentDescription="${stock.name}，${stock.makerLabel}，${stock.categoryLabel}"
            card.setOnClickListener { if(!exporting && !importing) {
                saveSession()
                val targets=if(selectedPhotos.isEmpty())listOf(currentPhoto) else selectedPhotos.toList()
                val saves=mutableListOf<Pair<Uri,Adjustments>>()
                for(i in targets.filter {it in photos.indices}) {
                    val entry=photos[i]
                    if(entry.stock!=index)histories.getOrPut(entry.uri.toString()){EditHistory()}.remember(EditorSnapshot(entry.stock,entry.adjustments))
                    entry.stock=index
                    saves.add(entry.uri to entry.adjustments)
                }
                if(saves.isNotEmpty())worker.execute {for((uri,a) in saves){if(activityDisposed)break;runCatching {editStore.save(uri,index,a)}}}
                if(selectedPhotos.isEmpty() || currentPhoto in selectedPhotos) { stockIndex=index;updateStockLabel();scheduleRender() }
                haptic();buildFilmCards();if(selectedPhotos.size>1)toast("已应用至 ${selectedPhotos.size} 张，各张参数保持独立")
            } }
            filmRow.addView(card,LinearLayout.LayoutParams(dp(160f*resources.configuration.fontScale.coerceAtMost(1.5f)),-2).apply {rightMargin=d(8)})
        }
        if(filmRow.childCount==0) filmRow.addView(text("暂无收藏",12f,muted),LinearLayout.LayoutParams(-1,d(64)))
    }
    private fun updateStockLabel() {
        val stock=engine?.stocks?.getOrNull(stockIndex)
        if(::filmTitle.isInitialized)filmTitle.text=stock?.name ?: "选择胶片"
        if(::subtitle.isInitialized) {
            subtitle.text=""
            subtitle.setTextColor(muted)
            subtitle.contentDescription=stock?.let {"完整光谱显影，${it.categoryLabel}"} ?: "完整光谱显影"
        }
    }
    private fun scheduleRender() {
        if(importing || exporting)return
        generation++;canvas.geometry=values.geometry;queuePersistEdits();updateActions()
        if(!previewPosted) { previewPosted=true;main.postDelayed(pendingRender,24) }
        main.removeCallbacks(refineRender)
        if(!dragging)main.postDelayed(refineRender,180)
    }
    private fun renderPreview(interactive:Boolean=false) {
        if(importing || exporting)return
        val quality=if(interactive)1 else 2
        if(!interactive && dragging)return
        val lane=if(interactive)0 else 1
        if(renderRunning[lane]) {queuedRender[lane]=true;return}
        val original=(if(interactive)interactionSource ?: source else spectralSource ?: source) ?: return
        val e=engine ?: return;val stock=e.stocks.getOrNull(stockIndex) ?: return
        val input=original.copy(Bitmap.Config.ARGB_8888,false)
        val a=values.filmOnly();val request=generation;val inputUri=sourceUri;val fullSize=sourceDimensions()
        renderRunning[lane]=true
        status.text="正在更新预览…"
        (if(interactive)fastWorker else fullWorker).execute {
            try {
                val cancelled={activityDisposed || isFinishing || isDestroyed || importing || exporting || sourceUri!=inputUri || (request!=generation && (!interactive || !dragging))}
                val result=if(request!=generation || cancelled())null else e.render(input,stock,a,previewMode=true,sourceWidth=fullSize.first,sourceHeight=fullSize.second,cancelled=cancelled,interactive=interactive)
                main.post {
                    if(result!=null) {
                        if(!activityDisposed && !isFinishing && !importing && !exporting && sourceUri==inputUri &&
                            (request==generation || (interactive && dragging && request>dragStartGeneration && request>publishedGeneration)) &&
                            request>=publishedGeneration && (publishedGeneration!=request || quality>=publishedQuality)) {
                            val old=rendered;rendered=result;canvas.original=source;canvas.processed=result;canvas.invalidate()
                            publishedGeneration=request;publishedQuality=quality
                            if(old!==source && old!==interactionSource && old!==spectralSource)old?.recycle()
                            status.text=""
                            updateActions()
                        } else result.recycle()
                    }
                }
            } catch(error:Exception) {main.post {if(!activityDisposed && request==generation) {status.text="显影失败";showError(error.message ?: "资源读取失败")}}}
            finally {input.recycle();main.post {renderRunning[lane]=false;val next=queuedRender[lane];queuedRender[lane]=false;if(next && !activityDisposed && !importing && !exporting && !isFinishing && !isDestroyed)renderPreview(interactive)}}
        }
    }
    private fun clearPreviewBase() {publishedGeneration=-1;publishedQuality=0}
    private fun importPhoto() { if(exporting || importing)return;if(cropEditor!=null)closeCrop(false);startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type="*/*";putExtra(Intent.EXTRA_MIME_TYPES,arrayOf("image/*","application/octet-stream"));putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);addCategory(Intent.CATEGORY_OPENABLE);addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION) },100) }
    @Deprecated("Framework callback") override fun onActivityResult(requestCode:Int,resultCode:Int,data:Intent?) {
        super.onActivityResult(requestCode,resultCode,data);if(resultCode!=RESULT_OK || data==null)return
        if(requestCode==100) {
            val uris=mutableListOf<Uri>();data.clipData?.let { clip->for(i in 0 until clip.itemCount)uris.add(clip.getItemAt(i).uri) };data.data?.let { uris.add(it) }
            importDocuments(uris.distinct())
        } else if(requestCode==201)data.data?.let {saveBatch(it)}
        else if(requestCode==102)data.data?.let {uri ->
            worker.execute {
                val result=runCatching {
                    val content=contentResolver.openInputStream(uri)?.bufferedReader()?.use {it.readText().also {text ->require(text.length<=2*1024*1024){"风格文件过大"}}} ?: error("无法读取风格")
                    val preset=StylePreset.fromJson(org.json.JSONObject(content))
                    require(preset.settings.lookLut.isBlank()) {"当前只支持参数风格，不包含外部 LUT"}
                    ImportedStyleStore(this).save(preset)
                }
                main.post {if(!activityDisposed){result.onFailure {showError(it.message ?: "风格导入失败")};if(result.isSuccess){toolGroup=7;showTab(1)}}}
            }
        }
    }
    private fun saveSession() {
        if(currentPhoto in photos.indices) {
            photos[currentPhoto].stock=stockIndex;photos[currentPhoto].adjustments=values.filmOnly()
            main.removeCallbacks(persistEdits);persistCurrentEdits()
        }
    }
    private fun queuePersistEdits() {
        if(currentPhoto !in photos.indices)return
        photos[currentPhoto].stock=stockIndex;photos[currentPhoto].adjustments=values.filmOnly()
        main.removeCallbacks(persistEdits);main.postDelayed(persistEdits,650)
    }
    private fun persistCurrentEdits() {
        if(currentPhoto !in photos.indices || worker.isShutdown)return
        val entry=photos[currentPhoto];val a=entry.adjustments.filmOnly();val stock=entry.stock
        worker.execute { runCatching { editStore.save(entry.uri,stock,a) } }
    }
    private fun importDocuments(uris:List<Uri>) {
        if(uris.isEmpty() || importing || exporting)return
        saveSession();importing=true;val request=++generation;main.removeCallbacks(pendingRender);previewPosted=false;main.removeCallbacks(refineRender);updateActions();status.text="正在读取 ${uris.size} 张照片…"
        for(uri in uris)try { contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch(_:Exception) {}
        worker.execute {
            val entries=mutableListOf<PhotoEdit>();val errors=mutableListOf<String>()
            for(uri in uris)try {
                if(activityDisposed || request!=generation)break
                var name=uri.lastPathSegment ?: "Untitled"
                contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME),null,null,null)?.use { if(it.moveToFirst())name=it.getString(0) }
                val saved=editStore.load(uri)
                entries.add(PhotoEdit(uri,name,saved?.stock?.coerceIn(0,(engine?.stocks?.lastIndex ?: 0).coerceAtLeast(0)) ?: stockIndex,(saved?.adjustments ?: Adjustments()).filmOnly()))
            } catch(error:Exception) { errors.add(error.message ?: "无法读取文件") }
            main.post {
                if(activityDisposed || request!=generation)return@post
                importing=false;selectedPhotos.clear()
                for(entry in entries) { val old=photos.indexOfFirst { it.uri==entry.uri };if(old>=0)selectedPhotos.add(old) else { photos.add(entry);selectedPhotos.add(photos.lastIndex) } }
                updateActions();if(selectedPhotos.isNotEmpty())openPhoto(selectedPhotos.minOrNull()!!) else status.text="照片导入失败"
                if(errors.isNotEmpty())toast("${errors.size} 个文件无法读取")
            }
        }
    }
    private fun photoPicker() {
        if(photos.isEmpty()) { importPhoto();return }
        saveSession()
        val snapshot=photos.toList()
        PhotoBrowserDialog(this,snapshot.map { it.name },currentPhoto,selectedPhotos.toSet(),
            loadThumbnail={ index -> val entry=snapshot[index];if(ExportPreset.rawExtension(entry.name)!=null)rawCache.cachedPreview(entry.uri,160) else decode(entry.uri,160) },
            onEdit={ index -> openPhoto(index) },
            onSelection={ selected ->
                selectedPhotos.clear();selectedPhotos.addAll(selected.filter { it in photos.indices })
                if(selectedPhotos.isEmpty() && currentPhoto in photos.indices)selectedPhotos.add(currentPhoto)
                updateActions()
            },
            onRemove={ selected -> removePhotos(selected) }
        ).show()
    }
    private fun removePhotos(indices:Set<Int>) {
        if(exporting || importing)return
        val removed=indices.filter { it in photos.indices }.toSet()
        if(removed.isEmpty())return
        saveSession()
        if(rawCacheDelegate.isInitialized())removed.forEach {rawCache.discard(photos[it].uri)}
        val oldCurrent=currentPhoto
        val survivors=photos.indices.filter { it !in removed }
        val newCurrent=survivors.indexOf(oldCurrent)
        val remaining=survivors.map { photos[it] }
        photos.clear();photos.addAll(remaining)
        selectedPhotos.clear()
        if(newCurrent>=0) {
            currentPhoto=newCurrent;selectedPhotos.add(newCurrent);updateActions()
        } else {
            generation++;main.removeCallbacks(pendingRender);previewPosted=false;main.removeCallbacks(refineRender)
            queuedRender.fill(false);currentPhoto=-1
            if(photos.isNotEmpty()) {
                val target=survivors.count { it<oldCurrent }.coerceAtMost(photos.lastIndex)
                selectedPhotos.add(target);openPhoto(target)
            } else {
                val oldSource=source;val oldRender=rendered;val oldSmall=interactionSource;val oldSpectral=spectralSource
                clearPreviewBase();source=null;rendered=null;interactionSource=null;spectralSource=null;sourceUri=null
                canvas.original=null;canvas.processed=null;canvas.originalOnly=false;canvas.comparing=false;compare=false;canvas.resetZoom()
                if(oldSmall!==oldSource && oldSmall!==oldRender)oldSmall?.recycle()
                if(oldSpectral!==oldSource && oldSpectral!==oldSmall && oldSpectral!==oldRender)oldSpectral?.recycle()
                oldRender?.recycle();if(oldSource!==oldRender)oldSource?.recycle()
                fileName="尚未导入照片";filename.text=fileName;fileDimensions.text="未导入照片";values=Adjustments();canvas.crop=CropBounds();updateCropUi();showTab(currentTab)
                status.text="照片已移除 · 原片保留";updateActions()
            }
        }
        toast("已从列表移除 "+removed.size+" 张，原片保留")
    }
    private fun openPhoto(index:Int) {
        if(exporting || importing || index !in photos.indices)return
        if(cropEditor!=null)closeCrop(false)
        saveSession();val entry=photos[index];val uri=entry.uri
            try { contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch(_:Exception) {}
            status.text="正在打开照片…";importing=true;main.removeCallbacks(pendingRender);previewPosted=false;main.removeCallbacks(refineRender);updateActions();val request=++generation
            worker.execute {
                try { var name=entry.name
                    contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME),null,null,null)?.use { if(it.moveToFirst()) name=it.getString(0) }
                    val raw=ExportPreset.rawExtension(name)!=null
                    val cancelled={activityDisposed || request!=generation}
                    var rawFailure:String?=null;var sourceWidth=0;var sourceHeight=0
                    val bitmap=if(raw)try {
                        var lastStage="";var lastPercent=-1
                        val preview=rawCache.preview(uri,edge={width,height -> previewTargetEdge(width,height,prefs.getInt("preview-edge",1920))},progress={stage,percent ->
                            if(stage!=lastStage || percent>=lastPercent+2) { lastStage=stage;lastPercent=percent;main.post {if(!activityDisposed && request==generation)status.text="$stage · $percent%"} }
                        },cancelled=cancelled)
                        sourceWidth=preview.sourceWidth;sourceHeight=preview.sourceHeight
                        preview.bitmap
                    } catch(error:java.util.concurrent.CancellationException) {throw error}
                    catch(error:OutOfMemoryError) {System.gc();rawFailure="当前设备内存不足，无法生成这张 RAW 的预览";null}
                    catch(error:Exception) {rawFailure=error.message ?: "本机 RAW 显影失败";null}
                    else {
                        FullResolutionPhoto(contentResolver,uri).use {sourceWidth=it.sourceWidth;sourceHeight=it.sourceHeight}
                        decode(uri,prefs.getInt("preview-edge",1920))
                    }
                    val small=bitmap?.let { scalePreview(it) }
                    val spectral=bitmap
                    main.post { if(!activityDisposed && request==generation) {
                        importing=false;clearPreviewBase();val oldSource=source;val oldRender=rendered;val oldSmall=interactionSource;val oldSpectral=spectralSource;interactionSource=small;spectralSource=spectral;sourceUri=uri;source=bitmap;canvas.original=bitmap;canvas.processed=null;canvas.originalOnly=bitmap==null && raw;rendered=null;canvas.resetZoom()
                        if(oldSmall!==oldSource && oldSmall!==oldRender)oldSmall?.recycle()
                        if(oldSpectral!==oldSource && oldSpectral!==oldSmall && oldSpectral!==oldRender)oldSpectral?.recycle()
                        oldRender?.recycle();if(oldSource!==oldRender)oldSource?.recycle();entry.sourceWidth=sourceWidth;entry.sourceHeight=sourceHeight;fileName=name;filename.text=name;fileDimensions.text=if(sourceWidth>0)"$sourceWidth × $sourceHeight · 原片尺寸" else "尺寸读取中";values=entry.adjustments.filmOnly();stockIndex=entry.stock;currentPhoto=index;canvas.crop=values.geometry.crop;updateCropUi();compare=false;canvas.comparing=false;showTab(currentTab)
                        if(bitmap!=null)scheduleRender() else { status.text="RAW 显影失败 · 可原片另存";updateActions();showError("${rawFailure ?: "RAW 无法显影"}。原片保留，可选择 RAW 原片逐字节另存；不会用内嵌缩略图导出。") }
                    } else { if(small!==bitmap)small?.recycle();if(spectral!==bitmap && spectral!==small)spectral?.recycle();bitmap?.recycle() } }
                } catch(error:OutOfMemoryError) { System.gc();main.post {if(!activityDisposed && request==generation) {importing=false;updateActions();status.text="完整显影内存不足 · 原片保留";showError("当前设备内存不足，无法完整显影这张照片；未使用内嵌缩略图，也未修改原片。")}} }
                catch(e:Exception) { main.post { if(!activityDisposed && request==generation) { importing=false;updateActions();showError("无法读取照片：${e.message}");status.text="打开失败，已保留当前照片" } } }
            }
    }
    private fun cancelPhotoImport() {
        if(!importing)return
        generation++;importing=false;if(rawCacheDelegate.isInitialized())rawCache.cancelActive()
        status.text="载入已取消 · 原片保留";updateActions()
    }
    private fun ratioLabel(value:Float):String = when {
        abs(value-65f/24f)<.025f -> "XPan"
        abs(value-24f/65f)<.01f -> "XPan 竖幅"
        abs(value-1f)<.02f -> "1:1"
        abs(value-1.5f)<.02f -> "3:2"
        abs(value-2f/3f)<.015f -> "2:3"
        abs(value-.75f)<.02f -> "3:4"
        abs(value-4f/3f)<.025f -> "4:3"
        abs(value-16f/9f)<.03f -> "16:9"
        abs(value-9f/16f)<.015f -> "9:16"
        else -> "自定义"
    }
    private fun showFileInfo() {
        if(sourceUri==null)return
        val message="${fileName}\n${fileDimensions.text}\n\n原片始终保留，预览使用有界缓存。"
        styleDialog(AlertDialog.Builder(this).setTitle("照片信息").setMessage(message).setPositiveButton("完成",null).show())
    }
    private fun sourceDimensions():Pair<Int,Int> =
        (photos.getOrNull(currentPhoto)?.sourceWidth?.takeIf {it>0} ?: source?.width ?: 1) to
        (photos.getOrNull(currentPhoto)?.sourceHeight?.takeIf {it>0} ?: source?.height ?: 1)
    private fun outputFrameDimensions():Pair<Int,Int> {val (w,h)=sourceDimensions();return PhotoGeometry.frameSize(w,h,values.geometry)}
    private fun rotatePhoto(turns:Int) {
        if(source==null || importing || exporting)return
        rememberEdit();var crop=values.geometry.crop
        repeat(turns.mod(4)){crop=CropBounds(1-crop.bottom,crop.left,1-crop.top,crop.right)}
        values=values.copy(geometry=values.geometry.copy(quarterTurns=(values.geometry.quarterTurns+turns).mod(4),crop=crop))
        canvas.geometry=values.geometry;canvas.resetZoom();updateCropUi();showTab(currentTab);scheduleRender()
    }
    private fun updateCropUi() {
        val aspect=currentCropAspect()
        val label=if(aspect<=0.001f)"原图" else ratioLabel(aspect)
        cropRatioButton.text="裁切";cropRatioButton.isSelected=!values.geometry.crop.isFull()
        cropRatioButton.contentDescription="裁切照片，当前$label，在照片预览中调整"
        if(::canvas.isInitialized)canvas.crop=values.geometry.crop
    }
    private fun currentCropAspect():Float {
        val crop=values.geometry.crop
        if(crop.isFull())return 0f
        val (width,height)=outputFrameDimensions()
        return width*(crop.right-crop.left)/(height*(crop.bottom-crop.top))
    }
    private fun openCropRatios() {
        if(source==null || importing || exporting || cropEditor!=null)return
        val original=source ?: return
        val ready=rendered?.takeUnless {it.isRecycled || publishedGeneration!=generation}
        val corrected=ready ?: PhotoGeometry.preview(original,values.geometry)
        val snapshot=corrected.copy(Bitmap.Config.ARGB_8888,false)
        if(ready==null && corrected!==original)corrected.recycle()
        val (w,h)=outputFrameDimensions();val originalAspect=w.toFloat()/h
        val editor=CropEditorView(this,snapshot,w,h).apply {setCrop(values.geometry.crop);setBackgroundColor(UiTheme.canvas)}
        cropEditor=editor;cropSnapshot=snapshot;panelBeforeCrop=panelVisible
        canvas.cancelStroke();canvas.visibility=View.INVISIBLE;compare=false;canvas.comparing=false
        previewStage.addView(editor,FrameLayout.LayoutParams(-1,-1))
        panelBeforeCrop=panelVisible;panelVisible=false;editorPanel.visibility=View.GONE;previewTools.visibility=View.GONE
        val toolbar=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(0,d(4),0,d(4))}
        cropToolbar=toolbar;previewPane.addView(toolbar,LinearLayout.LayoutParams(-1,-2))
        val ratios=listOf("原图" to originalAspect,"自由" to null,"1:1" to 1f,"3:2" to 1.5f,"4:3" to 4f/3f,"16:9" to 16f/9f,"XPan" to 65f/24f)
        var inverted=false
        val current=currentCropAspect()
        var selected=if(current<=.001f)0 else ratios.indices.firstOrNull {i ->ratios[i].second?.let {abs(current-it)<.018f}==true} ?: 1
        if(current>0f && selected==1)ratios.indices.firstOrNull {i ->i>=3 && ratios[i].second?.let {abs(current-1f/it)<.018f}==true}?.let {selected=it;inverted=true}
        val strip=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL}
        val choices=mutableListOf<TextView>()
        val pixels=text("",12f,muted).apply {gravity=Gravity.CENTER;accessibilityLiveRegion=View.ACCESSIBILITY_LIVE_REGION_POLITE}
        var swap:TextView?=null
        fun ratio():Float?=ratios[selected].second?.let {if(inverted)1f/it else it}
        fun refresh() {
            choices.forEachIndexed {i,v ->
                val active=i==selected;v.isSelected=active
                v.text=if(inverted && i>=3 && i<6)ratios[i].first.split(":").reversed().joinToString(":") else ratios[i].first
                v.background=UiTheme.controlBackground(this,if(active)UiTheme.selection else Color.TRANSPARENT,7f,if(active)accent else Color.TRANSPARENT)
                v.setTextColor(UiTheme.textColors(if(active)UiTheme.accentText else ink))
                if(Build.VERSION.SDK_INT>=30)v.stateDescription=if(active)"已选中" else "未选中"
            }
            swap?.isEnabled=selected>=3
            swap?.contentDescription=if(inverted)"将裁切框切换为宽幅" else "将裁切框切换为竖幅"
        }
        ratios.forEachIndexed {i,item ->
            val v=button(item.first,{selected=i;if(i==0 || i==6)inverted=false;editor.setAspect(ratio());refresh()}).apply {setPadding(d(10),d(6),d(10),d(6));contentDescription="裁切比例 ${item.first}"}
            choices.add(v);strip.addView(v,LinearLayout.LayoutParams(-2,-2).apply {rightMargin=d(2)})
        }
        toolbar.addView(HorizontalScrollView(this).apply {isHorizontalScrollBarEnabled=false;addView(strip)},LinearLayout.LayoutParams(-1,-2))
        val actions=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL}
        actions.addView(button("取消",{closeCrop(false)}),LinearLayout.LayoutParams(-2,-2))
        actions.addView(button("恢复",{selected=0;inverted=false;editor.setCrop(CropBounds());editor.setAspect(originalAspect);refresh()}),LinearLayout.LayoutParams(-2,-2))
        swap=button("",{if(selected>=3){inverted=!inverted;editor.setAspect(ratio());refresh()}}).apply {contentDescription="交换裁切比例方向";tooltipText="交换裁切比例方向"}
        actions.addView(FrameLayout(this).apply {addView(CropOrientationMark(this@MainActivity),FrameLayout.LayoutParams(d(22),d(22),Gravity.CENTER));addView(swap,FrameLayout.LayoutParams(-1,-1))},LinearLayout.LayoutParams(d(48),d(48)))
        actions.addView(pixels,LinearLayout.LayoutParams(0,-2,1f))
        actions.addView(button("应用",{closeCrop(true)}).apply {setTextColor(UiTheme.accentText)},LinearLayout.LayoutParams(-2,-2))
        toolbar.addView(actions,LinearLayout.LayoutParams(-1,-2))
        editor.onCropChange={draft ->val r=spectralCropRect(draft,w,h);pixels.text="${r.width()} × ${r.height()}"}
        editor.setAspect(ratio());editor.setCrop(values.geometry.crop);refresh();updateActions()
    }
    private fun closeCrop(apply:Boolean) {
        val editor=cropEditor ?: return
        if(apply && editor.crop!=values.geometry.crop) {rememberEdit();values=values.copy(geometry=values.geometry.copy(crop=editor.crop));queuePersistEdits()}
        previewStage.removeView(editor);cropEditor=null
        cropSnapshot?.let {if(!it.isRecycled)it.recycle()};cropSnapshot=null
        cropToolbar?.let {previewPane.removeView(it)};cropToolbar=null
        canvas.visibility=View.VISIBLE;previewTools.visibility=View.VISIBLE
        setEditorVisible(panelBeforeCrop);updateCropUi();updateActions()
    }
    @Deprecated("Framework callback") override fun onBackPressed() {
        if(cropEditor!=null){closeCrop(false);return}
        if(panelVisible && source!=null){setEditorVisible(false,true);return}
        super.onBackPressed()
    }
    private fun previewTargetEdge(width:Int,height:Int,maxEdge:Int):Int {
        val budgetPixels=(Runtime.getRuntime().maxMemory()*.42/256).toLong().coerceIn(220_000L,1_200_000L)
        val aspect=max(width,height).toDouble()/min(width,height)
        return min(maxEdge.toDouble(),sqrt(budgetPixels*aspect)).toInt().coerceAtLeast(1)
    }
    private fun decode(uri:Uri,maxEdge:Int):Bitmap {
        val options=BitmapFactory.Options().apply { inJustDecodeBounds=true };contentResolver.openInputStream(uri).use { BitmapFactory.decodeStream(it,null,options) }
        require(options.outWidth>0 && options.outHeight>0) { "不支持的图片格式；请使用 JPEG、PNG 或 WebP" }
        // Bound concurrent Android/NumPy buffers while using more source detail than a thumbnail.
        val targetEdge=previewTargetEdge(options.outWidth,options.outHeight,maxEdge)
        var sample=1;while(max(options.outWidth,options.outHeight)/sample>targetEdge)sample*=2
        val bitmap=contentResolver.openInputStream(uri).use { BitmapFactory.decodeStream(it,null,BitmapFactory.Options().apply { inSampleSize=sample;inPreferredConfig=Bitmap.Config.ARGB_8888 }) } ?: error("图片解码失败")
        val rotated=orient(uri,bitmap);if(rotated!==bitmap)bitmap.recycle()
        if(max(rotated.width,rotated.height)<=targetEdge)return rotated
        val scale=targetEdge.toFloat()/max(rotated.width,rotated.height);val result=Bitmap.createScaledBitmap(rotated,max(1,(rotated.width*scale).roundToInt()),max(1,(rotated.height*scale).roundToInt()),true);if(result!==rotated)rotated.recycle();return result
    }
    private fun orient(uri:Uri,bitmap:Bitmap):Bitmap {
        return try {
            val exif=contentResolver.openInputStream(uri).use { android.media.ExifInterface(it!!) };val orientation=exif.getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,1)
            val matrix=Matrix();when(orientation) { 2->matrix.setScale(-1f,1f);3->matrix.setRotate(180f);4->matrix.setScale(1f,-1f);5->{matrix.setRotate(90f);matrix.postScale(-1f,1f)};6->matrix.setRotate(90f);7->{matrix.setRotate(270f);matrix.postScale(-1f,1f)};8->matrix.setRotate(270f) }
            if(matrix.isIdentity)bitmap else Bitmap.createBitmap(bitmap,0,0,bitmap.width,bitmap.height,matrix,true)
        }catch(_:Exception){bitmap}
    }
    private fun scalePreview(bitmap:Bitmap):Bitmap { val ratio=min(1f,640f/max(bitmap.width,bitmap.height));return if(ratio==1f)bitmap else Bitmap.createScaledBitmap(bitmap,max(1,(bitmap.width*ratio).roundToInt()),max(1,(bitmap.height*ratio).roundToInt()),true) }
    private var exportRecipe=OutputRecipe.DEFAULTS.first()
    private fun outputChoices()=OutputRecipe.DEFAULTS.map {default->
        runCatching {prefs.getString("output-recipe-${default.id}",null)?.let {OutputRecipe.fromJson(org.json.JSONObject(it))}}.getOrNull() ?: default
    }
    private fun exportIndices():List<Int> {
        val selected=selectedPhotos.filter { it in photos.indices }.sorted()
        return when {
            selected.isNotEmpty() -> selected
            currentPhoto in photos.indices -> listOf(currentPhoto)
            else -> emptyList()
        }
    }
    private fun exportOptions() {
        if(exporting || importing || sourceUri==null)return
        if(cropEditor!=null){closeCrop(true)}
        saveSession();val indices=exportIndices();if(indices.isEmpty())return
        val rawAvailable=indices.all {ExportPreset.rawExtension(photos[it].name)!=null}
        if(exportRecipe.raw && !rawAvailable)exportRecipe=outputChoices().first()
        val panel=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(22),d(6),d(22),d(10))}
        var dialog:AlertDialog?=null
        val choices=mutableListOf<Triple<View,TextView,OutputRecipe>>()
        val note=text("",12f,muted).apply {setPadding(d(12),d(10),d(12),d(10));setLineSpacing(d(3).toFloat(),1f)}
        fun refreshChoices() {
            choices.forEach { (row,mark,preset) ->
                val selected=exportRecipe.id==preset.id;mark.text=if(selected)"●" else "○";mark.setTextColor(if(selected)UiTheme.accentText else muted)
                mark.contentDescription=if(selected)"已选择" else "未选择";row.isSelected=selected
                row.background=UiTheme.controlBackground(this,UiTheme.surface,8f,line,selected)
            }
            note.text=(if(exportRecipe.raw)"RAW 原片另存，不应用调整。" else if(exportRecipe.longEdge==0)"保留原片像素，裁切除外。" else "按所选长边缩小，不放大原片。")+
                "保存到「${exportRecipe.subfolder}」文件夹。"+(if(exportRecipe.conflict=="skip")"同名文件跳过。" else "同名文件自动编号。")
        }
        for(preset in outputChoices()) {
            val available=if(preset.raw)rawAvailable else source!=null && engine!=null
            val row=LinearLayout(this).apply {gravity=Gravity.CENTER_VERTICAL;setPadding(d(13),d(12),d(13),d(12));isEnabled=available;isClickable=available;isFocusable=available}
            val mark=text("○",16f,muted,true).apply {gravity=Gravity.CENTER};row.addView(mark,LinearLayout.LayoutParams(d(25),-1).apply {rightMargin=d(9)})
            val copy=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL}
            copy.addView(text(preset.name,15f,if(available)ink else muted,true))
            copy.addView(text(if(preset.raw && !rawAvailable)"所选照片需全部为相机 RAW" else if(!available)"显影资源尚未就绪" else preset.detail,12f,muted).apply {setPadding(0,d(5),0,0);maxLines=2})
            row.addView(copy,LinearLayout.LayoutParams(0,-2,1f));row.contentDescription=preset.name+"，"+preset.detail
            if(available)row.setOnClickListener {exportRecipe=preset;refreshChoices()}
            panel.addView(row,LinearLayout.LayoutParams(-1,-2));choices.add(Triple(row,mark,preset))
        }
        panel.addView(note)
        panel.addView(button("输出设置…",{dialog?.dismiss();editOutputRecipe()}),LinearLayout.LayoutParams(-1,-2))
        if(indices.size>1)panel.addView(text("${indices.size} 张照片 · 每张保留各自胶片参数",12f,muted))
        panel.addView(button("选择位置并导出",{dialog?.dismiss();chooseExport(exportRecipe)},true),LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(12)})
        dialog=AlertDialog.Builder(this).setTitle(if(indices.size>1)"批量导出 ${indices.size} 张" else "导出作品").setView(ScrollView(this).apply {addView(panel)}).setNegativeButton("取消",null).create()
        dialog.show();styleDialog(dialog);refreshChoices()
    }
    private fun editOutputRecipe() {
        val recipe=exportRecipe
        val panel=LinearLayout(this).apply {orientation=LinearLayout.VERTICAL;setPadding(d(22),d(6),d(22),d(12))}
        fun input(label:String,value:String,numeric:Boolean=false):EditText {
            panel.addView(text(label,12f,muted),LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(12)})
            return EditText(this).apply {
                setText(value);textSize=14f;typeface=InterfaceTypography.forText(this@MainActivity,value,14f)
                setTextColor(ink);setSingleLine();minHeight=d(48);setPadding(d(12),d(8),d(12),d(8))
                background=UiTheme.controlBackground(this@MainActivity,UiTheme.surface,8f,line)
                contentDescription=label;inputType=if(numeric)android.text.InputType.TYPE_CLASS_NUMBER else android.text.InputType.TYPE_CLASS_TEXT
                panel.addView(this,LinearLayout.LayoutParams(-1,-2))
            }
        }
        fun select(label:String,options:List<String>,current:Int):Spinner {
            panel.addView(text(label,12f,muted),LinearLayout.LayoutParams(-1,-2).apply {topMargin=d(12)})
            return Spinner(this).apply {
                adapter=object:ArrayAdapter<String>(this@MainActivity,android.R.layout.simple_spinner_item,options) {
                    override fun getView(position:Int,convertView:View?,parent:ViewGroup):View=super.getView(position,convertView,parent).apply {
                        if(this is TextView){textSize=14f;setTextColor(ink);typeface=InterfaceTypography.forText(this@MainActivity,options[position],14f)}
                    }
                    override fun getDropDownView(position:Int,convertView:View?,parent:ViewGroup):View=super.getDropDownView(position,convertView,parent).apply {
                        setBackgroundColor(UiTheme.surface);if(this is TextView){textSize=14f;setTextColor(ink);minHeight=d(48);typeface=InterfaceTypography.forText(this@MainActivity,options[position],14f)}
                    }
                }.apply {setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)}
                setSelection(current.coerceAtLeast(0));contentDescription=label;minimumHeight=d(48)
                background=UiTheme.controlBackground(this@MainActivity,UiTheme.surface,8f,line)
                panel.addView(this,LinearLayout.LayoutParams(-1,-2))
            }
        }
        val depth=if(recipe.format in listOf("png","tiff"))select("位深",listOf("8 bit","16 bit"),if(recipe.bitDepth==16)1 else 0) else null
        val space=if(!recipe.raw && recipe.format!="dng")select("输出色彩空间",OutputRecipe.COLOR_SPACES,OutputRecipe.COLOR_SPACES.indexOf(recipe.colorSpace)) else null
        val quality=if(recipe.format=="jpeg")input("JPG 质量 · 1–100",recipe.quality.toString(),true) else null
        val edge=if(!recipe.raw)input("长边像素 · 0 保留原尺寸",recipe.longEdge.toString(),true) else null
        val naming=input("文件命名",recipe.naming)
        val folder=input("子文件夹",recipe.subfolder)
        val skip=CheckBox(this).apply {text="跳过同名文件";isChecked=recipe.conflict=="skip";setTextColor(ink);minHeight=d(48);typeface=bookTypeface}
        val open=CheckBox(this).apply {text="完成后打开文件夹";isChecked=recipe.openAfter;setTextColor(ink);minHeight=d(48);typeface=bookTypeface}
        panel.addView(skip);panel.addView(open)
        val dialog=AlertDialog.Builder(this).setTitle(recipe.name).setView(ScrollView(this).apply {addView(panel)})
            .setPositiveButton("保存",null).setNegativeButton("取消"){_,_->exportOptions()}.create()
        dialog.show();styleDialog(dialog)
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            try {
                val next=recipe.copy(bitDepth=depth?.let {if(it.selectedItemPosition==1)16 else 8} ?: recipe.bitDepth,
                    colorSpace=space?.selectedItem?.toString() ?: recipe.colorSpace,
                    quality=quality?.text?.toString()?.toIntOrNull() ?: if(quality==null)recipe.quality else error("请输入 JPG 质量"),
                    longEdge=edge?.text?.toString()?.toIntOrNull() ?: if(edge==null)0 else error("请输入长边像素"),
                    naming=naming.text.toString().trim(),subfolder=folder.text.toString().trim(),conflict=if(skip.isChecked)"skip" else "rename",openAfter=open.isChecked).validated()
                exportRecipe=next;prefs.edit().putString("output-recipe-${next.id}",next.toJson().toString()).apply()
                dialog.dismiss();exportOptions()
            } catch(error:Exception){toast(error.message ?: "导出参数无效")}
        }
    }
    private fun chooseExport(preset:OutputRecipe) {
        if(exporting)return
        val indices=exportIndices()
        if(indices.isEmpty())return
        exportRecipe=preset
        if(preset.raw && indices.any { ExportPreset.rawExtension(photos[it].name)==null }) { showError("RAW 原片要求所选照片全部为相机 RAW；普通图片无法转换为 RAW。");return }
        val intent=Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            val sourceFolder=sourceUri?.let {uri->runCatching {
                if(!DocumentsContract.isDocumentUri(this@MainActivity,uri))null else {
                    val id=DocumentsContract.getDocumentId(uri);val parent=id.substringBeforeLast('/',"")
                    if(parent.isBlank())null else DocumentsContract.buildDocumentUri(requireNotNull(uri.authority),parent)
                }
            }.getOrNull()}
            val initial=sourceFolder ?: prefs.getString("last_export_tree",null)?.let(Uri::parse)
            initial?.let {putExtra(DocumentsContract.EXTRA_INITIAL_URI,it)}
        }
        startActivityForResult(intent,201)
    }
    private fun showExportProgress(total:Int,preset:OutputRecipe,developSummary:String):Long {
        val run=++exportProgressRun
        lastProgressPosition=-1;lastPhotoProgress=0;lastOverallProgress=0
        exportStartedAt=SystemClock.elapsedRealtime()
        val panel=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(d(24),d(8),d(24),d(14)) }
        val modeLine=if(preset.raw)"RAW 原片 · 不应用调整" else developSummary
        exportProgressText=text("$modeLine\n"+(if(total>1)"准备导出 $total 张照片" else "准备原尺寸显影"),13f,muted).apply { setPadding(0,0,0,d(15));setLineSpacing(d(3).toFloat(),1f) }
        panel.addView(exportProgressText)
        exportProgressBar=ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal).apply {
            max=100;progress=0;progressTintList=UiTheme.accentColors()
            progressBackgroundTintList=android.content.res.ColorStateList.valueOf(line)
        }
        panel.addView(exportProgressBar,LinearLayout.LayoutParams(-1,d(5)))
        exportCancelButton=text("取消导出",13f,ink,true).apply {
            gravity=Gravity.CENTER;minHeight=d(44);background=UiTheme.controlBackground(this@MainActivity,UiTheme.surface,8f,line);isClickable=true;isFocusable=true
            setOnClickListener { requestExportCancel() }
        }
        panel.addView(exportCancelButton,LinearLayout.LayoutParams(-1,d(44)).apply { topMargin=d(18) })
        exportProgressDialog=AlertDialog.Builder(this).setTitle(if(total>1)"正在批量导出 · ${preset.name}" else "正在导出 · ${preset.name}").setView(panel).create().apply {
            setCancelable(false);setCanceledOnTouchOutside(false);show();styleDialog(this)
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        return run
    }
    private fun requestExportCancel() {
        if(!exporting || cancelBatch)return
        cancelBatch=true
        if(rawCacheDelegate.isInitialized())rawCache.cancelActive()
        exportCancelButton?.text="正在停止…"
        exportCancelButton?.isEnabled=false
        val activeModeLabel=if(activeExportRaw)"RAW 原片" else "完整光谱"
        exportProgressText?.text="正在停止$activeModeLabel；已完成的照片会保留。"
        status.text="正在停止导出…"
    }
    private fun postExportProgress(run:Long,position:Int,total:Int,name:String,percent:Int) {
        main.post {
            if(!exporting || cancelBatch || run!=exportProgressRun)return@post
            val currentPosition=position.coerceIn(0,total-1)
            if(currentPosition<lastProgressPosition)return@post
            val safe=if(currentPosition==lastProgressPosition)max(lastPhotoProgress,percent.coerceIn(0,100)) else percent.coerceIn(0,100)
            lastProgressPosition=currentPosition;lastPhotoProgress=safe
            val candidate=((currentPosition*100L+safe)/total).toInt().coerceIn(0,100)
            val overall=max(lastOverallProgress,candidate)
            lastOverallProgress=overall
            exportProgressBar?.progress=overall
            val elapsed=(SystemClock.elapsedRealtime()-exportStartedAt)/1000
            val eta=if(overall>=3) {
                val seconds=(elapsed.toLong()*(100-overall)/overall).coerceAtMost(99L*60*60)
                val minutes=seconds/60
                if(minutes>0)" · 约剩 $minutes 分钟" else " · 约剩 $seconds 秒"
            } else ""
            val modeLabel=if(activeExportRaw)"RAW 原片（不显影）" else "原尺寸照片"
            exportProgressText?.text=("$modeLabel\n")+(if(total>1)"照片 ${position+1}/$total · $name\n单张 $safe% · 总进度 $overall%$eta" else "$name\n原尺寸显影与编码 · $overall%$eta")
            status.text=if(total>1)"正在导出 ${position+1}/$total · $overall%" else "正在显影并导出 · $overall%"
        }
    }
    private fun closeExportProgress() {
        exportProgressRun++
        exportProgressDialog?.dismiss();exportProgressDialog=null
        exportProgressBar=null;exportProgressText=null;exportCancelButton=null
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
    private fun exportFolder(tree:Uri,preset:OutputRecipe):Pair<Uri,MutableSet<String>> {
        val rootId=DocumentsContract.getTreeDocumentId(tree)
        val rootUri=DocumentsContract.buildDocumentUriUsingTree(tree,rootId)
        val rootChildren=DocumentsContract.buildChildDocumentsUriUsingTree(tree,rootId)
        var folderId:String?=null
        var conflictingFile=false
        contentResolver.query(rootChildren,arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
        ),null,null,null)?.use { cursor ->
            while(cursor.moveToNext()) {
                val name=cursor.getString(1)
                if(!name.equals(preset.subfolder,ignoreCase=true))continue
                if(cursor.getString(2)==DocumentsContract.Document.MIME_TYPE_DIR)folderId=cursor.getString(0) else conflictingFile=true
            }
        }
        check(!conflictingFile || folderId!=null) { "目标位置已有同名文件「${preset.subfolder}」，请选择其他位置。" }
        val folderUri=folderId?.let { DocumentsContract.buildDocumentUriUsingTree(tree,it) }
            ?: DocumentsContract.createDocument(contentResolver,rootUri,DocumentsContract.Document.MIME_TYPE_DIR,preset.subfolder)
            ?: error("无法创建「${preset.subfolder}」文件夹；请改选可写入的位置。")
        val children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getDocumentId(folderUri))
        val occupied=mutableSetOf<String>()
        contentResolver.query(children,arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME),null,null,null)?.use { cursor ->
            while(cursor.moveToNext())occupied.add(cursor.getString(0).lowercase(java.util.Locale.ROOT))
        }
        return folderUri to occupied
    }
    private fun saveBatch(tree:Uri) {
        if(exporting || importing)return
        saveSession()
        val entries=exportIndices().map { photos[it].copy(adjustments=photos[it].adjustments.filmOnly()) }
        if(entries.isEmpty())return
        val preset=exportRecipe.validated();val e=engine
        if(!preset.raw && e==null) { showError("胶片引擎尚未就绪");return }
        if(preset.raw && entries.any { ExportPreset.rawExtension(it.name)==null }) { showError("RAW 原片要求所选照片全部为相机 RAW；普通图片无法转换为 RAW。");return }
        try { contentResolver.takePersistableUriPermission(tree,Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION) } catch(_:Exception) {}
        prefs.edit().putString("last_export_tree",tree.toString()).apply()
        val developSummary=if(preset.raw)"RAW 原片另存" else preset.detail
        cancelBatch=false;batchTotal=entries.size;exporting=true;activeExportRaw=preset.raw;generation++;main.removeCallbacks(pendingRender);previewPosted=false;main.removeCallbacks(refineRender);updateActions();status.text="准备导出…";val progressRun=showExportProgress(entries.size,preset,developSummary)
        worker.execute {
            var completed=0;var skipped=0;var exportedFolder:Uri?=null;val errors=mutableListOf<String>()
            try {
                e?.releasePreviewMemory()
                val (parent,occupied)=exportFolder(tree,preset)
                exportedFolder=parent
                for((position,entry) in entries.withIndex()) {
                    if(cancelBatch)break
                    var temporary:File?=null;var created:Uri?=null
                    try {
                        val filmName=(if(entry.adjustments.filmEnabled)e?.stocks?.getOrNull(entry.stock)?.name ?: "Film" else "调整").map {
                            if(it in "<>:\"/\\|?*" || it.code<32)'_' else it
                        }.joinToString("").trim(' ','.')
                        var name=preset.filename(entry.name,filmName,position+1,ExportPreset.rawExtension(entry.name))
                        val stem=name.substringBeforeLast('.');val suffix=name.substringAfterLast('.');var number=2
                        if(preset.conflict=="skip" && name.lowercase(java.util.Locale.ROOT) in occupied) {
                            skipped++;postExportProgress(progressRun,position,entries.size,entry.name,100);continue
                        }
                        while(name.lowercase(java.util.Locale.ROOT) in occupied) { name="${stem}_${number++}.$suffix" }
                        occupied.add(name.lowercase(java.util.Locale.ROOT))
                        val staged=File.createTempFile("spektrafilm-export-",".tmp",cacheDir);temporary=staged
                        postExportProgress(progressRun,position,entries.size,entry.name,0)
                        if(preset.raw) {
                            FileOutputStream(staged).use { stream -> contentResolver.openInputStream(entry.uri).use { input ->
                                requireNotNull(input);val buffer=ByteArray(1024*1024)
                                while(true) { check(!cancelBatch) { "导出已取消" };val count=input.read(buffer);if(count<0)break;stream.write(buffer,0,count) }
                            } }
                            postExportProgress(progressRun,position,entries.size,entry.name,95)
                        } else {
                            val stock=requireNotNull(e).stocks[entry.stock]
                            val cancelled={cancelBatch || activityDisposed || progressRun!=exportProgressRun}
                            FullResolutionPhoto.open(contentResolver,entry.uri,entry.name,rawCache,
                                progress={stage,percent ->
                                    main.post {if(!activityDisposed && progressRun==exportProgressRun)status.text="$stage · $percent%"}
                                    postExportProgress(progressRun,position,entries.size,entry.name,percent*30/100)
                                },cancelled=cancelled).use { photo ->
                                entry.sourceWidth=photo.sourceWidth;entry.sourceHeight=photo.sourceHeight
                                photo.writeRecipe(requireNotNull(e),stock,entry.adjustments,staged,preset,assets,progress={percent->
                                    postExportProgress(progressRun,position,entries.size,entry.name,30+percent*65/100)
                                },cancelled=cancelled)
                            }
                        }
                        check(!cancelBatch) { "导出已取消" }
                        FileOutputStream(staged,true).use { it.fd.sync() }
                        val target=DocumentsContract.createDocument(contentResolver,parent,preset.mime,name) ?: error("目标文件无法创建")
                        created=target;check(target!=entry.uri) { "不能覆盖原片" }
                        contentResolver.openOutputStream(target,"w").use { stream -> requireNotNull(stream);staged.inputStream().use { input ->
                            val buffer=ByteArray(1024*1024);while(true) {check(!cancelBatch && !activityDisposed) {"导出已取消"};val count=input.read(buffer);if(count<0)break;if(count>0)stream.write(buffer,0,count)}
                        };stream.flush() }
                        completed++
                        postExportProgress(progressRun,position,entries.size,entry.name,100)
                    } catch(error:OutOfMemoryError) {
                        created?.let { if(it!=entry.uri)try { DocumentsContract.deleteDocument(contentResolver,it) } catch(_:Exception) {} }
                        System.gc();cancelBatch=true
                        errors.add(entry.name+"：设备内存不足，已停止；原片未缩小、未修改")
                    } catch(error:Exception) {
                        created?.let { if(it!=entry.uri)try { DocumentsContract.deleteDocument(contentResolver,it) } catch(_:Exception) {} }
                        if(!cancelBatch)errors.add(entry.name+"："+(error.message ?: "保存失败"))
                    } finally { temporary?.delete() }
                }
            } catch(error:Exception) { if(!cancelBatch)errors.add(error.message ?: "输出文件夹无法访问") }
            finally {
                val count=completed;val skipCount=skipped;val folder=exportedFolder;val stopped=cancelBatch;val failures=errors.toList()
                main.post {
                    if(activityDisposed || progressRun!=exportProgressRun)return@post
                    closeExportProgress();exporting=false;batchTotal=0;updateActions()
                    status.text=(if(stopped)"导出已停止" else if(failures.isEmpty())"导出完成" else "导出未完成")+" · $count/${entries.size}"+(if(skipCount>0)" · 跳过 $skipCount 张" else "")+(if(failures.isNotEmpty())" · ${failures.size} 项失败" else "")
                    if(failures.isNotEmpty())showError(failures.take(5).joinToString("\n")) else toast(status.text.toString())
                    if(preset.openAfter && !stopped && failures.isEmpty() && folder!=null)runCatching {
                        startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(folder,DocumentsContract.Document.MIME_TYPE_DIR).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                    }.onFailure {toast("已保存；系统没有可打开文件夹的应用")}
                    if(source!=null && !isFinishing && !isDestroyed)scheduleRender()
                }
            }
        }
    }
    private fun finishExport() {
        closeExportProgress();exporting=false;batchTotal=0;updateActions()
        if(source!=null && !isFinishing && !isDestroyed)scheduleRender()
    }
    private fun settings() {
        val panel=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(d(24),d(12),d(24),d(12)) }
        fun toggle(title:String,key:String) { panel.addView(Switch(this).apply { text=title;textSize=14f;typeface=InterfaceTypography.forText(this@MainActivity,title,14f);isChecked=prefs.getBoolean(key,true);setPadding(0,d(12),0,d(12));thumbTintList=UiTheme.toggleColors();trackTintList=UiTheme.trackColors();setTextColor(UiTheme.textColors());setOnCheckedChangeListener { _,checked->
            prefs.edit().putBoolean(key,checked).apply()
        } }) }
        toggle("细腻过渡动画","motion");toggle("轻触反馈","haptic")
        panel.addView(button("预览精度",{
            val edges=listOf(1080,1920,2560);val labels=arrayOf("1080 · 较低占用","1920 · 平衡","2560 · 更多细节")
            val choice=AlertDialog.Builder(this).setTitle("预览精度").setSingleChoiceItems(labels,edges.indexOf(prefs.getInt("preview-edge",1920)).coerceAtLeast(0)){dialog,index ->prefs.edit().putInt("preview-edge",edges[index]).apply();dialog.dismiss();if(currentPhoto in photos.indices)openPhoto(currentPhoto)}.setNegativeButton("取消",null).create()
            choice.show();styleDialog(choice)
        }).apply {gravity=Gravity.START},LinearLayout.LayoutParams(-1,-2))
        panel.addView(button("RAW 缓存上限",{
            val limits=listOf(768,1536,3072);val labels=arrayOf("768 MB","1.5 GB","3 GB")
            val choice=AlertDialog.Builder(this).setTitle("RAW 缓存上限").setSingleChoiceItems(labels,limits.indexOf(prefs.getInt("raw-cache-mb",1536)).coerceAtLeast(0)){dialog,index ->prefs.edit().putInt("raw-cache-mb",limits[index]).apply();dialog.dismiss();if(rawCacheDelegate.isInitialized())rawCache.trimIdle()}.setNegativeButton("取消",null).create()
            choice.show();styleDialog(choice)
        }).apply {gravity=Gravity.START},LinearLayout.LayoutParams(-1,-2))
        panel.addView(button("清理空闲缓存",{if(rawCacheDelegate.isInitialized())rawCache.trimIdle(true);toast("空闲缓存已清理")}).apply {gravity=Gravity.START},LinearLayout.LayoutParams(-1,-2))
        panel.addView(text("界面字体",14f,ink,true).apply { setPadding(0,d(20),0,d(9)) })
        panel.addView(text(InterfaceTypography.description(this),12f,muted).apply { setLineSpacing(d(4).toFloat(),1f) })
        panel.addView(text("关于光谱与色彩",14f,ink,true).apply { setPadding(0,d(20),0,d(9)) })
        panel.addView(text("原生处理 · Vulkan\n胶片显影可自由启用。预览与导出共享同一套调整，最终输出始终读取原片。RAW 由本机 LibRaw 解码；预览使用有界缓存，JPG 与 TIFF 按源图像素显影，显式裁切除外。TIFF 保留 16 bit / 通道，JPG 按选择的品质编码。RAW 原片另存不执行显影。\n\n编辑记录独立保存，不改写原片。\n\nFilm modeling · spektrafilm\nAndrea Volpato · GPLv3\nFilm profiles / LUTs · CC BY-SA 4.0\nRAW decoding · LibRaw\n\nSpektraFilm · 0.5",12f,muted).apply {setLineSpacing(d(4).toFloat(),1f)})
        panel.addView(button("查看原项目与许可", { startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://github.com/andreavolpato/spektrafilm"))) }),LinearLayout.LayoutParams(-1,d(42)).apply { topMargin=d(16) })
        styleDialog(AlertDialog.Builder(this).setTitle("设置").setView(ScrollView(this).apply { addView(panel) }).setPositiveButton("完成",null).show())
    }
    private fun styleDialog(dialog:AlertDialog) {
        fun applyFont(view:View) {
            if(view is TextView) {view.typeface=InterfaceTypography.forText(this@MainActivity,view.text,view.textSize/resources.displayMetrics.scaledDensity)}
            if(view is CheckedTextView) {
                view.minHeight=d(48);view.setTextColor(UiTheme.choiceTextColors());view.checkMarkTintList=UiTheme.toggleColors()
                view.background=UiTheme.controlBackground(this@MainActivity,UiTheme.surface,6f,Color.TRANSPARENT)
            }
            if(view is ViewGroup)for(i in 0 until view.childCount)applyFont(view.getChildAt(i))
        }
        dialog.window?.decorView?.let { applyFont(it) }
        dialog.listView?.setOnHierarchyChangeListener(object:ViewGroup.OnHierarchyChangeListener {
            override fun onChildViewAdded(parent:View?,child:View?) { child?.let { applyFont(it) } }
            override fun onChildViewRemoved(parent:View?,child:View?) {}
        })
        dialog.window?.let { window ->
            window.setBackgroundDrawable(shape(UiTheme.surface,16f,line))
            if(!motionEnabled())window.setWindowAnimations(0)
            val attributes=window.attributes;attributes.dimAmount=.32f;window.attributes=attributes
            window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            window.setLayout(min(resources.displayMetrics.widthPixels-d(32),d(520)),WindowManager.LayoutParams.WRAP_CONTENT)
        }
        for(which in arrayOf(AlertDialog.BUTTON_POSITIVE,AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL)) {
            dialog.getButton(which)?.apply {
                typeface=InterfaceTypography.forText(this@MainActivity,text,14f,true);textSize=14f;isAllCaps=false
                setPadding(d(14),0,d(14),0);minHeight=d(44)
                background=UiTheme.controlBackground(this@MainActivity,if(which==AlertDialog.BUTTON_POSITIVE)ink else Color.TRANSPARENT,6f,Color.TRANSPARENT)
                setTextColor(UiTheme.textColors(if(which==AlertDialog.BUTTON_POSITIVE)UiTheme.surface else ink))
            }
        }
    }
    private fun toast(value:String) { val label=text(value,13f,UiTheme.surface).apply { background=shape(ink,10f);setPadding(d(20),d(13),d(20),d(13)) };Toast(this).apply { duration=Toast.LENGTH_SHORT;view=label;show() } }
    private fun showError(value:String) { if(!isFinishing) styleDialog(AlertDialog.Builder(this).setTitle("暂时无法完成").setMessage(value).setPositiveButton("知道了",null).show()) }
    override fun onStop() { saveSession();super.onStop() }
    override fun onDestroy() {closeCrop(false);window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);activityDisposed=true;cancelBatch=true;generation++;if(rawCacheDelegate.isInitialized())rawCache.close();main.removeCallbacksAndMessages(null);worker.shutdown();fastWorker.shutdown();fullWorker.shutdown();Thread {engine?.close()}.start();listOf(source,spectralSource,interactionSource,rendered).filterNotNull().distinct().forEach {if(!it.isRecycled)it.recycle()};super.onDestroy()}
}

class FavoriteMark(context:Context,private val selected:Boolean,private val accent:Int,private val muted:Int):View(context) {
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG)
    private val starPath=Path()
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);val radius=min(width,height)*.32f;val cx=width/2f;val cy=height/2f;val path=starPath;path.rewind()
        for(i in 0 until 10) { val angle=-Math.PI/2+i*Math.PI/5;val r=if(i%2==0)radius else radius*.44f;val x=cx+cos(angle).toFloat()*r;val y=cy+sin(angle).toFloat()*r;if(i==0)path.moveTo(x,y)else path.lineTo(x,y) };path.close()
        paint.color=if(selected)accent else muted;paint.style=if(selected)Paint.Style.FILL else Paint.Style.STROKE;paint.strokeWidth=resources.displayMetrics.density;canvas.drawPath(path,paint)
    }
}

/** Font-independent affordance keeps the selector label and width stable. */
private class DropdownMark(context:Context):View(context) {
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG).apply {style=Paint.Style.STROKE;strokeCap=Paint.Cap.ROUND;strokeJoin=Paint.Join.ROUND}
    private val path=Path()
    init {importantForAccessibility=IMPORTANT_FOR_ACCESSIBILITY_NO}
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);val unit=resources.displayMetrics.density
        paint.color=if(isEnabled)UiTheme.muted else UiTheme.line;paint.strokeWidth=1.5f*unit
        val x=width/2f;val y=height/2f;path.rewind();path.moveTo(x-4*unit,y-2*unit);path.lineTo(x,y+2*unit);path.lineTo(x+4*unit,y-2*unit)
        canvas.drawPath(path,paint)
    }
}

private class CropMark(context:Context):View(context) {
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG).apply {style=Paint.Style.STROKE;strokeCap=Paint.Cap.ROUND;strokeJoin=Paint.Join.ROUND}
    init {importantForAccessibility=IMPORTANT_FOR_ACCESSIBILITY_NO}
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);val unit=resources.displayMetrics.density
        paint.color=if(isEnabled)UiTheme.muted else UiTheme.line;paint.strokeWidth=1.4f*unit
        val cx=width/2f;val cy=height/2f
        canvas.drawLine(cx-5*unit,cy-8*unit,cx-5*unit,cy+5*unit,paint)
        canvas.drawLine(cx-5*unit,cy+5*unit,cx+8*unit,cy+5*unit,paint)
        canvas.drawLine(cx-8*unit,cy-5*unit,cx+5*unit,cy-5*unit,paint)
        canvas.drawLine(cx+5*unit,cy-5*unit,cx+5*unit,cy+8*unit,paint)
    }
}

/** Small vector marks keep the app bar usable when system text is enlarged. */
private class AppBarMark(context:Context,private val importing:Boolean):View(context) {
    private val paint=Paint(Paint.ANTI_ALIAS_FLAG).apply {style=Paint.Style.STROKE;strokeCap=Paint.Cap.ROUND;strokeJoin=Paint.Join.ROUND}
    init {importantForAccessibility=IMPORTANT_FOR_ACCESSIBILITY_NO}
    override fun onDraw(canvas:Canvas) {
        super.onDraw(canvas);val unit=resources.displayMetrics.density;val cx=width/2f;val cy=height/2f
        paint.color=if(importing)UiTheme.accent else UiTheme.ink;paint.strokeWidth=1.6f*unit
        if(importing) {
            canvas.drawRoundRect(cx-8*unit,cy-6*unit,cx+8*unit,cy+8*unit,2*unit,2*unit,paint)
            canvas.drawLine(cx,cy-10*unit,cx,cy+1*unit,paint)
            canvas.drawLine(cx,cy+1*unit,cx-3*unit,cy-2*unit,paint);canvas.drawLine(cx,cy+1*unit,cx+3*unit,cy-2*unit,paint)
        } else {
            for(index in 0..2) {
                val y=cy+(index-1)*6*unit;val knob=cx+(if(index==1)4 else -3)*unit
                canvas.drawLine(cx-8*unit,y,cx+8*unit,y,paint)
                paint.style=Paint.Style.FILL;paint.color=UiTheme.background;canvas.drawCircle(knob,y,2.5f*unit,paint)
                paint.style=Paint.Style.STROKE;paint.color=UiTheme.ink;canvas.drawCircle(knob,y,2.5f*unit,paint)
            }
        }
    }
}
