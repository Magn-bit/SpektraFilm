"""Real DNG payloads prove routing without claiming to emulate other RAW formats."""
import hashlib
from pathlib import Path
import re
import tempfile
import unittest

import numpy as np
from PySide6.QtCore import QMimeData, QUrl

from desktop.imaging import Settings, export_preset, photo_dimensions, read_photo
from desktop.import_bridge import mime_paths
from shared.photo_formats import RAW_EXTENSIONS, PHOTO_DIALOG_FILTER
from test_raw_brightness import _synthetic_dng, _official_pixels


class RawRoutingTests(unittest.TestCase):
    def test_medium_format_extensions_route_through_decoder_and_original_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # These are valid DNG bytes with changed suffixes. This checks the
            # import/decode/export boundary, not Hasselblad/Phase One codecs.
            for extension in ('.IIQ', '.3FR', '.FFF', '.RAF', '.MOS', '.CRW'):
                with self.subTest(extension=extension):
                    path = root / ('input' + extension)
                    _synthetic_dng(path, orientation=6)
                    before = hashlib.sha256(path.read_bytes()).digest()
                    mime = QMimeData()
                    mime.setUrls([QUrl.fromLocalFile(str(path))])
                    self.assertEqual([Path(value) for value in mime_paths(mime)], [path])
                    self.assertEqual(photo_dimensions(str(path)), (64, 96))
                    with read_photo(str(path)) as image:
                        self.assertEqual(image.size, (64, 96))
                        np.testing.assert_array_equal(np.asarray(image), _official_pixels(path))
                    destination = root / ('copy' + extension)
                    export_preset(str(path), str(destination), Settings(), 'RAW')
                    self.assertEqual(hashlib.sha256(destination.read_bytes()).digest(), before)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)

    def test_android_and_windows_accept_the_same_raw_extensions(self):
        source = (Path(__file__).resolve().parents[1] / 'android/app/src/main/java/com/spektra/film/ExportPreset.kt').read_text(encoding='utf-8')
        raw_list = re.search(r'rawExtensions=setOf\(([^)]+)\)', source).group(1)
        self.assertEqual({'.' + value for value in re.findall(r'"([a-z0-9]+)"', raw_list)}, RAW_EXTENSIONS)
        self.assertTrue(all('*' + extension in PHOTO_DIALOG_FILTER for extension in RAW_EXTENSIONS))


if __name__ == '__main__':
    unittest.main()
