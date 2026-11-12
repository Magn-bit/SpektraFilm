import QtQuick

FineParameter {
    id: root
    property real valueScale: 1
    property bool localAdjustment: true
    property string scope: 'mask'
    property string zone: ''
    property real currentValue: {
        var s=ctrl.parameters
        var values=scope==='geometry' ? s.geometry : scope==='hsl' ? (s.hsl || {})[zone] :
                   scope==='grading' ? (zone ? (s.grading || {})[zone] : s.grading) : ctrl.activeMaskGuide
        return ((values || {})[root.parameter] || 0)*valueScale
    }
    signal edited(real value)
    minimum: -100; maximum: 100; step: 1
    directParameter: false; recordEdits: localAdjustment; externalValue: currentValue
    defaultValue: scope==='geometry' && parameter==='scale' ? 100 :
                  scope==='mask' && parameter==='opacity' ? valueScale :
                  scope==='grading' && parameter==='blending' ? 50 : 0
    onValueEdited: function(value) {
        if(localAdjustment) {
            if(scope==='geometry')ctrl.updateGeometry(parameter,value/valueScale)
            else if(scope==='hsl')ctrl.updateHslParameter(zone,parameter,value/valueScale)
            else if(scope==='grading')ctrl.updateGradingParameter(zone,parameter,value/valueScale)
            else if(scope==='maskGeometry')ctrl.updateMaskGeometry(parameter,value/valueScale)
            else ctrl.updateMaskParameter(parameter,value/valueScale)
        }
        root.edited(value)
    }
}
