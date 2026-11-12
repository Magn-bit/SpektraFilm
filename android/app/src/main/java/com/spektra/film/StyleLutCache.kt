package com.spektra.film

import android.content.Context
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.security.MessageDigest

/** Only catalog-listed assets may become renderer paths; persisted edits contain IDs only. */
internal class StyleLutCache(private val context:Context) {
    private data class Entry(val asset:String,val size:Int,val sha256:String) {
        val bytes get()=size.toLong()*size*size*3
    }
    private val manifest:Map<String,Entry> by lazy {
        val document=JSONObject(context.assets.open("styles/luts/manifest.json").bufferedReader().use {it.readText()})
        val array=document.getJSONArray("luts")
        val entries=linkedMapOf<String,Entry>()
        for(index in 0 until array.length()) {
            val item=array.getJSONObject(index);val id=item.getString("id")
            val filename=item.getString("file").replace('\\','/')
            val asset=if(filename.startsWith("styles/luts/"))filename else "styles/luts/$filename"
            val size=item.getInt("size");val hash=item.getString("sha256").lowercase(java.util.Locale.ROOT)
            require(id.isNotBlank() && !entries.containsKey(id)) {"风格 CLUT 目录存在重复或空标识"}
            require(size in 2..256 && hash.matches(Regex("[0-9a-f]{64}"))) {"风格 CLUT 资源描述不完整"}
            require(asset.startsWith("styles/luts/") && asset.split('/').none {it.isBlank() || it=="." || it==".."} && !asset.contains(':')) {"风格 CLUT 资源路径不合法"}
            entries[id]=Entry(asset,size,hash)
        }
        entries
    }
    private val directory=File(context.cacheDir,"style-luts")
    private val verified=mutableMapOf<String,File>()
    @Synchronized fun requireKnown(id:String) {
        require(id.isEmpty() || manifest.containsKey(id)) {"未找到风格 CLUT「$id」，请检查完整资源安装"}
    }
    @Synchronized fun resolve(id:String):String {
        if(id.isEmpty())return ""
        val entry=manifest[id] ?: throw IllegalArgumentException("未找到风格 CLUT「$id」，请检查完整资源安装")
        verified[id]?.takeIf {it.isFile && it.length()==entry.bytes}?.let {return it.absolutePath}
        require(directory.isDirectory || directory.mkdirs()) {"无法创建风格 CLUT 缓存"}
        val output=AtomicFile(File(directory,"${entry.sha256}.rgb8"))
        val base=output.baseFile
        if(base.isFile && base.length()==entry.bytes) {
            val existing=base.inputStream().use {digest(it)}
            if(existing.second==entry.bytes && existing.first==entry.sha256) {verified[id]=base;return base.absolutePath}
        }
        val stream=output.startWrite()
        try {
            val hash=MessageDigest.getInstance("SHA-256");var count=0L
            context.assets.open(entry.asset).use {input ->
                val buffer=ByteArray(64*1024)
                while(true) {
                    val n=input.read(buffer);if(n<0)break
                    count+=n;require(count<=entry.bytes) {"风格 CLUT 文件大小与目录不一致"}
                    hash.update(buffer,0,n);stream.write(buffer,0,n)
                }
            }
            require(count==entry.bytes && hex(hash.digest())==entry.sha256) {"风格 CLUT 校验失败，请重新安装完整版本"}
            output.finishWrite(stream);verified[id]=base;return base.absolutePath
        } catch(error:Exception) {output.failWrite(stream);throw error}
    }
    private fun digest(input:InputStream):Pair<String,Long> {
        val hash=MessageDigest.getInstance("SHA-256");val buffer=ByteArray(64*1024);var count=0L
        while(true) {val n=input.read(buffer);if(n<0)break;hash.update(buffer,0,n);count+=n}
        return hex(hash.digest()) to count
    }
    private fun hex(bytes:ByteArray)=bytes.joinToString("") {"%02x".format(it)}
}
