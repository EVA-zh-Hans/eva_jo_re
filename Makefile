GAME_ID ?= 00201

# Temporary and Build Directories
TEMP_DIR        := temp
DOWNLOAD_DIR    := $(TEMP_DIR)/downloads
BUILD_DIR       := build
EXPORT_GAME_DIR := $(BUILD_DIR)/ULJS00201/PSP_GAME
EXPORT_BIN_DIR  := $(EXPORT_GAME_DIR)/USRDIR
EXPORT_SYSDIR   := $(EXPORT_GAME_DIR)/SYSDIR
EXPORT_USRDIR   := $(EXPORT_GAME_DIR)/USRDIR
TOOLS_DIR       := $(BUILD_DIR)/tools

# Source Directories
PSP_GAME_DIR    := $(TEMP_DIR)/ULJS00201/PSP_GAME
USRDIR          := $(PSP_GAME_DIR)/USRDIR

# ==========================================
# ISO & Patch Operations
# ==========================================

extract_iso:
	@echo "Extracting game files..."
	$(UV_RUN) scripts/pack/unpack.py -o '$(TEMP_DIR)/ULJS00201' '$(TEMP_DIR)/ULJS00201.iso'

decrypt_eboot: pspdecrypt
	@echo "Decrypting EBOOT..."
	@mkdir -p $(EXPORT_SYSDIR)
	./$(TOOLS_DIR)/pspdecrypt '$(PSP_GAME_DIR)/SYSDIR/EBOOT.BIN' -o '$(EXPORT_SYSDIR)/BOOT.BIN'

repack_iso:
	@echo "Repacking game files into ISO..."
	@mkdir -p $(BUILD_DIR)
	$(UV_RUN) scripts/pack/repack_add.py '$(TEMP_DIR)/ULJS$(GAME_ID).iso' '$(PATCHED_ISO)' '$(BUILD_DIR)/ULJS00201'

gen_xdelta:
	@echo "Generating xdelta patch..."
	xdelta3 -e -9 -S djw -f -s '$(TEMP_DIR)/ULJS$(GAME_ID).iso' '$(PATCHED_ISO)' '$(PATCH_XDELTA)'

patch_iso: repack_iso gen_xdelta