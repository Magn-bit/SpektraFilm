package com.spektra.film

enum class ExportPreset(val title:String,val detail:String,val mime:String,val extension:String,val quality:Int,val folder:String) {
    JPG_HIGH("高品质 JPG","原尺寸 · 质量 100 · sRGB","image/jpeg","jpg",100,"高品质 JPG"),
    JPG_SHARE("分享 JPG","原尺寸 · 质量 85 · 适合微信等平台","image/jpeg","jpg",85,"分享 JPG"),
    TIFF("无损 TIFF","原尺寸 · 无损 Deflate · 16 bit / 通道 · sRGB","image/tiff","tif",100,"无损 TIFF"),
    RAW("RAW 原片","保留相机原始文件 · 不包含胶片显影效果","application/octet-stream","",100,"RAW 原片");

    companion object {
        // Kept in sync with shared/photo_formats.py; the decoder validates camera/compression support.
        private val rawExtensions=setOf("arw","cr2","cr3","crw","nef","nrw","dng","raf","raw","rw2","rwl","orf","pef","srw","sr2","srf","3fr","fff","iiq","mos","mef","mrw","erf","dcr","kdc","bay")
        fun rawExtension(name:String)=name.substringAfterLast('.',"").lowercase(java.util.Locale.ROOT).takeIf { it in rawExtensions }
    }
}

