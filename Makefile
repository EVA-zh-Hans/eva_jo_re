GAME_ID      := ULJS00201
TEMP_DIR     := temp
BUILD_DIR    := build
DIST_DIR     := dist
SOURCE_ISO   := $(TEMP_DIR)/$(GAME_ID).iso
TRANSLATIONS := translations
OVERRIDES    := overrides
PATCHED_ISO  := $(DIST_DIR)/$(GAME_ID)-zh.iso
PATCH_XDELTA := $(DIST_DIR)/$(GAME_ID)-zh.xdelta
UV_CACHE_DIR ?= $(BUILD_DIR)/uv-cache
UV_RUN       := UV_CACHE_DIR='$(UV_CACHE_DIR)' uv run python -m app

.PHONY: export check build verify test xdelta release clean

export:
	$(UV_RUN) export --iso '$(SOURCE_ISO)' --translations '$(TRANSLATIONS)' --work-dir '$(TEMP_DIR)/cache/$(GAME_ID)' --report '$(BUILD_DIR)/reports/export.json'

check:
	$(UV_RUN) check --iso '$(SOURCE_ISO)' --translations '$(TRANSLATIONS)' --work-dir '$(TEMP_DIR)/cache/$(GAME_ID)' --report '$(BUILD_DIR)/reports/check.json'

build:
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
