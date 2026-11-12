"""Copy capture metadata into the staged output, never modify source files."""
from pathlib import Path
import os
import subprocess


CAPTURE_TAGS=(
    'Make','Model','LensModel','LensMake','LensInfo','LensSerialNumber',
    'ExposureTime','ExposureProgram','ExposureCompensation','FNumber','ISO',
    'ShutterSpeedValue','ApertureValue','BrightnessValue','MeteringMode','Flash',
    'FocalLength','FocalLengthIn35mmFormat','DateTimeOriginal','CreateDate',
    'OffsetTime','OffsetTimeOriginal','OffsetTimeDigitized','SubSecTime',
    'SubSecTimeOriginal','SubSecTimeDigitized','Artist','Copyright','BodySerialNumber')


def copy_capture_metadata(source,target,dimensions):
    from .lens import _exiftool
    tool=_exiftool()
    if not tool:raise RuntimeError('缺少拍摄信息写入工具，请修复应用安装')
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target:raise ValueError('源照片不能作为元数据写入目标')
    width,height=dimensions
    arguments=['-overwrite_original','-TagsFromFile',str(source)]
    arguments+=['-EXIF:'+tag for tag in CAPTURE_TAGS]
    arguments+=['-GPS:all','-IPTC:all','-XMP-dc:all','-XMP-photoshop:all',
        '-Orientation#=1','-ExifImageWidth='+str(width),'-ExifImageHeight='+str(height),
        '-Software=SpektraFilm',str(target)]
    # The Windows Perl launcher uses a legacy argv code page. UTF-8 argument
    # input preserves Chinese source/target paths across that boundary.
    command=[tool,'-charset','filename=UTF8','-@','-']
    environment=dict(os.environ,LC_ALL='C',LC_CTYPE='C',LANG='C')
    result=subprocess.run(command,input='\n'.join(arguments)+'\n',env=environment,
        capture_output=True,text=True,encoding='utf-8',errors='replace',
        timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('无法保留拍摄信息：'+(result.stderr.strip() or result.stdout.strip())[:500])
