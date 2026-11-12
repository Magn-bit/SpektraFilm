package com.spektra.film

import org.json.JSONObject
import kotlin.math.abs

/** One host integration check for the Android state/geometry contract, without image renders. */
fun main(args:Array<String>) {
    check(!Adjustments().filmEnabled)
    val a=Adjustments(exposure=.333f,temperature=4200f,tint=-12f,contrast=23f,saturation=-9f,vibrance=19f,
        texture=11f,clarity=7f,dehaze=-5f,shadowTint=9f,sharpening=27f,noiseLuminance=33f,noiseColor=41f,highlights=-27f,shadows=31f,blackPoint=5f,whitePoint=96f,gamma=1.2f,
        redHue=17f,redSaturation=5f,greenHue=-8f,blueSaturation=11f,filmEnabled=false,
        masks=listOf(MaskLayer(id="radial",kind="radial",exposure=.7f,center=MaskPoint(.2f,.6f))),
        curves=CurveSet(luma=listOf(CurvePoint(0f,0f),CurvePoint(.4f,.6f),CurvePoint(1f,1f))),
        hsl=HslSettings(orange=HslBand(12f,-15f,7f)),grading=ColorGrading(midtones=TonalGrade(37f,13f,8f)),
        sceneLatitudeParams="{\"scene_latitude_active\":true,\"scene_latitude_norm\":\"power\",\"scene_latitude_highlight_knee\":2,\"scene_latitude_highlight_room\":3}",neutralM=64f,
        geometry=Geometry(rotation=8f,crop=CropBounds(.1f,.2f,.9f,.8f),quarterTurns=1))
    val canonical=a.filmOnly()
    check(canonical.filmOnly()==canonical)
    check(decodeAdjustments(a.toEditorJson())==canonical && canonical.sceneLatitudeParams.isNotEmpty())
    val legacy=decodeAdjustments(a.toEditorJson().put("crop",a.geometry.crop.toJson()),2)
    check(legacy.filmEnabled && legacy.temperature==6500f && legacy.masks.isEmpty() && legacy.curves.isIdentity())
    check(legacy.geometry==Geometry(crop=a.geometry.crop) && legacy.exposure==a.exposure)
    check(Adjustments(exposure=Float.NaN,grain=Float.POSITIVE_INFINITY,grainType="unknown").filmOnly()==Adjustments())
    val native=a.nativeEditorSettings()
    check(native.getDouble("calibration_red_hue")==17.0 && native.getJSONArray("masks").getJSONObject(0).getString("kind")=="radial")
    check(native.getDouble("sharpening")==27.0 && native.getDouble("noise_luminance")==33.0 && native.getDouble("noise_color")==41.0)
    check(!Adjustments().hasCaptureEdits() && !Adjustments().hasPostEdits() && a.hasCaptureEdits() && a.hasPostEdits())
    val h=EditHistory(4);val original=EditorSnapshot(1,Adjustments());val edited=EditorSnapshot(2,a)
    h.remember(original);check(h.undo(edited)==original && !h.canUndo && h.canRedo)
    check(h.redo(original)==edited && h.canUndo && !h.canRedo)
    val transfer=EditClipboard(edited,EditCategory.entries.filter {it.selectedByDefault}.toSet())
    val target=EditorSnapshot(0,Adjustments(geometry=Geometry(rotation=-13f),masks=listOf(MaskLayer(id="own"))))
    val synced=transfer.applyTo(target)
    check(synced.stock==edited.stock && synced.values.temperature==a.temperature && synced.values.curves==a.curves)
    check(synced.values.geometry==target.values.geometry && synced.values.masks==target.values.masks)
    val composition=EditClipboard(edited,setOf(EditCategory.GEOMETRY)).applyTo(target)
    check(composition.stock==target.stock && composition.values.geometry==a.geometry && composition.values.temperature==target.values.temperature)
    check(OutputRecipe.fromJson(OutputRecipe.DEFAULTS[3].toJson())==OutputRecipe.DEFAULTS[3])
    check(OutputRecipe().filename("DSC0001.ARW","Kodak 5219",7)=="DSC0001_Kodak 5219.jpg")
    check(runCatching {OutputRecipe(format="dng",bitDepth=16,colorSpace="Display P3").validated()}.isFailure)
    check(runCatching {OutputRecipe(naming="{name.__class__}").validated()}.isFailure)
    val width=9504;val height=6336
    val flip=PhotoGeometry.matrix(width,height,Geometry(flipHorizontal=true))
    val flipped=PhotoGeometry.point(flip,0.0,0.0)
    check(abs(flipped.first-(width-1))<1e-6 && abs(flipped.second)<1e-6)
    for(turn in 0..3) {
        val g=Geometry(quarterTurns=turn);val frame=PhotoGeometry.frameSize(width,height,g)
        check(frame==if(turn%2==1)height to width else width to height)
        val m=PhotoGeometry.matrix(width,height,g);val inv=PhotoGeometry.inverse(m)
        for((x,y) in listOf(0.0 to 0.0,3200.0 to 1800.0,(width-1.0) to (height-1.0))) {
            val q=PhotoGeometry.point(m,x,y);val restored=PhotoGeometry.point(inv,q.first,q.second)
            check(q.first==q.first.toInt().toDouble() && q.second==q.second.toInt().toDouble())
            check(abs(restored.first-x)<1e-6 && abs(restored.second-y)<1e-6)
            if(turn==1)check(q.first==height-1-y && q.second==x)
        }
    }
    val transformations=listOf(Geometry(rotation=17f),Geometry(horizontal=35f,vertical=-20f),Geometry(rotation=-8f,aspect=22f,flipVertical=true),a.geometry)
    for(g in transformations) {
        val forward=PhotoGeometry.matrix(width,height,g);val inverse=PhotoGeometry.inverse(forward)
        for((x,y) in listOf(0.0 to 0.0,3200.25 to 1800.75,(width-1.0) to (height-1.0))) {
            val q=PhotoGeometry.point(forward,x,y);val restored=PhotoGeometry.point(inverse,q.first,q.second)
            check(abs(restored.first-x)<1e-6 && abs(restored.second-y)<1e-6)
        }
        val (fw,fh)=PhotoGeometry.frameSize(width,height,g)
        for((x,y) in listOf(0.0 to 0.0,(fw-1.0) to 0.0,0.0 to (fh-1.0),(fw-1.0) to (fh-1.0))) {
            val q=PhotoGeometry.point(inverse,x,y)
            check(q.first>=-1e-5 && q.first<=width-1+1e-5 && q.second>=-1e-5 && q.second<=height-1+1e-5)
        }
    }
    println("OK: editor state/migration, native schema, classified sync with composition opt-in, per-photo undo, portable output recipes, A7CR geometry")
}
