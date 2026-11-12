# 2026-11-09 film frames and print materials

This increment uses SpektraLab 2.2 source `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea` and the user-provided paper/frame screenshots. It retains native pre-development film-space overscan; no finished photograph is painted into a fake film border.

## Actual changes

- Separated physical film frames from graphic paper/instant/contact layouts. Six physical configurations expose 135, 120 6×6, filed carrier, XPan, 120 6×7 and a physical half-frame pair. Thumbnails are actual native developments of the current photograph, never generic sprocket illustrations.
- Made the style chooser compact and initially collapsed so gauge and physical controls are immediately available. Thumbnail rendering is explicitly requested, serial and yields to live canvas work. Only the active thumbnail shows loading, rather than spinning all cards.
- Made the parameter viewport shrinkable and explicitly bounded above an opaque, separately laid-out output footer. The final parameter can scroll clear of the footer. Preserved font system and restrained warm gray-green palette.
- Reused the current developed proxy or file thumbnail immediately. Native option changes retain the preceding valid canvas; failures offer a retry. Final output continues to reopen originals, never the proxy.
- Fixed half-frame independent preflash: each hole now consumes its own setting in the same native per-hole print path as exposure/filter trims.

## Nine print materials

The exact screenshot materials already had distinct spectral resources: Portra Endura, Endura Premier, Ektacolor Edge, Supra Endura, Ultra Endura, Crystal Archive Type II, Vision2383, Vision Premier2393, and Multigrade IV RC. Runtime and vendor data agree, including upstream unmeasured dye-support tails represented by null/NaN and prepared by the native loader. It would be wrong to fill those tails with invented measured data. The actual native render outputs are finite and visibly different on one common input. The black-and-white paper is paired with a true silver film, not a color-negative desaturation.

Primary data attribution remains Andrea Volpato / Spektrafilm CC BY-SA 4.0; the black-and-white feasibility fit and its provenance remain under the SpektraLab product-material notice.

## Three additional spectral films

Pro 160S, Pro 160C and Superia Reala use Jan Lohse's MIT numeric datasets from `spectral_film_lut`, revision `a15043f6fe2d365d0c359d22e0868076800916d9`. Sources are AST-read literal dictionaries; the application never imports downloaded Python code. The complete data, original source text, MIT license, conversion assumptions and neutral-print calibration are retained.

The conversion produces 81 wavelengths (380–780 nm in 5 nm steps), independent sensitivity/dye/base curves and 256 density samples. Numerical density components are a fit, not measured individual emulsions. Unsupported stock-specific DIR chemistry is disabled. Each stock's independent neutral CMY pack is actually consumed by the full spectral renderer. Optional compatibility LUTs are generated from each stock's own full spectral output and do not replace the spectral data.

Neutral CMY: Pro160S `[0,28.37597,38.11793]`, Pro160C `[0,28.37173,33.06078]`, Reala `[0,54.34014,49.27000]`. All use Crystal Archive Type II / TH-KG3. Modeled 18.4% gray prints at approximately linear RGB0.18 with chromatic-ratio residual below5e-11. This does not claim a laboratory match of complete real stock behavior, grain or chemistry.

## Verification scope

One bounded paper/frame/UI milestone and one additional-material conversion milestone are used. No file hashes and no repeated large RAW export. Reports and same-window screenshots are in `output/lab-frames-papers-review/`. The main Studio package still requires the parent's final integrated candidate check. The two-purpose source fixture is only a preview/effect comparison, not product example content.


## EDR calibration resources

Eight matching color print materials now retain the latest SpektraLab `data.edr_tone_map` tables. Every pre-existing wavelength, sensitivity, dye, base, exposure and density array was compared to the same material before adding only its own 256-entry calibration table. Multigrade IV RC has no upstream EDR calibration and stays unavailable. Vendor Python profile files remain unchanged because their dataclass does not consume EDR; the native runtime owns this addition.

The actual native gray-ramp EDR toggle was checked for all eight: finite output and mean RGB difference0.00418–0.01678. Tables retain the original calibration-film/semantic fields and source attribution. Evidence: `edr-materials.json`. This is an SDR print tone mapping feature, not a claim of monitor HDR output.

The installed catalog now contains30 film entries and9 print materials. Two layout-only viewport checks at1366×768 and1440×900 confirm the last physical parameter is entirely reachable above the independent output footer. Those screenshots use a source proxy to isolate layout and do not claim a native output render; the real native-film screenshots are separate.
