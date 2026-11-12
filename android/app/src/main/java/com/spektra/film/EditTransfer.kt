package com.spektra.film

/** Explicit transfer groups; spatial edits are opt-in to avoid moving another photo's composition. */
internal enum class EditCategory(val title:String,val selectedByDefault:Boolean=true) {
    FILM("胶片与颗粒"), PAPER("相纸与印相"), EXPOSURE("曝光"), WHITE_BALANCE("白平衡"),
    BASIC("基础调整"), COLOR("色彩、校准与曲线"), MASKS("蒙版",false), GEOMETRY("裁切与几何",false);
}

internal data class EditClipboard(val source:EditorSnapshot,val categories:Set<EditCategory>) {
    fun applyTo(target:EditorSnapshot):EditorSnapshot {
        val source=source.values;var a=target.values
        if(EditCategory.FILM in categories)a=a.copy(filmEnabled=source.filmEnabled,strength=source.strength,
            grain=source.grain,grainType=source.grainType,grainSize=source.grainSize,halation=source.halation,
            halationHeadroom=source.halationHeadroom,filmFormatMm=source.filmFormatMm)
        if(EditCategory.PAPER in categories)a=a.copy(paper=source.paper,printExposure=source.printExposure,
            printY=source.printY,printM=source.printM,glare=source.glare,neutralC=source.neutralC,neutralM=source.neutralM,neutralY=source.neutralY)
        if(EditCategory.EXPOSURE in categories)a=a.copy(exposure=source.exposure,sceneLatitude=source.sceneLatitude,sceneLatitudeParams=source.sceneLatitudeParams,meterMethod=source.meterMethod)
        if(EditCategory.WHITE_BALANCE in categories)a=a.copy(temperature=source.temperature,tint=source.tint,warmth=source.warmth)
        if(EditCategory.BASIC in categories)a=a.copy(contrast=source.contrast,saturation=source.saturation,
            vibrance=source.vibrance,highlights=source.highlights,shadows=source.shadows,whites=source.whites,blacks=source.blacks,levels=source.levels,blackPoint=source.blackPoint,
            whitePoint=source.whitePoint,gamma=source.gamma,texture=source.texture,clarity=source.clarity,dehaze=source.dehaze,vignette=source.vignette,
            sharpening=source.sharpening,noiseLuminance=source.noiseLuminance,noiseColor=source.noiseColor)
        if(EditCategory.COLOR in categories)a=a.copy(shadowTint=source.shadowTint,redHue=source.redHue,redSaturation=source.redSaturation,
            greenHue=source.greenHue,greenSaturation=source.greenSaturation,blueHue=source.blueHue,blueSaturation=source.blueSaturation,
            curves=source.curves,grading=source.grading,hsl=source.hsl,lookLut=source.lookLut,lookStrength=source.lookStrength)
        if(EditCategory.MASKS in categories)a=a.copy(masks=source.masks)
        if(EditCategory.GEOMETRY in categories)a=a.copy(geometry=source.geometry)
        return EditorSnapshot(if(EditCategory.FILM in categories)this.source.stock else target.stock,a.filmOnly())
    }
}
