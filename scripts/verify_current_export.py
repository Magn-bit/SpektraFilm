"""One current full RAW→spectral→TIFF16 integration measurement, no hashes."""
from pathlib import Path
import argparse
from dataclasses import asdict,replace
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]


def main():
    import numpy as np
    import tifffile
    from desktop import output,imaging,native_spectral,raw_development
    from shared.output_recipes import OutputRecipe
    from scripts.verify_full_export import peak_mib
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args()
    args.folder.mkdir(parents=True,exist_ok=True)
    target=args.folder/'A7CR_5219.tif'
    source=args.source.resolve();before=(source.stat().st_size,source.stat().st_mtime_ns)
    timings={}
    for name in ('read_photo','prepare_photo_source','render_pixels'):
        fn=getattr(output,name)
        def timed(*a,_name=name,_fn=fn,**kw):
            start=time.perf_counter()
            try:return _fn(*a,**kw)
            finally:timings[_name]=time.perf_counter()-start
        setattr(output,name,timed)
    settings=replace(imaging.Settings(),film_enabled=True,stock='kodak_vision3_500t',
        temperature=6100,shadows=8,grain=12,halation=5,sharpening=15,noise_color=10)
    dimensions=imaging.photo_dimensions(str(source))
    started=time.perf_counter()
    size=output.export_recipe(str(source),str(target),settings,OutputRecipe(format='tiff',bit_depth=16))
    total=time.perf_counter()-started
    timings['encode_write_publish']=max(0,total-sum(timings.values()))
    assert tuple(size)==tuple(dimensions)
    with tifffile.TiffFile(target) as handle:
        page=handle.pages[0]
        assert page.shape==(dimensions[1],dimensions[0],3)
        assert page.dtype==np.uint16 and page.tags.get(34675)
        first=next(page.segments())[0]
        levels=int(np.unique(first).size)
        assert levels>256 and np.ptp(first)>1024
    assert before==(source.stat().st_size,source.stat().st_mtime_ns)
    report=dict(ok=True,version='0.5.0',source=source.name,dimensions=list(size),settings=asdict(settings),
        total_seconds=total,stages_seconds=timings,peak_working_set_mib=peak_mib(),
        output_bytes=target.stat().st_size,output_bits=16,icc=True,first_strip_levels=levels,
        source_size_mtime_unchanged=True,native=native_spectral.backend_info(),raw_ownership=raw_development.memory_info(),
        scope='Source process, first export; actual source-resolution optical corrections, restored details, complete spectrum, TIFF16 encoding/fsync/publication')
    (args.folder/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('ok','dimensions','total_seconds','stages_seconds','peak_working_set_mib','raw_ownership')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
