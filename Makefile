GAME_ID      := ULJS00201
TEMP_DIR     := temp
BUILD_DIR    := build
DIST_DIR     := dist
SOURCE_ISO   := $(TEMP_DIR)/$(GAME_ID).iso
TRANSLATIONS := translations
STATIC_OVERRIDES := overrides
OVERRIDES    := $(BUILD_DIR)/overrides
PATCHED_ISO  := $(DIST_DIR)/$(GAME_ID)-zh.iso
PATCH_XDELTA := $(DIST_DIR)/$(GAME_ID)-zh.xdelta
PLUGIN_DIR   := plugin
PLUGIN_BUILD := $(abspath $(BUILD_DIR)/plugin)
PLUGIN_EBOOT := $(PLUGIN_BUILD)/EBOOT.BIN
PLUGIN_PRX   := $(PLUGIN_BUILD)/EVAJORT.PRX
PLUGIN_FONT  := $(PLUGIN_DIR)/fonts.pgf
ORIGINAL_EBOOT := $(TEMP_DIR)/$(GAME_ID)/PSP_GAME/SYSDIR/EBOOT.BIN
DECRYPTED_EBOOT := $(TEMP_DIR)/cache/$(GAME_ID)/EBOOT.BIN
PSPDECRYPT   := third_party/pspdecrypt/build/pspdecrypt
UV_CACHE_DIR ?= $(BUILD_DIR)/uv-cache
UV_RUN       := UV_CACHE_DIR='$(UV_CACHE_DIR)' uv run python -m app

.PHONY: export check plugin plugin-overlay build verify test xdelta release clean

export:
	$(UV_RUN) export --iso '$(SOURCE_ISO)' --translations '$(TRANSLATIONS)' --work-dir '$(TEMP_DIR)/cache/$(GAME_ID)' --report '$(BUILD_DIR)/reports/export.json'

check: $(DECRYPTED_EBOOT)
	$(UV_RUN) check --iso '$(SOURCE_ISO)' --eboot '$(DECRYPTED_EBOOT)' --translations '$(TRANSLATIONS)' --work-dir '$(TEMP_DIR)/cache/$(GAME_ID)' --report '$(BUILD_DIR)/reports/check.json'

$(DECRYPTED_EBOOT): $(ORIGINAL_EBOOT) $(PSPDECRYPT)
	mkdir -p '$(@D)'
	'$(PSPDECRYPT)' -o '$@' '$<'

plugin:
	$(MAKE) -C '$(PLUGIN_DIR)' BUILD_DIR='$(PLUGIN_BUILD)'

plugin-overlay: plugin $(DECRYPTED_EBOOT)
	@test -f '$(ORIGINAL_EBOOT)' || (echo "Original EBOOT not found: $(ORIGINAL_EBOOT)" >&2; exit 1)
	@test -f '$(PLUGIN_FONT)' || (echo "Custom PGF not found: $(PLUGIN_FONT)" >&2; exit 1)
	@test -x '$(PSPDECRYPT)' || (echo "pspdecrypt not executable: $(PSPDECRYPT)" >&2; exit 1)
	rm -rf '$(OVERRIDES)'
	mkdir -p '$(OVERRIDES)/PSP_GAME/SYSDIR' '$(OVERRIDES)/PSP_GAME/USRDIR'
	@if [ -d '$(STATIC_OVERRIDES)' ]; then cp -R '$(STATIC_OVERRIDES)/.' '$(OVERRIDES)/'; fi
	cp '$(PLUGIN_EBOOT)' '$(OVERRIDES)/PSP_GAME/SYSDIR/EBOOT.BIN'
	cp '$(PLUGIN_PRX)' '$(OVERRIDES)/PSP_GAME/SYSDIR/EVAJORT.PRX'
	cp '$(DECRYPTED_EBOOT)' '$(OVERRIDES)/PSP_GAME/SYSDIR/BOOT.BIN'
	cp '$(PLUGIN_FONT)' '$(OVERRIDES)/PSP_GAME/USRDIR/fonts.pgf'

build: plugin-overlay
	$(UV_RUN) build --iso '$(SOURCE_ISO)' --translations '$(TRANSLATIONS)' --overrides '$(OVERRIDES)' --build-dir '$(BUILD_DIR)' --output '$(PATCHED_ISO)'

verify:
	$(UV_RUN) verify --source-iso '$(SOURCE_ISO)' --patched-iso '$(PATCHED_ISO)' --translations '$(TRANSLATIONS)' --report '$(BUILD_DIR)/reports/verify.json'

test:
	UV_CACHE_DIR='$(UV_CACHE_DIR)' uv run python -m unittest discover -s tests -v

xdelta: verify
	mkdir -p '$(DIST_DIR)'
	xdelta3 -e -9 -S djw -f -s '$(SOURCE_ISO)' '$(PATCHED_ISO)' '$(PATCH_XDELTA)'

verify: build

release: xdelta
	shasum -a 256 '$(PATCHED_ISO)' '$(PATCH_XDELTA)' > '$(DIST_DIR)/SHA256SUMS'

clean:
	rm -rf '$(BUILD_DIR)' '$(DIST_DIR)'
