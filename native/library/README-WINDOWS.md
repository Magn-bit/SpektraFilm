# Windows library helper

The source is the real MIT `JamesQiu2005/SpektraLab_library` 0.3.1 SDK, pinned
in `UPSTREAM.json`, with all 42 C ABI / JSONL methods and ABI 1, schema 3 retained.
`LICENSE` and the vendored nlohmann MIT license must accompany distribution.
SQLite 3.54.1 is retained as public-domain amalgamation source.

Build from PowerShell 7:

```powershell
./native/library/build-windows.ps1
```

The build uses the existing Ubuntu-24.04 WSL MinGW cross compiler. It writes
`runtime/spklib-host.exe`; the binary imports only Windows `KERNEL32`, `msvcrt`
and `Normaliz`, without a Python or external SQLite runtime. There is no listener
or network endpoint. SQLite extension loading is disabled.

The port supplies UTF-8/generic paths, UTF-16 host arguments, NFC normalization,
Windows file timestamps, native drive-root storage and non-overwriting atomic
session moves. A cross-volume move fails instead of silently copying a photo.

Capture One sources are always read through a private byte copy. Only the copy
is opened by SQLite. Nonempty rollback journals are refused; source metadata
is checked around the copy; a copied WAL is checkpointed only in the private
snapshot. Imported catalog data includes locations, collections, variants,
metadata, tags and edits belonging to SpektraFilm. This does not import or
reproduce proprietary Capture One RAW processing or adjustments.

Application transport: `desktop/library_service.py` runs the helper with
asynchronous `QProcess` pipes. `desktop/library_workspace.py` owns the optional
workspace, bounded image pages and optimistic edit revisions. The default quick
session does not require a catalog. Full native contract: `API-SPEC.md`.

Critical verification uses `scripts/verify_library_service.py` (small synthetic
catalog/session and the upstream 16.8 schema fixture), then
`scripts/verify_library_workspace.py` (edit flush/conflict, albums, search,
native folder notification and a real QML screenshot). Neither executes RAW
processing or creates a hash manifest. Windows Capture One builds with a
different database schema still require a real-source compatibility check;
unknown schemas fail explicitly, leaving the source untouched.
