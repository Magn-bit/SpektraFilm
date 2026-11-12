import QtQuick
import QtQuick.Layouts

Column {
    width:parent.width;spacing:22
    FineParameter {label:qsTr(String('阴影色调'));parameter:'calibration_shadow_tint';minimum:-100;maximum:100;step:.1;trackColors:['#718D70','#B7B5A9','#AD7E9A'];signedValue:true}
    Repeater {
        model:[{id:'red',name:'红原色',hue:['#B775A4','#C76D61','#CA9A66'],sat:['#BDBCB5','#C5968F','#C76D61']},
               {id:'green',name:'绿原色',hue:['#B8AD65','#789C75','#69A9A1'],sat:['#BDBCB5','#9EB39A','#789C75']},
               {id:'blue',name:'蓝原色',hue:['#6CA7AB','#708EB8','#9C7AAE'],sat:['#BDBCB5','#9AA8B9','#708EB8']}]
        delegate:Column {
            required property var modelData
            width:parent.width;spacing:8
            MinchoText {text:qsTr(String(modelData.name));color:Theme.secondary;font.pixelSize:Theme.caption;height:26}
            FineParameter {label:qsTr(String('色相'));parameter:'calibration_'+modelData.id+'_hue';minimum:-100;maximum:100;step:.1;signedValue:true;trackColors:modelData.hue}
            FineParameter {label:qsTr(String('饱和度'));parameter:'calibration_'+modelData.id+'_saturation';minimum:-100;maximum:100;step:.1;signedValue:true;trackColors:modelData.sat}
        }
    }
}
