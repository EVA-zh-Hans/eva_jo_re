unpack:
	./build/unpacker data/raw/NEVA.PKG 0x12242C10 345 data/workspace/raw_unpacked
repack:
	./build/repacker '/Users/liu/Documents/eva-jo-re/data/workspace/manifest.json' ./build/PSP_GAME/USRDIR/NEVA.PKG
extract:
	uv run python ./python/extractor.py
inject:
	uv run python ./python/injector.py