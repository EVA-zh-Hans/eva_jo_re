CMAKE ?= cmake
BUILD_DIR ?= build
PSP_TOOLCHAIN ?= $(PSPDEV)/psp/share/pspdev.cmake

all: build

check-toolchain:
	@test -n "$(PSPDEV)" || (echo "PSPDEV is not set" >&2; exit 1)
	@test -f "$(PSP_TOOLCHAIN)" || (echo "PSP toolchain not found: $(PSP_TOOLCHAIN)" >&2; exit 1)

configure: check-toolchain
	$(CMAKE) -S . -B "$(BUILD_DIR)" -DCMAKE_TOOLCHAIN_FILE="$(PSP_TOOLCHAIN)"

build: configure
	$(CMAKE) --build "$(BUILD_DIR)"

clean:
	$(CMAKE) -E remove_directory "$(BUILD_DIR)"

.PHONY: all check-toolchain configure build clean
