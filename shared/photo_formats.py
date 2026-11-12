"""File routing shared by import, metadata, development and original export.

An extension selects the RAW decoder; it is not a promise that every camera's
compression variant is supported. LibRaw validates the file contents.
"""

RAW_EXTENSIONS = frozenset({
    '.arw', '.sr2', '.srf', '.crw', '.cr2', '.cr3', '.nef', '.nrw',
    '.dng', '.raf', '.raw', '.rw2', '.rwl', '.orf', '.pef', '.srw',
    '.3fr', '.fff', '.iiq', '.mos', '.mef', '.mrw', '.erf', '.dcr',
    '.kdc', '.bay',
})
RASTER_EXTENSIONS = frozenset({
    '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.bmp',
    '.avif', '.heic', '.heif',
})
PHOTO_EXTENSIONS = RAW_EXTENSIONS | RASTER_EXTENSIONS
PHOTO_DIALOG_FILTER = '照片 (' + ' '.join('*' + suffix for suffix in sorted(PHOTO_EXTENSIONS)) + ')'
