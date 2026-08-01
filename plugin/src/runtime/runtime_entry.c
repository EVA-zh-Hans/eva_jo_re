#include <pspkernel.h>
#include <pspmodulemgr.h>

#include "runtime_args.h"
#include "runtime_patch.h"

PSP_MODULE_INFO("EVAJORuntime", PSP_MODULE_USER, 1, 0);

int module_start(SceSize args, void *argp)
{
    const EvaJoRuntimeStartArgs *start_args;
    SceKernelModuleInfo info;

    if (args < sizeof(*start_args) || !argp) {
        return 0;
    }

    start_args = (const EvaJoRuntimeStartArgs *)argp;
    if (start_args->boot_mid < 0) {
        return 0;
    }

    info.size = sizeof(info);
    if (sceKernelQueryModuleInfo(start_args->boot_mid, &info) < 0) {
        return 0;
    }

    RuntimePatch_Install(info.segmentaddr[0]);
    return 0;
}

int module_stop(SceSize args, void *argp)
{
    (void)args;
    (void)argp;
    return 0;
}
