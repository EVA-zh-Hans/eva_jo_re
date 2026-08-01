#pragma once

#include <psptypes.h>

#define EVAJO_STD_BASE 0x08804000u

u32 HookWrite_GameAddr(u32 game_base, u32 original_addr);
void HookWrite_Call(u32 addr, const void *target);
void HookWrite_FlushCaches(void);
