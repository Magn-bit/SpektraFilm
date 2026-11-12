"""Record one reproducible large-image render, not an animation FPS claim."""
import ctypes,json,sys,time
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from desktop.imaging import render,Settings
class Counters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
def peak():
    c=Counters();c.cb=ctypes.sizeof(c)
    fn=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not fn(wintypes.HANDLE(-1),ctypes.byref(c),c.cb):return None
    return round(c.PeakWorkingSetSize/1024**2,1)
image=Image.fromarray(np.random.default_rng(17).integers(0,256,(4000,6000,3),dtype=np.uint8))
baseline=peak();start=time.perf_counter()
output=render(image,Settings())
elapsed=time.perf_counter()-start
report={'dimensions':[6000,4000],'megapixels':24,'mode':'LUT + default approximate grain and halation','seconds':round(elapsed,3),'peak_working_set_mib':peak(),'baseline_peak_mib':baseline,'output_size':list(output.size),'python':sys.version.split()[0]}
Path('output/render-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))

