from __future__ import annotations
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import math
import os
import threading
import time
import uuid
from collections import OrderedDict

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QThreadPool, QRunnable, QUrl, QStandardPaths, Qt
from PySide6.QtGui import QImage, QGuiApplication, QDesktopServices
from PySide6.QtQuick import QQuickImageProvider
from .dialogs import StudioFileDialog as QFileDialog
from .imaging import Settings, FILM_FIELDS, film_settings, settings_from_record, ASSETS, PARAMETER_LIMITS, RAW_EXTENSIONS, EXPORT_PRESETS, catalog, read_photo, read_thumbnail, photo_dimensions, prepare_photo_source, render, render_interactive, export_photo, export_preset
from .import_bridge import PHOTO_EXTENSIONS, mime_paths, has_photos
from .batch import plan_exports,plan_recipe_exports
from .batch_jobs import BatchExportJournal,source_matches
from .photo_model import PhotoListModel,PhotoBrowserModel
from .editor_bindings import EditorBindings
from .mask_overlay import MaskOverlay
from .preferences import PreferenceStore,DiagnosticTimings,export_diagnostics
from shared.local_masks import MaskLayer, MaskStroke, normalize_masks, apply_masks
from shared.color_tools import CurveSet, ColorGrading, normalize_curves, normalize_grading, normalize_channel_mixer, evaluate_curve, CHANNELS
from shared.hsl import BANDS, HslSettings, normalize_hsl
from shared.geometry import Geometry, normalize_geometry, apply_geometry_image, output_size, oriented_size, normalized_matrices
from shared.style_presets import catalog as style_catalog, import_style_json, normalize_style, NONE_STYLE_ID, STYLE_DEFAULTS
from shared.style_luts import known_lut
from shared.photo_formats import PHOTO_DIALOG_FILTER
from shared.darkroom import PAPER_IDS, FILM_FORMATS, paper_choices, scans_directly
from shared.output_recipes import DEFAULT_RECIPES,normalize_recipe,recipe_json
from shared.settings_sync import category_fields,DEFAULT_CATEGORIES,normalize_clip
from .output import export_recipe,ExportCancelled

MASK_PARAMETER_LIMITS = {'opacity': (0, 1), 'exposure': (-3, 3),
    'temperature': (-100, 100), 'tint': (-100, 100), 'contrast': (-100, 100),
    'saturation': (-100, 100), 'highlights': (-100, 100), 'shadows': (-100, 100)}

PREVIEW_EDGE = 800
STYLE_FIELDS = ('contrast','saturation','vibrance','highlights','shadows','black_point','white_point','gamma','curves','grading','channel_mixer','hsl','look_lut','look_strength')
BUILTIN_STYLE_KINDS = ('original','creative-hald','community-hald')

def _full_settings(data=None):
    return film_settings(data)

class PhotoProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.images = {}
        self.thumbnail_sources = {}
        self.thumbnail_order = OrderedDict()
        self.lock = threading.RLock()
    def publish(self, name, image):
        with self.lock:
            # Workers provide immutable QImages for previews. QImage shares its
            # backing store until a writer detaches; publishing stays O(1).
            self.images[name] = QImage(image) if isinstance(image,QImage) else QImage(ImageQt(image)).copy()
    def discard(self, *names):
        with self.lock:
            for name in names:
                self.images.pop(name, None)
                self.thumbnail_sources.pop(name,None)
                self.thumbnail_order.pop(name,None)
    def publish_thumbnail(self, name, path, image):
        with self.lock:
            self.thumbnail_sources[name]=path
            self.images[name]=QImage(ImageQt(image)).copy()
            self.thumbnail_order[name]=None
            self.thumbnail_order.move_to_end(name)
            while len(self.thumbnail_order)>64:
                evicted,_=self.thumbnail_order.popitem(last=False)
                self.images.pop(evicted,None)
    def register_thumbnail(self,name,path):
        with self.lock:
            self.thumbnail_sources[name]=path
    def requestImage(self, ident, size, requestedSize):
        if ident.startswith('ui-icon/'):
            from .icon_provider import theme_icon
            image=theme_icon(ident,requestedSize)
            size.setWidth(image.width());size.setHeight(image.height())
            return image
        key=ident.split('?')[0]
        with self.lock:
            image = QImage(self.images.get(key,QImage()))
            path=self.thumbnail_sources.get(key)
            if not image.isNull() and key in self.thumbnail_order:
                self.thumbnail_order.move_to_end(key)
        if image.isNull() and path:
            try:
                image=QImage(ImageQt(read_thumbnail(path,180))).copy()
                with self.lock:
                    if key in self.thumbnail_sources:
                        self.images[key]=image.copy()
                        self.thumbnail_order[key]=None
                        self.thumbnail_order.move_to_end(key)
                        while len(self.thumbnail_order)>64:
                            evicted,_=self.thumbnail_order.popitem(last=False)
                            self.images.pop(evicted,None)
            except Exception:
                image=QImage()
        if not image.isNull():
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image

class JobSignals(QObject):
    done = Signal(object)
    progress = Signal(object)

class Job(QRunnable):
    def __init__(self, fn, context):
        super().__init__()
        self.fn, self.context = fn, context
        self.signals = JobSignals()
    def run(self):
        try:
            value = self.fn()
            self.signals.done.emit(dict(self.context, ok=True, value=value))
        except Exception as error:
            self.signals.done.emit(dict(self.context, ok=False, error=f'{type(error).__name__}: {error}'))

class Controller(QObject):
    stateChanged = Signal()
    parameterChanged = Signal()
    geometryChanged = Signal()
    masksChanged = Signal()
    maskLayersChanged = Signal()
    curvesChanged = Signal()
    sceneCurvesChanged = Signal()
    materialsChanged = Signal()
    stylesChanged = Signal()
    preferencesChanged = Signal()
    recipesChanged = Signal()
    exportItemsChanged = Signal()
    maskGuideChanged = Signal()
    maskOverlayChanged = Signal()
    levelHistogramChanged = Signal()
    autoAdjustChanged = Signal()
    frameChanged = Signal()
    photosChanged = Signal()
    selectionChanged = Signal()
    clipboardChanged = Signal()
    persisted = Signal(str,dict)
    libraryPhotoOpened = Signal()
    importWorkspaceRequested = Signal()
    toast = Signal(str)

    def __init__(self, provider, isolated_store=None):
        super().__init__()
        self.provider = provider
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.export_pool = QThreadPool(self)
        self.export_pool.setMaxThreadCount(1)
        self.fast_pool = QThreadPool(self)
        self.fast_pool.setMaxThreadCount(1)
        self.crop_pool = QThreadPool(self)
        self.crop_pool.setMaxThreadCount(1)
        self._crop_source = ''
        self._crop_busy = False
        self._crop_request = 0
        self._settings = _full_settings()
        self._default_settings = self._settings
        self._photos, self._current = [], -1
        self._photo_model=PhotoListModel(self._photos,self)
        self._browser_model=PhotoBrowserModel(self._photo_model,self)
        self._stocks = catalog()
        self._styles = []
        self._custom_style_path = Path(isolated_store or QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'styles.json'
        try:
            self._styles=style_catalog()
            if self._custom_style_path.is_file():
                self._styles.extend(normalize_style(item) for item in json.loads(self._custom_style_path.read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError,KeyError):
            pass
        self._imported_style_id = ''
        self._busy = False
        self._exporting = False
        self._importing = False
        self._last_export_dir = ''
        self._status = '准备就绪'
        self._frame = self._original = ''
        self._generation = self._published = 0
        self._pending = False
        self._jobs = {}
        self._import_queue = []
        self._queued_paths = set()
        self._closed = False
        self._history, self._redo = {}, {}
        self._library_context={}
        self._library_source_record={}
        self._library_histories={}
        self._pending_library_open=None
        self._suppress_library_persist=False
        self._selected, self._selection_anchor = set(), -1
        self._batch_progress, self._batch_total = 0, 0
        self._batch_result = {}
        self._export_items=[]
        self._recipe_export_snapshot=None
        self._batch_plan=[]
        self._batch_job_id=''
        self._batch_recovery_prompt=False
        self._cancel_export = threading.Event()
        self._before = None
        self._active_masks = {}
        self._mask_stroke = None
        self._edit_generation = -1
        self._cache = OrderedDict()
        self._source_stamps = {}
        self._cache_lock = threading.RLock()
        self._prepared = OrderedDict()
        self._mask_bases = OrderedDict()
        self._render_epochs = {}
        self._lens_status = {}
        self._fast_busy = self._fast_pending = False
        self._quality_generation, self._quality = -1, 0
        self._display_generation = -1
        self._minimum_frame_generation = 0
        self._render_ms = 0
        self._analysis_busy=False
        self._analysis={}
        # Scene measurements are expensive GPU probes. Keep a small identity
        # keyed cache so pressing Auto twice or reopening the same photo does
        # not rebuild the source/session while the source and relevant settings
        # are unchanged. It is deliberately bounded and never used for final
        # rendering.
        self._analysis_cache=OrderedDict()
        self._analysis_cache_lock=threading.RLock()
        self._preview_edge = PREVIEW_EDGE
        self._store = Path(isolated_store or QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'edits'
        self._store.mkdir(parents=True, exist_ok=True)
        self._batch_journal=BatchExportJournal(self._store.parent/'batch-export')
        self._preferences=PreferenceStore(self._store.parent/'preferences.json')
        self._frame_defaults_path=self._store.parent/'new-frame-defaults.json'
        try:self._new_frame_defaults=Settings.from_mapping(json.loads(self._frame_defaults_path.read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError):self._new_frame_defaults=Settings()
        self._preview_edge=self._preferences.values['preview_long_edge']
        self._cache_budget=self._preferences.values['memory_budget_mb']*1024**2
        os.environ['SPEKTRAFILM_DISK_CACHE_MB']=str(self._preferences.values['disk_cache_mb'])
        self._recipe_path=self._store.parent/'output-recipes.json'
        self._output_recipes=list(DEFAULT_RECIPES)
        try:
            saved=json.loads(self._recipe_path.read_text(encoding='utf-8'))
            if isinstance(saved,list):
                valid=[]
                for item in saved[:64]:
                    try:
                        value=normalize_recipe(item)
                        if not any(r.id==value.id for r in valid):valid.append(value)
                    except (ValueError,TypeError):pass
                self._output_recipes=valid or list(DEFAULT_RECIPES)
        except (OSError,ValueError,TypeError):pass
        self._settings_clipboard={}
        self._clipboard_path=self._store.parent/'settings-clipboard.json'
        self._clipboard_categories=list(DEFAULT_CATEGORIES)
        self._clipboard_source=''
        self._copied_categories=[]
        try:
            if self._clipboard_path.stat().st_size<=1024*1024:
                document=json.loads(self._clipboard_path.read_text(encoding='utf-8'))
                clip=normalize_clip(document)
                selected=document.get('selected_categories',clip['categories'])
                category_fields(selected)
                self._clipboard_categories=list(selected)
                self._copied_categories=clip['categories']
                self._clipboard_source=clip['source_name']
                typed=Settings.from_mapping(clip['settings'])
                self._settings_clipboard={key:getattr(typed,key) for key in clip['settings']}
        except (OSError,ValueError,TypeError):pass
        self._diagnostics=DiagnosticTimings(self._store.parent/'timings.json',self._preferences.values['diagnostic_retention_days'])
        self._diagnostic_samples=self._diagnostics.samples
        self._native_budget_applied=None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self._schedule)
        self.fast_timer = QTimer(self)
        self.fast_timer.setSingleShot(True)
        self.fast_timer.setInterval(24)
        self.fast_timer.timeout.connect(self._schedule_fast)
        self._clipboard = QGuiApplication.clipboard()
        self._clipboard.dataChanged.connect(self.clipboardChanged)
        self._parameters = EditorBindings(self._settings, self)
        self._binding_geometry = self._binding_masks = None
        self._binding_mask_list = None
        self._binding_curves = self._binding_stock = None
        self._binding_scene_curves=None
        self._mask_guide={}
        self._level_histogram={}
        self._auto_adjust_busy=False
        self._mask_overlay=MaskOverlay(self.provider,self)
        self._mask_overlay.changed.connect(self.maskOverlayChanged)
        from .composition import Composition
        self._composition=Composition(self)
        self._composition.message.connect(self.toast)
        from .light_table import LightTable
        self._light_table=LightTable(self)
        self._light_table.message.connect(self.toast)
        from .library_workspace import LibraryWorkspace
        self._library_workspace=LibraryWorkspace(self,thumbnail_provider=self.provider)
        self._library_workspace.notice.connect(self.toast)
        self._library_workspace.flushCurrent.connect(self._persist)
        self._library_workspace.openPhoto.connect(self._open_library_photo)
        self._library_workspace.quickSessionRequested.connect(self._leave_library)
        self.persisted.connect(self._library_workspace.saveEdit)
        from .color_display import ColorDisplay
        self._color_display=ColorDisplay(self,self._store.parent/'display-management.json')
        self._color_display.message.connect(self.toast)
        self._color_display.renderChanged.connect(self._changed)
        from .full_detail import FullDetail
        self._full_detail=FullDetail(self)
        self._full_detail.changed.connect(self.stateChanged)
        from .output_proof import OutputProof
        self._output_proof=OutputProof(self)
        from .film_library import FilmLibrary
        self._film_library=FilmLibrary(self)
        from .gui_automation import GuiAutomation
        self._gui_automation=GuiAutomation(self)
        self._gui_automation.error.connect(self.toast)
        from .update_check import UpdateCheck
        self._update_check=UpdateCheck(self)
        from .import_workspace import ImportWorkspace
        self._import_workspace=ImportWorkspace(self)
        self._matrix_key = self._matrix_values = None
        # Connect before QML: observers always see a consistent current graph.
        self.stateChanged.connect(self._sync_editor_bindings)
        self.stateChanged.connect(self.parameterChanged)
        self.selectionChanged.connect(self.stateChanged)
        self._sync_editor_bindings()

        from .scene_histogram import SceneHistogram
        self._scene_histogram=SceneHistogram(self,self)
        self._load_batch_export()

    def _sync_editor_bindings(self):
        self._parameters.sync(self._settings)
        geometry = (tuple(self.sourceDimensions), self._settings.geometry)
        geometry_changed = geometry != self._binding_geometry
        if geometry_changed:
            self._binding_geometry = geometry
            self.geometryChanged.emit()
        masks = (self.currentPath, self._settings.masks, self.activeMaskId)
        masks_changed = masks != self._binding_masks
        if masks_changed:
            self._binding_masks = masks
            self.masksChanged.emit()
        # Editing one stroke must not destroy/recreate every layer delegate.
        layer_list=tuple((layer.id,layer.name,layer.enabled) for layer in self._settings.masks)
        if layer_list!=self._binding_mask_list:
            self._binding_mask_list=layer_list
            self.maskLayersChanged.emit()
        layer=next((layer for layer in self._settings.masks if layer.id==self.activeMaskId),None)
        guide={} if layer is None else {key:list(value) if isinstance(value,tuple) else value
            for key,value in layer.__dict__.items() if key!='strokes'}
        if layer is not None:guide['strokeCount']=len(layer.strokes)
        if guide!=self._mask_guide:
            self._mask_guide=guide;self.maskGuideChanged.emit()
        if masks_changed or geometry_changed:
            self._mask_overlay.update(layer,self.sourceDimensions,self._settings.geometry)
        if self._settings.curves != self._binding_curves:
            self._binding_curves = self._settings.curves
            self.curvesChanged.emit()
        if self._settings.scene_curves != self._binding_scene_curves:
            self._binding_scene_curves=self._settings.scene_curves
            self.sceneCurvesChanged.emit()
        if self._settings.stock != self._binding_stock:
            self._binding_stock = self._settings.stock
            self.materialsChanged.emit()

    @Property('QVariantList', constant=True)
    def stocks(self): return self._stocks
    @Property('QVariantList', notify=materialsChanged)
    def papers(self): return [dict(id='auto',name='随胶片')] + paper_choices(self._settings.stock)
    @Property('QVariantList', constant=True)
    def filmFormats(self): return list(FILM_FORMATS)
    @Property(bool, notify=stateChanged)
    def directScan(self): return self._settings.scan_film or self._settings.digital_intermediate or scans_directly(self._settings.stock)

    @Property(bool,notify=stateChanged)
    def diSupported(self):
        from shared.darkroom import BLACK_AND_WHITE
        return self._settings.stock not in BLACK_AND_WHITE and not scans_directly(self._settings.stock)

    @Property(bool,notify=stateChanged)
    def hdrSupported(self):
        from shared.darkroom import BLACK_AND_WHITE
        return (self._settings.film_enabled and self._settings.strength>0 and
            self._settings.stock not in BLACK_AND_WHITE and not self._settings.scan_film and
            not self._settings.digital_intermediate and not self._settings.extended_dynamic_range)

    @Property(bool,notify=stateChanged)
    def edrSupported(self):
        from .native_spectral import paper_supports_edr
        from shared.darkroom import resolve_paper
        if self.directScan:return False
        return paper_supports_edr(resolve_paper(self._settings.stock,self._settings.paper))

    @Property('QVariantMap',notify=stateChanged)
    def paperLutInfo(self):
        from .paper_lut import paper_info
        return dict(paper_info(self._settings),busy=getattr(self,'_paper_lut_active',False))

    @Slot(result=bool)
    def exportPaperLut(self):
        if self._exporting or getattr(self,'_paper_lut_active',False):return False
        info=self.paperLutInfo
        if not info['available']:
            self.toast.emit(info['reason']);return False
        initial=str(Path(self.currentPath).parent/info['paper'])+'.cube' if self.currentPath else info['paper']+'.cube'
        target,_=QFileDialog.getSaveFileName(None,'导出相纸 LUT',initial,'相纸 LUT (*.cube)')
        if not target:return False
        from .paper_lut import start_export
        return start_export(self,info['paper'],target,Job)

    @Slot(str,bool)
    def setFilmOption(self,key,value):
        if key not in ('scan_film','extended_dynamic_range','print_effects','grain_layered','grain_enabled','halation_enabled','hdr_enabled','digital_intermediate'):return
        if key=='extended_dynamic_range' and value and not self.edrSupported:return
        if key=='hdr_enabled' and value and not self.hdrSupported:return
        if key=='digital_intermediate' and value and not self.diSupported:return
        values={key:bool(value)}
        if key in ('scan_film','digital_intermediate') and value:
            values.update(minilab_active=False,scan_film=key=='scan_film',digital_intermediate=key=='digital_intermediate',hdr_enabled=False,extended_dynamic_range=False)
        if key=='extended_dynamic_range' and value:values['hdr_enabled']=False
        self._replace_tools(**values)
    @Property(bool, notify=materialsChanged)
    def couplersSupported(self):
        from shared.darkroom import BLACK_AND_WHITE
        from shared.film_profiles import extension_profiles
        return self._settings.stock not in BLACK_AND_WHITE and self._settings.stock not in extension_profiles()
    @Property(bool, notify=materialsChanged)
    def backReflectionSupported(self):
        # This is a material property, not the user switch which substitutes
        # a stronger Gaussian preset on materials with an existing backing.
        resources=ASSETS.parent/'native/engine/runtime/resources/profiles'
        try:
            profile=json.loads((resources/(self._settings.stock+'.json')).read_text(encoding='utf-8'))
            return profile.get('info',{}).get('antihalation')=='no'
        except (OSError,ValueError):
            return False
    @Property('QVariantList', notify=stylesChanged)
    def stylePresets(self):
        return [dict({key:item.get(key,'') for key in ('id','name','description','author','kind','source')},category=item.get('category','general'),warnings=item.get('warnings',[])) for item in self._styles]
    @Property(str, notify=stateChanged)
    def importedStyleId(self): return self._imported_style_id
    @Property(str, notify=stateChanged)
    def currentStyleName(self):
        ident=self._settings.look_lut
        if ident:
            preset=next((item for item in self._styles if item.get('settings',{}).get('look_lut')==ident),None)
            if preset:return preset['name']
            entry=known_lut(ident)
            if entry:return entry.get('name','创作者风格')
        values=asdict(self._settings)
        for preset in self._styles:
            if preset.get('id')==NONE_STYLE_ID:continue
            settings=preset.get('settings',{})
            if all(values.get(key)==settings.get(key) for key in STYLE_FIELDS):
                return preset['name']
        return '无预设'
    @Property('QVariantMap', constant=True)
    def exportPresetFolders(self): return {key: value['folder'] for key,value in EXPORT_PRESETS.items()}
    @Property('QVariantList', notify=photosChanged)
    def photos(self): return self._photos
    @Property(QObject,constant=True)
    def photoModel(self):return self._photo_model
    @Property(QObject,constant=True)
    def browserModel(self):return self._browser_model
    @Property(int,notify=photosChanged)
    def photoCount(self):return len(self._photos)
    @Property(str,notify=photosChanged)
    def currentPath(self):return self._photos[self._current]['path'] if self._current>=0 else ''
    @Property(int, notify=photosChanged)
    def currentIndex(self): return self._current
    @Property('QVariantMap', notify=stateChanged)
    def settings(self): return asdict(self._settings)
    @Property(QObject,constant=True)
    def composition(self):return self._composition
    @Property(QObject,constant=True)
    def lightTable(self):return self._light_table
    @Property(QObject,constant=True)
    def libraryWorkspace(self):return self._library_workspace
    @Property(QObject,constant=True)
    def colorDisplay(self):return self._color_display

    @Property(QObject,constant=True)
    def sceneHistogram(self):return self._scene_histogram

    @Property(QObject,constant=True)
    def outputProof(self):return self._output_proof

    @Property(QObject,constant=True)
    def filmLibrary(self):return self._film_library
    @Property(QObject,constant=True)
    def guiAutomation(self):return self._gui_automation
    @Property(QObject,constant=True)
    def updateCheck(self):return self._update_check
    @Property(QObject,constant=True)
    def importWorkspace(self):return self._import_workspace
    @Slot()
    def openLicenseFolder(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(ASSETS.parent/'licenses')))
    @Slot()
    def saveNewFrameDefaults(self):
        from .preferences import _atomic_json
        keys=category_fields(['materials','film_effects','print_effects'])
        defaults=Settings.from_mapping(asdict(replace(Settings(),**{key:getattr(self._settings,key) for key in keys})))
        try:_atomic_json(self._frame_defaults_path,asdict(defaults))
        except OSError as error:self.toast.emit(str(error));return
        self._new_frame_defaults=defaults
        self._preferences.update('default_stock','saved');self._preferences.update('default_paper','saved');self.preferencesChanged.emit()
        self.toast.emit('新照片将使用当前胶片设置，已有照片保持各自参数')
    @Slot()
    def resetNewFrameDefaults(self):
        from .preferences import _atomic_json
        try:_atomic_json(self._frame_defaults_path,asdict(Settings()))
        except OSError as error:self.toast.emit(str(error));return
        self._new_frame_defaults=Settings()
        self._preferences.update('default_stock','saved');self._preferences.update('default_paper','saved');self.preferencesChanged.emit()
        self.toast.emit('新照片默认设置已恢复')

    def _settings_for_import(self):
        preferences=self._preferences.values
        saved=self._new_frame_defaults
        stock=preferences['default_stock'];paper=preferences['default_paper']
        stock=saved.stock if stock=='saved' else self._settings.stock if stock=='last' else stock
        paper=saved.paper if paper=='saved' else self._settings.paper if paper=='last' else paper
        compatible={item['id'] for item in paper_choices(stock)}|{'auto'}
        return replace(saved,stock=stock,paper=paper if paper in compatible else 'auto')

    def _leave_library(self):
        self._library_context={}
        self._library_source_record={}
        self._pending_library_open=None

    def _open_library_photo(self,path,record,metadata):
        if self._exporting or self._closed:return
        path=str(Path(path).resolve())
        if not Path(path).is_file():
            self.toast.emit('原片不在当前位置，请在资料库中重新定位文件夹。');return
        # Workspace has flushed the previous variant before emitting this.
        # Suppress the per-path editor's activation persist: the workspace
        # already points at the new variant, possibly of the very same file.
        if self._current>=0:
            key=self._library_context.get('variant') or self.currentPath
            self._library_histories[key]=(self._history.get(self._current,[])[:],self._redo.get(self._current,[])[:])
            while len(self._library_histories)>32:self._library_histories.pop(next(iter(self._library_histories)))
        self._pending_library_open=(path,dict(record),dict(metadata))
        if any(os.path.normcase(p['path'])==os.path.normcase(path) for p in self._photos):
            self._apply_pending_library()
        else:self.add_paths([path])

    def _apply_pending_library(self):
        if self._pending_library_open is None:return
        path,record,metadata=self._pending_library_open
        index=next((i for i,p in enumerate(self._photos) if os.path.normcase(p['path'])==os.path.normcase(path)),None)
        if index is None:return
        self._suppress_library_persist=True
        try:
            self._finish_mask_stroke()
            if self._before is not None:self.endEdit()
            if record and not (record.get('version')==4 and isinstance(record.get('settings'),dict)):
                self.toast.emit('此记录来自其他显影格式，保留原记录并从自然原片开始。')
                settings=_full_settings()
            else:settings=settings_from_record(record) if record else _full_settings()
            self._photos[index]['settings']=asdict(settings)
            self._activate_photo(index)
            self._selected={index};self._selection_anchor=index
            self._library_context=metadata
            self._library_source_record=record.get('source_edit',{}) if record.get('version')==4 else record
            self._history[index],self._redo[index]=self._library_histories.get(metadata['variant'],([],[]))
            self._pending_library_open=None
            self.selectionChanged.emit();self.stateChanged.emit();self.libraryPhotoOpened.emit()
        finally:self._suppress_library_persist=False
    @Slot(result=bool)
    def prepareComposition(self):
        if self._current<0 or self._exporting:return False
        if self._before is not None:self.endEdit()
        indices=self.selectedIndices or [self._current]
        if len(indices)>9:self.toast.emit('一次最多选择9张照片进行拼图');return False
        photos=[dict(self._photos[i],settings=self._settings if i==self._current else _full_settings(self._photos[i]['settings'])) for i in indices]
        return self._composition.open_selection(photos)
    @Property('QVariantMap',notify=maskGuideChanged)
    def activeMaskGuide(self):return self._mask_guide
    @Property(str,notify=maskOverlayChanged)
    def maskOverlaySource(self):return self._mask_overlay.source
    @Slot(bool)
    def setMaskOverlayVisible(self,value):self._mask_overlay.set_visible(value)
    @Slot(str)
    def setMaskOverlayColor(self,value):self._mask_overlay.set_color(value)
    @Property('QVariantMap',notify=levelHistogramChanged)
    def levelHistogram(self):return self._level_histogram
    @Property(bool,notify=autoAdjustChanged)
    def autoAdjustBusy(self):return self._auto_adjust_busy
    @Property(QObject, constant=True)
    def parameters(self): return self._parameters
    @Property('QVariantList', notify=maskLayersChanged)
    def maskLayers(self): return [dict(id=layer.id,name=layer.name,enabled=layer.enabled) for layer in self._settings.masks]
    @Property(bool, notify=masksChanged)
    def hasMasks(self): return bool(self._settings.masks)
    @Property('QVariantMap', notify=curvesChanged)
    def colorCurves(self): return {key:[list(point) for point in getattr(self._settings.curves,key)] for key in CHANNELS}
    @Property('QVariantMap',notify=sceneCurvesChanged)
    def sceneCurves(self):return {key:[list(point) for point in getattr(self._settings.scene_curves,key)] for key in CHANNELS}

    @Property('QVariantMap',notify=curvesChanged)
    def curveParametric(self):return asdict(self._settings.curves.parametric)

    @Property('QVariantMap',notify=sceneCurvesChanged)
    def sceneCurveParametric(self):return asdict(self._settings.scene_curves.parametric)

    @Slot(str,bool,result='QVariantList')
    def curveSamples(self,channel,scene=False):
        if channel not in CHANNELS:return []
        import numpy as np
        return evaluate_curve(self._settings.scene_curves if scene else self._settings.curves,channel,np.linspace(0,1,161)).tolist()
    @Slot(str,bool,result='QVariantList')
    def curveInputSamples(self,channel,scene=False):
        if channel not in CHANNELS:return []
        import numpy as np
        curves=self._settings.scene_curves if scene else self._settings.curves
        return evaluate_curve(replace(curves,**{channel:((0.,0.),(1.,1.))}),channel,np.linspace(0,1,161)).tolist()
    @Property(bool,notify=stateChanged)
    def minilabSupported(self):
        from shared.darkroom import resolve_paper
        return self._settings.stock=='kodak_portra_400' and resolve_paper(self._settings.stock,self._settings.paper)=='kodak_portra_endura'

    @Slot(bool)
    def setMinilab(self,value):
        if value and not self.minilabSupported:return
        self._replace_tools(minilab_active=bool(value))

    @Slot(str)
    def setFilmFormatAxis(self,value):
        if value not in ('long','short') or value==self._settings.film_format_axis:return
        width,height=self.sourceDimensions
        aspect=max(width,height)/max(1,min(width,height)) if min(width,height)>0 else 1.
        millimetres=self._settings.film_format_mm*(aspect if value=='long' else 1/aspect)
        if not 4<=millimetres<=200:
            self.toast.emit('切换后尺寸超出 4–200 mm 范围，请先调整尺寸。');return
        self._replace_tools(film_format_axis=value,film_format_mm=millimetres)

    @Slot(float)
    def setFilmFormat(self,value):
        if not math.isfinite(value) or not 4<=value<=200:return
        self._replace_tools(film_format_mm=value,film_format_axis='long')
    @Property(str, notify=masksChanged)
    def activeMaskId(self):
        if self._current < 0: return ''
        selected=self._active_masks.get(self._photos[self._current]['path'],'')
        return selected if any(layer.id==selected for layer in self._settings.masks) else (self._settings.masks[0].id if self._settings.masks else '')
    @Property('QVariantMap', notify=masksChanged)
    def activeMask(self):
        layer=next((layer for layer in self._settings.masks if layer.id==self.activeMaskId),None)
        if layer is None: return {}
        result=asdict(layer)
        # Explicit lists cross QVariantMap into QML as JavaScript arrays;
        # nested Python tuples are otherwise opaque PyObject wrappers.
        result['strokes']=[dict(stroke,points=[list(point) for point in stroke['points']]) for stroke in result['strokes']]
        for key in ('start','end','center'): result[key]=list(result[key])
        return result
    @Property(bool, notify=parameterChanged)
    def busy(self): return self._busy or self._pending or self._fast_busy or self._fast_pending or self._exporting or bool(self._import_queue)
    @Property(bool, notify=stateChanged)
    def canStartExport(self): return self._current >= 0 and not self._exporting and not self._importing and not self._import_queue and not self._closed
    @Property(bool, notify=stateChanged)
    def exporting(self): return self._exporting
    @Property(str, notify=parameterChanged)
    def status(self): return self._status
    @Property(str, notify=frameChanged)
    def frame(self): return self._frame
    @Property(str, notify=frameChanged)
    def original(self): return self._original
    @Property(str, notify=photosChanged)
    def filename(self): return self._photos[self._current]['name'] if self._current >= 0 else '你的下一张作品'
    @Property(str, notify=photosChanged)
    def dimensions(self): return self._photos[self._current]['dimensions'] if self._current >= 0 else ''
    @Property(int, notify=geometryChanged)
    def imageWidth(self): return self._output_dimensions()[0]
    @Property(int, notify=geometryChanged)
    def imageHeight(self): return self._output_dimensions()[1]
    def _output_dimensions(self):
        if self._current<0: return (0,0)
        photo=self._photos[self._current]
        return output_size(photo['width'],photo['height'],self._settings.geometry)
    @Property('QVariantList', notify=photosChanged)
    def sourceDimensions(self):
        return [self._photos[self._current]['width'],self._photos[self._current]['height']] if self._current>=0 else [0,0]
    @Property('QVariantList', notify=geometryChanged)
    def cropSourceDimensions(self):
        dims=self.sourceDimensions
        return list(oriented_size(*dims,self._settings.geometry)) if self._current>=0 else [0,0]
    @Property(str, notify=frameChanged)
    def cropSource(self): return self._crop_source
    @Property(bool, notify=stateChanged)
    def cropBusy(self): return self._crop_busy
    @Property('QVariantList', notify=geometryChanged)
    def cropBounds(self): return list(self._settings.geometry.crop)
    def _geometry_matrices(self):
        key = (tuple(self.sourceDimensions), self._settings.geometry)
        if key != self._matrix_key:
            self._matrix_values = normalized_matrices(*key[0], key[1])
            self._matrix_key = key
        return self._matrix_values
    @Property('QVariantList',notify=geometryChanged)
    def geometryForward(self):
        return self._geometry_matrices()[0]
    @Property('QVariantList',notify=geometryChanged)
    def geometryInverse(self):
        return self._geometry_matrices()[1]
    @Property(bool, notify=stateChanged)
    def detailReady(self):
        return self._current >= 0 and self._full_detail.ready
    @Property(QObject,constant=True)
    def fullDetail(self):return self._full_detail
    @Property(bool, notify=photosChanged)
    def canExportRaw(self):
        return self._current>=0 and Path(self._photos[self._current]['path']).suffix.lower() in RAW_EXTENSIONS
    @Property(str, notify=materialsChanged)
    def stockName(self): return next((s['name'] for s in self._stocks if s['id']==self._settings.stock), '')
    @Property(bool, notify=stateChanged)
    def canUndo(self): return bool(self._history.get(self._current))
    @Property(bool, notify=stateChanged)
    def canRedo(self): return bool(self._redo.get(self._current))
    @Property(bool, notify=parameterChanged)
    def canReset(self): return self._current>=0 and self._settings!=self._default_settings
    @Property(int, notify=parameterChanged)
    def renderMs(self): return self._render_ms
    @Property(bool,notify=stateChanged)
    def analysisBusy(self):return self._analysis_busy
    @Property('QVariantMap',notify=stateChanged)
    def analysis(self):return self._analysis
    @Property(bool,notify=parameterChanged)
    def analysisIsCurrent(self):
        return self._analysis.get('path')==self.currentPath and self._analysis.get('generation')==self._generation
    @Property('QVariantMap',notify=preferencesChanged)
    def preferences(self):return self._preferences.values
    @Property('QVariantList',notify=recipesChanged)
    def outputRecipes(self):return [recipe_json(item) for item in self._output_recipes]
    @Property(bool,notify=stateChanged)
    def canPasteSettings(self):return bool(self._settings_clipboard) and self._current>=0 and not self._exporting
    @Property('QVariantMap',notify=stateChanged)
    def clipboardInfo(self):
        return dict(source_name=self._clipboard_source,categories=self._copied_categories,
                    selected_categories=self._clipboard_categories,fields=len(self._settings_clipboard))

    def _save_settings_clipboard(self):
        from .preferences import _atomic_json
        from shared.settings_sync import make_clip
        document=make_clip(self._settings_clipboard,self._copied_categories,self._clipboard_source)
        document['selected_categories']=self._clipboard_categories
        try:_atomic_json(self._clipboard_path,document)
        except OSError as error:self.toast.emit(str(error))

    @Slot('QVariantList')
    def setClipboardCategories(self,categories):
        try:category_fields(categories)
        except ValueError as error:self.toast.emit(str(error));return
        self._clipboard_categories=list(dict.fromkeys(categories))
        self._save_settings_clipboard();self.stateChanged.emit()

    def setSettingsClipboard(self,clip):
        clip=normalize_clip(clip)
        typed=Settings.from_mapping(clip['settings'])
        self._settings_clipboard={key:getattr(typed,key) for key in clip['settings']}
        self._copied_categories=list(clip['categories'])
        self._clipboard_categories=list(clip['categories'])
        self._clipboard_source=clip['source_name']
        self._save_settings_clipboard();self.stateChanged.emit()

    def _save_recipes(self,recipes):
        from .preferences import _atomic_json
        _atomic_json(self._recipe_path,[recipe_json(item) for item in recipes])
        self._output_recipes=recipes
        self.recipesChanged.emit()
        self.stateChanged.emit()

    @Slot('QVariantMap')
    def saveOutputRecipe(self,value):
        try:
            recipe=normalize_recipe(value)
            recipes=[recipe if item.id==recipe.id else item for item in self._output_recipes]
            if not any(item.id==recipe.id for item in recipes):
                if len(recipes)>=64:raise ValueError('最多保存64个导出配方')
                recipes.append(recipe)
            self._save_recipes(recipes)
        except (OSError,ValueError,TypeError) as error:self.toast.emit(str(error))

    @Slot(str)
    def removeOutputRecipe(self,ident):
        try:self._save_recipes([item for item in self._output_recipes if item.id!=ident])
        except OSError as error:self.toast.emit(str(error))

    @Slot('QVariantList')
    def copySettings(self,categories):
        if self._current<0 or self._exporting:return
        try:fields=category_fields(categories)
        except ValueError as error:self.toast.emit(str(error));return
        if self._before is not None:self.endEdit()
        self._settings_clipboard={key:getattr(self._settings,key) for key in fields}
        self._copied_categories=list(dict.fromkeys(categories))
        self._clipboard_categories=list(self._copied_categories)
        self._clipboard_source=self.filename
        self._save_settings_clipboard()
        self.stateChanged.emit()

    @Slot('QVariantList')
    def pasteSettings(self,categories):
        if not self.canPasteSettings:return
        try:fields=category_fields(categories)
        except ValueError as error:self.toast.emit(str(error));return
        copied={key:self._settings_clipboard[key] for key in fields if key in self._settings_clipboard}
        count=self._apply_settings_values(copied)
        self.toast.emit(f'已同步 {count} 张，可逐张撤销')

    @Slot('QVariantMap',result=int)
    def applySettingsClip(self,clip):
        """Apply a named preset without changing the transient clipboard."""
        if self._current<0 or self._exporting:return 0
        clip=normalize_clip(clip)
        return self._apply_settings_values(clip['settings'])

    def _apply_settings_values(self,copied):
        if not copied:return 0
        if self._before is not None:self.endEdit()
        updates=[]
        for index in sorted(self._selected or {self._current}):
            previous=self._settings if index==self._current else _full_settings(self._photos[index]['settings'])
            updated=Settings.from_mapping(asdict(replace(previous,**copied)))
            compatible={item['id'] for item in paper_choices(updated.stock)}|{'auto'}
            if updated.paper not in compatible:updated=replace(updated,paper='auto')
            if updated==previous:continue
            updates.append((index,previous,updated))
        # Validate the whole selection before committing any photo.
        changed=[]
        for index,previous,updated in updates:
            self._push(previous,index)
            self._persist_photo(index,updated)
            if index==self._current:self._settings=updated
            changed.append(index)
        if self._current in changed:self._changed()
        else:self.stateChanged.emit()
        return len(changed)

    @Slot(str,'QVariant')
    def updatePreference(self,key,value):
        try:changed=self._preferences.update(key,value)
        except (OSError,ValueError) as error:self.toast.emit(str(error));return
        if not changed:return
        self.preferencesChanged.emit()
        self._cache_budget=self._preferences.values['memory_budget_mb']*1024**2
        os.environ['SPEKTRAFILM_DISK_CACHE_MB']=str(self._preferences.values['disk_cache_mb'])
        if key in ('working_cache_mb','preview_cache_mb','full_render_cache_mb'):
            self._full_detail.configureBudgets(self._preferences.values)
        if key=='preview_long_edge' and self._preview_edge:
            self._preview_edge=self._preferences.values[key]
            self._changed()
        if key=='ui_scale':self.toast.emit('界面缩放将在下次启动时生效')
        if key=='diagnostic_retention_days':
            self._diagnostics.prune(self._preferences.values[key])
            try:self._diagnostics.save()
            except OSError:pass
        with self._cache_lock:self._trim_source_cache_locked()
        self.stateChanged.emit()

    @Slot()
    def clearCaches(self):
        if self._exporting:return
        with self._cache_lock:
            self._cache.clear();self._prepared.clear();self._mask_bases.clear()
        def work():
            from .native_spectral import clear_sessions
            from .raw_development import clear_cache
            clear_sessions();clear_cache();return None
        self._submit(work,dict(kind='cache'))

    @Slot()
    def exportDiagnostics(self):
        target,_=QFileDialog.getSaveFileName(None,'导出诊断','SpektraFilm-诊断.zip','ZIP (*.zip)')
        if not target:return
        try:
            self._diagnostics.save()
            from .version import VERSION
            export_diagnostics(target,self.preferences,version=VERSION,timings=dict(preview_ms=self._diagnostic_samples[-128:]))
            self.toast.emit('诊断已保存')
        except (OSError,ValueError) as error:self.toast.emit('诊断导出失败：'+str(error))
    @Property('QVariantList', notify=selectionChanged)
    def selectedIndices(self): return sorted(self._selected)
    @Property(int, notify=selectionChanged)
    def selectedCount(self): return len(self._selected)
    @Property(bool, notify=selectionChanged)
    def selectionCanExportRaw(self):
        return bool(self._selected) and all(Path(self._photos[i]['path']).suffix.lower() in RAW_EXTENSIONS for i in self._selected)
    @Property(bool,notify=stateChanged)
    def selectionCanExportDI(self):
        if not self._selected:return False
        for index in self._selected:
            value=self._settings if index==self._current else Settings.from_mapping(self._photos[index]['settings'])
            if not value.film_enabled or value.strength<=0 or scans_directly(value.stock):return False
        return True
    @Slot('QVariantMap',result=str)
    @Slot('QVariantMap',bool,result=str)
    def outputRecipeError(self,recipe,hdr_enabled=None):
        try:
            recipe=normalize_recipe(recipe)
            if recipe.format=='raw':return ''
            from .hdr_output import validate
            for index in self.selectedIndices or ([self._current] if self._current>=0 else []):
                value=self._settings if index==self._current else Settings.from_mapping(self._photos[index]['settings'])
                enabled=bool(hdr_enabled) if index==self._current and hdr_enabled is not None else value.hdr_enabled
                if enabled:validate(value,recipe)
            return ''
        except (ValueError,RuntimeError) as error:return str(error)
    @Property(bool, notify=clipboardChanged)
    def canPaste(self): return has_photos(self._clipboard.mimeData())
    @Property(int, notify=stateChanged)
    def batchProgress(self): return self._batch_progress
    @Property(int, notify=stateChanged)
    def batchTotal(self): return self._batch_total
    @Property('QVariantMap', notify=stateChanged)
    def batchResult(self): return self._batch_result

    @Property(bool, notify=exportItemsChanged)
    def pendingBatchRecovery(self): return self._batch_recovery_prompt

    @Property(bool, notify=exportItemsChanged)
    def canResumeBatchExport(self):
        return not self._exporting and any(item['status'] in ('queued','cancelled') for item in self._export_items)

    @Property(bool, notify=exportItemsChanged)
    def canClearBatchExport(self):
        return not self._exporting and bool(self._batch_job_id) and any(item['status']!='completed' for item in self._export_items)

    @Property('QVariantList',notify=exportItemsChanged)
    def exportItems(self):return [dict(item) for item in self._export_items]

    @Property(bool,notify=exportItemsChanged)
    def canRetryFailedExports(self):
        return not self._exporting and self._recipe_export_snapshot is not None and any(item['status'] in ('failed','present') for item in self._export_items)

    def _load_batch_export(self):
        try:
            snapshot=self._batch_journal.load()
        except (OSError,ValueError,TypeError,KeyError):
            return
        if not snapshot:return
        self._batch_job_id=snapshot['job_id']
        recipe=snapshot['recipe']
        self._batch_plan=[]
        self._export_items=[]
        for index,record in enumerate(snapshot['items']):
            settings=Settings.from_mapping(record['settings'])
            item=dict(id=str(index),name=Path(record['source']).name,path=record['source'],
                status=record['status'],phase='',output=record['output'],error=record.get('error',''))
            self._export_items.append(item)
            self._batch_plan.append(dict(source=record['source'],output=record['output'],settings=settings,
                source_identity=record['source_identity']))
        if all(item['status']=='completed' for item in self._export_items):
            self._batch_journal.clear(self._batch_job_id)
            self._batch_job_id='';self._batch_plan=[];self._export_items=[]
            return
        self._recipe_export_snapshot=(recipe,tuple((item['source'],item['output'],item['settings']) for item in self._batch_plan))
        self._batch_total=len(self._export_items)
        self._batch_progress=sum(item['status'] in ('completed','failed','present','changed') for item in self._export_items)
        self._batch_result=self._batch_result_from_items()
        self._batch_recovery_prompt=any(item['status']!='completed' for item in self._export_items)
        self._status='发现未完成的批量出片' if self._batch_recovery_prompt else '准备就绪'

    def _batch_result_from_items(self,cancelled=False):
        completed=[item['output'] for item in self._export_items if item['status']=='completed']
        errors=[item['name']+'：'+item['error'] for item in self._export_items
            if item['status'] in ('failed','present','changed') and item.get('error')]
        return dict(completed=completed,errors=errors,cancelled=bool(cancelled or any(
            item['status'] in ('queued','cancelled') for item in self._export_items)))

    @Slot()
    def dismissBatchRecoveryPrompt(self):
        if self._batch_recovery_prompt:
            self._batch_recovery_prompt=False
            self.exportItemsChanged.emit()

    @Slot()
    def discardBatchExport(self):
        if self._exporting or not self._batch_job_id:return
        try:
            if not self._batch_journal.clear(self._batch_job_id):
                self.toast.emit('批量任务记录已变化，请重新打开导出面板。');return
        except OSError as error:
            self.toast.emit('清除任务记录失败：'+str(error));return
        self._batch_job_id='';self._batch_plan=[];self._export_items=[]
        self._recipe_export_snapshot=None;self._batch_recovery_prompt=False;self._batch_result={}
        self._batch_progress=self._batch_total=0
        self.exportItemsChanged.emit();self.stateChanged.emit()
        self.toast.emit('任务记录已清除，已导出的文件未删除。')

    @Slot()
    def resumeBatchExport(self):
        if not self.canResumeBatchExport:return False
        self._batch_recovery_prompt=False
        indices=[i for i,item in enumerate(self._export_items) if item['status'] in ('queued','cancelled')]
        return self._run_batch_items(indices)

    @Slot()
    def retryFailedExports(self):
        if not self.canRetryFailedExports:return
        indices=[]
        for index,item in enumerate(self._export_items):
            if item['status'] not in ('failed','present'):continue
            plan=self._batch_plan[index]
            original=Path(plan['output']);output=original;number=2
            while output.exists():
                output=original.with_name(f'{original.stem}_{number}{original.suffix}');number+=1
            if output!=original:
                plan['output']=str(output);item['output']=str(output)
            item['status']='queued';item['error']=''
            try:self._batch_journal.record(self._batch_job_id,index,'queued',output=plan['output'])
            except (OSError,ValueError) as error:
                item['status']='failed';item['error']='无法保存任务状态：'+str(error);continue
            indices.append(index)
        if indices:self._run_batch_items(indices)
    @Property(str, notify=parameterChanged)
    def lensStatus(self):
        if self._current < 0: return ''
        if not self._settings.lens_correction:
            return '镜头校正已关闭'
        if not self._lens_status.get('correction_enabled', False):
            return '正在匹配镜头…'
        return self._lens_status.get('summary', '正在匹配镜头…')
    @Property(str, notify=parameterChanged)
    def lensProfilePath(self):
        return self._lens_status.get('profile_path', '') if self._settings.lens_correction else ''

    def _edit_path(self, path):
        return self._store/(hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()+'.json')
    def _persist(self):
        if self._current < 0: return
        self._persist_photo(self._current, self._settings)

    def _persist_photo(self, index, settings):
        settings=film_settings(settings)
        photo = self._photos[index]
        photo['settings'] = asdict(settings)
        target = self._edit_path(photo['path'])
        try:
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(version=4, settings=photo['settings']), ensure_ascii=False,allow_nan=False), encoding='utf-8')
            os.replace(temp,target)
            if not self._suppress_library_persist:
                record=dict(version=4,settings=photo['settings'])
                if self._library_source_record and photo['path']==self._library_context.get('row',{}).get('path'):
                    record['source_edit']=self._library_source_record
                self.persisted.emit(photo['path'],record)
        except OSError as error:
            self.toast.emit('编辑记录保存失败：'+str(error))

    @Slot()
    def importPhotos(self):
        if not self._exporting:self.importWorkspaceRequested.emit()

    @Slot('QVariantList')
    def dropPhotos(self, urls):
        self.add_paths([QUrl(u).toLocalFile() for u in urls])

    @Slot()
    def pastePhotos(self):
        if not self.import_mime(self._clipboard.mimeData()):
            self.toast.emit('剪贴板中没有可导入的本地照片。请复制照片文件或图片后按 Ctrl+V。')

    def import_mime(self, mime):
        if self._exporting or self._closed: return False
        paths = mime_paths(mime)
        if paths:
            self.add_paths(paths)
            return True
        if mime and mime.hasImage():
            image = mime.imageData()
            if not isinstance(image, QImage):
                image = image.toImage() if hasattr(image, 'toImage') else QImage()
            if image.isNull(): return False
            directory = self._store.parent / 'clipboard'
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / ('粘贴照片-' + time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + '.png')
            if not image.save(str(path), 'PNG'):
                self.toast.emit('剪贴板图片保存失败，请检查缓存目录空间。')
                return False
            self.add_paths([str(path)])
            return True
        return False

    def add_paths(self, paths):
        if self._exporting or self._closed: return
        new_paths=[]
        existing_index=None
        existing_paths={os.path.normcase(photo['path']):i for i,photo in enumerate(self._photos)}
        queued_keys={os.path.normcase(path) for path in self._queued_paths}
        for path in paths:
            if not path: continue
            # Lexical normalization avoids filesystem IO on the GUI thread.
            path = os.path.abspath(path)
            if Path(path).suffix.lower() not in PHOTO_EXTENSIONS:
                self.toast.emit('跳过非照片文件：'+Path(path).name)
                continue
            existing = existing_paths.get(os.path.normcase(path))
            if existing is not None:
                if existing_index is None: existing_index=existing
                continue
            key=os.path.normcase(path)
            if key in queued_keys: continue
            queued_keys.add(key)
            self._queued_paths.add(path)
            new_paths.append(path)
        if existing_index is not None: self.selectPhoto(existing_index)
        if new_paths:
            # Publish metadata in bounded chunks. A selected preview gets a
            # turn between chunks instead of waiting for hundreds of RAWs.
            # The first preview must not wait for fifteen other metadata reads.
            self._import_queue.append((new_paths[:1],existing_index is None,self._generation))
            for start in range(1,len(new_paths),16):
                self._import_queue.append((new_paths[start:start+16],False,self._generation))
            self.stateChanged.emit()
            self.timer.start(0)

    def _read_imports(self, paths):
        loaded,errors=[],[]
        for path in paths:
            try:
                path=str(Path(path).resolve())
                if not Path(path).is_file():raise FileNotFoundError('照片文件不存在')
                width,height=0,0
                try:
                    width,height=photo_dimensions(path)
                    dims=f'{width:,} × {height:,}'
                except Exception: dims='RAW · 相机原始文件'
                saved = self._settings_for_import()
                record = self._edit_path(path)
                if record.exists():
                    try:
                        data=json.loads(record.read_text(encoding='utf-8'))
                        saved=settings_from_record(data)
                    except (OSError,ValueError,KeyError,TypeError): pass
                loaded.append(dict(path=path,name=Path(path).name,dimensions=dims,width=width,height=height,settings=asdict(saved)))
            except Exception as error:
                errors.append(f'无法打开 {Path(path).name}：{error}')
        return loaded,errors

    @Slot(int)
    def selectPhoto(self, index):
        if self._exporting or not 0<=index<len(self._photos): return
        self._selected={index}
        self._selection_anchor=index
        self.selectionChanged.emit()
        self._activate_photo(index)

    def _activate_photo(self, index):
        self._finish_mask_stroke()
        if self._before is not None: self.endEdit()
        if not self._suppress_library_persist:self._persist()
        self._current=index
        self._crop_request+=1;self._crop_busy=False;self._crop_source=''
        self._minimum_frame_generation=self._generation+1
        self._settings=_full_settings(self._photos[index]['settings'])
        self._before=None
        self._edit_generation=-1
        self._lens_status={}
        self._frame=self._original=''
        self.frameChanged.emit()
        self.photosChanged.emit()
        self._changed()

    @Slot(int,int)
    def selectWithModifiers(self, index, modifiers):
        if self._exporting or not 0<=index<len(self._photos): return
        shift = bool(modifiers & Qt.ShiftModifier.value)
        toggle = bool(modifiers & Qt.ControlModifier.value)
        if shift and self._selection_anchor >= 0:
            section=set(range(min(index,self._selection_anchor),max(index,self._selection_anchor)+1))
            self._selected=(self._selected | section) if toggle else section
        elif toggle:
            if index in self._selected:
                if len(self._selected)>1: self._selected.remove(index)
            else: self._selected.add(index)
            self._selection_anchor=index
        else:
            self._selected={index}
            self._selection_anchor=index
        target=index if index in self._selected else min(self._selected)
        if target!=self._current: self._activate_photo(target)
        self.selectionChanged.emit()

    @Slot()
    def selectAllPhotos(self):
        if self._exporting or not self._photos: return
        self._selected=set(range(len(self._photos)))
        if self._current<0: self._activate_photo(0)
        self.selectionChanged.emit()

    @Slot()
    def removeSelectedPhotos(self):
        """Remove session entries; never unlink source files or saved edits."""
        if self._exporting or self._closed or not self._photos: return
        removed=set(self._selected or {self._current}) & set(range(len(self._photos)))
        if not removed: return
        if self._before is not None: self.endEdit()
        self._persist()
        old_current=self._current
        old_photos=self._photos
        surviving=[i for i in range(len(old_photos)) if i not in removed]
        mapping={old:new for new,old in enumerate(surviving)}
        self._history={mapping[i]:values for i,values in self._history.items() if i in mapping}
        self._redo={mapping[i]:values for i,values in self._redo.items() if i in mapping}
        self._photos=[old_photos[i] for i in surviving]
        self._photo_model.replace(self._photos)
        for i in removed: self.provider.discard(old_photos[i]['thumbnail'].rsplit('/',1)[-1])
        paths={old_photos[i]['path'] for i in removed}
        with self._cache_lock:
            for cache in (self._cache,self._prepared,self._mask_bases):
                for key in list(cache):
                    if key[0] in paths: cache.pop(key,None)
        # An active worker may finish later; invalidate it before changing slots.
        self._generation+=1
        self._minimum_frame_generation=self._generation
        self._fast_pending=False
        self.fast_timer.stop()
        self.timer.stop()
        self._current=-1
        self._before=None
        self._selected=set()
        self._selection_anchor=-1
        self._pending=False
        if self._photos:
            target=mapping.get(old_current,min(sum(i<old_current for i in surviving),len(surviving)-1))
            self._selected={target}
            self._selection_anchor=target
            self._activate_photo(target)
        else:
            self._settings=_full_settings()
            self._frame=self._original=''
            self._lens_status={}
            self.provider.discard('frame','original')
            self._status='照片已移除 · 原片保留'
            self.frameChanged.emit()
            self.photosChanged.emit()
            self.stateChanged.emit()
        self.selectionChanged.emit()
        self.toast.emit(f'已从列表移除 {len(removed)} 张照片，磁盘原片和编辑记录均保留。')

    def _push(self, state, index=None):
        index=self._current if index is None else index
        self._history.setdefault(index,[]).append(state)
        self._history[index]=self._history[index][-64:]
        self._redo[index]=[]

    @Slot()
    def beginEdit(self):
        if not self._exporting and self._before is None:
            self._before=self._settings
            self._edit_generation=self._generation
    @Slot()
    def endEdit(self):
        self._mask_stroke=None
        if self._before and self._before!=self._settings: self._push(self._before)
        self._before=None
        self._edit_generation=-1
        self._persist()
        self.stateChanged.emit()
        if self._pending: self.timer.start(120)

    def _replace_masks(self, layers):
        if self._current<0 or self._exporting: return
        layers=normalize_masks(layers)
        if layers==self._settings.masks:return
        def visible(masks):
            # A new neutral mask has no effect on the photo. Painting it (or
            # renaming any mask) must not compete with its live overlay by
            # re-running spectral rendering for identical pixels.
            return tuple(replace(layer,name='') for layer in masks
                if layer.enabled and layer.opacity>0 and any(getattr(layer,key)
                    for key in MASK_PARAMETER_LIMITS if key!='opacity'))
        pixels_changed=visible(layers)!=visible(self._settings.masks)
        continuous=self._before is not None
        if not continuous:self._push(self._settings)
        self._settings=replace(self._settings,masks=layers)
        if continuous:
            self._sync_editor_bindings()
            if pixels_changed:self._changed(continuous=True)
            else:self.parameterChanged.emit()
        elif pixels_changed:self._changed()
        else:self.stateChanged.emit()
        if not continuous:self._persist()

    def _finish_mask_stroke(self):
        if self._mask_stroke is not None: self.endEdit()

    @Slot(result=str)
    def addMask(self):
        return self.addMaskOfKind('brush')

    @Slot(str,result=str)
    def addMaskOfKind(self, kind):
        if kind not in ('brush','linear','radial'): return ''
        if self._exporting or self._current<0: return ''
        if len(self._settings.masks)>=32:
            self.toast.emit('每张照片最多可创建 32 个蒙版。')
            return ''
        self._finish_mask_stroke()
        ident=uuid.uuid4().hex
        label={'brush':'画笔','linear':'线性','radial':'径向'}[kind]
        layer=MaskLayer(id=ident,name=f'{label} {len(self._settings.masks)+1}',kind=kind)
        self._active_masks[self._photos[self._current]['path']]=ident
        self._replace_masks((*self._settings.masks,layer))
        return ident

    @Slot(str)
    def selectMask(self, ident):
        if self._current<0 or not any(layer.id==ident for layer in self._settings.masks): return
        self._finish_mask_stroke()
        self._active_masks[self._photos[self._current]['path']]=ident
        self.stateChanged.emit()

    @Slot(str,str)
    def renameMask(self, ident, name):
        if self._exporting or not name.strip(): return
        self._replace_masks(tuple(replace(layer,name=name.strip()[:80]) if layer.id==ident else layer for layer in self._settings.masks))

    @Slot(str,bool)
    def setMaskEnabled(self, ident, enabled):
        if self._exporting: return
        self._finish_mask_stroke()
        self._replace_masks(tuple(replace(layer,enabled=enabled) if layer.id==ident else layer for layer in self._settings.masks))

    @Slot()
    def invertMask(self):
        if self._exporting or not self.activeMaskId: return
        self._finish_mask_stroke()
        self._replace_masks(tuple(replace(layer,inverted=not layer.inverted) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot()
    def clearMask(self):
        if self._exporting or not self.activeMaskId: return
        self._finish_mask_stroke()
        self._replace_masks(tuple(replace(layer,strokes=(),inverted=False) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot()
    def removeLastMaskStroke(self):
        if self._exporting or not self.activeMaskId:return
        self._finish_mask_stroke()
        self._replace_masks(tuple(replace(layer,strokes=layer.strokes[:-1])
            if layer.id==self.activeMaskId and layer.kind=='brush' and layer.strokes else layer
            for layer in self._settings.masks))

    @Slot()
    def deleteMask(self):
        if self._exporting or not self.activeMaskId: return
        self._finish_mask_stroke()
        ident=self.activeMaskId
        self._replace_masks(tuple(layer for layer in self._settings.masks if layer.id!=ident))

    @Slot(str,float)
    def updateMaskParameter(self, key, value):
        if self._exporting or not self.activeMaskId or key not in MASK_PARAMETER_LIMITS or not math.isfinite(value): return
        low,high=MASK_PARAMETER_LIMITS[key]
        value=max(low,min(high,value))
        self._replace_masks(tuple(replace(layer,**{key:value}) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot(str,float)
    def updateMaskGeometry(self,key,value):
        limits={'radius_x':(.002,2),'radius_y':(.002,2),'rotation':(-360,360),'feather':(0,1)}
        if self._exporting or not self.activeMaskId or key not in limits or not math.isfinite(value): return
        low,high=limits[key]
        self._replace_masks(tuple(replace(layer,**{key:max(low,min(high,value))}) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot(str,float,float)
    def updateMaskPoint(self,key,u,v):
        if self._exporting or key not in ('start','end','center') or not all(math.isfinite(value) for value in (u,v)): return
        self._replace_masks(tuple(replace(layer,**{key:(max(0,min(1,u)),max(0,min(1,v)))}) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot('QVariantMap')
    def updateMaskGeometryMap(self,values):
        """One pointer sample is one immutable mask update, not three renders."""
        if self._exporting or not self.activeMaskId:return
        changes={}
        limits={'radius_x':(.002,2),'radius_y':(.002,2),'rotation':(-360,360),'feather':(0,1)}
        for key,value in values.items():
            if key in ('start','end','center'):
                if isinstance(value,(tuple,list)) and len(value)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in value):
                    changes[key]=tuple(max(0,min(1,float(v))) for v in value)
            elif key in limits and isinstance(value,(int,float)) and math.isfinite(value):
                low,high=limits[key];changes[key]=max(low,min(high,float(value)))
        if changes:self._replace_masks(tuple(replace(layer,**changes) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))

    @Slot(str,'QVariantList')
    def setCurvePoints(self,channel,points):
        if self._exporting or self._current<0 or channel not in ('master','red','green','blue','luma'): return
        data=asdict(self._settings.curves);data[channel]=points
        self._replace_tools(curves=normalize_curves(data))

    @Slot(str)
    def resetCurve(self,channel):
        self.setCurvePoints(channel,[[0,0],[1,1]])

    @Slot(str,'QVariantList')
    def setSceneCurvePoints(self,channel,points):
        if self._exporting or self._current<0 or channel not in ('master','red','green','blue','luma'):return
        data=asdict(self._settings.scene_curves);data[channel]=points
        self._replace_tools(scene_curves=normalize_curves(data))

    @Slot(str)
    def resetSceneCurve(self,channel):self.setSceneCurvePoints(channel,[[0,0],[1,1]])

    @Slot(str,str,float,bool)
    def setParametricCurve(self,channel,key,value,scene=False):
        if channel not in CHANNELS or not math.isfinite(value):return
        if key not in ('shadows','darks','lights','highlights','shadow_split','midtone_split','highlight_split'):return
        field='scene_curves' if scene else 'curves'
        data=asdict(getattr(self._settings,field));data['parametric'][channel][key]=value
        self._replace_tools(**{field:normalize_curves(data)})

    @Slot(str,bool)
    def resetParametricCurve(self,channel,scene=False):
        if channel not in CHANNELS:return
        field='scene_curves' if scene else 'curves'
        data=asdict(getattr(self._settings,field));data['parametric'][channel]={}
        self._replace_tools(**{field:normalize_curves(data)})

    @Slot(str,str,float)
    def setChannelMixer(self,row,channel,value):
        if row not in ('red','green','blue') or channel not in ('red','green','blue') or not math.isfinite(value):return
        data=asdict(self._settings.channel_mixer);data[row][channel]=value
        self._replace_tools(channel_mixer=normalize_channel_mixer(data))

    @Slot(str)
    def resetChannelMixer(self,row):
        data=asdict(self._settings.channel_mixer)
        if row in data:data[row]={}
        else:data={}
        self._replace_tools(channel_mixer=normalize_channel_mixer(data))

    @Slot(str,str,float)
    def updateHslParameter(self,band,key,value):
        if self._exporting or self._current<0 or band not in BANDS or key not in ('hue','saturation','luminance') or not math.isfinite(value): return
        data=asdict(self._settings.hsl);data[band][key]=value
        self._replace_tools(hsl=normalize_hsl(data))

    @Slot(str)
    def resetHsl(self,band):
        if self._exporting or self._current<0: return
        data=asdict(self._settings.hsl)
        if band in BANDS: data[band]=dict(hue=0,saturation=0,luminance=0)
        else: data=asdict(HslSettings())
        self._replace_tools(hsl=normalize_hsl(data))

    @Slot(str,str,float)
    def updateGradingParameter(self,zone,key,value):
        if self._exporting or self._current<0 or not math.isfinite(value): return
        data=asdict(self._settings.grading)
        if zone in ('master','shadows','midtones','highlights') and key in ('hue','saturation','luminance'): data[zone][key]=value
        elif not zone and key in ('balance','blending'): data[key]=value
        else: return
        self._replace_tools(grading=normalize_grading(data))

    @Slot(str,float,float)
    def setGradingWheel(self,zone,hue,saturation):
        if self._exporting or self._current<0 or zone not in ('master','shadows','midtones','highlights') or not all(math.isfinite(v) for v in (hue,saturation)): return
        data=asdict(self._settings.grading);data[zone].update(hue=hue,saturation=saturation)
        self._replace_tools(grading=normalize_grading(data))

    @Slot(str)
    def resetGrading(self,zone):
        if self._exporting or self._current<0: return
        data=asdict(self._settings.grading)
        if zone in ('master','shadows','midtones','highlights'): data[zone]=dict(hue=0,saturation=0,luminance=0)
        else: data=asdict(ColorGrading())
        self._replace_tools(grading=normalize_grading(data))

    def _replace_tools(self,**changes):
        if self._current<0 or self._exporting: return
        updated=film_settings(replace(self._settings,**changes))
        if updated==self._settings: return
        continuous=self._before is not None
        if not continuous:self._push(self._settings)
        self._settings=updated
        if continuous:self._sync_editor_bindings()
        self._changed(continuous=continuous)
        if not continuous:self._persist()

    @Slot(str,result=bool)
    def applyStyle(self,ident):
        if self._exporting or self._current<0: return False
        style=next((item for item in self._styles if item.get('id')==ident),None)
        if not style: return False
        if self._before is not None: self.endEdit()
        self._persist();changed=[]
        for index in sorted(self._selected or {self._current}):
            previous=_full_settings(self._photos[index]['settings'])
            data=asdict(previous)
            data.update({key:style['settings'][key] for key in STYLE_FIELDS if key in style.get('settings',{})})
            updated=_full_settings(data)
            if updated==previous: continue
            self._push(previous,index);self._persist_photo(index,updated);changed.append(index)
            if index==self._current:self._settings=updated
        if self._current in changed:self._changed()
        else:self.stateChanged.emit()
        self.photosChanged.emit()
        self.toast.emit(f'已应用「{style["name"]}」至 {len(changed)} 张照片，可逐张撤销。')
        return True

    @Slot()
    def clearStyleLut(self):
        if self._exporting or self._current<0 or not self._settings.look_lut:return
        if self._before is not None:self.endEdit()
        self._replace_tools(look_lut='')

    @Slot(result=bool)
    def importStyle(self):
        if self._exporting:return False
        paths,_=QFileDialog.getOpenFileNames(None,'导入风格预设','','风格预设 (*.sfpreset *.json *.xmp)')
        return self.import_style_path(paths[0]) if paths else False

    def import_style_path(self,path):
        if self._exporting:return False
        try:
            source=Path(path)
            if source.stat().st_size>2*1024**2:raise ValueError('预设文件过大（上限 2 MiB）')
            style=json.loads(import_style_json(source.read_bytes(),source.name))
            if style['settings'].get('look_lut') and not known_lut(style['settings']['look_lut']):
                raise ValueError('预设依赖的色彩资源未安装')
            custom=[item for item in self._styles if item.get('kind') not in BUILTIN_STYLE_KINDS and item['id']!=style['id']]
            custom.append(style)
            self._custom_style_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self._custom_style_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(custom,ensure_ascii=False,allow_nan=False),encoding='utf-8')
            os.replace(temporary,self._custom_style_path)
            self._styles=[item for item in self._styles if item['id']!=style['id']]+[style]
            self.stylesChanged.emit()
            self._imported_style_id=style['id'];self.stateChanged.emit()
            if style.get('warnings'):self.toast.emit(style['warnings'][0])
            return True
        except (OSError,ValueError,TypeError,KeyError) as error:
            self.toast.emit('预设导入失败：'+str(error));return False

    def _geometry_allowed(self):
        return self._current>=0 and not self._exporting

    def _crop_allowed(self):
        return self._current>=0 and not self._exporting

    @Slot(str,float)
    def updateGeometry(self,key,value):
        if key not in ('rotation','vertical','horizontal','aspect','scale') or not math.isfinite(value) or not self._geometry_allowed(): return
        data=asdict(self._settings.geometry);data[key]=value
        self._replace_tools(geometry=normalize_geometry(data))

    @Slot(int)
    def rotateQuarterTurn(self,direction):
        if not self._geometry_allowed():return
        if self._before is not None:self.endEdit()
        geometry=self._settings.geometry
        crop=geometry.crop
        turns=int(direction)%4
        for _ in range(turns):
            left,top,right,bottom=crop
            crop=(1-bottom,left,1-top,right)
        self._replace_tools(geometry=replace(geometry,quarter_turns=(geometry.quarter_turns+turns)%4,crop=crop))

    @Slot(str,bool)
    def setGeometryFlag(self,key,value):
        if key not in ('flip_horizontal','flip_vertical','auto_crop') or not self._geometry_allowed(): return
        self._replace_tools(geometry=replace(self._settings.geometry,**{key:value}))

    @Slot()
    def resetGeometry(self):
        if self._geometry_allowed(): self._replace_tools(geometry=Geometry())

    @Slot(str,'QVariantList',result='QVariantMap')
    def applyGuidedGeometry(self,mode,points):
        if not self._geometry_allowed():return dict(ok=False,error='请先选择可以编辑的照片')
        try:
            from shared.geometry import solve_guided_geometry
            width,height=self.sourceDimensions
            geometry,diagnostics=solve_guided_geometry(width,height,self._settings.geometry,mode,points)
            if self._before is not None:self.endEdit()
            self._replace_tools(geometry=geometry)
            return dict(ok=True,**diagnostics)
        except (ValueError,TypeError) as error:
            return dict(ok=False,error=str(error))

    @Slot(result=bool)
    def requestCropPreview(self):
        if not self._crop_allowed(): return False
        path=self._photos[self._current]['path'];settings=self._settings
        self._crop_request+=1;request=self._crop_request
        self._crop_busy=True;self._crop_source='';self.stateChanged.emit();self.frameChanged.emit()
        def work():
            uncropped=replace(settings,geometry=replace(settings.geometry,crop=(0.,0.,1.,1.)))
            return self._render_photo(path,uncropped,1400)[1]
        context=dict(kind='crop',path=path,request=request)
        worker=Job(work,context);key=id(worker);context['job']=key;self._jobs[key]=worker
        worker.signals.done.connect(self._done);self.crop_pool.start(worker)
        return True

    @Slot('QVariantList')
    def applyCrop(self,bounds):
        if not self._crop_allowed(): return
        if self._before is not None: self.endEdit()
        self._replace_tools(geometry=replace(self._settings.geometry,crop=normalize_geometry({'crop':bounds}).crop))

    @Slot(float,float,float,float,float,bool,result=str)
    def beginMaskStroke(self, u, v, radius, feather, flow, erase):
        layer=next((layer for layer in self._settings.masks if layer.id==self.activeMaskId),None)
        if self._exporting or self._current<0 or layer is None or layer.kind!='brush': return ''
        if not all(math.isfinite(value) for value in (u,v,radius,feather,flow)): return ''
        self._finish_mask_stroke()
        self.beginEdit()
        token=uuid.uuid4().hex
        stroke=MaskStroke(points=((max(0,min(1,u)),max(0,min(1,v))),),radius=max(.002,min(.5,radius)),feather=max(0,min(1,feather)),flow=max(0,min(1,flow)),erase=erase)
        self._mask_stroke=(token,self._photos[self._current]['path'],self.activeMaskId)
        self._replace_masks(tuple(replace(layer,strokes=(*layer.strokes,stroke)) if layer.id==self.activeMaskId else layer for layer in self._settings.masks))
        return token

    @Slot(str,'QVariantList')
    def appendMaskPoints(self, token, points):
        if not self._mask_stroke or self._mask_stroke[0]!=token or self._current<0 or self._mask_stroke[1]!=self._photos[self._current]['path']: return
        valid=[]
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2: continue
            if all(isinstance(value,(int,float)) and math.isfinite(value) for value in point): valid.append(tuple(max(0,min(1,float(value))) for value in point))
        if not valid: return
        ident=self._mask_stroke[2]
        layers=[]
        for layer in self._settings.masks:
            if layer.id==ident and layer.strokes:
                stroke=replace(layer.strokes[-1],points=(*layer.strokes[-1].points,*valid))
                layer=replace(layer,strokes=(*layer.strokes[:-1],stroke))
            layers.append(layer)
        self._replace_masks(layers)

    @Slot(str)
    def endMaskStroke(self, token):
        if self._mask_stroke and self._mask_stroke[0]==token: self.endEdit()
    @Slot(str,float)
    def updateParameter(self, key, value):
        if self._exporting or self._current<0: return
        if key not in PARAMETER_LIMITS or not math.isfinite(value): return
        value=max(PARAMETER_LIMITS[key][0],min(PARAMETER_LIMITS[key][1],value))
        if getattr(self._settings,key)==value: return
        if self._before is None: self._push(self._settings)
        changes={key:value}
        self._settings=replace(self._settings,**changes)
        continuous=self._before is not None
        if continuous: self._parameters.sync_field(self._settings,key)
        self._changed(continuous=continuous)
        if not continuous: self._persist()
    @Slot(str,str,float)
    def setLevelParameter(self,channel,key,value):
        from shared.levels import normalize_levels
        if channel not in ('master','red','green','blue') or key not in ('black','white','gamma','output_black','output_white') or not math.isfinite(value):return
        levels=self._settings.levels
        data=asdict(levels);data[channel][key]=value
        self._replace_tools(levels=normalize_levels(data))
    @Slot(str)
    def resetLevels(self,channel):
        from shared.levels import LevelChannel
        if channel in ('master','red','green','blue'):self._replace_tools(levels=replace(self._settings.levels,**{channel:LevelChannel()}))

    @Slot(str)
    def autoAdjust(self,kind):
        if kind not in ('white_balance','levels','tone','geometry','geometry_vertical','geometry_full') or self._current<0 or self._exporting or self._auto_adjust_busy:return
        if self._before is not None:self.endEdit()
        self._auto_adjust_busy=True;self.autoAdjustChanged.emit()
        path=self.currentPath;generation=self._generation;settings=self._settings
        def work():
            from shared.auto_adjust import analyze_auto
            from .raw_source import source_pixels,source_metadata
            from .native_spectral import process_editor
            prepared,_=self._prepared_source(path,settings,800)
            metadata=source_metadata(prepared);pixels=source_pixels(prepared)
            if kind in ('levels','tone','geometry','geometry_vertical','geometry_full'):
                neutral=replace(settings,temperature=6500,tint=0) if kind.startswith('geometry') else settings
                pixels=process_editor(pixels,neutral,stage='pre',exposure_ev=metadata.get('baseline_exposure_ev',0),
                    source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'])
                return analyze_auto(pixels,kind,settings)
            return analyze_auto(pixels,kind,settings,source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'])
        self._submit(work,dict(kind='auto_adjust',path=path,generation=generation))
    @Slot(str)
    def resetParameter(self,key):
        if key not in PARAMETER_LIMITS:return
        self._replace_tools(**{key:getattr(Settings(),key)})

    @Slot(str,str)
    def autoMeter(self,target,method):
        if target not in ('exposure','filter_pack','both') or method not in ('balanced','center','protect_highlights','protect_shadows'):return
        self._analyze_scene(target,method)

    @Slot()
    def measureLatitude(self):
        self._analyze_scene('latitude',self._settings.metering_method)

    def _analyze_scene(self,target,method):
        if self._current<0 or self._exporting or self._analysis_busy:return
        if self._before is not None:self.endEdit()
        path=self._photos[self._current]['path'];settings=replace(self._settings,metering_method=method)
        try:
            stat=Path(path).stat();stamp=(stat.st_mtime_ns,stat.st_size)
        except OSError:
            stamp=(0,0)
        fields=('stock','paper','temperature','tint','calibration_red_hue','calibration_red_saturation',
                'calibration_green_hue','calibration_green_saturation','calibration_blue_hue',
                'calibration_blue_saturation','sharpening','noise_luminance','noise_color',
                'lens_correction','defringe')
        if target=='latitude':
            fields+=('exposure','print_exposure','print_y','print_m','density_curve_gamma',
                'dir_couplers_amount','scene_latitude_norm','scene_latitude_rolloff','scene_latitude_max_lift')
        cache_key=(path,stamp,target,method,tuple(getattr(settings,key) for key in fields),self._render_epochs.get(path,0))
        generation=self._generation
        self._analysis_busy=True;self.stateChanged.emit()
        def work():
            with self._analysis_cache_lock:
                cached=self._analysis_cache.get(cache_key)
                if cached is not None:
                    self._analysis_cache.move_to_end(cache_key)
                    return cached
            from .native_spectral import process_editor,solve_spectral,scene_latitude
            from .raw_source import source_pixels
            if target=='filter_pack':
                result=solve_spectral(None,settings,target=target)
            else:
                source,_=self._prepared_source(path,settings,640)
                from .raw_source import source_metadata
                metadata=source_metadata(source)
                full_size=tuple(source.info.get('source_size',source.size))
                values=process_editor(source_pixels(source),settings,stage='pre',
                    source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'],
                    exposure_ev=metadata.get('baseline_exposure_ev',0),source_size=full_size,
                    pixel_scale=(full_size[0]/source.width,full_size[1]/source.height))
                result=scene_latitude(values,settings) if target=='latitude' else solve_spectral(values,settings,target=target)
            with self._analysis_cache_lock:
                self._analysis_cache[cache_key]=result
                self._analysis_cache.move_to_end(cache_key)
                while len(self._analysis_cache)>8:self._analysis_cache.popitem(last=False)
            return result
        self._submit(work,dict(kind='analysis',generation=generation,path=path,target=target,method=method,cache_key=cache_key))

    @Slot()
    def applyLatitude(self):
        if self._current<0 or self._exporting:return
        record=self._analysis
        if record.get('path')!=self.currentPath or record.get('generation')!=self._generation:return
        fit=record.get('latitude',{}).get('fit',{})
        if not fit.get('valid'):return
        raw=asdict(self._settings);raw.update(fit.get('params_delta',{}))
        self._replace_tools(**{key:getattr(Settings.from_mapping(raw),key)
            for key in ('scene_latitude_active','scene_latitude_norm','scene_latitude_highlight_knee',
                        'scene_latitude_highlight_room','scene_latitude_shadow_knee','scene_latitude_shadow_room',
                        'scene_latitude_rolloff','scene_latitude_max_lift')})
        self._analysis=dict(record,generation=self._generation,applied=True)
        self.stateChanged.emit()

    @Slot()
    def resetLatitude(self):
        self._replace_tools(scene_latitude_active=False)
    @Slot(str)
    def setPaper(self, paper):
        if self._exporting or self._current<0 or paper not in PAPER_IDS|{'auto'}: return
        if self._settings.paper==paper and not self._settings.scan_film and not self._settings.digital_intermediate:return
        if paper!='auto' and paper not in {item['id'] for item in paper_choices(self._settings.stock)}: return
        if self._before is not None: self.endEdit()
        self._push(self._settings)
        self._settings=replace(self._settings,paper=paper,minilab_active=False,scan_film=False,digital_intermediate=False)
        self._changed()
        self._persist()

    @Slot(str)
    def setGrainType(self, grain_type):
        if self._exporting or self._current<0 or grain_type not in ('classic','fine','coarse','clustered') or self._settings.grain_type==grain_type: return
        if self._before is None: self._push(self._settings)
        self._settings=replace(self._settings,grain_type=grain_type)
        self._changed()
        if self._before is None: self._persist()
    @Slot(str)
    def selectStock(self, ident):
        self._select_stock(ident)

    @Slot(str)
    def chooseFilm(self,ident):
        self._select_stock(ident,enable=True)

    def _select_stock(self,ident,enable=False):
        if self._exporting or self._current<0 or ident not in [s['id'] for s in self._stocks]: return
        if self._before is not None: self.endEdit()
        self._persist()
        changed=[]
        for index in sorted(self._selected or {self._current}):
            previous=_full_settings(self._photos[index]['settings'])
            if previous.stock==ident and (not enable or previous.film_enabled): continue
            self._push(previous,index)
            updated=replace(previous,stock=ident,minilab_active=False,film_enabled=previous.film_enabled or enable)
            from shared.darkroom import BLACK_AND_WHITE
            if ident in BLACK_AND_WHITE or scans_directly(ident):updated=replace(updated,digital_intermediate=False)
            if ident in BLACK_AND_WHITE:updated=replace(updated,hdr_enabled=False)
            self._persist_photo(index,updated)
            if index==self._current: self._settings=updated
            changed.append(index)
        if self._current in changed: self._changed()
        else: self.stateChanged.emit()
        self.photosChanged.emit()
        if len(self._selected)>1: self.toast.emit(f'已将胶片应用至 {len(changed)} 张照片；各张曝光与显影参数保持独立。')

    @Slot()
    def applyCurrentSettings(self):
        self.copySettings(list(DEFAULT_CATEGORIES))
        self.pasteSettings(list(DEFAULT_CATEGORIES))
    @Slot(bool)
    def setSpectral(self, value):
        # Compatibility for older automation; public UI has only full mode.
        if self._exporting or self._settings.spectral: return
        self._push(self._settings)
        self._settings=replace(self._settings,spectral=True)
        self._changed()
        self._persist()
    @Slot(str,bool)
    def setCorrection(self,key,value):
        if key not in ('lens_correction','defringe','antihalation_removed'):return
        self._replace_tools(**{key:bool(value)})
    @Slot(bool)
    def setFilmEnabled(self,value):
        values=dict(film_enabled=True) if value else dict(film_enabled=False,hdr_enabled=False)
        self._replace_tools(**values)
    @Slot()
    def undo(self):
        if self._exporting: return
        if self._before is not None: self.endEdit()
        if not self.canUndo: return
        self._redo.setdefault(self._current,[]).append(self._settings)
        self._settings=self._history[self._current].pop()
        self._changed()
        self._persist()
    @Slot()
    def redo(self):
        if self._exporting or not self.canRedo: return
        self._history.setdefault(self._current,[]).append(self._settings)
        self._settings=self._redo[self._current].pop()
        self._changed()
        self._persist()
    @Slot()
    def reset(self):
        if self._exporting or not self.canReset: return
        if self._before is not None: self.endEdit()
        self._push(self._settings)
        self._settings=_full_settings()
        self._changed()
        self._persist()
    def _changed(self, *, continuous=False):
        self._settings=film_settings(self._settings)
        # Retire an old full-resolution tile immediately. Recomputing settings
        # bindings or publishing a broad state event here defeats live input.
        self._full_detail._edited()
        self._generation+=1
        self._pending=self._current>=0
        self._status='正在精细显影…' if self._pending else '准备就绪'
        if self._pending and self._current >= 0:
            self._fast_pending=True
            if not self.fast_timer.isActive(): self.fast_timer.start()
        if continuous:
            self.parameterChanged.emit()
        else:
            self.stateChanged.emit()
        self.timer.start()
    @Slot()
    def retry(self):
        if self._current<0: self.importPhotos()
        else:
            path=self._photos[self._current]['path']
            with self._cache_lock:
                self._render_epochs[path]=self._render_epochs.get(path,0)+1
                for key in [key for key in self._mask_bases if key[0]==path]: self._mask_bases.pop(key,None)
                for key in [key for key in self._prepared if key[0]==path]:
                    self._prepared.pop(key)
                # A neutral optical preparation can share its PIL object with
                # the decoded source. Detach that object without re-decoding;
                # do not clear a dict which an in-flight worker may be reading.
                for key,image in list(self._cache.items()):
                    if key[0]==path and hasattr(image,'_spektrafilm_preview_cache'): self._cache[key]=image.copy()
            self._changed()

    @Slot(bool)
    def setActualSize(self,value):
        if self._exporting:return
        # Preview and full detail are independent surfaces. A zoom no longer
        # replaces the entire frame with a multi-hundred-MB GUI image.
        self._full_detail.set_enabled(value)

    def _submit(self,fn,context,*,fast=False,export=False):
        worker=Job(fn,context)
        key=id(worker)
        self._jobs[key]=worker
        context['job']=key
        worker.signals.done.connect(self._done)
        (self.export_pool if export else self.fast_pool if fast else self.pool).start(worker)

    def _cache_source(self,key,image):
        try:
            info=Path(key[0]).stat()
            stamp=(info.st_mtime_ns,info.st_size)
        except OSError: stamp=None
        with self._cache_lock:
            self._source_stamps[key[0]]=stamp
            self._cache[key]=image
            self._cache.move_to_end(key)
            self._trim_source_cache_locked()

    def _trim_source_cache_locked(self):
        def cached_bytes():
            seen=set()
            def size(value):
                if value is None or id(value) in seen:return 0
                seen.add(id(value))
                if hasattr(value,'nbytes'):
                    # Crops/strips may share a whole-array owner.
                    owner=getattr(value,'base',None)
                    return size(owner) if hasattr(owner,'nbytes') else value.nbytes
                if hasattr(value,'info') and hasattr(value,'width'):
                    total=value.width*value.height*3
                    total+=size(getattr(value,'_spektrafilm_source_pixels',value.info.get('_spektrafilm_source_pixels')))
                    total+=size(getattr(value,'_spektrafilm_render_pixels',None))
                    for name in ('_spektrafilm_preview_cache','_spektrafilm_spectral_stage_cache',
                                 '_spektrafilm_prepared_editor','_spektrafilm_comparison_cache','_spektrafilm_hdr_base'):
                        total+=size(getattr(value,name,{}))
                    return total
                if isinstance(value,dict):return sum(size(item) for item in value.values())
                if isinstance(value,(list,tuple)):return sum(size(item) for item in value)
                return 0
            return sum(size(cache) for cache in (self._cache,self._prepared,self._mask_bases))
        for cache,limit in ((self._cache,6),(self._prepared,3),(self._mask_bases,4)):
            while len(cache)>limit:cache.popitem(last=False)
        # The budget covers all retained CPU preview stages, rather than each
        # map independently. In-flight full-resolution jobs have separate lives.
        while cached_bytes()>self._cache_budget:
            cache=next((item for item in (self._mask_bases,self._prepared,self._cache) if item),None)
            if cache is None:break
            cache.popitem(last=False)

    def _source(self,path,edge):
        info=Path(path).stat()
        stamp=(info.st_mtime_ns,info.st_size)
        with self._cache_lock:
            if path in self._source_stamps and self._source_stamps[path]!=stamp:
                for key in [key for key in self._cache if key[0]==path]:self._cache.pop(key)
                for key in [key for key in self._prepared if key[0]==path]:self._prepared.pop(key)
                for key in [key for key in self._mask_bases if key[0]==path]:self._mask_bases.pop(key)
                self._source_stamps[path]=stamp
            image=self._cache.get((path,edge))
            larger=next((value for (p,e),value in reversed(self._cache.items()) if p==path and edge and (e==0 or e>=edge)),None)
        if image is not None: return image
        if larger is not None:
            image=larger.copy()
            from PIL import Image
            image.thumbnail((edge,edge),Image.Resampling.LANCZOS)
        else:
            from .full_detail import read_cached_photo
            image=read_cached_photo(path,edge or None,reader=read_photo)
        self._cache_source((path,edge),image)
        return image

    def _configure_native_budget(self):
        budget=max(0,self._cache_budget//2)
        if self._native_budget_applied==budget:return
        from .native_spectral import set_cache_limits
        set_cache_limits(max_entries=2,source_bytes=min(192*1024**2,budget//2),retained_bytes=budget)
        self._native_budget_applied=budget

    def _begin_full_export(self):
        self._full_detail.pause()
        self.fast_pool.waitForDone();self.pool.waitForDone();self.crop_pool.waitForDone()
        self._output_proof.pool.waitForDone()
        self._full_detail.pool.waitForDone()
        # Do not retain preview stages while a high-resolution frame owns
        # decode/spectral/encoder storage. Current displayed QImages stay visible.
        with self._cache_lock:
            self._cache.clear();self._prepared.clear();self._mask_bases.clear()
        from .native_spectral import clear_sessions
        clear_sessions()

    def _prepared_source(self,path,settings,edge):
        """Share immutable optical preparation between render and analysis."""
        original=self._source(path,edge)
        epoch=self._render_epochs.get(path,0)
        status={}
        if settings.lens_correction or settings.defringe:
            optical_key=(path,edge,self._source_stamps.get(path),settings.lens_correction,settings.defringe,epoch)
            with self._cache_lock:cached=self._prepared.get(optical_key)
            if cached is None:
                cached=prepare_photo_source(original,path,settings)
                if 0<edge<=2560:
                    with self._cache_lock:
                        self._prepared[optical_key]=cached
                        self._trim_source_cache_locked()
            original,status=cached
        return original,status

    def _render_photo(self,path,settings,edge,interactive=False,color_config=None):
        settings=film_settings(settings)
        self._configure_native_budget()
        start=time.perf_counter()
        original,status=self._prepared_source(path,settings,edge)
        epoch=self._render_epochs.get(path,0)
        # Keep bounded film results; original-size viewing/export stays uncached.
        cacheable=0<edge<=self._preferences.values['preview_long_edge']
        if cacheable and not hasattr(original,'_spektrafilm_preview_cache'):
            original._spektrafilm_preview_cache={}
        display_key=tuple(sorted(color_config.items())) if color_config else None
        key=(path,edge,interactive,self._source_stamps.get(path),settings,epoch,display_key)
        with self._cache_lock:
            developed=self._mask_bases.get(key) if cacheable else None
            if developed is not None: self._mask_bases.move_to_end(key)
        if developed is None:
            from . import native_spectral
            native = (os.environ.get('SPEKTRAFILM_COMPUTE', 'auto').lower() != 'cpu'
                      and native_spectral.available())
            if color_config and native:
                from .imaging import render_pixels
                from .color_display import transform_pixels,standard_srgb_display,canvas_pixels
                from .raw_source import display_image,quantize_display
                from shared.color_management import convert_pixels
                standard_display=standard_srgb_display(color_config)
                if standard_display:
                    display=render_pixels(original,settings,preview=True,preserve_headroom=True)
                    histogram=quantize_display(display[::max(1,len(display)//256),::max(1,display.shape[1]//384)])
                    shown,space=canvas_pixels(display,'sRGB',color_config)
                    developed=display_image(transform_pixels(shown,space,color_config))
                else:
                    wide=render_pixels(original,settings,preview=True,output_color_space='ProPhoto RGB')
                    sample=wide[::max(1,len(wide)//256),::max(1,wide.shape[1]//384)]
                    histogram=quantize_display(convert_pixels(sample,'ProPhoto RGB','sRGB'))
                    shown,space=canvas_pixels(wide,'ProPhoto RGB',color_config)
                    developed=display_image(transform_pixels(shown,space,color_config))
                developed._spektrafilm_histogram_sample=histogram
            else:
                developed=(render_interactive(original,replace(settings,spectral=False))
                           if interactive and not native else render(original,settings,preview=True))
            with self._cache_lock:
                self._trim_source_cache_locked()
            if cacheable:
                with self._cache_lock:
                    self._mask_bases[key]=developed
                    self._mask_bases.move_to_end(key)
                    self._trim_source_cache_locked()
        from . import native_spectral
        native = (os.environ.get('SPEKTRAFILM_COMPUTE', 'auto').lower() != 'cpu'
                  and native_spectral.available())
        # Keep comparison and rendered output on the same crop; never mutate
        # or re-cache the cropped view as the full source.
        comparison_key=(settings.geometry,display_key,bool(native))
        saved=getattr(original,'_spektrafilm_comparison_cache',None) if cacheable else None
        if saved is not None and saved[0] == comparison_key:
            comparison=saved[1]
        else:
            comparison=apply_geometry_image(original,settings.geometry)
            if color_config and native:
                from .color_display import transform_pixels,canvas_pixels
                from .raw_source import display_image
                import numpy as np
                shown,space=canvas_pixels(np.asarray(comparison,dtype=np.float32)/255,'sRGB',color_config)
                comparison=display_image(transform_pixels(shown,space,color_config))
            if cacheable:original._spektrafilm_comparison_cache=(comparison_key,comparison)
        return comparison,developed,round((time.perf_counter()-start)*1000),dict(status,spectral_backend='Vulkan' if native else 'CPU')

    def _preview_images(self,path,settings,edge,interactive=False):
        original,output,milliseconds,status=self._render_photo(path,settings,edge,interactive,self._color_display.snapshot())
        # Detach PIL storage while still in the worker. The GUI completion slot
        # only swaps immutable handles; large refined frames cannot stall input
        # with two synchronous PIL -> QImage conversions.
        import numpy as np
        # Histogram sampling remains off the input thread and uses the current
        # displayed result; its 256 bins never carry full image arrays into QML.
        sample=getattr(output,'_spektrafilm_histogram_sample',None)
        if sample is None:sample=np.asarray(output)[::max(1,output.height//256),::max(1,output.width//384),:3]
        channels={name:np.bincount(sample[...,i].ravel(),minlength=256).tolist() for i,name in enumerate(('red','green','blue'))}
        grey=np.rint(sample@np.array([.2126,.7152,.0722])).astype(np.uint8)
        channels['master']=np.bincount(grey.ravel(),minlength=256).tolist()
        return (QImage(ImageQt(original)).copy(),QImage(ImageQt(output)).copy(),milliseconds,status,channels)

    def _schedule_fast(self):
        if self._closed or self._exporting or self._fast_busy or not self._fast_pending: return
        if self._current<0:
            self._fast_pending=False
            return
        self._fast_busy=True
        self._fast_pending=False
        path=self._photos[self._current]['path']
        settings=film_settings(self._settings)
        generation=self._generation
        def work():
            if self._closed or generation!=self._generation: return None
            return self._preview_images(path,settings,640,interactive=True)
        self._submit(work,dict(kind='fast',generation=generation,path=path),fast=True)
    def _schedule(self):
        if self._closed or self._busy or self._exporting: return
        if self._import_queue and not (self._pending and self._current>=0):
            paths,select,generation=self._import_queue.pop(0)
            self._busy=True
            self._importing=True
            self._status=f'正在打开 {len(paths)} 张照片…'
            self.stateChanged.emit()
            self._submit(lambda:self._read_imports(paths),dict(kind='import',paths=paths,select=select,generation=generation))
            return
        if self._current<0 or not self._pending: return
        if self._before is not None: return
        self._pending=False
        self._busy=True
        self.stateChanged.emit()
        path=self._photos[self._current]['path']
        settings=film_settings(self._settings)
        edge=self._preview_edge
        self._submit(lambda:self._preview_images(path,settings,edge),dict(kind='render',generation=self._generation))
    @Slot(object)
    def _done(self, result):
        self._jobs.pop(result['job'],None)
        if self._closed: return
        kind=result['kind']
        fast=kind=='fast'
        if fast: self._fast_busy=False
        elif kind not in ('export','batch_export','crop','analysis','cache','auto_adjust'): self._busy=False
        if kind=='import': self._importing=False
        if kind=='auto_adjust':
            self._auto_adjust_busy=False;self.autoAdjustChanged.emit()
            if result['generation']==self._generation and result['path']==self.currentPath:
                if result['ok']:
                    proposal=result['value'];changes=proposal.get('changes',{})
                    if changes:
                        normalized=Settings.from_mapping(dict(asdict(self._settings),**changes))
                        self._replace_tools(**{key:getattr(normalized,key) for key in changes})
                    else:self.toast.emit(proposal.get('reason','未找到可靠的自动调整'))
                else:self.toast.emit('自动调整失败：'+result['error'])
        elif kind=='cache':
            self.toast.emit('缓存已清理')
        elif kind=='analysis':
            self._analysis_busy=False
            try:
                source_stat=Path(result['path']).stat()
                source_current=(source_stat.st_mtime_ns,source_stat.st_size)==result['cache_key'][1]
            except (OSError,KeyError,IndexError,TypeError):source_current=False
            if result['generation']==self._generation and result['path']==self.currentPath and source_current:
                if not result['ok']:self.toast.emit('测量失败：'+result['error'])
                elif result['target']=='latitude':
                    self._analysis=dict(path=result['path'],generation=self._generation,latitude=result['value'])
                else:
                    solved=result['value'].get('solved_params',{})
                    changes={} if result['target']=='filter_pack' else dict(metering_method=result['method'])
                    if 'exposure_compensation_ev' in solved:
                        low,high=PARAMETER_LIMITS['exposure']
                        changes['exposure']=max(low,min(high,float(solved['exposure_compensation_ev'])))
                    if 'y_filter_neutral' in solved or 'm_filter_neutral' in solved:
                        from .native_spectral import parameters
                        base=parameters(self._settings)
                        for axis in ('y','m'):
                            key=axis+'_filter_neutral'
                            if key in solved:changes['print_'+axis]=max(-100,min(100,(float(solved[key])-base[key])/60*100))
                    self._replace_tools(**changes)
                    self._analysis=dict(path=result['path'],generation=self._generation,metering=result['value'])
        elif kind=='crop':
            if result['request']==self._crop_request and self._current>=0 and result['path']==self._photos[self._current]['path']:
                self._crop_busy=False
                if result['ok']:
                    self.provider.publish('crop',result['value'])
                    self._crop_source=f'image://photos/crop?v={self._crop_request}'
                    self.frameChanged.emit()
                else: self.toast.emit('裁切预览加载失败：'+result['error'])
        elif kind=='import':
            self._queued_paths.difference_update(result['paths'])
            first=len(self._photos)
            if result['ok']:
                loaded,errors=result['value']
                # Resolve aliases off-thread, then deduplicate canonical paths.
                known={os.path.normcase(photo['path']) for photo in self._photos}
                unique=[]
                for photo in loaded:
                    key=os.path.normcase(photo['path'])
                    if key not in known:unique.append(photo);known.add(key)
                loaded=unique
                for photo in loaded:
                    key='thumb'+uuid.uuid4().hex
                    self.provider.register_thumbnail(key,photo['path'])
                    photo['thumbnail']='image://photos/'+key
                self._photo_model.append(loaded)
                self.photosChanged.emit()
                if loaded and self._pending_library_open is None and result['select'] and result['generation']==self._generation:
                    self.selectPhoto(first)
                elif loaded and self._pending_library_open is None and self._current<0:
                    self.selectPhoto(first)
                elif not self._pending:
                    self._status='准备就绪' if loaded else '照片打开失败'
                for error in errors: self.toast.emit(error)
                self._apply_pending_library()
            else:
                self._status='照片打开失败'
                self.toast.emit(result['error'])
        elif kind=='export':
            self._exporting=False
            self._status='导出完成' if result['ok'] else '导出失败'
            self.toast.emit('照片已导出：'+result['path'] if result['ok'] else result['error'])
        elif kind=='batch_export':
            self._exporting=False
            value=result['value'] if result['ok'] else dict(errors=[result.get('error','导出未完成')],cancelled=False)
            for index,item in enumerate(self._export_items):
                if item['status'] in ('queued','running'):
                    item['status']='cancelled' if value.get('cancelled') else 'failed'
                    item['error']='' if value.get('cancelled') else result.get('error','导出未完成')
                    try:self._batch_journal.record(self._batch_job_id,index,item['status'],error=item['error'])
                    except (OSError,ValueError):pass
            self._batch_progress=sum(item['status'] in ('completed','failed','present','changed') for item in self._export_items)
            self._batch_result=self._batch_result_from_items(bool(value.get('cancelled')))
            if self._batch_job_id and all(item['status']=='completed' for item in self._export_items):
                try:
                    self._batch_journal.clear(self._batch_job_id)
                    self._batch_job_id=''
                except OSError:pass
            self._batch_recovery_prompt=False
            self.exportItemsChanged.emit()
            count=len(self._batch_result['completed'])
            errors=self._batch_result['errors']
            cancelled=self._batch_result.get('cancelled',False)
            self._status=f'批量导出{"已停止" if cancelled else "完成"} · {count}/{self._batch_total} 张' + (f' · {len(errors)} 张失败' if errors else '')
            self.toast.emit(self._status + ('；'+str(errors[0]) if errors else '；原片保持不变。'))
            if result.get('open_after') and count:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._batch_result['completed'][0]).parent)))
        elif result['generation']==self._generation or (fast and self._before is not None and self._current>=0 and result.get('path')==self._photos[self._current]['path'] and result['generation']>=self._minimum_frame_generation and result['generation']>self._edit_generation and result['generation']>self._display_generation):
            quality=1 if fast else 2
            generation=result['generation']
            obsolete=generation<self._display_generation or (self._quality_generation==generation and quality<self._quality)
            if result['ok'] and result['value'] is not None and not obsolete:
                original,output,self._render_ms,*lens_status=result['value']
                if len(lens_status)>1:self._level_histogram=lens_status[1];self.levelHistogramChanged.emit()
                self._diagnostic_samples=(self._diagnostic_samples+[self._render_ms])[-128:]
                self._diagnostics.append(self._render_ms,self._preferences.values['diagnostic_retention_days'])
                if lens_status: self._lens_status=lens_status[0]
                self._display_generation=generation
                self._quality_generation,self._quality=generation,quality
                self.provider.publish('original',original)
                self.provider.publish('frame',output)
                self._published+=1
                self._frame=f'image://photos/frame?v={self._published}'
                self._original=f'image://photos/original?v={self._published}'
                self._status='准备就绪'
                self.frameChanged.emit()
            elif not result['ok'] and not obsolete:
                self._status='显影失败 · 点击重试'
                self.toast.emit(result['error'])
        if kind in ('fast','render') and self._before is not None:
            self.parameterChanged.emit()
        else:
            self.stateChanged.emit()
        if self._fast_pending: self.fast_timer.start(0)
        if self._import_queue or (self._pending and self._before is None):
            if not self.timer.isActive(): self.timer.start(10)
    @Slot(str)
    def exportRecipe(self,ident):
        if not self.canStartExport:return
        recipe=next((item for item in self._output_recipes if item.id==ident),None)
        if recipe is None:return
        initial=self._last_export_dir or str(Path(self.currentPath).parent)
        directory=QFileDialog.getExistingDirectory(None,'选择导出位置',initial,location_key='photo-export')
        if not directory:return
        self._last_export_dir=directory
        self.export_recipe_batch(recipe,directory)

    def export_recipe_batch(self,recipe,destination_root=None):
        if not self.canStartExport:return False
        if self._batch_job_id and any(item['status']!='completed' for item in self._export_items):
            self.toast.emit('请先继续、重试或清除上次的批量出片任务。');return False
        if self._before is not None:self.endEdit()
        self._persist()
        try:
            recipe=normalize_recipe(recipe)
            error=self.outputRecipeError(asdict(recipe))
            if error:raise ValueError(error)
            planned=plan_recipe_exports(self._photos,self.selectedIndices or [self._current],recipe,destination_root)
        except (OSError,ValueError) as error:self.toast.emit(str(error));return False
        if not planned:
            self.toast.emit('目标文件已存在，已按配方跳过');return False
        return self._start_recipe_export(planned,recipe)

    def _start_recipe_export(self,planned,recipe):
        if self._batch_job_id and any(item['status']!='completed' for item in self._export_items):
            self.toast.emit('请先处理上次的批量出片任务。');return False
        try:
            manifest=self._batch_journal.create(recipe,planned)
        except (OSError,ValueError,TypeError) as error:
            self.toast.emit('无法创建批量恢复记录：'+str(error));return False
        self._batch_job_id=manifest['job_id']
        self._batch_plan=[];self._export_items=[]
        for index,record in enumerate(manifest['items']):
            settings=Settings.from_mapping(record['settings'])
            self._batch_plan.append(dict(source=record['source'],output=record['output'],settings=settings,
                source_identity=record['source_identity']))
            self._export_items.append(dict(id=str(index),name=Path(record['source']).name,path=record['source'],
                status='queued',phase='',output=record['output'],error=''))
        self._recipe_export_snapshot=(recipe,tuple((item['source'],item['output'],item['settings']) for item in self._batch_plan))
        self._batch_recovery_prompt=False
        self.exportItemsChanged.emit()
        return self._run_batch_items(list(range(len(self._batch_plan))))

    def _run_batch_items(self,indices):
        if self._exporting or not self._batch_plan or not self._batch_job_id:return False
        recipe=self._recipe_export_snapshot[0]
        runnable=[]
        for index in indices:
            item=self._export_items[index];plan=self._batch_plan[index]
            if item['status']=='completed':continue
            if not source_matches(plan['source'],plan['source_identity']):
                item['status']='changed';item['phase']='';item['error']='原片已移动、删除或内容时间已变化；为保护编辑快照，未导出。'
                try:self._batch_journal.record(self._batch_job_id,index,'changed',error=item['error'])
                except (OSError,ValueError) as error:item['error']='无法保存任务状态：'+str(error)
                continue
            if Path(plan['output']).exists():
                item['status']='present';item['phase']='';item['error']='目标文件已存在，未覆盖；重试时会使用新文件名。'
                try:self._batch_journal.record(self._batch_job_id,index,'present',error=item['error'])
                except (OSError,ValueError) as error:item['error']='无法保存任务状态：'+str(error)
                continue
            was_queued=item['status']=='queued'
            item['status']='queued';item['phase']='';item['error']=''
            if not was_queued:
                try:self._batch_journal.record(self._batch_job_id,index,'queued',output=plan['output'])
                except (OSError,ValueError) as error:
                    item['status']='failed';item['error']='无法保存任务状态：'+str(error);continue
            runnable.append(index)
        self._batch_progress=sum(item['status'] in ('completed','failed','present','changed') for item in self._export_items)
        self._batch_total=len(self._export_items)
        self._batch_result=self._batch_result_from_items()
        self.exportItemsChanged.emit()
        if not runnable:
            self._status=f'批量任务已检查 · {self._batch_progress}/{self._batch_total} 张'
            self.stateChanged.emit()
            return False
        encoded_proof=self._output_proof.exportArtifact()
        self._output_proof.release()
        self._cancel_export.clear()
        self._generation+=1
        self._pending=self._fast_pending=False
        self.timer.stop();self.fast_timer.stop()
        self._exporting=True
        self._status=f'正在批量导出 · {self._batch_progress}/{self._batch_total} 张'
        self.exportItemsChanged.emit()
        self.stateChanged.emit()
        # GUI progress callbacks update _batch_progress while this worker runs.
        # Capture the starting count so later phases cannot count it twice.
        progress_base=self._batch_progress
        def work():
            # Drain earlier interactive work before full-resolution allocation.
            # This wait runs in the export worker, never the GUI thread.
            self._begin_full_export()
            completed,errors=[],[]
            journal_error=''
            for position,index in enumerate(runnable):
                plan=self._batch_plan[index]
                source,target,settings=plan['source'],plan['output'],plan['settings']
                if self._cancel_export.is_set():break
                if not source_matches(source,plan['source_identity']):
                    error='原片已移动、删除或内容时间已变化；为保护编辑快照，未导出。'
                    try:self._batch_journal.record(self._batch_job_id,index,'changed',error=error)
                    except (OSError,ValueError) as failure:journal_error=str(failure)
                    worker.signals.progress.emit(dict(done=progress_base+position+1,total=self._batch_total,
                        item=index,status='changed',error=error,phase=''))
                    errors.append(Path(source).name+'：'+error)
                    if journal_error:break
                    continue
                if Path(target).exists():
                    error='目标文件已存在，未覆盖；重试时会使用新文件名。'
                    try:self._batch_journal.record(self._batch_job_id,index,'present',error=error)
                    except (OSError,ValueError) as failure:journal_error=str(failure)
                    worker.signals.progress.emit(dict(done=progress_base+position+1,total=self._batch_total,
                        item=index,status='present',error=error,phase=''))
                    errors.append(Path(source).name+'：'+error)
                    if journal_error:break
                    continue
                try:
                    def phase(value):
                        worker.signals.progress.emit(dict(done=progress_base+position,total=self._batch_total,
                            phase=value,item=index,status='running'))
                    phase('decode')
                    export_recipe(source,target,settings,recipe,cancel=self._cancel_export,progress=phase,encoded_proof=encoded_proof)
                except ExportCancelled:
                    try:self._batch_journal.record(self._batch_job_id,index,'cancelled')
                    except (OSError,ValueError) as error:journal_error=str(error)
                    worker.signals.progress.emit(dict(done=progress_base+position,total=self._batch_total,
                        item=index,status='cancelled',phase=''))
                    break
                except Exception as error:
                    if self._cancel_export.is_set():break
                    errors.append(Path(source).name+'：'+str(error))
                    try:self._batch_journal.record(self._batch_job_id,index,'failed',error=str(error))
                    except (OSError,ValueError) as failure:journal_error=str(failure)
                    worker.signals.progress.emit(dict(done=progress_base+position+1,total=self._batch_total,
                        item=index,status='failed',error=str(error),phase=''))
                    if journal_error:break
                    continue
                try:
                    self._batch_journal.record(self._batch_job_id,index,'completed')
                except (OSError,ValueError) as error:
                    journal_error=str(error)
                    errors.append(Path(source).name+'：输出已生成，但恢复状态写入失败。')
                    worker.signals.progress.emit(dict(done=progress_base+position+1,total=self._batch_total,
                        item=index,status='present',error='输出已生成，但恢复状态写入失败；文件已保留。',phase=''))
                    break
                completed.append(target)
                worker.signals.progress.emit(dict(done=progress_base+position+1,total=self._batch_total,
                    item=index,status='completed',phase=''))
            return dict(completed=completed,errors=errors,cancelled=self._cancel_export.is_set(),journal_error=journal_error)
        context=dict(kind='batch_export',open_after=recipe.open_after)
        worker=Job(work,context)
        key=id(worker);context['job']=key;self._jobs[key]=worker
        worker.signals.progress.connect(self._export_progress)
        worker.signals.done.connect(self._done)
        self.export_pool.start(worker)
        return True

    @Slot(str)
    def exportPreset(self, preset):
        if not self.canStartExport: return
        if preset not in EXPORT_PRESETS: return
        indices=self.selectedIndices or [self._current]
        if preset=='RAW' and any(Path(self._photos[i]['path']).suffix.lower() not in RAW_EXTENSIONS for i in indices):
            self.toast.emit('RAW 原片仅适用于所选相机 RAW 文件；普通图片无法转换为 RAW。')
            return
        if self._before is not None: self.endEdit()
        initial=self._last_export_dir or str(Path(self._photos[indices[0]]['path']).parent)
        directory=QFileDialog.getExistingDirectory(None,'选择导出位置',initial,location_key='photo-export')
        if not directory: return
        self._last_export_dir=directory
        self.export_batch(preset,destination_root=directory)

    def export_to(self,path,edge=0,quality=95,*,preset=None):
        """Dispatch the same export used by the save dialog and runtime checks."""
        if not self.canStartExport: return False
        # Export is non-destructive and never overwrites an existing result.
        # Direct callers may bypass the normal recipe planner, so resolve a
        # collision here as well instead of leaving the user at a dead-end
        # toast/dialog. The selected folder and extension stay unchanged.
        requested=Path(path)
        target=requested
        counter=2
        while target.exists():
            target=requested.with_name(f'{requested.stem}_{counter}{requested.suffix}')
            counter+=1
        if target != requested:
            self.toast.emit('目标文件已存在，已自动使用新文件名：'+target.name)
        path=str(target)
        source=self._photos[self._current]['path']
        if preset is not None and (preset not in EXPORT_PRESETS or (preset=='RAW' and not self.canExportRaw)):
            self.toast.emit('所选导出格式不可用于当前照片。')
            return False
        settings=film_settings(self._settings)
        encoded_proof=self._output_proof.exportArtifact()
        self._output_proof.release()
        self._cancel_export.clear()
        self._batch_total=self._batch_progress=0
        self._generation+=1
        self._pending=False
        self._fast_pending=False
        self.timer.stop()
        self.fast_timer.stop()
        self._exporting=True
        self._status='正在保存 RAW 原片…' if preset=='RAW' else '正在压缩分享照片…' if preset=='JPG_SHARE' else '正在导出原尺寸照片…'
        self.stateChanged.emit()
        def work():
            self._begin_full_export()
            return export_preset(source,path,settings,preset,encoded_proof=encoded_proof,cancel=self._cancel_export) if preset else export_photo(source,path,settings,edge,quality)
        self._submit(work,dict(kind='export',path=path),export=True)
        return True

    def export_batch(self,preset,destination_root=None):
        if preset not in EXPORT_PRESETS:return False
        ident={'JPG_HIGH':'jpg-high','JPG_SHARE':'jpg-share','TIFF':'tiff','RAW':'raw'}[preset]
        recipe=next(item for item in DEFAULT_RECIPES if item.id==ident)
        recipe=replace(recipe,subfolder=EXPORT_PRESETS[preset]['folder'])
        return self.export_recipe_batch(recipe,destination_root)

    @Slot(object)
    def _export_progress(self,value):
        if 'item' in value and 0<=value['item']<len(self._export_items):
            item=self._export_items[value['item']]
            for key in ('status','phase','error'):
                if key in value:item[key]=value[key]
            self.exportItemsChanged.emit()
        self._batch_progress=value['done']
        phase={'decode':'读取原片','render':'显影','encode':'编码写入'}.get(value.get('phase'))
        self._status=(f'第 {self._batch_progress+1}/{self._batch_total} 张 · {phase}' if phase
            else f'正在批量导出 · {self._batch_progress}/{self._batch_total} 张')
        self.stateChanged.emit()

    @Slot()
    def cancelBatchExport(self):
        if self._exporting and self._batch_total:
            self._cancel_export.set()
            from .native_spectral import cancel_active
            cancel_active()
            self._status='正在完成当前照片，随后停止…'
            self.stateChanged.emit()

    def close(self):
        self._closed=True
        self._scene_histogram.close()
        self._full_detail.close()
        self._film_library.close()
        self._output_proof.close()
        self._gui_automation.close()
        self._update_check.close()
        self._import_workspace.close()
        self._composition.close()
        self._light_table.close()
        self._library_workspace.shutdown()
        self._mask_overlay.close()
        self._import_queue.clear()
        self._queued_paths.clear()
        self.timer.stop()
        self.fast_timer.stop()
        self._cancel_export.set()
        self._persist()
        try:self._diagnostics.save()
        except OSError:pass
        self.pool.waitForDone()
        self.fast_pool.waitForDone()
        self.export_pool.waitForDone()
        self.crop_pool.waitForDone()
        # Release exact source maps after all consumers stop. Windows cannot
        # remove a session/cache directory while an ndarray still owns a map.
        self._jobs.clear()
        with self._cache_lock:
            self._cache.clear();self._prepared.clear();self._mask_bases.clear()
        self._analysis_cache.clear()
