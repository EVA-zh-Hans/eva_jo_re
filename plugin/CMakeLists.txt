cmake_minimum_required(VERSION 3.10)

project(EVAJO_FONT_PATCH C ASM)

set(LOADER_SOURCES
    src/loader/loader.c
)

set(RUNTIME_SOURCES
    src/runtime/runtime_entry.c
    src/runtime/runtime_patch.c
    src/runtime/hook_write.c
    src/runtime/patches/font_patch.c
    src/sceLibFont.S
)

add_prx_module(EBOOT ${LOADER_SOURCES} src/loader/exports_loader.exp)
add_prx_module(EVAJORT ${RUNTIME_SOURCES} src/runtime/exports_runtime.exp)

target_compile_options(EBOOT PRIVATE -O2 -Wall)
target_compile_options(EVAJORT PRIVATE -O2 -G0 -Wall -fno-pic)

target_include_directories(EBOOT PRIVATE include)
target_include_directories(EVAJORT PRIVATE include)

set_property(SOURCE src/sceLibFont.S APPEND PROPERTY COMPILE_DEFINITIONS
    F_sceLibFont_0000
    F_sceLibFont_0014
)

add_custom_command(
    TARGET EBOOT
    POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        $<TARGET_FILE_DIR:EBOOT>/EBOOT.prx
        $<TARGET_FILE_DIR:EBOOT>/EBOOT.BIN
)

add_custom_command(
    TARGET EVAJORT
    POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        $<TARGET_FILE_DIR:EVAJORT>/EVAJORT.prx
        $<TARGET_FILE_DIR:EVAJORT>/EVAJORT.PRX
)
