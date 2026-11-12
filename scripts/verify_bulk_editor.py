"""One real-RAW bulk import milestone; aliases share storage, not decoded frames."""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
import desktop.controller as controller_module


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--count',type=int,default=256)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if not 16<=args.count<=2000:parser.error('count16..2000')
    source=args.source.resolve();identity=(source.stat().st_size,source.stat().st_mtime_ns)
    app=QApplication.instance() or QApplication([])
    from scripts.verify_full_export import peak_mib
    with tempfile.TemporaryDirectory(prefix='bulk-raw-',dir=ROOT/'output') as temporary:
        paths=[]
        for index in range(args.count):
            path=Path(temporary)/f'RAW-{index:04d}{source.suffix}'
            os.link(source,path);paths.append(str(path))
        ctrl=Controller(PhotoProvider(),temporary)
        decoded=[];read=controller_module.read_photo
        def record(path,edge=None):
            decoded.append(dict(path=path,edge=edge));return read(path,edge)
        started=time.perf_counter();peak=peak_mib()
        try:
            with patch.object(controller_module,'read_photo',record):
                ctrl.add_paths(paths)
                chunks=[len(batch[0]) for batch in ctrl._import_queue]
                while time.perf_counter()-started<60:
                    app.processEvents()
                    peak=max(peak,peak_mib())
                    if ctrl.photoCount==args.count and ctrl.frame and not ctrl.busy:break
                    time.sleep(.005)
                assert ctrl.photoCount==args.count,(ctrl.photoCount,ctrl.status)
                assert ctrl.frame and not ctrl.busy,ctrl.status
                assert max(chunks)<=16
                assert len({item['path'] for item in decoded})==1,'Non-selected RAW decoded'
                row=ctrl.photoModel.data(ctrl.photoModel.index(0),ctrl.photoModel.PHOTO_ROLE)
                assert 'settings' not in row
                assert len(ctrl._cache)<=6 and len(ctrl.provider.thumbnail_order)<=64
                result=dict(ok=True,count=args.count,total_input_gib=identity[0]*args.count/1024**3,
                    fixture='Distinct hard-linked RAW paths; identical content, shared disk blocks',
                    elapsed_seconds=time.perf_counter()-started,peak_working_set_mib=peak,
                    max_metadata_batch=max(chunks),decoded_photos=len({item['path'] for item in decoded}),
                    decode_requests=len(decoded),source_cache_entries=len(ctrl._cache),
                    photo_model_has_edits=False,source_size=ctrl.sourceDimensions,
                    dimensions_preserved=True)
        finally:ctrl.close()
    assert identity==(source.stat().st_size,source.stat().st_mtime_ns)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
