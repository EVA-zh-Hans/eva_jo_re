#include <pspkernel.h>
#include <pspsdk.h>

#include "hook_write.h"

#define MIPS_J_ADDRESS(addr) (((u32)(addr) & 0x0fffffffu) >> 2)
#define JAL_TO(addr) (0x0c000000u | MIPS_J_ADDRESS(addr))

u32 HookWrite_GameAddr(u32 game_base, u32 original_addr)
{
    return game_base + (original_addr - EVAJO_STD_BASE);
}

void HookWrite_Call(u32 addr, const void *target)
{
    _sw(JAL_TO((u32)target), addr);
}

void HookWrite_FlushCaches(void)
{
    sceKernelDcacheWritebackAll();
    sceKernelIcacheInvalidateAll();
}
