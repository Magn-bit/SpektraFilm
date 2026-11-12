"""Prepare user-authorized personal fonts from cached official Apple packages."""
from pathlib import Path
import hashlib
import json
import plistlib
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.tools/apple-fonts'
TARGET = ROOT / 'personal-fonts'
CATALOG_URL = 'https://mesu.apple.com/assets/macos/com_apple_MobileAsset_Font8/com_apple_MobileAsset_Font8.xml'

def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    assets = plistlib.loads((CACHE / 'Font8.xml').read_bytes())['Assets']
    asset = next(a for a in assets if any(f.get('FontFamilyName') == 'PingFang SC' for f in a.get('FontInfo4', [])))
    archive = CACHE / 'PingFang-10M11177.zip'
    assert archive.stat().st_size == asset['_DownloadSize']
    with archive.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha1').hexdigest()
    expected = asset['_Measurement']
    if isinstance(expected, bytes):
        expected = expected.hex()
    assert checksum == expected, 'Apple asset catalog checksum mismatch'
    TARGET.mkdir(exist_ok=True)
    font_path = TARGET / 'PingFang.ttc'
    with zipfile.ZipFile(archive) as package:
        font_path.write_bytes(package.read('AssetData/PingFang.ttc'))
    collection = TTCollection(font_path, lazy=True)
    faces = []
    for index, font in enumerate(collection.fonts):
        name = font['name']
        family = name.getDebugName(16) or name.getDebugName(1)
        if family == 'PingFang SC':
            faces.append(dict(index=index, family=family, style=name.getDebugName(17) or name.getDebugName(2), weight=font['OS/2'].usWeightClass))
    regular = next(face for face in faces if face['weight'] == 400)
    font = collection.fonts[regular['index']]
    missing = [c for c in '照片编辑胶片导出曝光强度设置（）0123456789' if ord(c) not in font.getBestCmap()]
    assert not missing, missing
    collection.close()

    package_path = CACHE / 'expanded/SFProFonts.pkg'
    with package_path.open('rb') as stream:
        magic, header_size, _, compressed_size, _, _ = struct.unpack('>4sHHQQI', stream.read(28))
        assert magic == b'xar!'
        stream.seek(header_size)
        tree = ET.fromstring(zlib.decompress(stream.read(compressed_size)))
        heap = header_size + compressed_size
        records = {}
        def visit(node, prefix=''):
            for entry in node.findall('file'):
                name = prefix + entry.findtext('name', '')
                data = entry.find('data')
                if data is not None:
                    records[name] = data
                visit(entry, name + '/')
        visit(tree.find('toc'))
        licenses = {}
        for language in ('en', 'zh_CN'):
            relative = f'Resources/{language}.lproj/License.rtf'
            data = records[relative]
            stream.seek(heap + int(data.findtext('offset')))
            payload = stream.read(int(data.findtext('length')))
            archived = data.find('archived-checksum')
            assert archived.get('style') == 'sha1'
            assert hashlib.sha1(payload).hexdigest() == archived.text
            assert data.find('encoding').get('style') == 'application/octet-stream'
            assert payload.startswith(bytes((123, 92)) + b'rtf'), 'Expected actual RTF content'
            target = TARGET / f'Apple-License-{language}.rtf'
            target.write_bytes(payload)
            licenses[target.name] = dict(source=relative, bytes=len(payload), sha256=sha256(target))
        (TARGET / 'Apple-License.rtf').write_bytes((TARGET / 'Apple-License-en.rtf').read_bytes())
    record_path = TARGET / 'font-source.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    medium_sources = list((CACHE / 'payload-0').rglob('SF-Pro-Text-Medium.otf'))
    assert len(medium_sources) == 1
    medium_path = TARGET / 'SFProText-Medium.otf'
    medium_path.write_bytes(medium_sources[0].read_bytes())
    with TTFont(medium_path, lazy=True) as medium:
        assert medium['OS/2'].usWeightClass == 500
        assert medium['name'].getDebugName(1) == 'SF Pro Text'
    record['fonts']['TextMedium'] = dict(file=medium_path.name, original=medium_sources[0].name, sha256=sha256(medium_path), weight=500)
    record['fonts']['CJK'] = dict(file='PingFang.ttc', original='AssetData/PingFang.ttc', sha256=sha256(font_path), family='PingFang SC', regular_index=regular['index'], faces=faces)
    record['pingfang_found'] = True
    record['pingfang_source'] = dict(catalog=CATALOG_URL, asset=asset['__BaseURL'] + asset['__RelativePath'], build=asset['Build'], archive_sha1=checksum, archive_sha256=sha256(archive), font_bytes=font_path.stat().st_size)
    record['licenses'] = licenses
    record['scope'] = 'User-authorized personal local build; separate from shared assets'
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (TARGET / 'README.md').write_text('个人使用字体：SF Pro Text / SF Pro Display + 苹方简体 PingFang SC。\n苹方原始 TTC 来自 Apple 官方字体资源服务，来源与校验见 font-source.json。\n原始集合保留，简体字面通过集合索引选择；不以文件名冒充字形来源。\n官方包内原始 SF Pro 许可保留；用户已声明具备本次使用授权。\n', encoding='utf-8')
    print(json.dumps(dict(ok=True, font=str(font_path), bytes=font_path.stat().st_size, faces=faces, regular_index=regular['index'], licenses=licenses), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
