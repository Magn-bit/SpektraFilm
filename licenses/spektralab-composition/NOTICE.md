# SpektraLab composition reference

The film dimensions, 135 perforation geometry, manufacturer edge-print words, ISO 1007 barcode encoder and layout guides in `shared/composition_edge.py` are adapted from SpektraLab 2.2.0, commit `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`.

Source: https://github.com/JamesQiu2005/SpektraLab

Files: `engine/src/pipeline/overscan.cpp`, `app/SpektraLab/Sources/FilmEdge/FilmLayout.swift`, `FilmEdgeStock.swift`. Copyright SpektraLab contributors, GNU GPL version 3; a copy is included here. DX values in the upstream table are credited there to The Big Film Database (CC BY-SA 4.0) and NegativeConverter (MIT).

Changes: portable Python layout/parameter adapters, a Qt workspace and original-source integration with the native overscan/date/pair renderer. `desktop/film_canvas.py` crops prepared sources before exposure, combines half frames in linear ProPhoto, applies independent native print trims, and reads the native gate geometry. Physical output does not use a post-painted border. Non-film paper/contact layouts remain graphic compositions. Native engine adaptations carry their additional source/license notices in the native tree.
