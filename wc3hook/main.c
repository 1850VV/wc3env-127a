/* wc3hook.dll entry: DllMain, hook installation order, the ready signal, heartbeat. */
#include "wc3hook.h"

char g_dir[MAX_PATH];
HANDLE g_log = INVALID_HANDLE_VALUE;
BYTE *g_base;
static HMODULE(WINAPI *LoadLibraryA_orig)(LPCSTR);
static volatile LONG g_engine_ready;

/* War3.exe loads the engine after resuming. Install engine hooks before its
 * GameMain runs; the bootstrap-ready event only releases the suspended launcher. */
static void engine_loaded(HMODULE module) {
    if (!module || module != GetModuleHandleW(L"Game.dll") || InterlockedCompareExchange(&g_engine_ready, 1, 0))
        return;
    g_base = (BYTE *)module;
    if (memcmp(g_base + P127_GET_UNIT_X, "\x55\x8b\xec\x8b\x4d\x08", 6) ||
        memcmp(g_base + P127_GAME_UPDATE, "\x55\x8b\xec\x6a\xff", 5)) {
        hook_log("1.27a engine prologue mismatch");
        ExitProcess(1);
    }
    clock_init_hooks();
    accessors_init();
    step_init_hooks();
    players_init_hooks();
    setup_init_hooks();
    act_init_hooks();
    events_init_hooks();
    result_init_hooks();
    require_hook(MH_EnableHook(MH_ALL_HOOKS), "enable 1.27a engine hooks");
    hook_log("1.27a engine initialized base=%p", g_base);
    InterlockedExchange(&g_engine_ready, 2);
}

static HMODULE WINAPI LoadLibraryA_hook(LPCSTR name) {
    HMODULE result = LoadLibraryA_orig(name);
    engine_loaded(result);
    return result;
}

__declspec(dllexport) int WC3Adapter127(void) {
    return 127;
}

MH_STATUS require_hook(MH_STATUS status, const char *name) {
    if (status != MH_OK) {
        hook_log("required hook %s failed: %s", name, MH_StatusToString(status));
        ExitProcess(1);
    }
    return status;
}

void hook_log(const char *fmt, ...) {
    char buf[1024];
    DWORD n;
    va_list ap;
    va_start(ap, fmt);
    int len = _vsnprintf(buf, sizeof buf - 2, fmt, ap);
    va_end(ap);
    if (len < 0)
        len = sizeof buf - 2;
    buf[len++] = '\n';
    if (g_log != INVALID_HANDLE_VALUE)
        WriteFile(g_log, buf, len, &n, NULL);
}

/* heartbeat: one log line every 5 s so a "stuck" game can be read off hook-<pid>.log */
static DWORD WINAPI heartbeat_thread(LPVOID arg) {
    for (;;) {
        Sleep_orig ? Sleep_orig(5000) : Sleep(5000);
        hook_log("heartbeat: step_target=%lu stepmode=%ld stepping=%ld frozen=%ld speed=%.0f render=%ld frames=%ld "
                 "status=%ld",
                 g_step_target, g_stepmode, g_stepping, g_frozen, g_speed, g_render, g_frames_seen, g_status);
    }
}

static DWORD WINAPI main_thread(LPVOID arg) {
    char exe_path[MAX_PATH];
    GetModuleFileNameA(NULL, exe_path, MAX_PATH);
    hook_log("wc3hook loaded: pid=%lu exe=%s base=%p cmdline=%s", GetCurrentProcessId(), exe_path, g_base,
             GetCommandLineA());
    /* Above realtime the game's timed waits scale to zero and its threads spin; below-normal
     * priority keeps a run from freezing the desktop. */
    SetPriorityClass(GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS);
    {
        require_hook(MH_Initialize(), "MinHook initialization");
        if (GetModuleHandleW(L"Game.dll")) {
            /* Injected into a game that was already running (not launched suspended): nobody passed
             * settings, so keep the player's normal window instead of the background default. */
            SetEnvironmentVariableA("WC3HOOK_WINDOW_MODE", "interactive");
            hook_log("late attach: the game was already running");
        }
        rpc_init();
        if (!LoadLibraryW(L"shell32.dll") || !LoadLibraryW(L"Mss32.dll"))
            ExitProcess(1);
        instance_init_hooks();
        diag_init_hooks();
        MH_CreateHookApi(L"kernel32", "LoadLibraryA", LoadLibraryA_hook, (void **)&LoadLibraryA_orig);
        CreateThread(NULL, 0, heartbeat_thread, NULL, 0, NULL);
        require_hook(MH_EnableHook(MH_ALL_HOOKS), "enable hooks");
        engine_loaded(GetModuleHandleW(L"Game.dll"));
    }
    {
        /* Tell the injector the hooks are in place; it resumes the game's main thread only then,
         * so even the earliest startup code (the instance guards) runs hooked. */
        char ev[64];
        _snprintf(ev, sizeof ev, "wc3hook-ready-%lu", GetCurrentProcessId());
        HANDLE h = OpenEventA(EVENT_MODIFY_STATE, FALSE, ev);
        if (h) {
            SetEvent(h);
            CloseHandle(h);
            hook_log("signalled %s", ev);
        }
    }
    while (g_engine_ready != 2)
        Sleep(10);
    pipe_thread(NULL);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        g_base = (BYTE *)GetModuleHandleA(NULL);
        GetModuleFileNameA(inst, g_dir, MAX_PATH);
        char *slash = strrchr(g_dir, '\\');
        if (slash)
            slash[1] = 0;
        wchar_t logdir[MAX_PATH], path[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(L"WC3HOOK_LOG_DIR", logdir, MAX_PATH);
        if (!n || n >= MAX_PATH) {
            GetModuleFileNameW(inst, logdir, MAX_PATH);
            wchar_t *end = wcsrchr(logdir, L'\\');
            if (end)
                *end = 0;
        }
        _snwprintf(path, MAX_PATH, L"%s\\hook-%lu.log", logdir, GetCurrentProcessId());
        path[MAX_PATH - 1] = 0;
        g_log = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
        InitializeCriticalSection(&g_lock);
        hook_log("DllMain attach");
        /* Never do real work inside DllMain (loader lock); spin a thread. Hooks are installed there,
         * long before the game's own startup code runs. */
        CreateThread(NULL, 0, main_thread, NULL, 0, NULL);
    }
    return TRUE;
}
