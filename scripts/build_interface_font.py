"""Build the requested Chinese/Latin pairing without platform fallback differences.

Source outlines stay unchanged. Both original SIL OFL notices are retained.
Requires fonttools; this is a development step, never an application startup task.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json

from fontTools import subset
from fontTools.merge import Merger
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets/fonts"
FAMILY = "Spektra Bilingual Serif"
INPUTS = {
    "latin": ("NotoSerifSC.ttf", "050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9"),
    "chinese": ("ZhuqueFangsong-Regular.ttf", "558c62730844fe54ba220146ed62f859d4e2880188d92d985f8921c6e3743bc4"),
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def signature(font, codepoint):
    glyph_name = font.getBestCmap()[codepoint]
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[glyph_name].draw(pen)
    return font["hmtx"][glyph_name], pen.value

def prepare(font, codepoints, target):
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.layout_features = ["*"]
    options.glyph_names = True
    options.recalc_timestamp = False
    tool = subset.Subsetter(options=options)
    tool.populate(unicodes=codepoints)
    tool.subset(font)
    for table in ("DSIG", "BASE", "STAT", "vhea", "vmtx"):
        if table in font:
            del font[table]
    font.recalcTimestamp = False
    font.save(target)

def main():
    for filename, sha in INPUTS.values():
        assert digest(FONTS / filename) == sha, filename
    latin = instantiateVariableFont(TTFont(FONTS / INPUTS["latin"][0]), {"wght": 400}, inplace=True)
    chinese = TTFont(FONTS / INPUTS["chinese"][0])
    assert latin["head"].unitsPerEm == chinese["head"].unitsPerEm == 1000
    ranges = ((0x20, 0x250), (0x300, 0x370), (0x1E00, 0x1F00), (0x2000, 0x2300))
    latin_codes = {c for c in latin.getBestCmap() if any(start <= c < end for start, end in ranges)}
    chinese_codes = set(chinese.getBestCmap()) - latin_codes
    assert set(map(ord, "SpektraFilm Portra 400 JPG TIFF RAW")) <= latin_codes
    assert set(map(ord, "导入照片胶片档案导出作品曝光补偿对比度色温饱和度仿宋")) <= chinese_codes
    output = FONTS / "SpektraBilingualSerif-Regular.ttf"
    with TemporaryDirectory() as folder:
        paths = [Path(folder) / "latin.ttf", Path(folder) / "chinese.ttf"]
        prepare(latin, latin_codes, paths[0])
        prepare(chinese, chinese_codes, paths[1])
        source_fonts = [TTFont(path) for path in paths]
        merged = Merger().merge([str(path) for path in paths])
        merged.recalcTimestamp = False
        merged["head"].created = max(font["head"].created for font in source_fonts)
        merged["head"].modified = max(font["head"].modified for font in source_fonts)
        merged["head"].macStyle = 0
        merged["OS/2"].usWeightClass = 400
        merged["OS/2"].fsSelection = 0xC0
        names = merged["name"]
        replacements = {1: FAMILY, 2: "Regular", 3: "SpektraBilingualSerif-Regular-1.0", 4: FAMILY + " Regular", 5: "Version 1.000", 6: "SpektraBilingualSerif-Regular", 16: FAMILY, 17: "Regular"}
        for record in list(names.names):
            if record.nameID in replacements:
                names.setName(replacements[record.nameID], record.nameID, record.platformID, record.platEncID, record.langID)
        for ident, value in replacements.items():
            names.setName(value, ident, 3, 1, 0x409)
        copyright_text = " | ".join(dict.fromkeys(font["name"].getDebugName(0) or "" for font in source_fonts))
        names.setName(copyright_text, 0, 3, 1, 0x409)
        names.setName("Derived from Noto Serif SC Regular (Latin/numerals) and Zhuque Fangsong Regular (Chinese). Original SIL OFL notices accompany this font.", 10, 3, 1, 0x409)
        merged.save(output)
        actual = TTFont(output)
        assert set(actual.getBestCmap()) == latin_codes | chinese_codes
        verified = 0
        for font in source_fonts:
            for codepoint in font.getBestCmap():
                assert signature(actual, codepoint) == signature(font, codepoint), hex(codepoint)
                verified += 1
    record = {"style": "chinese-fangsong-latin-serif", "family": FAMILY, "file": output.name, "weight": 400, "sha256": digest(output), "scripts": {"chinese": "Zhuque Fangsong (technical preview)", "latin_and_numerals": "Noto Serif SC Regular"}, "sources": {role: {"file": filename, "sha256": sha} for role, (filename, sha) in INPUTS.items()}, "licenses": ["OFL.txt", "ZhuqueFangsong-OFL.txt"], "verified_glyphs": verified, "verification": "All encoded glyph outlines and horizontal metrics match their source subsets; Chinese punctuation remains Fangsong.", "sizes": {"display": 32, "heading": 18, "body": 14, "caption": 13}}
    (FONTS / "interface-font.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
