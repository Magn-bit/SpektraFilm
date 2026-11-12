"""Single representative full-size physical film export, without file hashes."""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]


def main():
    import numpy as np
    import tifffile
    from desktop.imaging import Settings,read_photo,_tiff_strips,SRGB,_publish_export
    from desktop.film_canvas import render_film_edge
    from desktop import native_spectral
    from desktop.raw_source import source_metadata
    source=Path(sys.argv[1]).resolve()
    folder=Path(sys.argv[2]).resolve();folder.mkdir(parents=True,exist_ok=True)
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    query=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    def memory():
        c=Counters();c.cb=ctypes.sizeof(c)
        if not query(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):raise ctypes.WinError()
        return c
    samples=[];events=[];done=threading.Event();started=time.perf_counter()
    def monitor():
        while not done.is_set():
            value=dict(seconds=time.perf_counter()-started,working_set_mib=memory().WorkingSetSize/1024**2)
            try:
                result=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],
                    capture_output=True,text=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                parts=result.stdout.strip().split(',')
                value.update(gpu_all_processes_mib=float(parts[0]),gpu_utilization_percent=float(parts[1]))
            except (ValueError,subprocess.SubprocessError,OSError):pass
            samples.append(value);done.wait(.75)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    def progress(value):
        current=dict(seconds=time.perf_counter()-started,fraction=round(float(value),6))
        if not events or current['fraction']>events[-1]['fraction']:
            events.append(current);print('PROGRESS',json.dumps(current),flush=True)
    output=folder/(source.stem+'_Portra400_physical.tif')
    report=dict(source=str(source),source_bytes=before[0],source_mtime_ns=before[1],
        scope='One full original RAW decode, physical 135 gate crop and expanded native film canvas, original source pixel density, complete optical pipeline, TIFF16 Deflate/ICC. GPU sampling includes other processes.')
    try:
        stage=time.perf_counter();image=read_photo(str(source),None)
        report.update(source_dimensions=list(image.size),source_metadata=source_metadata(image),decode_seconds=time.perf_counter()-stage)
        print('DECODE',json.dumps(dict(dimensions=image.size,seconds=report['decode_seconds'])),flush=True)
        settings=Settings(film_enabled=True)
        options=dict(style='film',frame_format='135',edge=0,edge_view='strip',carrier='none',
            gate='auto',frame_number=12,camera_seed=31,frame_seed=17,date_imprint_active=True,date='2026-11-09',
            placements=[dict(path=str(source),zoom=1.,pan_x=.5,pan_y=.5)])
        stage=time.perf_counter();pixels,geometry=render_film_edge(image,settings,options,preview=False,progress=progress)
        report.update(render_prepare_seconds=time.perf_counter()-stage,geometry=geometry,
            output_dimensions=[pixels.shape[1],pixels.shape[0]],native=native_spectral.backend_info())
        print('RENDER',json.dumps(dict(seconds=report['render_prepare_seconds'],dimensions=report['output_dimensions'],bounded=geometry['bounded_report'])),flush=True)
        stage=time.perf_counter()
        def encode(target):
            rows,strips=_tiff_strips(pixels)
            handle=tifffile.FileHandle(target,mode='wb',name='SpektraFilm.tif')
            tifffile.imwrite(handle,data=strips,shape=pixels.shape,dtype=np.uint16,photometric='rgb',
                compression='deflate',rowsperstrip=rows,metadata=None,iccprofile=SRGB)
            return pixels.shape[1],pixels.shape[0]
        _publish_export(output,encode)
        report['encode_seconds']=time.perf_counter()-stage
        with tifffile.TiffFile(output) as file:
            page=file.pages[0];assert page.dtype==np.uint16 and page.samplesperpixel==3 and page.bitspersample==16
            assert [page.imagewidth,page.imagelength]==report['output_dimensions'];assert page.tags.get(34675)
            first=next(page.segments())[0]
            report.update(bits_per_sample=page.bitspersample,first_strip_distinct_values=int(np.unique(first).size),
                          first_strip_min=int(first.min()),first_strip_max=int(first.max()))
        after=(source.stat().st_size,source.stat().st_mtime_ns)
        assert before==after,'source size or mtime changed'
        assert geometry['bounded_report']['exact_iir_sweeps'] and not geometry['bounded_report']['finite_iir_context']
        assert all(b['fraction']>=a['fraction'] for a,b in zip(events,events[1:])),events
        report.update(ok=True,source_stat_unchanged=True,output=str(output),output_bytes=output.stat().st_size)
    except BaseException as error:
        report.update(ok=False,error=repr(error));raise
    finally:
        done.set();thread.join(5)
        report.update(total_seconds=time.perf_counter()-started,samples=samples,progress=events,
            process_peak_working_set_mib=memory().PeakWorkingSetSize/1024**2,
            sampled_peak_working_set_mib=max((s['working_set_mib'] for s in samples),default=0),
            sampled_peak_gpu_all_processes_mib=max((s.get('gpu_all_processes_mib',0) for s in samples),default=0))
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('RESULT',json.dumps({k:v for k,v in report.items() if k not in ('samples','progress','native','geometry','source_metadata')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
