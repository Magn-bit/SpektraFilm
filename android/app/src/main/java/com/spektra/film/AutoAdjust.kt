package com.spektra.film

import android.graphics.Bitmap
import kotlin.math.*

/** Independent offline proposals, matching shared/auto_adjust.py statistics; never applies edits itself. */
internal object AutoAdjust {
    data class Proposal(val values:Adjustments?,val reason:String)
    private fun percentile(values:FloatArray,p:Double):Float {values.sort();val t=(values.size-1)*p;val i=t.toInt();return values[i]+(values[min(i+1,values.lastIndex)]-values[i])*(t-i).toFloat()}
    private fun median(values:List<Float>)=percentile(values.toFloatArray(),.5)
    fun analyze(image:Bitmap,kind:String,a:Adjustments):Proposal {
        val pixels=IntArray(image.width*image.height);image.getPixels(pixels,0,image.width,0,0,image.width,image.height)
        val rgb=Array(3){FloatArray(pixels.size)};val encodedY=FloatArray(pixels.size);val linearY=FloatArray(pixels.size)
        pixels.forEachIndexed {i,p->val r=(p ushr 16 and 255)/255f;val g=(p ushr 8 and 255)/255f;val b=(p and 255)/255f
            encodedY[i]=.2126f*r+.7152f*g+.0722f*b
            floatArrayOf(r,g,b).forEachIndexed {c,v->rgb[c][i]=if(v<=.04045f)v/12.92f else ((v+.055f)/1.055f).pow(2.4f)}
            linearY[i]=.2126f*rgb[0][i]+.7152f*rgb[1][i]+.0722f*rgb[2][i]}
        if(kind=="geometry")return straighten(encodedY,image.width,image.height,a)
        if(kind=="white_balance") {
            val neutral=Array(3){mutableListOf<Float>()}
            for(i in pixels.indices){val lo=minOf(rgb[0][i],rgb[1][i],rgb[2][i]);val hi=maxOf(rgb[0][i],rgb[1][i],rgb[2][i]);val y=linearY[i]
                if(y>.015f && y<.8f && lo>.004f && (hi-lo)/max(hi,1e-6f)<.55f)for(c in 0..2)neutral[c].add(rgb[c][i]/y)}
            if(neutral[0].size<max(64,pixels.size/100))return Proposal(null,"缺少可靠的中性区域，保留白平衡")
            val n=DoubleArray(3){median(neutral[it]).toDouble()};var temperature=6500.0;var tint=0.0;var error=Double.MAX_VALUE
            fun score(t:Double,g:Double):Double {val m=wb(t,g);val v=DoubleArray(3){r->(0..2).sumOf {c->m[r*3+c]*n[c]}};val mean=max(v.average(),1e-6);return v.sumOf {ln(max(it/mean,1e-6)).pow(2)}}
            for(t in 2000..10000 step 400)for(g in -100..100 step 20){val e=score(t.toDouble(),g.toDouble());if(e<error){error=e;temperature=t.toDouble();tint=g.toDouble()}}
            for(step in listOf(100.0,25.0,5.0)){val ct=temperature;val cg=tint
                for(i in -4..4)for(j in -4..4){val t=(ct+i*step).coerceIn(2000.0,10000.0);val g=(cg+j*step/20).coerceIn(-100.0,100.0);val e=score(t,g);if(e<error){error=e;temperature=t;tint=g}}}
            val confidence=min(.9,.45+.45*neutral[0].size/pixels.size)*max(0.0,1-sqrt(error)*2)
            return if(confidence<.4)Proposal(null,"中性估计不可靠，保留白平衡") else Proposal(a.copy(temperature=temperature.toFloat(),tint=tint.toFloat()),"依据未剪切的近中性区域估计")
        }
        val low=percentile(encodedY.copyOf(),.002);val high=percentile(encodedY.copyOf(),.998)
        if(high-low<.015)return Proposal(null,"画面层次不足，保留当前调整")
        if(kind=="levels") {
            val black=low.coerceIn(0f,.18f);val white=high.coerceIn(.55f,1f);val middle=((percentile(encodedY,.5)-black)/(white-black)).coerceIn(.03f,.97f)
            val level=a.levels.master.copy(black=black,white=white,gamma=(ln(middle)/ln(.46f)).coerceIn(.65f,1.6f))
            return Proposal(a.copy(levels=a.levels.copy(master=level)),"建立主色阶，保留各色通道")
        }
        val mid=percentile(linearY.copyOf(),.5);val top=percentile(linearY.copyOf(),.995)
        val correction=log2(.18/max(mid.toDouble(),1e-5)).coerceIn(-1.25,1.25)
        return Proposal(a.copy(exposure=(a.exposure+correction).toFloat().coerceIn(-3f,3f),highlights=(-(top*2.0.pow(correction)-.88)*75).toFloat().coerceIn(-70f,0f),shadows=((.07f-percentile(linearY,.1))*220).coerceIn(0f,35f)),"保守调整中间调、高光与阴影")
    }
    private fun multiply(a:DoubleArray,b:DoubleArray)=DoubleArray(9){i->(0..2).sumOf {k->a[i/3*3+k]*b[k*3+i%3]}}
    private fun vector(a:DoubleArray,b:DoubleArray)=DoubleArray(3){r->(0..2).sumOf {c->a[r*3+c]*b[c]}}
    private val xyz=doubleArrayOf(.4124564,.3575761,.1804375,.2126729,.7151522,.072175,.0193339,.119192,.9503041)
    private val bradford=doubleArrayOf(.8951,.2664,-.1614,-.7502,1.7135,.0367,.0389,-.0685,1.0296)
    private fun white(t:Double,g:Double=0.0):DoubleArray {
        val x=if(t>4000)-3.0258469e9/t.pow(3)+2.1070379e6/t.pow(2)+.2226347e3/t+.240390 else -.2661239e9/t.pow(3)-.2343580e6/t.pow(2)+.8776956e3/t+.179910
        var y=if(t<=2222)-1.1063814*x.pow(3)-1.34811020*x*x+2.18555832*x-.20219683 else if(t<=4000)-.9549476*x.pow(3)-1.37418593*x*x+2.09137015*x-.16748867 else 3.081758*x.pow(3)-5.8733867*x*x+3.75112997*x-.37001483
        y=(y+g*.000045).coerceIn(.30,.36);return doubleArrayOf(x/y,1.0,(1-x-y)/y)
    }
    private fun wb(t:Double,g:Double):DoubleArray {
        val target=vector(bradford,white(t,g));val source=vector(bradford,white(6500.0));val d=doubleArrayOf(target[0]/source[0],0.0,0.0,0.0,target[1]/source[1],0.0,0.0,0.0,target[2]/source[2])
        return multiply(multiply(PhotoGeometry.inverse(xyz),multiply(multiply(PhotoGeometry.inverse(bradford),d),bradford)),xyz)
    }
    private fun straighten(gray:FloatArray,w:Int,h:Int,a:Adjustments):Proposal {
        val edges=mutableListOf<Pair<Int,Int>>()
        for(y in 1 until h-1)for(x in 1 until w-1){val i=y*w+x;val gx=gray[i+1]-gray[i-1];val gy=gray[i+w]-gray[i-w];if(hypot(gx,gy)>.16f)edges.add(x to y)}
        if(edges.size<max(64,w*h/500))return Proposal(null,"未检测到足够的直线")
        val diagonal=ceil(hypot(w.toDouble(),h.toDouble())).toInt();val lineThreshold=max(24.0,min(w,h)*.12).toInt()
        data class Peak(val angle:Double,val rho:Int,val score:Int,val axis:Int)
        val candidates=mutableListOf<Peak>()
        for(axis in 0..1)for(step in -40..40){val deviation=step*.25;val angle=(axis*90.0+deviation)*PI/180;val cs=cos(angle);val sn=sin(angle);val votes=IntArray(diagonal*2+1)
            for((x,y) in edges)votes[(x*cs+y*sn).roundToInt()+diagonal]++
            for(r in 1 until votes.lastIndex)if(votes[r]>=lineThreshold && votes[r]>=votes[r-1] && votes[r]>=votes[r+1])candidates.add(Peak(deviation,r-diagonal,votes[r],axis))}
        val peaks=mutableListOf<Peak>()
        for(p in candidates.sortedByDescending {it.score}){if(peaks.none {it.axis==p.axis && abs(it.rho-p.rho)<12 && abs(it.angle-p.angle)<2})peaks.add(p);if(peaks.size>=24)break}
        if(peaks.size<3)return Proposal(null,"可靠直线不足，保留拉直角度")
        val best=peaks.maxBy {p->peaks.filter {abs(it.angle-p.angle)<1}.sumOf {it.score}}
        val kept=peaks.filter {abs(it.angle-best.angle)<1};val support=kept.sumOf {it.score}.toDouble()/peaks.sumOf {it.score}
        val mean=kept.sumOf {it.angle*it.score}/kept.sumOf {it.score};val spread=sqrt(kept.sumOf {(it.angle-mean).pow(2)*it.score}/kept.sumOf {it.score})
        val confidence=support*min(1.0,kept.size/5.0)*max(0.0,1-spread/1.2)
        if(kept.size<3 || support<.65 || confidence<.5 || abs(mean)>10)return Proposal(null,"直线方向不一致，未强行拉直")
        val angle=if(a.geometry.flipHorizontal!=a.geometry.flipVertical)mean else -mean
        return Proposal(a.copy(geometry=a.geometry.copy(rotation=angle.toFloat())),"依据一致的水平与垂直直线估计倾斜")
    }
}
