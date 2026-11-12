package com.spektra.film

import android.app.Dialog
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.util.LruCache
import android.view.*
import android.widget.*
import java.util.concurrent.Executors
import kotlin.math.min

/** Tapping a photo edits it; checkboxes have an independent batch scope. */
class PhotoBrowserDialog(
    context:Context,
    private val names:List<String>,
    private val current:Int,
    selected:Set<Int>,
    private val loadThumbnail:(Int)->Bitmap?,
    private val onEdit:(Int)->Unit,
    private val onSelection:(Set<Int>)->Unit,
    private val onRemove:(Set<Int>)->Unit
) : Dialog(context) {
    private val selection=selected.toMutableSet()
    private val ink=UiTheme.ink
    private val muted=UiTheme.muted
    private val line=UiTheme.line
    private val main=Handler(Looper.getMainLooper())
    private val worker=Executors.newSingleThreadExecutor()
    private val cache=object:LruCache<Int,Bitmap>(6*1024*1024) {
        override fun sizeOf(key:Int,value:Bitmap)=value.allocationByteCount
    }
    private val pending=mutableSetOf<Int>()
    private val unavailable=mutableSetOf<Int>()
    private val face=InterfaceTypography.load(context)
    @Volatile private var disposed=false
    private lateinit var summary:TextView
    private lateinit var all:TextView
    private lateinit var remove:TextView
    private val rows=Rows()
    private fun d(value:Int)=(value*context.resources.displayMetrics.density+.5f).toInt()
    private fun surface(color:Int,radius:Int=10,border:Int=Color.TRANSPARENT)=GradientDrawable().apply {
        setColor(color);cornerRadius=d(radius).toFloat();if(border!=Color.TRANSPARENT)setStroke(d(1),border)
    }
    private fun label(value:String,size:Float,color:Int=ink)=TextView(context).apply {
        text=value;textSize=maxOf(size,UiTokens.caption);setTextColor(UiTheme.textColors(color));typeface=InterfaceTypography.forText(context,value,size)
        includeFontPadding=false;gravity=Gravity.CENTER_VERTICAL
    }
    private fun action(value:String,primary:Boolean=false,run:()->Unit)=label(value,14f,if(primary)UiTheme.surface else ink).apply {
        gravity=Gravity.CENTER;minHeight=d(48);setPadding(d(12),0,d(12),0)
        background=UiTheme.controlBackground(context,if(primary)ink else Color.TRANSPARENT,9f,Color.TRANSPARENT)
        isClickable=true;isFocusable=true;setOnClickListener { run() }
    }
    override fun onCreate(state:Bundle?) {
        super.onCreate(state);requestWindowFeature(Window.FEATURE_NO_TITLE)
        val panel=LinearLayout(context).apply { orientation=LinearLayout.VERTICAL;setPadding(d(20),d(22),d(20),d(12)) }
        panel.addView(label("照片",20f))
        panel.addView(label("点照片开始编辑 · 勾选用于批量处理",12f,muted).apply { setPadding(0,d(8),0,d(14)) })
        summary=label("",12f,muted);panel.addView(summary,LinearLayout.LayoutParams(-1,d(30)))
        val list=ListView(context).apply { adapter=rows;divider=android.graphics.drawable.ColorDrawable(line);dividerHeight=d(1);isVerticalScrollBarEnabled=true;selector=android.graphics.drawable.ColorDrawable(Color.TRANSPARENT);contentDescription="已导入的照片" }
        val height=min(d(names.size*84), (context.resources.displayMetrics.heightPixels*.49f).toInt())
        panel.addView(list,LinearLayout.LayoutParams(-1,height))
        val footer=LinearLayout(context).apply { gravity=Gravity.CENTER_VERTICAL;setPadding(0,d(12),0,0) }
        all=action("全选") { if(selection.size==names.size)selection.clear() else selection.addAll(names.indices);changed() }
        remove=action("移除") { if(selection.isNotEmpty()) { val targets=selection.toSet();dismiss();onRemove(targets) } }
        footer.addView(all,LinearLayout.LayoutParams(-2,d(48)))
        footer.addView(remove,LinearLayout.LayoutParams(-2,d(48)))
        footer.addView(Space(context),LinearLayout.LayoutParams(0,1,1f))
        footer.addView(action("完成",true) { dismiss() },LinearLayout.LayoutParams(-2,d(48)))
        panel.addView(footer);setContentView(panel)
        window?.setBackgroundDrawable(surface(UiTheme.surface,16,line))
        window?.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
        window?.attributes=window!!.attributes.apply { dimAmount=.32f }
        setOnDismissListener {
            disposed=true;worker.shutdownNow();main.removeCallbacksAndMessages(null);cache.evictAll()
            onSelection(selection.toSet())
        }
        changed()
    }
    override fun onStart() {
        super.onStart()
        window?.setLayout(min(context.resources.displayMetrics.widthPixels-d(24),d(520)),WindowManager.LayoutParams.WRAP_CONTENT)
    }
    private fun changed() {
        summary.text="共 "+names.size+" 张 · 批量已选 "+selection.size+" 张"
        all.text=if(selection.size==names.size)"取消全选" else "全选"
        remove.isEnabled=selection.isNotEmpty();remove.setTextColor(UiTheme.textColors())
        rows.notifyDataSetChanged()
    }
    private inner class Holder(val row:LinearLayout,val photo:ImageView,val title:TextView,val detail:TextView,val check:CheckBox)
    private inner class Rows:BaseAdapter() {
        override fun getCount()=names.size
        override fun getItem(position:Int)=names[position]
        override fun getItemId(position:Int)=position.toLong()
        override fun getView(position:Int,convert:View?,parent:ViewGroup):View {
            val holder=if(convert?.tag is Holder)convert.tag as Holder else {
                val row=LinearLayout(context).apply { gravity=Gravity.CENTER_VERTICAL;setPadding(d(2),d(10),0,d(10)) }
                val photo=ImageView(context).apply { scaleType=ImageView.ScaleType.CENTER_CROP;background=surface(UiTheme.canvas,6);clipToOutline=true;importantForAccessibility=View.IMPORTANT_FOR_ACCESSIBILITY_NO }
                row.addView(photo,LinearLayout.LayoutParams(d(62),d(62)))
                val copy=LinearLayout(context).apply { orientation=LinearLayout.VERTICAL;gravity=Gravity.CENTER_VERTICAL;setPadding(d(12),0,d(4),0) }
                val title=label("",14f).apply { maxLines=1;ellipsize=TextUtils.TruncateAt.MIDDLE }
                val detail=label("",12f,muted).apply { setPadding(0,d(7),0,0) }
                copy.addView(title,LinearLayout.LayoutParams(-1,-2));copy.addView(detail,LinearLayout.LayoutParams(-1,-2))
                row.addView(copy,LinearLayout.LayoutParams(0,-1,1f))
                val check=CheckBox(context).apply { buttonTintList=UiTheme.toggleColors();minWidth=d(48);minHeight=d(48) }
                row.addView(check,LinearLayout.LayoutParams(d(48),d(48)))
                Holder(row,photo,title,detail,check).also { row.tag=it }
            }
            holder.title.text=names[position]
            holder.detail.text=if(position==current)"正在编辑 · "+(position+1)+" / "+names.size else "轻点编辑 · "+(position+1)+" / "+names.size
            holder.row.background=UiTheme.controlBackground(context,UiTheme.surface,8f,Color.TRANSPARENT,position==current)
            holder.title.setTextColor(if(position==current)UiTheme.accentText else ink)
            holder.row.isFocusable=true;holder.row.contentDescription=names[position]+if(position==current)"，当前编辑" else "，轻点编辑"
            holder.row.setOnClickListener { selection.clear();selection.add(position);dismiss();onEdit(position) }
            holder.check.setOnCheckedChangeListener(null);holder.check.isChecked=position in selection
            holder.check.contentDescription="批量选择 "+names[position]
            holder.check.setOnCheckedChangeListener { _,checked -> if(checked)selection.add(position)else selection.remove(position);changed() }
            holder.photo.tag=position
            holder.photo.setImageBitmap(cache.get(position))
            if(cache.get(position)==null && position !in unavailable && pending.add(position))worker.execute {
                val bitmap=try { loadThumbnail(position) } catch(_:Exception) { null }
                if(disposed)bitmap?.recycle() else main.post {
                    pending.remove(position)
                    if(disposed)bitmap?.recycle() else if(bitmap!=null) { cache.put(position,bitmap);notifyDataSetChanged() } else unavailable.add(position)
                }
            }
            return holder.row
        }
    }
}
