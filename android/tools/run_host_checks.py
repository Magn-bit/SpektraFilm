"""Use the existing Gradle Kotlin/JVM runtime; no device, download, image render or hash pass."""
from pathlib import Path
import os
import subprocess
import sys
import struct
import zlib
import numpy as np
import tifffile

root = Path(__file__).resolve().parents[2]
cache = Path.home() / '.gradle/caches/modules-2/files-2.1'
dev = Path(os.environ['LOCALAPPDATA']) / 'SpektraFilmDev'
java = Path(os.environ.get('JAVA_HOME', str(Path.home() / 'tools/jdk-21.0.12.1+1'))) / 'bin/java.exe'
compiler = dev / 'maven/org/jetbrains/kotlin/kotlin-compiler-embeddable/2.1.20/kotlin-compiler-embeddable-2.1.20.jar'
def dependency(group, artifact, version):
    return next((cache / group / artifact / version).rglob(f'{artifact}-{version}.jar'))
stdlib = dependency('org.jetbrains.kotlin', 'kotlin-stdlib', '2.1.20')
json = dependency('org.json', 'json', '20160810')
compiler_cp = [compiler, stdlib,
    dependency('org.jetbrains.kotlin', 'kotlin-reflect', '1.6.10'),
    dependency('org.jetbrains.intellij.deps', 'trove4j', '1.0.20200330'),
    dependency('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.8.0'),
    dependency('org.jetbrains', 'annotations', '13.0')]
classes = root / 'android/app/build/tmp/kotlin-classes/debug'
android = dev / 'android-sdk/platforms/android-35/android.jar'
out = root / 'android/app/build/host-editor-checks'
out.mkdir(parents=True, exist_ok=True)
java_classes=root/'android/app/build/intermediates/javac/debug/compileDebugJavaWithJavac/classes'
runtime = os.pathsep.join(map(str, [out, classes, java_classes, stdlib, json, android]))
sources=['OutputPixelChecks.kt'] if '--native-pixels' in sys.argv else ['EditorStateChecks.kt','FineSliderGestureChecks.kt','OutputEncoderChecks.kt']
subprocess.run([str(java), '-cp', os.pathsep.join(map(str, compiler_cp)),
    'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-no-stdlib', '-no-reflect',
    '-classpath', runtime, '-Xfriend-paths=' + str(classes), '-d', str(out),
    *[str(root/'android/tools'/name) for name in sources]], check=True)
for entry in ([] if '--native-pixels' in sys.argv else ['EditorStateChecksKt', 'FineSliderGestureChecksKt']):
    subprocess.run([str(java), '-cp', runtime, 'com.spektra.film.' + entry], check=True)
if '--native-pixels' in sys.argv:
    subprocess.run([str(java),'-Djava.library.path='+str(out),'-cp',runtime,'com.spektra.film.OutputPixelChecksKt',str(out),str(root)],check=True)
    sys.path.insert(0,str(root))
    from shared.color_management import convert_pixels,encode
    values=np.fromfile(out/'input.rgb16',dtype='<u2').reshape(1,-1,3)/65535
    for name,space in [('p3','Display P3'),('prophoto','ProPhoto RGB')]:
        expected=np.rint(np.clip(convert_pixels(values,target=space),0,1)*65535).astype(np.uint16).reshape(-1)
        actual=np.fromfile(out/(name+'.rgb16'),dtype='<u2')
        assert np.max(np.abs(expected.astype(np.int32)-actual.astype(np.int32)))<=2
    area=np.fromfile(out/'area.rgb16',dtype='<u2')
    assert np.all(np.abs(area.astype(np.int32)-round(float(encode(.5))*65535))<=1)
    print('OK: native P3/ProPhoto samples match shared transform within 2/65535; area reduction is linear-light')
    raise SystemExit(0)
if '--state-only' in sys.argv:
    raise SystemExit(0)
encoders=out/'output-encoders'
subprocess.run([str(java),'-cp',runtime,'com.spektra.film.OutputEncoderChecksKt',str(encoders),str(root)],check=True)
width,height=64,48
expected=(np.arange(width*height*3,dtype=np.uint32).reshape(height,width,3)*113).astype(np.uint16)
for name,depth in [('rgb16.png',16),('rgb8.png',8)]:
    data=(encoders/name).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    pos=8;idat=bytearray();icc=None
    while pos<len(data):
        size=struct.unpack_from('>I',data,pos)[0];kind=data[pos+4:pos+8];payload=data[pos+8:pos+8+size];pos+=size+12
        if kind==b'IHDR':assert struct.unpack('>IIBBBBB',payload)==(width,height,depth,2,0,0,0)
        elif kind==b'iCCP':icc=zlib.decompress(payload[payload.index(0)+2:])
        elif kind==b'IDAT':idat.extend(payload)
    assert icc==(root/'assets/color/sRGB.icc').read_bytes()
    decoded=np.frombuffer(zlib.decompress(idat),dtype=np.uint8).reshape(height,1+width*3*(depth//8)).copy()
    assert np.all(decoded[:,0]==1)
    row=decoded[:,1:];stride=3*(depth//8)
    for x in range(stride,row.shape[1]):row[:,x]=(row[:,x].astype(np.uint16)+row[:,x-stride])%256
    values=row.copy().reshape(height,width,3,depth//8)
    actual=(values[...,0].astype(np.uint16)*256+values[...,1]) if depth==16 else values[...,0]
    assert np.array_equal(actual,expected if depth==16 else ((expected.astype(np.uint32)+128)//257).astype(np.uint8))
for name in ['rgb16.tif','linear.dng']:
    with tifffile.TiffFile(encoders/name) as f:
        assert f.pages[0].bitspersample==16 and np.array_equal(f.asarray(),expected)
        if name.endswith('dng'):
            tags=f.pages[0].tags
            assert tags[262].value==34892 and bytes(tags[50706].value)==b'\x01\x04\x00\x00'
            assert len(tags[50721].value)==18 and tags[50778].value==21
print('OK: independently decoded PNG8/16, TIFF16, and processed LinearRaw DNG16 pixels and ICC/DNG tags')
import rawpy
with rawpy.imread(str(encoders/'linear.dng')) as raw:
    assert raw.sizes.width==width and raw.sizes.height==height
    assert np.array_equal(raw.raw_image_visible[...,:3],expected)
print('OK: LibRaw accepts the exported linear DNG and unpacks all original RGB16 samples')
