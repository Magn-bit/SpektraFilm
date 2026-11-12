import QtQuick

// Create secondary workspaces on first use, then retain their state.
Loader {
    id: root
    active: false
    readonly property bool opened: item ? item.opened : false
    function open() {
        active = true
        if (item) item.open()
    }
    function close() { if (item) item.close() }
    onLoaded: item.parent = parent
}
