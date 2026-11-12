# Import workspace / quick-session boundary

Reference inspected: SpektraLab 2.2.0, revision
`2201f5fa4d256b0c742b46b8e31f8176a12ca6ea` (2026-11-08).
`app/SpektraLab/PAGES.md` defines Import as a full-window task;
`Sources/Mac/Import/MacImportFlow.swift` places the source/subfolder controls on
the left, browser and optional viewer on the right, and selection/cancel/commit
at the bottom. The current product keeps the user-requested quick-session
workflow: original files stay where they are; creating a catalog is optional
and is not a prerequisite for import.

## Parent integration

`desktop/import_workspace.py` provides `ImportWorkspace(controller)`.
The controller supplies `provider`, `photos`, `exporting`, and `add_paths`.
The existing `_queued_paths` set is read defensively to recognize photos that
have already entered the controller queue but have not published metadata yet.
No backend rendering/settings/history code is replaced.

```python
from desktop.import_workspace import ImportWorkspace
self._import_workspace = ImportWorkspace(self)

@Property(QObject, constant=True)
def importWorkspace(self):
    return self._import_workspace
```

Instantiate the page inside the client content, below the window chrome:

```qml
ImportWorkspace {
    anchors.fill: parent
    workspace: ctrl.importWorkspace
    visible: currentWorkspace === "import"
    onCloseRequested: currentWorkspace = "editor"
}
Connections {
    target: ctrl.importWorkspace
    function onImported(count) { currentWorkspace = "editor" }
}
```

Call `importWorkspace.close()` during app shutdown before releasing the image
provider/controller. This permanently closes the backend; ordinary page Cancel
calls `cancelScan()` instead. Hide/disable the editor's conflicting Ctrl+A,
Return/Escape and drop targets while this page owns them. Ctrl+O may open this
page and `choosePhotos()`; a folder entry may use `chooseFolder()`. The existing
window drag/paste quick-import path can continue to call `ctrl.dropPhotos` /
`ctrl.add_paths` directly, preserving the fastest workflow.

## Public behavior

- `setSources(list[str])` replaces staged sources; accepts folders and files.
- `receiveDrop(list[URL])` adds local drop sources and retains prior choices.
- `setRecursive(bool)` rescans while preserving choices for already-found files.
- `photos` is a `QAbstractListModel` with one `entry` role; it carries stable
  source index, filename, path, format, selected/current flags and dimensions.
- `thumbnail(index)` registers only requested grid items with the existing
  bounded image provider. The grid is virtualized; it never develops all RAWs.
- `activate(index)` loads one bounded 960 px candidate using the embedded RAW
  preview/raster reader; active generation/index guards reject stale results.
- `toggle(index, extend)` and `selectAll(bool)` preserve current-session
  exclusions. Ctrl+A / Ctrl+Shift+A and Space are available on the page.
- `cancelScan()` sets a thread event immediately. Generation checks prevent an
  obsolete source scan from appending into the replacement source.
- `addSelected()` admits 128 paths per Qt event-loop turn through the existing
  `controller.add_paths`. It emits `imported(count)` after admission. Subsequent
  metadata validation/development stays on the controller's bounded queue.

The scanner uses `os.scandir` and 64-row / 100 ms batches, does not traverse
directory symlinks, and does not decode sensor pixels, copy files or create
sidecars. File names, byte sizes and times are the only scan-time metadata.
RAW dimensions are read only for the active candidate. A disabled duplicate is
identified in its tooltip/accessibility text and active preview; failed/empty
sources have explicit UI states. Current selection remains usable after a
cancelled partial scan.

## Verification

`scripts/verify_import_workspace.py` uses the real Qt component and image
provider with owned JPEG fixtures and an admission-only controller adapter.
One run covers 24 top-level / 34 recursive files, an existing-session duplicate,
five-item range selection, choice preservation after recursion, cancellation
and stale-result rejection, two-path admission and local already-added state.
Actual 1366×768 and 1440×900 captures show the selected count, virtual grid,
candidate viewer and fully reachable footer; no QML errors were reported.
Evidence: `output/import-workspace-review/`. Final parent integration still
needs one entry/return check with the actual Controller and window navigation;
the module check does not claim that wiring has already been installed.
