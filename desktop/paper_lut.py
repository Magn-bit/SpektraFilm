"""Export the engine's shipped print+scan table, without rebaking a photograph.

Input is normalized negative dye density, NOT photo RGB or Cineon. The paired
film and output transfer are part of the table's contract. Spatial effects and
the editor's current controls cannot be represented by this pointwise table.
"""
from __future__ import annotations

import ctypes as ct
from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from PySide6.QtCore import QObject, Slot


@lru_cache(maxsize=1)
def catalogue():
    from .native_spectral import _RUNTIME
    value=json.loads((_RUNTIME/'resources/print_luts.json').read_text(encoding='utf-8'))
    if not isinstance(value,dict):raise ValueError('相纸 LUT 目录无效')
    return value


def paper_info(settings):
    from shared.darkroom import resolve_paper
    paper=resolve_paper(settings.stock,settings.paper)
    try:entry=catalogue().get(paper)
    except (OSError,ValueError):entry=None
    available=isinstance(entry,dict) and isinstance(entry.get('lut_size'),int) and 2<=entry['lut_size']<=256
    return dict(available=available,paper=paper,paired_film=entry.get('paired_film','') if available else '',
                size=entry.get('lut_size',0) if available else 0,
                output_color_space=entry.get('output_color_space','') if available else '',
                reason='' if available else '当前相纸没有配套 LUT')


def native_table(paper):
    """Copy engine-owned float32 while holding the existing engine lane lock."""
    from . import native_spectral as native
    with native._LOCK:
        engine=native._get_engine()
        if engine is None:raise native.NativeSpectralError(native._INITIALIZATION_ERROR)
        lib=engine.lib
        function=lib.spk_print_lut_table
        function.argtypes=[ct.c_void_p,ct.c_char_p,ct.POINTER(ct.POINTER(ct.c_float)),ct.POINTER(ct.c_uint32)]
        function.restype=ct.c_int32
        get_catalogue=lib.spk_print_lut_catalog
        get_catalogue.argtypes=[ct.c_void_p];get_catalogue.restype=ct.c_char_p
        entries=json.loads(get_catalogue(engine.handle))
        entry=entries.get(paper)
        if not isinstance(entry,dict):raise ValueError('当前相纸没有配套 LUT')
        pointer=ct.POINTER(ct.c_float)();size=ct.c_uint32()
        if function(engine.handle,paper.encode('utf-8'),ct.byref(pointer),ct.byref(size)):
            raise native.NativeSpectralError(engine.error())
        side=size.value
        if not pointer or not 2<=side<=256 or side!=entry.get('lut_size'):
            raise ValueError('相纸 LUT 数据尺寸无效')
        table=np.ctypeslib.as_array(pointer,shape=(side**3*3,)).copy().reshape(side,side,side,3)
    if not np.isfinite(table).all():raise ValueError('相纸 LUT 包含无效数值')
    return table,dict(entry)


def write_cube(path,paper,table,metadata,*,overwrite=False):
    """Atomically write red-fastest .cube; retain native values and precision."""
    path=Path(path)
    if path.suffix.lower()!='.cube':path=path.with_suffix('.cube')
    side=table.shape[0]
    if table.shape!=(side,side,side,3) or not 2<=side<=256 or not np.isfinite(table).all():
        raise ValueError('相纸 LUT 数据无效')
    if path.exists() and not overwrite:raise FileExistsError('文件已存在，请换一个名称')
    path.parent.mkdir(parents=True,exist_ok=True)
    title='SpektraFilm print LUT '+str(paper).replace('"','').replace('\n',' ')
    # The .cube format has no color-management metadata. Keep its exact
    # interpretation next to the samples, in comments understood by people.
    header=[f'TITLE "{title}"',
        '# INPUT: normalized negative CMY dye density, each channel 0..1.',
        '# Use the matching print-LUT density axes (the legacy density tap).',
        '# NOT ordinary photo RGB, NOT Cineon log digital intermediate.',
        '# OUTPUT: '+str(metadata.get('output_color_space','unknown')),
        '# OUTPUT_CCTF_ENCODING: '+str(bool(metadata.get('output_cctf_encoding'))).lower(),
        '# PAIRED_FILM: '+str(metadata.get('paired_film','unknown')),
        '# DECLARED_PAIRING: '+str(bool(metadata.get('declared_pairing'))).lower(),
        '# Other films have unmeasured spectral dye mismatch.',
        '# Fixed shipped print+scan transform; current adjustment settings are not baked.',
        '# Excludes grain, halation, glare, local masks, geometry and film edges.',
        f'LUT_3D_SIZE {side}','DOMAIN_MIN 0 0 0','DOMAIN_MAX 1 1 1']
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',dir=path.parent,
                prefix=path.name+'.',suffix='.tmp',delete=False) as output:
            temporary=Path(output.name)
            output.write('\n'.join(header)+'\n')
            # Engine storage is [r,g,b,component]; .cube changes R first.
            np.savetxt(output,table.transpose(2,1,0,3).reshape(-1,3),fmt='%.9g')
            output.flush();os.fsync(output.fileno())
        if overwrite:os.replace(temporary,path)
        elif os.name=='nt':os.rename(temporary,path)  # fails if target appeared
        else:os.link(temporary,path);temporary.unlink()
        return dict(path=str(path),paper=paper,size=side,bytes=path.stat().st_size,**metadata)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def export_paper_lut(paper,path,*,overwrite=False):
    table,metadata=native_table(paper)
    return write_cube(path,paper,table,metadata,overwrite=overwrite)


class _PaperLutTask(QObject):
    """Keep completion on the GUI thread, using the controller's Job lane."""
    def __init__(self,controller,paper,path,job_class):
        super().__init__(controller)
        self.ctrl=controller
        self.worker=job_class(lambda:export_paper_lut(paper,path),dict(kind='paper_lut'))
        self.key=id(self.worker);self.worker.context['job']=self.key
        controller._jobs[self.key]=self.worker
        self.worker.signals.done.connect(self._done)
        controller._paper_lut_active=True
        controller.stateChanged.emit()
        controller.export_pool.start(self.worker)

    @Slot(object)
    def _done(self,result):
        ctrl=self.ctrl
        ctrl._jobs.pop(self.key,None);ctrl._paper_lut_active=False
        if not ctrl._closed:
            ctrl.stateChanged.emit()
            ctrl.toast.emit('相纸 LUT 已导出：'+result['value']['path'] if result['ok'] else '相纸 LUT 导出失败：'+result['error'])
        self.deleteLater()


def start_export(controller,paper,path,job_class):
    if getattr(controller,'_paper_lut_active',False) or controller._closed:return False
    _PaperLutTask(controller,paper,path,job_class)
    return True
