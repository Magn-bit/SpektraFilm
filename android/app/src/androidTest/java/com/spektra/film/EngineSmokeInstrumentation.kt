package com.spektra.film

import android.app.Activity
import android.app.Instrumentation
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.ExifInterface
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.widget.SeekBar
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Small on-device checks using Android Bitmap and the actual packaged LUTs. */
class EngineSmokeInstrumentation : Instrumentation() {
    private var mode=""
    private var rawPath=""
    override fun onCreate(arguments: Bundle?) { mode=arguments?.getString("mode").orEmpty();rawPath=arguments?.getString("raw_path").orEmpty();super.onCreate(arguments);start() }
    override fun onStart() {
        val report=Bundle()
        try {
            if(mode=="native") {
                verifyNativeRelease(report)
                finish(Activity.RESULT_OK,report)
                return
            }
            verifyRawMemoryAdmission()
            verifyRawFullSizePolicy()
            verifyFilmCatalogMetadata()
            val heapBytes=256L*1024*1024
            val exportSizes=listOf(
                4032 to 3024,
                6000 to 4000,
                8064 to 6048,
                9504 to 6336,       // Sony A7CR, 61 MP
                11648 to 8736,      // Medium format, 100 MP
                12000 to 9000,
                14204 to 10652,     // Medium format, 150 MP
                16000 to 12000,
            )
            for((width,height) in exportSizes) {
                val plan=planSpectralTiles(width,height,heapBytes)
                check(plan.core>=32) { "Full-resolution export planner rejected ${width}x$height" }
                check(plan.tileWidth.toLong()*plan.tileHeight<=plan.maxTilePixels) { "Tile exceeded its planned memory budget" }
                check(plan.overlap>0 && plan.bandRows>0)
            }
            val engine=FilmEngine(targetContext)
            verifyRawPreviewCache(engine)
            check(engine.stocks.isNotEmpty() && engine.stocks.map {it.id}.toSet().size==engine.stocks.size)
            val pixels=IntArray(32*24) { i -> -0x1000000 or (((i%32)*255/31) shl 16) or (((i/32)*255/23) shl 8) or 105 }
            val image=Bitmap.createBitmap(pixels,32,24,Bitmap.Config.ARGB_8888)
            val packedInput=ByteBuffer.allocate(image.byteCount).order(ByteOrder.LITTLE_ENDIAN)
            image.copyPixelsToBuffer(packedInput)
            packedInput.flip()
            val copiedPixels=IntArray(pixels.size)
            packedInput.asIntBuffer().get(copiedPixels)
            check(pixels.contentEquals(copiedPixels)) { "ARGB bitmap byte transport must preserve packed pixel values" }
            val copiedBitmap=Bitmap.createBitmap(32,24,Bitmap.Config.ARGB_8888)
            copiedBitmap.copyPixelsFromBuffer(ByteBuffer.wrap(packedInput.array()).order(ByteOrder.LITTLE_ENDIAN))
            val restoredPixels=IntArray(pixels.size)
            copiedBitmap.getPixels(restoredPixels,0,32,0,0,32,24)
            check(pixels.contentEquals(restoredPixels)) { "ARGB bitmap byte roundtrip changed pixels" }
            copiedBitmap.recycle()
            val untouched=engine.render(image,engine.stocks.first(),Adjustments(exposure=2f,grain=1f,halation=1f,strength=0f))!!
            val restored=IntArray(pixels.size);untouched.getPixels(restored,0,32,0,0,32,24)
            check(!pixels.contentEquals(restored)) { "Zero film strength must retain base exposure adjustment" }
            untouched.recycle()
            verifyFilmPolicy(engine,image)
            check(engine.render(image,engine.stocks.first(),Adjustments()) { true }==null)
            val interaction=engine.renderInteractive(image,engine.stocks.first(),Adjustments(exposure=.25f,grain=.4f,halation=.2f))!!
            check(interaction.width==image.width && interaction.height==image.height)
            check(engine.renderInteractive(image,engine.stocks.first(),Adjustments()) {true}==null)
            interaction.recycle()
            verifyRawPixelSource(engine)
            image.recycle()
            val sourceFile=File.createTempFile("spektra-source-",".jpg",targetContext.cacheDir)
            val outputFile=File.createTempFile("spektra-output-",".jpg",targetContext.cacheDir)
            val sourcePixels=IntArray(37*23) { index ->
                val x=index%37;val y=index/37
                if(x<18 && y<11)Color.RED else if(x>=18 && y<11)Color.GREEN else if(x<18)Color.BLUE else Color.WHITE
            }
            val sourceBitmap=Bitmap.createBitmap(sourcePixels,37,23,Bitmap.Config.ARGB_8888)
            try {
                FileOutputStream(sourceFile).use { sourceBitmap.compress(Bitmap.CompressFormat.JPEG,100,it) }
            } finally { sourceBitmap.recycle() }
            ExifInterface(sourceFile.absolutePath).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_ROTATE_90.toString())
                saveAttributes()
            }
            FullResolutionPhoto(targetContext.contentResolver,Uri.fromFile(sourceFile)).use { photo ->
                check(photo.width==23 && photo.height==37) { "EXIF orientation must set full-size export dimensions" }
                photo.writeJpeg(engine,engine.stocks.first(),Adjustments(strength=0f),outputFile,100) { false }
            }
            val output=BitmapFactory.decodeFile(outputFile.absolutePath) ?: error("Scanline JPG could not be decoded")
            check(output.width==23 && output.height==37) { "JPG scanline output must retain oriented source dimensions" }
            check(Color.red(output.getPixel(18,4))>200 && Color.green(output.getPixel(18,4))<80) { "EXIF-rotated source pixels were mapped incorrectly" }
            output.recycle();sourceFile.delete();outputFile.delete()
            val activity=startActivitySync(android.content.Intent(targetContext,MainActivity::class.java).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
            runOnMainSync {
                fun sliders(view:android.view.View):List<SeekBar> = if(view is SeekBar)listOf(view) else if(view is ViewGroup)(0 until view.childCount).flatMap { sliders(view.getChildAt(it)) } else emptyList()
                val controls=sliders(activity.window.decorView)
                check(controls.isNotEmpty())
                for(slider in controls) {
                    slider.measure(android.view.View.MeasureSpec.makeMeasureSpec(600,android.view.View.MeasureSpec.EXACTLY),android.view.View.MeasureSpec.makeMeasureSpec(100,android.view.View.MeasureSpec.EXACTLY))
                    slider.layout(0,0,600,100)
                    for(position in listOf(0,slider.max)) {
                        slider.progress=position
                        val thumb=slider.thumb.bounds
                        val left=thumb.left+slider.paddingLeft-slider.thumbOffset
                        val right=thumb.right+slider.paddingLeft-slider.thumbOffset
                        check(left>=0 && right<=slider.width) { "Slider thumb clipped at endpoint" }
                    }
                }
                val labels=allText(activity.window.decorView)
                check(labels.none {it in setOf("蒙版","HSL","曲线","色轮","校准","几何","原创风格","导入预设")})
                val develop=allViews(activity.window.decorView).filterIsInstance<android.widget.TextView>().first {it.text.toString()=="显影"}
                develop.performClick()
                check(sliders(activity.window.decorView).map {it.contentDescription.toString()}.toSet()==setOf("曝光补偿","颗粒","颗粒大小","高光光晕","暗角"))
                verifyPhotoGestures(activity)
            }
            var browser:PhotoBrowserDialog?=null
            var edited=-1
            var selection=setOf<Int>()
            runOnMainSync {
                browser=PhotoBrowserDialog(activity,listOf("第一张.jpg","Screenshot_2026_11_05_a_very_long_filename.jpg","第三张.jpg"),0,setOf(0),
                    loadThumbnail={ Bitmap.createBitmap(16,16,Bitmap.Config.ARGB_8888) },
                    onEdit={ edited=it },onSelection={ selection=it },onRemove={ error("unexpected removal") }).also { it.show() }
            }
            waitForIdleSync()
            runOnMainSync {
                fun list(view:android.view.View):android.widget.ListView? = if(view is android.widget.ListView)view else if(view is ViewGroup)(0 until view.childCount).firstNotNullOfOrNull { list(view.getChildAt(it)) } else null
                val photos=requireNotNull(list(requireNotNull(browser).window!!.decorView))
                val row=requireNotNull(photos.getChildAt(1))
                row.performClick()
                check(edited==1 && selection==setOf(1)) { "Tapping the second photo must directly edit it without retaining unrelated batch choices" }
                check(!requireNotNull(browser).isShowing)
                activity.finish()
            }
            report.putString("stream","OK: film-only policy and migration, spectral model, full RAW pixels, source-size export, zoom/comparison and photo selection\n")
            finish(Activity.RESULT_OK,report)
        } catch(error:Throwable) {
            report.putString("stream",error.stackTraceToString())
            finish(Activity.RESULT_CANCELED,report)
        }
    }


    /** Changed native path only: avoid rerunning all historical editor tests. */
    private fun verifyNativeRelease(report:Bundle) {
        val engine=FilmEngine(targetContext)
        try {
            val device=engine.nativeDevice();check(device.isNotBlank())
            check(engine.stocks.size==27)
            val width=127;val height=95
            val pixels=FloatArray(width*height*3){i->((i*37+11)%65536)/65535f}
            val stock=engine.stocks.first {it.id=="kodak_portra_400"}
            val noFilm=Adjustments(strength=0f,grain=0f,halation=0f)
            val restored=requireNotNull(engine.render16(pixels,width,height,stock,noFilm))
            for(i in pixels.indices)check((restored[i].toInt() and 65535)==(pixels[i]*65535+.5f).toInt()) {"Native path lost RGB16 source detail"}
            val darkroom=Adjustments(paper="kodak_2383",filmFormatMm=70f,printExposure=.5f,printY=15f,printM=-7f,glare=2f)
            check(PhotoEditsStore.adjustmentsFromJson(PhotoEditsStore.adjustmentsToJson(darkroom))==darkroom)
            for(id in listOf("kodak_portra_400","fujifilm_provia_100f","kodak_tri_x_400","ilford_hp5_plus_400")) {
                val material=engine.stocks.first {it.id==id}
                val output=requireNotNull(engine.render16(pixels,width,height,material,Adjustments(filmEnabled=true,grain=0f,halation=0f)))
                check(output.size==pixels.size && output.any {(it.toInt() and 65535)>1024}) {"Native $id output is empty/black"}
            }
            val first=requireNotNull(engine.render16(pixels,width,height,stock,Adjustments(filmEnabled=true,grain=0f,halation=0f)))
            val reprint=requireNotNull(engine.render16(pixels,width,height,stock,Adjustments(filmEnabled=true,grain=0f,halation=0f,printExposure=1f)))
            check(!first.contentEquals(reprint)) {"Print exposure did not update the cached negative"}
            verifyRawPreviewCache(engine)
            val rgb16=File.createTempFile("native-rgb16-",".raw16",targetContext.cacheDir)
            val tiff=File.createTempFile("native-export-",".tif",targetContext.cacheDir)
            val inputBytes=ByteBuffer.allocate(width*height*6).order(ByteOrder.LITTLE_ENDIAN)
            restored.forEach {inputBytes.putShort(it)};rgb16.writeBytes(inputBytes.array())
            try {
                FullResolutionPhoto(targetContext.contentResolver,Uri.fromFile(rgb16),Rgb16PixelSource(rgb16,width,height)).use {photo->
                    val progress=mutableListOf<Int>()
                    tiff.outputStream().use {target->photo.writeTiff(engine,stock,noFilm,target,targetContext.assets.open("color/sRGB.icc").use {it.readBytes()},progress={progress.add(it)},cancelled={false})}
                    check(progress.last()==100 && progress.zipWithNext().all {it.first<=it.second})
                }
                val encoded=tiff.readBytes();val header=ByteBuffer.wrap(encoded).order(ByteOrder.LITTLE_ENDIAN)
                val count=header.getShort(8).toInt() and 65535;val tags=mutableMapOf<Int,Int>()
                for(i in 0 until count){val at=10+i*12;tags[header.getShort(at).toInt() and 65535]=header.getInt(at+8)}
                check(tags[256]==width && tags[257]==height && tags[259]==8)
                val bits=requireNotNull(tags[258]);check(header.getShort(bits).toInt()==16)
                val offset=requireNotNull(tags[273]);val size=requireNotNull(tags[279])
                val unpacked=java.util.zip.InflaterInputStream(java.io.ByteArrayInputStream(encoded,offset,size)).use {it.readBytes()}
                check(unpacked.contentEquals(inputBytes.array())) {"TIFF16 source values changed or were reduced to RGB8"}
            } finally {rgb16.delete();tiff.delete()}
            val details=org.json.JSONObject().put("device",device).put("native_rgb16",true).put("tiff16",true).put("materials",27)
            if(rawPath.isNotBlank()) {
                val raw=File(rawPath);check(raw.isFile)
                val uri=Uri.fromFile(raw)
                val output=File(targetContext.cacheDir,"native-full-export-test.jpg")
                val start=android.os.SystemClock.elapsedRealtime()
                var decoded=0L
                try {
                    RawPhotoCache(targetContext).use {cache->
                        FullResolutionPhoto.open(targetContext.contentResolver,uri,raw.name,cache).use {photo->
                            decoded=android.os.SystemClock.elapsedRealtime()-start
                            check(photo.width>=9000 && photo.height>=6000)
                            var last=0;var updates=0
                            photo.writeJpeg(engine,stock,Adjustments(),output,100,progress={value->check(value>=last);last=value;updates++},cancelled={false})
                            check(last==100 && updates>10)
                            val bounds=BitmapFactory.Options().apply {inJustDecodeBounds=true}
                            BitmapFactory.decodeFile(output.absolutePath,bounds)
                            check(bounds.outWidth==photo.width && bounds.outHeight==photo.height)
                            details.put("width",photo.width).put("height",photo.height).put("progress_updates",updates)
                            var canceled=false
                            val partial=File(targetContext.cacheDir,"native-cancel-export-test.jpg")
                            try {
                                val failed=runCatching {photo.writeJpeg(engine,stock,Adjustments(),partial,100,progress={if(it>0)canceled=true},cancelled={canceled})}.isFailure
                                check(failed && canceled && !partial.exists()) {"Canceled JPG must clean its incomplete output"}
                                details.put("cancellation",true)
                            } finally {partial.delete()}
                        }
                    }
                    details.put("raw_decode_ms",decoded).put("full_export_total_ms",android.os.SystemClock.elapsedRealtime()-start).put("jpg_bytes",output.length())
                    val preview=BitmapFactory.decodeFile(output.absolutePath,BitmapFactory.Options().apply {inSampleSize=8}) ?: error("Native JPG cannot be decoded")
                    try {check(preview.width>1000);val samples=IntArray(preview.width*preview.height);preview.getPixels(samples,0,preview.width,0,0,preview.width,preview.height);check(samples.count {it and 0xffffff>0x101010}>samples.size/10)} finally {preview.recycle()}
                } finally {output.delete()}
            }
            File(targetContext.filesDir,"native-test-report.json").writeText(details.toString(2))
            report.putString("stream","OK native C++/Vulkan: $device; 27 materials; RGB16 detail, black/white/positive, reprint, RAW proxy isolation, full-size TIFF16 Deflate and monotonic progress\n")
        } finally {engine.close()}
    }

    private fun allViews(view:android.view.View):List<android.view.View> =
        listOf(view)+(if(view is ViewGroup)(0 until view.childCount).flatMap {allViews(view.getChildAt(it))} else emptyList())
    private fun allText(view:android.view.View)=allViews(view).filterIsInstance<android.widget.TextView>().map {it.text.toString()}

    private fun verifyFilmCatalogMetadata() {
        val legacy=FilmStock.fromJson(org.json.JSONObject().put("id","kodak_portra_400").put("name","Kodak Portra 400").put("file","portra.bin"))
        check(legacy.makerLabel=="Kodak" && legacy.shortName=="Portra 400" && !legacy.isExtendedModel && legacy.type=="negative")
        val other=FilmStock.fromJson(org.json.JSONObject().put("id","independent_100").put("name","Independent 100").put("file","independent.bin"))
        check(other.makerLabel=="胶片档案") {"Unknown legacy brands must not be labelled Kodak"}
        val extended=FilmStock.fromJson(org.json.JSONObject().put("id","agfa_vista_100").put("name","Agfa Vista 100").put("file","vista.bin")
            .put("maker","Agfa").put("type","negative").put("category","negative").put("description","Estimated spectral model from published data").put("model_status","extended_estimated"))
        check(extended.makerLabel=="Agfa" && extended.shortName=="Vista 100" && extended.isExtendedModel && extended.sourceLabel=="扩展光谱 · 估计模型")
        check(extended.description.isNotEmpty() && extended.categoryLabel=="彩色负片")
        val slide=extended.copy(id="fujifilm_velvia_50",name="Fujifilm Velvia 50",maker="Fujifilm",type="positive",category="slide")
        check(slide.categoryLabel=="反转片" && slide.sourceLabel==extended.sourceLabel)
    }

    private fun verifyFilmPolicy(engine:FilmEngine,image:Bitmap) {
        check(!Adjustments().filmEnabled) {"A new photograph must open naturally before optional film development"}
        val edited=Adjustments(exposure=.5f,temperature=4200f,tint=12f,contrast=20f,grain=0f,halation=0f,
            masks=listOf(MaskLayer(id="radial",kind="radial",exposure=.5f)),geometry=Geometry(rotation=10f,crop=CropBounds(.1f,.1f,.9f,.9f)))
        check(edited.filmOnly()==edited && edited.filmOnly().filmOnly()==edited)
        val json=PhotoEditsStore.adjustmentsToJson(edited)
        check(PhotoEditsStore.adjustmentsFromJson(json)==edited) {"Every editing group must survive the current sidecar"}
        val legacy=PhotoEditsStore.adjustmentsFromJson(json,2)
        check(legacy.filmEnabled && legacy.temperature==6500f && legacy.masks.isEmpty() && legacy.geometry.isNeutral())
        val uri=Uri.parse("content://editor-state-test/${System.nanoTime()}");val store=PhotoEditsStore(targetContext)
        try {store.save(uri,3,edited);check(store.load(uri)==PhotoEditsStore.Saved(3,edited))}finally {store.remove(uri)}
        check(Adjustments(exposure=Float.NaN,grain=Float.POSITIVE_INFINITY,grainType="unknown").filmOnly()==Adjustments())
        val untouched=requireNotNull(engine.render(image,engine.stocks.first(),Adjustments()))
        try {
            val a=IntArray(image.width*image.height);val b=IntArray(a.size)
            image.getPixels(a,0,image.width,0,0,image.width,image.height);untouched.getPixels(b,0,image.width,0,0,image.width,image.height)
            check(a.contentEquals(b)) {"No-film neutral preview must preserve source values"}
        }finally {untouched.recycle()}
    }

    private fun verifyPhotoGestures(activity:Activity) {
        val original=Bitmap.createBitmap(64,48,Bitmap.Config.ARGB_8888).apply {eraseColor(Color.BLACK)}
        val processed=Bitmap.createBitmap(64,48,Bitmap.Config.ARGB_8888).apply {eraseColor(Color.WHITE)}
        val canvas=PhotoCanvas(activity,android.graphics.Typeface.DEFAULT).apply {
            this.original=original;this.processed=processed
            measure(android.view.View.MeasureSpec.makeMeasureSpec(800,android.view.View.MeasureSpec.EXACTLY),android.view.View.MeasureSpec.makeMeasureSpec(600,android.view.View.MeasureSpec.EXACTLY));layout(0,0,800,600)
        }
        val start=android.os.SystemClock.uptimeMillis()
        fun touch(action:Int,x:Float,y:Float,offset:Long) {
            val event=android.view.MotionEvent.obtain(start,start+offset,action,x,y,0)
            try {canvas.onTouchEvent(event)} finally {event.recycle()}
        }
        val before=canvas.normalizedPoint(500f,300f)!!
        touch(android.view.MotionEvent.ACTION_DOWN,400f,300f,0);touch(android.view.MotionEvent.ACTION_UP,400f,300f,40)
        touch(android.view.MotionEvent.ACTION_DOWN,400f,300f,100);touch(android.view.MotionEvent.ACTION_UP,400f,300f,140)
        val zoomed=canvas.normalizedPoint(500f,300f)!!
        check(zoomed.u<before.u && zoomed.u>.5f) {"Double tap must zoom the photograph around its focus"}
        canvas.resetZoom();check(canvas.normalizedPoint(500f,300f)==before)
        val shot=Bitmap.createBitmap(800,600,Bitmap.Config.ARGB_8888)
        try {
            canvas.comparing=true;canvas.draw(android.graphics.Canvas(shot));check(shot.getPixel(470,200)==Color.WHITE)
            touch(android.view.MotionEvent.ACTION_DOWN,400f,300f,1000);touch(android.view.MotionEvent.ACTION_MOVE,600f,300f,1040);touch(android.view.MotionEvent.ACTION_UP,600f,300f,1080)
            canvas.draw(android.graphics.Canvas(shot));check(shot.getPixel(470,200)==Color.BLACK) {"Dragging the comparison divider must reveal the original"}
        } finally {shot.recycle();original.recycle();processed.recycle()}
    }

    private fun verifyRawFullSizePolicy() {
        // The real Pixel 4 XL fixture is 3700 × 2774 after orientation, before DefaultCrop.
        val width=3700;val height=2774;val bytes=61_582_800L
        check(rgb16Bytes(width,height)==bytes)
        requireFullRawOutput(width,height,intArrayOf(width,height),bytes)
        requireFullRawOutput(height,width,intArrayOf(height,width),bytes)
        val uri="content://photos/same-original"
        check(rawCacheKey(uri,true)!=rawCacheKey(uri,false))
        requireRawPreviewOutput(width,height,intArrayOf(1850,1387),rgb16Bytes(1850,1387))
        check(runCatching {requireRawPreviewOutput(width,height,intArrayOf(width+1,height),rgb16Bytes(width+1,height))}.isFailure)
        val rejected=listOf(
            intArrayOf(1850,1387) to rgb16Bytes(1850,1387), // Self-consistent half-size decode.
            intArrayOf(1024,768) to rgb16Bytes(1024,768),   // Embedded preview.
            intArrayOf(3680,2760) to rgb16Bytes(3680,2760), // Metadata crop must not reduce the image.
            intArrayOf(height,width) to bytes,             // Equal byte count, wrong orientation.
            intArrayOf(width,height) to (bytes-6),
            intArrayOf(width,height) to (bytes+6),
            intArrayOf(0,height) to 0L,
            intArrayOf(width) to bytes,
            intArrayOf() to bytes,
        )
        rejected.forEach { (size,count) ->
            val error=runCatching {requireFullRawOutput(width,height,size,count)}.exceptionOrNull()
            check(error is IllegalArgumentException && error.message.orEmpty().contains("拒绝缩小")) {
                "A reduced, cropped, misoriented or incomplete RAW output must be rejected"
            }
        }
    }

    /** Actual bundled decoder + cache + full export: a proxy must never become the export source. */
    private fun verifyRawPreviewCache(engine:FilmEngine) {
        val original=File.createTempFile("spektra-preview-policy-",".dng",targetContext.cacheDir)
        val jpeg=File.createTempFile("spektra-full-policy-",".jpg",targetContext.cacheDir)
        context.assets.open("synthetic-neutral.dng").use {input -> original.outputStream().use {input.copyTo(it)} }
        val originalBytes=original.readBytes();val uri=Uri.fromFile(original)
        try {
            RawPhotoCache(targetContext).use {cache ->
                val preview=cache.preview(uri,edge={_,_ -> 32})
                try {
                    check(preview.sourceWidth==64 && preview.sourceHeight==96)
                    check(preview.bitmap.width==21 && preview.bitmap.height==32)
                } finally {preview.bitmap.recycle()}
                val proxy=requireNotNull(cache.cachedPreview(uri,256))
                try {check(proxy.width==32 && proxy.height==48)} finally {proxy.recycle()}
                cache.acquire(uri).use {pixels -> check(pixels.sourceWidth==64 && pixels.sourceHeight==96)}
                FullResolutionPhoto.open(targetContext.contentResolver,uri,original.name,cache).use {photo ->
                    check(photo.width==64 && photo.height==96)
                    photo.writeJpeg(engine,engine.stocks.first(),Adjustments(strength=0f),jpeg,100,cancelled={false})
                }
                val output=requireNotNull(BitmapFactory.decodeFile(jpeg.absolutePath))
                try {check(output.width==64 && output.height==96)} finally {output.recycle()}
                val full=requireNotNull(cache.cachedPreview(uri,256))
                try {check(full.width==64 && full.height==96)} finally {full.recycle()}
                cache.discard(uri);check(cache.cachedPreview(uri,256)==null)
                check(original.readBytes().contentEquals(originalBytes))
            }
        } finally {original.delete();jpeg.delete()}
    }

    private fun verifyRawPixelSource(engine:FilmEngine) {
        val width=37;val height=23
        val file=File.createTempFile("spektra-rgb16-test-",".rgb16le",targetContext.cacheDir)
        val jpeg=File.createTempFile("spektra-rgb16-export-",".jpg",targetContext.cacheDir)
        val expected=IntArray(width*height)
        val bytes=ByteBuffer.allocate(width*height*6).order(ByteOrder.LITTLE_ENDIAN)
        for(y in 0 until height)for(x in 0 until width) {
            val r=(x*65535/(width-1));val g=(y*65535/(height-1));val b=28033
            bytes.putShort(r.toShort()).putShort(g.toShort()).putShort(b.toShort())
            expected[y*width+x]=Color.rgb((r+128)/257,(g+128)/257,(b+128)/257)
        }
        file.writeBytes(bytes.array())
        try {
            Rgb16PixelSource(file,width,height).use {pixels ->
                val region=pixels.decodeRegion(-3,-2,width+6,height+4)
                try {
                    for(y in 0 until region.height)for(x in 0 until region.width) {
                        val sx=reflectPixel(x.toLong()-3,width);val sy=reflectPixel(y.toLong()-2,height)
                        check(region.getPixel(x,y)==expected[sy*width+sx]) {"RGB16LE region endian, reflection or source coordinates changed"}
                    }
                } finally {region.recycle()}
                val preview=pixels.preview(12)
                try {check(preview.width==12 && preview.height==7) {"RAW preview must be sampled from full oriented pixels"}} finally {preview.recycle()}
                check(runCatching {pixels.preview(12) {true}}.exceptionOrNull() is java.util.concurrent.CancellationException)
            }
            var releases=0
            FullResolutionPhoto(targetContext.contentResolver,Uri.parse("content://raw-not-a-bitmap/source"),Rgb16PixelSource(file,width,height) {releases++}).use {photo ->
                check(photo.sourceWidth==width && photo.sourceHeight==height)
                val dirty=Adjustments(strength=0f,grain=0f,halation=0f,filmEnabled=false)
                val progress=mutableListOf<Int>()
                photo.writeJpeg(engine,engine.stocks.first(),dirty,jpeg,100,progress={progress.add(it)}) {false}
                check(progress.isNotEmpty() && progress.last()==100 && progress.zipWithNext().all {it.first<=it.second})
                val profile=targetContext.assets.open("color/sRGB.icc").use {it.readBytes()}
                val tiff=java.io.ByteArrayOutputStream();val cleanTiff=java.io.ByteArrayOutputStream()
                photo.writeTiff(engine,engine.stocks.first(),dirty,tiff,profile=profile) {false}
                photo.writeTiff(engine,engine.stocks.first(),dirty.filmOnly(),cleanTiff,profile=profile) {false}
                check(tiff.size()>width*height && tiff.toByteArray().contentEquals(cleanTiff.toByteArray())) {
                    "TIFF must use the same complete spectral film policy and source dimensions"
                }
            }
            check(releases==1) {"RAW source lease must close exactly once after export"}
            val output=BitmapFactory.decodeFile(jpeg.absolutePath)!!
            try {
                check(output.width==width && output.height==height) {"RAW export must retain full source dimensions"}
                val actual=output.getPixel(18,11);val want=expected[11*width+18]
                check(kotlin.math.abs(Color.red(actual)-Color.red(want))<8 && kotlin.math.abs(Color.green(actual)-Color.green(want))<8)
            } finally {output.recycle()}
            file.appendBytes(byteArrayOf(0))
            check(runCatching {Rgb16PixelSource(file,width,height)}.isFailure) {"Truncated or extra RAW cache bytes must be rejected"}
        } finally {file.delete();jpeg.delete()}
        val original=File.createTempFile("spektra-invalid-raw-",".dng",targetContext.cacheDir)
        val originalBytes=ByteArray(128) {it.toByte()};original.writeBytes(originalBytes)
        try {
            RawPhotoCache(targetContext).use {cache ->
                val uri=Uri.fromFile(original)
                check(runCatching {cache.acquire(uri,cancelled={true})}.exceptionOrNull() is java.util.concurrent.CancellationException)
                check(RawImageDecoder.nativeVersion().isNotBlank()) {"Bundled native RAW library must load locally"}
                check(runCatching {cache.acquire(uri)}.isFailure) {"Invalid RAW bytes must fail rather than use a thumbnail"}
                check(original.readBytes().contentEquals(originalBytes)) {"RAW decoding must never rewrite the SAF source"}
            }
        } finally {original.delete()}
    }

}
