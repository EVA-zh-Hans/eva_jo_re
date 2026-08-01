#include <pspkernel.h>
#include <pspmodulemgr.h>

#include "runtime_args.h"

PSP_MODULE_INFO("EVAJO_LOADER", PSP_MODULE_USER, 1, 0);
PSP_NO_CREATE_MAIN_THREAD();

#define ORIGINAL_BOOT_PATH "disc0:/PSP_GAME/SYSDIR/BOOT.BIN"
#define RUNTIME_PATH "disc0:/PSP_GAME/SYSDIR/EVAJORT.PRX"

static int main_thread(SceSize args, void *argp)
{
    SceUID boot_mid;
    SceUID runtime_mid;
    EvaJoRuntimeStartArgs runtime_args;

    (void)args;
    (void)argp;

    boot_mid = sceKernelLoadModule(ORIGINAL_BOOT_PATH, 0, NULL);
    if (boot_mid < 0) {
        return sceKernelExitDeleteThread(boot_mid);
    }

    runtime_mid = sceKernelLoadModule(RUNTIME_PATH, 0, NULL);
    if (runtime_mid < 0) {
        return sceKernelExitDeleteThread(runtime_mid);
    }

    runtime_args.boot_mid = boot_mid;
    if (sceKernelStartModule(
            runtime_mid,
            sizeof(runtime_args),
            &runtime_args,
            NULL,
            NULL) < 0) {
        return sceKernelExitDeleteThread(-1);
    }

    sceKernelStartModule(boot_mid, 0, NULL, NULL, NULL);
    return sceKernelExitDeleteThread(0);
}

int module_start(SceSize args, void *argp)
{
    SceUID thread = sceKernelCreateThread("evajo_loader", main_thread, 0x1F, 0x1000, 0, NULL);

    if (thread >= 0) {
        sceKernelStartThread(thread, args, argp);
    }
    return 0;
}

int module_stop(SceSize args, void *argp)
{
    (void)args;
    (void)argp;
    return 0;
}
