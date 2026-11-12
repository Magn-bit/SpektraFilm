"""Real CFA decoding regression for the RAW auto-bright/transfer policy.

Fixtures are tiny valid DNGs generated in a temporary directory. No cached
output/, embedded JPEG, mocked rawpy calls or downloaded RAWs are involved.
"""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image
import rawpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from desktop.imaging import read_photo


def _synthetic_dng(path, orientation=6, exposure_scale=1/16):
    """Uncompressed 96x64 RGGB DNG with WB/matrix/white/black metadata.

    This is the same asymmetric CFA scene as the Android native regression,
    stored as real TIFF/DNG tags and raw sensor samples rather than RGB.
    """
    def shorts(*values):
        return struct.pack("<" + "H"*len(values), *values)

    def longs(*values):
        return struct.pack("<" + "I"*len(values), *values)

    tags = [
        (254, 4, 1, longs(0)), (256, 4, 1, longs(96)), (257, 4, 1, longs(64)),
        (258, 3, 1, shorts(16)), (259, 3, 1, shorts(1)), (262, 3, 1, shorts(32803)),
        (271, 2, 8, b"Spektra\0"), (272, 2, 14, b"Synthetic DNG\0"),
        (273, 4, 1, longs(0)), (274, 3, 1, shorts(orientation)),
        (277, 3, 1, shorts(1)), (278, 4, 1, longs(64)), (279, 4, 1, longs(96*64*2)),
        (284, 3, 1, shorts(1)), (33421, 3, 2, shorts(2, 2)),
        (33422, 1, 4, bytes((0, 1, 1, 2))), (50706, 1, 4, bytes((1, 4, 0, 0))),
        (50707, 1, 4, bytes((1, 1, 0, 0))), (50708, 2, 14, b"Synthetic DNG\0"),
        (50710, 1, 3, bytes((0, 1, 2))), (50711, 3, 1, shorts(1)),
        (50713, 3, 2, shorts(1, 1)), (50714, 5, 1, longs(64, 1)),
        (50717, 4, 1, longs(16383)),
        (50721, 10, 9, longs(1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1)),
        (50728, 5, 3, longs(1, 2, 1, 1, 2, 3)), (50778, 3, 1, shorts(21)),
    ]
    tags.sort()
    data = bytearray(8 + 2 + len(tags)*12 + 4)
    struct.pack_into("<2sHIH", data, 0, b"II", 42, 8, len(tags))
    strip_offset_at = None
    for index, (tag, kind, count, value) in enumerate(tags):
        entry = 10 + index*12
        struct.pack_into("<HHI", data, entry, tag, kind, count)
        if tag == 273:
            strip_offset_at = entry + 8
        if len(value) <= 4:
            data[entry+8:entry+8+len(value)] = value
        else:
            if len(data) & 1:
                data.append(0)
            struct.pack_into("<I", data, entry+8, len(data))
            data.extend(value)
    if len(data) & 1:
        data.append(0)
    struct.pack_into("<I", data, strip_offset_at, len(data))
    for y in range(64):
        for x in range(96):
            signal = 900 + x*70 + y*35 + ((x ^ y) & 7)*113
            if (y & 1) and (x & 1):
                signal += 1000
            signal = 64 + int((signal-64)*exposure_scale + .5)
            data.extend(shorts(signal))
    path.write_bytes(data)


def _official_pixels(path, *, half=False, highlight=rawpy.HighlightMode.Blend,
                     no_auto_bright=False):
    # Independent official postprocess call, rather than introspection of
    # read_photo's options. A fresh decoder is used because half_size mutates
    # LibRaw geometry. Match the promised sRGB/AHD/camera-WB output policy.
    with rawpy.imread(str(path)) as raw:
        return raw.postprocess(
            use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,
            gamma=(2.4, 12.92), highlight_mode=highlight,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            no_auto_bright=no_auto_bright, auto_bright_thr=.01,
            output_bps=8, half_size=half)


class RawBrightnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_full_dark_raw_matches_official_auto_brightness_and_preserves_source(self):
        for orientation, dimensions in ((1, (96, 64)), (6, (64, 96))):
            with self.subTest(orientation=orientation):
                path = self.directory / f"dark-{orientation}.dng"
                _synthetic_dng(path, orientation)
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                expected = _official_pixels(path)
                old = _official_pixels(path, highlight=rawpy.HighlightMode.ReconstructDefault)
                unnormalized = _official_pixels(path, no_auto_bright=True)
                with read_photo(str(path)) as actual:
                    self.assertEqual(actual.size, dimensions)
                    self.assertEqual(actual.info["source_size"], dimensions)
                    self.assertEqual(actual.mode, "RGB")
                    np.testing.assert_array_equal(np.asarray(actual), expected)
                    mean = float(np.asarray(actual).mean()/255)
                self.assertGreater(mean, .35)
                # Both the high-level policy and auto-bright output curve
                # must work: either old failure leaves this real RAW dark.
                self.assertGreater(mean, float(old.mean()/255)*1.75)
                self.assertGreater(mean, float(unnormalized.mean()/255)*1.75)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_preview_dark_raw_uses_same_brightness_policy_with_full_source_metadata(self):
        for orientation, dimensions, preview_size in (
                (1, (96, 64), (32, 21)), (6, (64, 96), (21, 32))):
            with self.subTest(orientation=orientation):
                path = self.directory / f"preview-{orientation}.dng"
                _synthetic_dng(path, orientation)
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                expected = Image.fromarray(_official_pixels(path, half=True))
                expected.thumbnail((32, 32), Image.Resampling.LANCZOS)
                old = Image.fromarray(_official_pixels(
                    path, half=True, highlight=rawpy.HighlightMode.ReconstructDefault))
                old.thumbnail((32, 32), Image.Resampling.LANCZOS)
                with expected, old, read_photo(str(path), 32) as actual:
                    self.assertEqual(actual.size, preview_size)
                    self.assertNotEqual(actual.size, dimensions)
                    self.assertEqual(actual.info["source_size"], dimensions)
                    np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))
                    self.assertGreater(float(np.asarray(actual).mean()/255), .35)
                    self.assertGreater(float(np.asarray(actual).mean()), float(np.asarray(old).mean())*1.75)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
