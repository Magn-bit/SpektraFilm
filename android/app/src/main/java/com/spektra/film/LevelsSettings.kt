package com.spektra.film

import org.json.JSONObject

data class LevelChannel(val black:Float=0f,val white:Float=1f,val gamma:Float=1f,val outputBlack:Float=0f,val outputWhite:Float=1f) {
    fun canonical():LevelChannel {
        fun bound(v:Float,d:Float,lo:Float,hi:Float)=if(v.isFinite())v.coerceIn(lo,hi) else d
        val b=bound(black,0f,0f,.999f);val w=bound(white,1f,b+.001f,1f)
        val ob=bound(outputBlack,0f,0f,1f);val ow=bound(outputWhite,1f,ob,1f)
        return LevelChannel(b,w,bound(gamma,1f,.1f,10f),ob,ow)
    }
    fun toJson()=canonical().let {a->JSONObject().put("black",a.black).put("white",a.white).put("gamma",a.gamma).put("output_black",a.outputBlack).put("output_white",a.outputWhite)}
    companion object {fun fromJson(j:JSONObject)=LevelChannel(j.number("black",0f,0f,1f),j.number("white",1f,0f,1f),j.number("gamma",1f,.1f,10f),j.number("output_black",0f,0f,1f),j.number("output_white",1f,0f,1f)).canonical()}
}
data class LevelsSettings(val master:LevelChannel=LevelChannel(),val red:LevelChannel=LevelChannel(),val green:LevelChannel=LevelChannel(),val blue:LevelChannel=LevelChannel()) {
    fun channel(index:Int)=when(index){1->red;2->green;3->blue;else->master}
    fun withChannel(index:Int,c:LevelChannel)=when(index){1->copy(red=c);2->copy(green=c);3->copy(blue=c);else->copy(master=c)}
    fun active()=this!=LevelsSettings()
    fun toJson()=JSONObject().apply {listOf("master","red","green","blue").forEachIndexed {i,k->put(k,channel(i).toJson())}}
    companion object {fun fromJson(j:JSONObject)=LevelsSettings(LevelChannel.fromJson(j.optJSONObject("master")?:JSONObject()),LevelChannel.fromJson(j.optJSONObject("red")?:JSONObject()),LevelChannel.fromJson(j.optJSONObject("green")?:JSONObject()),LevelChannel.fromJson(j.optJSONObject("blue")?:JSONObject()))}
}
