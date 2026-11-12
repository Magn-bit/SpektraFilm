"""One same-shape synthetic optical profile; no RAW decode or TIFF encoding."""
from pathlib import Path
import ctypes as ct
import json
import sys
import time
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from desktop import native_spectral as native
from desktop.imaging import Settings


def main():
    folder=ROOT/'output/native-canvas-adaptive-profile';folder.mkdir(parents=True,exist_ok=True)
    engine=native._get_engine();lib=engine.lib;session=None
    lib.spk_canvas_size.argtypes=[ct.c_void_p,ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_void_p)]
    lib.spk_render_canvas.argtypes=[ct.c_void_p,ct.c_char_p,ct.POINTER(ct.c_uint16),ct.c_uint32,ct.c_uint32,ct.POINTER(ct.c_void_p)]
    def reply(value):
        try:return json.loads(ct.string_at(value)) if value.value else None
        finally:engine._free_reply(value)
    with tempfile.TemporaryDirectory(prefix='spektrafilm-canvas-profile-') as temp:
        source=np.memmap(Path(temp)/'input.float32',mode='w+',dtype=np.float32,shape=(6376,9512,3))
        columns=np.linspace(.03,.7,source.shape[1],dtype=np.float32)[None,:,None]
        for y in range(0,source.shape[0],64):
            source[y:y+64]=columns*np.array([.9,1.,.7],np.float32)
        source[2800:2850,4400:4490]=[3.5,2.8,2.3]
        source.flush()
        settings=Settings(film_enabled=True)
        values=native.parameters(settings);values.update(input_color_space='ProPhoto RGB',input_cctf_decoding=False,
            overscan_active=True,overscan_format='135',overscan_camera_seed=31,overscan_frame_seed=17,
            overscan_frame_number=12,overscan_carrier='none',date_imprint_active=True,date_imprint_text='2026-11-09',film_format_mm=36.25)
        image=native._Image(source.ctypes.data_as(ct.POINTER(ct.c_float)),source.shape[1],source.shape[0],3)
        pointer=ct.c_void_p();started=time.perf_counter()
        session=lib.spk_open(engine.handle,ct.byref(image),native._json_bytes(values),ct.byref(pointer));opened=reply(pointer)
        assert session,engine.error()
        width,height=ct.c_uint32(),ct.c_uint32();assert lib.spk_canvas_size(session,ct.byref(width),ct.byref(height),ct.byref(pointer))==0,engine.error();size=reply(pointer)
        output=np.memmap(Path(temp)/'output.rgba16',mode='w+',dtype=np.uint16,shape=(height.value,width.value,4))
        try:
            render_started=time.perf_counter()
            status=lib.spk_render_canvas(session,b'{}',output.ctypes.data_as(ct.POINTER(ct.c_uint16)),width,height,ct.byref(pointer))
            report=reply(pointer)
            result=dict(ok=status==0,error=engine.error() if status else None,scope='Same native 9512x6376 source shape / physical 135 canvas as the real A7CR run, synthetic linear values, one native optical run, no RAW or encoding',
                settings=values,open_seconds=render_started-started,render_seconds=time.perf_counter()-render_started,size=size,native=report,
                output_sample=[int(v) for v in output[height.value//2,width.value//2]],memory=engine.memory_report())
            import subprocess
            dll=ROOT/'native/engine/runtime/spektrafilm_engine.dll';stat=dll.stat()
            result['runtime']=dict(path=str(dll),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)
            result['gpu']=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
            (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True);assert status==0,engine.error()
        finally:
            lib.spk_session_release(session);output._mmap.close();source._mmap.close()
    native.clear_sessions()


if __name__=='__main__':main()
