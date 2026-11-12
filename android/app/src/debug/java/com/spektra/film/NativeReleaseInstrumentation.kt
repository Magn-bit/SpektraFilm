package com.spektra.film

import android.app.Activity
import android.app.Instrumentation
import android.graphics.BitmapFactory
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Acceptance runner in the personal debug APK, so a second USB installation is unnecessary. */
class NativeReleaseInstrumentation : Instrumentation() {
    private var rawPath=""
    private var mode=""
    override fun onCreate(arguments:Bundle?) {rawPath=arguments?.getString("raw_path").orEmpty();mode=arguments?.getString("mode").orEmpty();super.onCreate(arguments);start()}
    override fun onStart() {
        val result=Bundle()
        val details=JSONObject()
        val file=File(targetContext.filesDir,"native-test-report.json")
        val engine=FilmEngine(targetContext)
        try {
            if(mode=="exposure_baseline" || mode=="exposure") {
                verifyExposure(engine,details,mode=="exposure_baseline")
                if(mode=="exposure")verifyCancellationOnly(engine,details)
                details.put("ok",true)
                File(targetContext.filesDir,if(mode=="exposure_baseline")"native-exposure-baseline.json" else "native-exposure-report.json").writeText(details.toString(2))
                result.putString("stream","OK targeted exposure: $details\n")
                finish(Activity.RESULT_OK,result)
                return
            }
            if(mode=="cancel") {
                verifyCancellationOnly(engine,details)
                details.put("ok",true)
                File(targetContext.filesDir,"native-cancel-report.json").writeText(details.toString(2))
                result.putString("stream","OK cancellation cleanup and native Bitmap/JPG transport: $details\n")
                finish(Activity.RESULT_OK,result)
                return
            }
            file.delete()
            details.put("device",engine.nativeDevice()).put("materials",engine.stocks.size)
            check(engine.stocks.size==27)
            val stock=engine.stocks.first {it.id=="kodak_portra_400"}
            val width=127;val height=95
            val pixels=FloatArray(width*height*3){((it*37+11)%65536)/65535f}
            val neutral=Adjustments(strength=0f,grain=0f,halation=0f)
            val restored=requireNotNull(engine.render16(pixels,width,height,stock,neutral))
            for(i in pixels.indices)check((restored[i].toInt() and 65535)==(pixels[i]*65535+.5f).toInt()) {"RGB16 source detail changed"}
            val bitmap=Bitmap.createBitmap(intArrayOf(Color.RED,Color.BLUE,Color.GREEN,Color.WHITE),2,2,Bitmap.Config.ARGB_8888)
            try {
                val packed=requireNotNull(engine.renderBitmapRegion(bitmap,stock,neutral,2,2,0,0,0,0,2,2,{false}))
                check((packed[0].toInt() and 65535)==65535 && (packed[2].toInt() and 65535)==0)
                check((packed[3].toInt() and 65535)==0 && (packed[5].toInt() and 65535)==65535)
            } finally {bitmap.recycle()}
            details.put("bitmap_rgb_channels",true)
            val defaultHalo=engine.spatialHalo(stock,Adjustments(filmEnabled=true),9564,6376)
            val capacity=engine.exportTileCapacity()
            details.put("default_61mp_halo",defaultHalo).put("native_tile_capacity",capacity)
            FilmEngine(targetContext).let {probe->
                try {
                    val values=FloatArray(1024*1024*3){.45f}
                    val probeStart=SystemClock.elapsedRealtime()
                    requireNotNull(probe.render16(values,1024,1024,stock,Adjustments(filmEnabled=true),9564,6376))
                    details.put("memory_probe_ms",SystemClock.elapsedRealtime()-probeStart)
                    details.put("native_memory_probe",org.json.JSONArray(probe.nativeMemoryPeak().toList()))
                } finally {probe.close()}
            }
            for(id in listOf("kodak_portra_400","fujifilm_provia_100f","kodak_tri_x_400","ilford_hp5_plus_400")) {
                val material=engine.stocks.first {it.id==id}
                val output=requireNotNull(engine.render16(pixels,width,height,material,Adjustments(filmEnabled=true,grain=0f,halation=0f)))
                check(output.size==pixels.size && output.any {(it.toInt() and 65535)>1024}) {"$id is black"}
            }
            val start=SystemClock.elapsedRealtime()
            val first=requireNotNull(engine.render16(pixels,width,height,stock,Adjustments(filmEnabled=true,grain=0f,halation=0f),preview=true))
            details.put("preview_first_ms",SystemClock.elapsedRealtime()-start)
            val reprintStart=SystemClock.elapsedRealtime()
            val reprint=requireNotNull(engine.render16(pixels,width,height,stock,Adjustments(filmEnabled=true,grain=0f,halation=0f,printExposure=1f),preview=true))
            check(!first.contentEquals(reprint)) {"Cached negative did not reprint"}
            details.put("preview_reprint_ms",SystemClock.elapsedRealtime()-reprintStart)
            val source=File.createTempFile("native-rgb16-",".rgb16le",targetContext.cacheDir)
            val tiff=File.createTempFile("native-tiff16-",".tif",targetContext.cacheDir)
            val bytes=ByteBuffer.allocate(restored.size*2).order(ByteOrder.LITTLE_ENDIAN).apply {restored.forEach {putShort(it)}}.array()
            source.writeBytes(bytes)
            try {
                FullResolutionPhoto(targetContext.contentResolver,Uri.fromFile(source),Rgb16PixelSource(source,width,height)).use {photo->
                    var last=-1
                    tiff.outputStream().use {out->photo.writeTiff(engine,stock,neutral,out,targetContext.assets.open("color/sRGB.icc").use {it.readBytes()},progress={check(it>=last);last=it},cancelled={false})}
                    check(last==100)
                }
                val encoded=tiff.readBytes();val header=ByteBuffer.wrap(encoded).order(ByteOrder.LITTLE_ENDIAN)
                val count=header.getShort(8).toInt() and 65535;val tags=mutableMapOf<Int,Int>()
                for(i in 0 until count){val at=10+i*12;tags[header.getShort(at).toInt() and 65535]=header.getInt(at+8)}
                check(tags[256]==width && tags[257]==height && tags[259]==8)
                check(header.getShort(requireNotNull(tags[258])).toInt()==16)
                val unpacked=java.util.zip.InflaterInputStream(java.io.ByteArrayInputStream(encoded,requireNotNull(tags[273]),requireNotNull(tags[279]))).use {it.readBytes()}
                check(unpacked.contentEquals(bytes)) {"TIFF16 lost source bits"}
            } finally {source.delete();tiff.delete()}
            details.put("native_rgb16",true).put("tiff16",true).put("reprint",true)
            if(rawPath.isNotBlank()) {
                val raw=File(rawPath);check(raw.isFile)
                val uri=Uri.fromFile(raw)
                val output=File(targetContext.cacheDir,"native-full-export-test.jpg")
                val partial=File(targetContext.cacheDir,"native-cancel-export-test.jpg")
                try {
                    RawPhotoCache(targetContext).use {cache->
                        val previewStart=SystemClock.elapsedRealtime()
                        val preview=cache.preview(uri,{_,_->1024})
                        check(preview.sourceWidth>=9000 && preview.bitmap.width<=1024 && preview.bitmap.height<=1024)
                        preview.bitmap.recycle()
                        details.put("raw_preview_decode_ms",SystemClock.elapsedRealtime()-previewStart)
                        val decodeStart=SystemClock.elapsedRealtime()
                        FullResolutionPhoto.open(targetContext.contentResolver,uri,raw.name,cache).use {photo->
                            check(photo.width>=9000 && photo.height>=6000)
                            details.put("raw_decode_ms",SystemClock.elapsedRealtime()-decodeStart)
                            var last=-1;var updates=0
                            val exportStart=SystemClock.elapsedRealtime()
                            photo.writeJpeg(engine,stock,Adjustments(),output,100,progress={check(it>=last);last=it;updates++},cancelled={false})
                            details.put("full_export_ms",SystemClock.elapsedRealtime()-exportStart)
                            details.put("native_memory_export",org.json.JSONArray(engine.nativeMemoryPeak().toList()))
                            check(last==100 && updates>10)
                            val bounds=BitmapFactory.Options().apply {inJustDecodeBounds=true}
                            BitmapFactory.decodeFile(output.absolutePath,bounds)
                            check(bounds.outWidth==photo.width && bounds.outHeight==photo.height)
                            details.put("width",photo.width).put("height",photo.height).put("progress_updates",updates).put("jpg_bytes",output.length())
                            val small=BitmapFactory.decodeFile(output.absolutePath,BitmapFactory.Options().apply {inSampleSize=8}) ?: error("JPG cannot decode")
                            try {
                                val samples=IntArray(small.width*small.height);small.getPixels(samples,0,small.width,0,0,small.width,small.height)
                                check(samples.count {(it and 0xffffff)>0x101010}>samples.size/10) {"Full export is black"}
                                File(targetContext.cacheDir,"native-export-preview.jpg").outputStream().use {small.compress(Bitmap.CompressFormat.JPEG,95,it)}
                            } finally {small.recycle()}
                            var cancel=false
                            val cancelStart=SystemClock.elapsedRealtime()
                            val failed=runCatching {photo.writeJpeg(engine,stock,Adjustments(),partial,100,progress={if(it>0)cancel=true},cancelled={cancel})}.isFailure
                            check(failed && cancel && !partial.exists()) {"Cancelled export left partial output"}
                            details.put("cancellation",true).put("cancellation_ms",SystemClock.elapsedRealtime()-cancelStart)
                        }
                    }
                    details.put("raw_proxy_isolation",true)
                } finally {output.delete();partial.delete()}
            }
            details.put("ok",true)
            file.writeText(details.toString(2))
            result.putString("stream","OK native Android acceptance: ${details}\n")
            finish(Activity.RESULT_OK,result)
        } catch(error:Throwable) {
            details.put("ok",false).put("error",error.stackTraceToString());file.writeText(details.toString(2))
            result.putString("stream",error.stackTraceToString());finish(Activity.RESULT_CANCELED,result)
        } finally {engine.close()}
    }

    private fun verifyExposure(engine:FilmEngine,details:JSONObject,baselineOnly:Boolean) {
        val width=127;val height=95
        val pixels=FloatArray(width*height*3){i->
            val p=i/3;val x=p%width;val y=p/width
            val value=.16f+.32f*x/(width-1)+.16f*y/(height-1)
            value*when(i%3){0->1.04f;1->1f;else->.96f}
        }
        val stock=engine.stocks.first {it.id=="kodak_portra_400"}
        fun render(ev:Float)=requireNotNull(engine.render16(pixels,width,height,stock,Adjustments(filmEnabled=true,exposure=ev,grain=0f,halation=0f),preview=true))
        fun bytes(values:ShortArray)=ByteBuffer.allocate(values.size*2).order(ByteOrder.LITTLE_ENDIAN).apply {values.forEach {putShort(it)}}.array()
        fun mean(values:ShortArray)=values.sumOf {(it.toInt() and 65535).toLong()}.toDouble()/values.size/65535
        val zero=render(0f);val zeroBytes=bytes(zero)
        val baseline=File(targetContext.filesDir,"native-zero-ev-baseline.rgb16le")
        if(baselineOnly) {
            baseline.writeBytes(zeroBytes)
            details.put("zero_ev_mean",mean(zero)).put("width",width).put("height",height)
            return
        }
        check(baseline.isFile && baseline.readBytes().contentEquals(zeroBytes)) {"Zero-EV pixels changed after aligning print compensation"}
        val minus=render(-1f);val plus=render(1f);val returned=render(0f)
        val meanMinus=mean(minus);val meanZero=mean(zero);val meanPlus=mean(plus)
        check(meanMinus+.01<meanZero && meanZero+.01<meanPlus) {"Camera exposure did not change final print brightness: $meanMinus / $meanZero / $meanPlus"}
        check(returned.contentEquals(zero)) {"Changing camera exposure left a stale cached negative"}
        details.put("zero_ev_unchanged",true).put("mean_minus_one_ev",meanMinus).put("mean_zero_ev",meanZero).put("mean_plus_one_ev",meanPlus).put("return_to_zero_matches",true)
    }

    private fun verifyCancellationOnly(engine:FilmEngine,details:JSONObject) {
        val source=File.createTempFile("cancel-source-",".jpg",targetContext.cacheDir)
        val target=File.createTempFile("cancel-output-",".jpg",targetContext.cacheDir)
        val partial=File.createTempFile("cancel-partial-",".jpg",targetContext.cacheDir)
        val width=127;val height=95
        val bitmap=Bitmap.createBitmap(IntArray(width*height){if(it%width<width/2)Color.RED else Color.BLUE},width,height,Bitmap.Config.ARGB_8888)
        try {
            source.outputStream().use {check(bitmap.compress(Bitmap.CompressFormat.JPEG,100,it))}
            bitmap.recycle()
            val stock=engine.stocks.first {it.id=="kodak_portra_400"}
            FullResolutionPhoto(targetContext.contentResolver,Uri.fromFile(source)).use {photo->
                photo.writeJpeg(engine,stock,Adjustments(strength=0f,grain=0f,halation=0f),target,100,cancelled={false})
                val decoded=requireNotNull(BitmapFactory.decodeFile(target.absolutePath))
                try {
                    check(decoded.width==width && decoded.height==height)
                    check(Color.red(decoded.getPixel(8,8))>220 && Color.blue(decoded.getPixel(8,8))<35)
                    check(Color.blue(decoded.getPixel(width-9,8))>220 && Color.red(decoded.getPixel(width-9,8))<35)
                } finally {decoded.recycle()}
                var cancelled=false;var progress=-1
                val error=runCatching {photo.writeJpeg(engine,stock,Adjustments(),partial,100,progress={progress=it;if(it>0)cancelled=true},cancelled={cancelled})}.exceptionOrNull()
                check(error!=null && cancelled && !partial.exists()) {"Cancellation did not delete its incomplete JPEG: error=$error, cancelled=$cancelled, exists=${partial.exists()}"}
                details.put("cancellation",true).put("partial_removed",true).put("last_progress",progress)
                details.put("bitmap_jpeg_channels",true).put("width",width).put("height",height)
            }
        } finally {if(!bitmap.isRecycled)bitmap.recycle();source.delete();target.delete();partial.delete()}
    }
}
