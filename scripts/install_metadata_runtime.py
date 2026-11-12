"""Fetch the pinned, official ExifTool Windows distribution and matching source."""
from pathlib import Path
import json
import tarfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]/'native/metadata'
VERSION='13.61'


def main():
    downloads=ROOT/'download';downloads.mkdir(parents=True,exist_ok=True)
    names=[f'exiftool-{VERSION}_64.zip',f'Image-ExifTool-{VERSION}.tar.gz']
    urls={name:'https://downloads.sourceforge.net/project/exiftool/'+name for name in names}
    for name,url in urls.items():
        target=downloads/name
        if not target.exists():
            request=urllib.request.Request(url,headers={'User-Agent':'SpektraFilm-build'})
            with urllib.request.urlopen(request,timeout=60) as source:target.write_bytes(source.read())
        if name.endswith('.zip'):
            directory=ROOT/'runtime'
            with zipfile.ZipFile(target) as archive:
                if any(not (directory/path).resolve().is_relative_to(directory.resolve()) for path in archive.namelist()):
                    raise ValueError('Invalid archive path')
                archive.extractall(directory)
            executable=directory/f'exiftool-{VERSION}_64'/'exiftool(-k).exe'
            executable.replace(executable.with_name('exiftool.exe'))
        else:
            with tarfile.open(target) as archive:archive.extractall(ROOT/'upstream',filter='data')
    (ROOT/'UPSTREAM.json').write_text(json.dumps(dict(name='ExifTool',version=VERSION,homepage='https://exiftool.org/',
        source=urls,license='Same terms as Perl: Artistic or GPL'),indent=2),encoding='utf-8')


if __name__=='__main__':main()
