#include <psptypes.h>

#include "hook_write.h"

#define FONT_OPEN_CALL_ADDR 0x089CA918u
#define CUSTOM_FONT_PATH "disc0:/PSP_GAME/USRDIR/fonts.pgf"

int sceFontOpenUserFile(int font_lib_handle, int file_name_addr, int mode, int *error_code);

static int FontPatch_Open(int font_lib_handle, int index, int mode, int *error_code)
{
    (void)index;
    return sceFontOpenUserFile(font_lib_handle, (int)CUSTOM_FONT_PATH, mode, error_code);
}

void FontPatch_Install(u32 game_base)
{
    HookWrite_Call(HookWrite_GameAddr(game_base, FONT_OPEN_CALL_ADDR), FontPatch_Open);
}
