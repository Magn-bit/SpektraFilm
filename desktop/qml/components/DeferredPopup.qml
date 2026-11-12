import QtQuick

// Create secondary workspaces on first use, then retain their state.
Loader {
    id: root
    active: false
    readonly property bool opened: item ? item.opened : false
    property string categoryOnOpen:''
    function open() {
        active = true
        if (item) {
            if(categoryOnOpen.length && item.category!==undefined)item.category=categoryOnOpen
            item.open()
        }
    }
    function openForCategory(category){categoryOnOpen=category;open()}
    function close() { if (item) item.close() }
    onLoaded: {item.parent = parent;if(categoryOnOpen.length && item.category!==undefined)item.category=categoryOnOpen}
}
