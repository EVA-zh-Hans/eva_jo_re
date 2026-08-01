#include "hook_write.h"
#include "runtime_patch.h"

void FontPatch_Install(u32 game_base);

void RuntimePatch_Install(u32 game_base)
{
    FontPatch_Install(game_base);
    HookWrite_FlushCaches();
}
