
unpack:
	./build/unpacker data/raw/NEVA.PKG 0x12242C10 345 data/workspace/raw_unpacked
repack:
	./build/repacker '/Users/liu/Documents/eva-jo-re/data/workspace/manifest.json' ./build/PSP_GAME/USRDIR/NEVA.PKG
extract:
	uv run python ./python/extractor.py
inject:
	uv run python ./python/injector.py --translation data/patch/translation_converted.json
gen_mapping:
	uv run python/gen_table.py --input data/workspace/raw_unpacked/FONT/JIS2UCS.BIN --output data/patch/FONT/JIS2UCS.BIN --json data/workspace/translation.json --mapping data/workspace/dynamic_mapping.json
convert:
	uv run python/convert_translation.py --json data/workspace/translation.json --output data/patch/translation_converted.json --mapping data/workspace/dynamic_mapping.json

# Make sure translation.json is in data/workspace
all: extract gen_mapping convert inject repack
	$(MAKE) extract
	$(MAKE) gen_mapping 
	$(MAKE) convert 
	$(MAKE) inject 
	$(MAKE) repack