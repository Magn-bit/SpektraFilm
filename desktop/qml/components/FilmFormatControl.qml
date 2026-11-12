import QtQuick
import QtQuick.Layouts

Column {
    id:root
    readonly property string sizeUnit:ctrl.preferences.format_unit
    readonly property real factor:sizeUnit==='cm' ? 10 : sizeUnit==='in' ? 25.4 : 1
    width:parent.width;spacing:12
    MaterialSelector {
        label:qsTr(String('模拟片幅'));value:ctrl.parameters.film_format_axis==='long' ? String(ctrl.parameters.film_format_mm) : 'custom'
        choices:{var r=[{id:'custom',name:'自定物理尺寸'}];for(var i=0;i<ctrl.filmFormats.length;i++)r.push({id:String(ctrl.filmFormats[i].mm),name:ctrl.filmFormats[i].name});if(!r.some(function(x){return x.id===String(ctrl.parameters.film_format_mm)}))r.push({id:String(ctrl.parameters.film_format_mm),name:ctrl.parameters.film_format_mm.toFixed(1)+' mm'});return r}
        onSelected:function(value){if(value!=='custom')ctrl.setFilmFormat(Number(value))}
    }
    MaterialSelector {label:qsTr(String('尺寸基准'));value:ctrl.parameters.film_format_axis;choices:[{id:'long',name:'画面长边'},{id:'short',name:'画面短边'}];onSelected:function(value){ctrl.setFilmFormatAxis(value)}}
    MaterialSelector {label:qsTr('单位');value:root.sizeUnit;choices:[{id:'mm',name:'mm'},{id:'cm',name:'cm'},{id:'in',name:'inch'}];onSelected:function(value){ctrl.updatePreference('format_unit',value)}}
    FineParameter {
        label:qsTr(String(ctrl.parameters.film_format_axis==='short' ? '短边尺寸' : '长边尺寸'));parameter:'film_format_mm'
        directParameter:false;controllerReset:true;externalValue:ctrl.parameters.film_format_mm/root.factor
        minimum:4/root.factor;maximum:(ctrl.parameters.film_format_axis==='short' && ctrl.sourceDimensions[0]>0 && ctrl.sourceDimensions[1]>0 ? 200*Math.min(ctrl.sourceDimensions[0],ctrl.sourceDimensions[1])/Math.max(ctrl.sourceDimensions[0],ctrl.sourceDimensions[1]) : 200)/root.factor
        step:root.sizeUnit==='mm' ? .1 : .01;fineStep:root.sizeUnit==='mm' ? .01 : .001;unit:root.sizeUnit;defaultValue:35/root.factor
        onValueEdited:function(value){ctrl.updateParameter('film_format_mm',value*root.factor)}
    }
}
