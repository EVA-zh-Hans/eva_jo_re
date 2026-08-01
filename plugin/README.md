# EVA-JO Font Loader

This directory builds the minimal PSP loader and runtime patch for ULJS00201.
The runtime replaces the game's `sceFontOpen` call with
`sceFontOpenUserFile` and loads:

```text
disc0:/PSP_GAME/USRDIR/fonts.pgf
```

No text encoding, translation, save-data, debug-menu, or UI patches are
included.

## Plugin build

The inner Makefile only configures and builds the two PSP modules. It requires
PSPDEV with its CMake toolchain:

```console
$ make
```

The default outputs are `build/EBOOT.BIN` and `build/EVAJORT.PRX`. A caller
can set `BUILD_DIR` to place them elsewhere.

## Integration

Run `make plugin-overlay` from the repository root to build the modules and
prepare this tree under `build/overrides`:

```text
PSP_GAME/
|-- SYSDIR/
|   |-- EBOOT.BIN    # Minimal loader
|   |-- BOOT.BIN     # Original EBOOT decrypted by pspdecrypt
|   `-- EVAJORT.PRX  # Runtime font patch
`-- USRDIR/
    `-- fonts.pgf
```

The root Makefile owns all copying and EBOOT decryption. `make build` also
includes this overlay in the translated ISO.

## Patch

The supported EBOOT uses the standard image base `0x08804000`. The runtime
relocates and patches the `jal sceFontOpen` instruction at original address
`0x089CA918`, then flushes the PSP data and instruction caches.

This first-stage patch intentionally does not override `sceFontGetFontInfo`.
The custom PGF must therefore provide metrics compatible with the game's
existing rendering buffers.
