/* Separate research DLL. No 1.29 engine offsets and no production RPC readiness claim. */
#include "wc3hook.h"
#include "objects127.h"

BYTE *g_base;
volatile LONG g_render = 1;
DWORD g_game_tid;
static HANDLE log_file = INVALID_HANDLE_VALUE;
static volatile LONG engine_seen, units_seen;
static LARGE_INTEGER started, frequency;
static HMODULE(WINAPI *LoadLibraryA_orig)(LPCSTR);
typedef int(__cdecl *CreateUnitFn)(int, int, float *, float *, float *);
static CreateUnitFn CreateUnit_orig;
typedef int(__fastcall *GameUpdateFn)(BYTE *, void *, DWORD);
static GameUpdateFn GameUpdate_orig;
typedef int(__fastcall *PacketFn)(BYTE *, void *);
static PacketFn Packet_orig;
static volatile LONG packet_count;
static DWORD(__cdecl *GameTick_orig)(void);
static DWORD tick_callers[64];
static volatile LONG tick_guard;
static const DWORD step_targets[] = {1000, 1025, 1275, 2275, 7275};
static unsigned step_index;
static volatile DWORD reached_at;
static DWORD step_started_at;
static int enable_step_probe;
static int probe_clock_active;
static double probe_speed;
static volatile LONG probe_next;
static CRITICAL_SECTION probe_state_lock;
static int enable_action_probe, player_count = 1;
typedef struct {
    int handle, sent;
    float x, y, target_x, target_y;
} Worker;
static Worker workers[2];
static void(__cdecl *StartMeleeAI_orig)(int, int);
static int enable_event_probe, victim_handle, death_events;
static int enable_object_probe;
static int episode = 1, episode_limit = 1, restarting;
static BYTE registered_wire[2];
static int(__fastcall *EventRegistered_orig)(void *, void *, int);
static int(__fastcall *EventDispatch_orig)(void *, void *, int, BYTE *);
static BYTE *probe_game;
static char replay_path[MAX_PATH];
static int replay_check;
static int enable_budget_probe;
static void *frame_tls;
static DWORD snapshot_hash, snapshot_count, serviced_target;
static volatile DWORD producer_target = 1000, sent_ms;
static int(__fastcall *TurnProducer_orig)(BYTE *, void *);
static BYTE *(__fastcall *TurnTime_orig)(BYTE *, const WORD *);

static BYTE *__fastcall TurnTime_hook(BYTE *store, const WORD *ms) {
    if ((BYTE *)_ReturnAddress() == g_base + P127_TURN_TIME_RET) {
        WORD credit = *ms;
        if (enable_budget_probe && !replay_check && !restarting && credit) {
            DWORD remaining = producer_target - sent_ms;
            if ((LONG)remaining <= 0) {
                hook_log("FAIL producer exceeded its published budget");
                ExitProcess(86);
            }
            credit = (WORD)(remaining > 400 ? 400 : remaining);
        }
        sent_ms += credit; /* Native transport may deliver before the call returns. */
        return TurnTime_orig(store, &credit);
    }
    return TurnTime_orig(store, ms);
}

static int __fastcall TurnProducer_hook(BYTE *host, void *edx) {
    if (!*(DWORD *)(host + P127_HOST_TIME_COUNT))
        sent_ms = 0;
    if (enable_budget_probe && !replay_check && !restarting && (LONG)(producer_target - sent_ms) <= 0)
        return 1;
    return TurnProducer_orig(host, edx);
}

typedef struct {
    DWORD count, hash, own, visible, matched_worker, target;
    int log_objects;
} Snapshot;

static float unit_real(int handle, DWORD rva);
static void signal_phase(const char *phase);
static void restart_probe(void);

typedef struct {
    BYTE *node, *unit;
} EventLookup;

static BYTE *resolve_ref(BYTE *object, int offset) {
    return ((BYTE * (__fastcall *)(DWORD, DWORD))(g_base + P127_RESOLVE_REF))(*(DWORD *)(object + offset),
                                                                              *(DWORD *)(object + offset + 4));
}

static int __fastcall event_unit(BYTE *unit, EventLookup *lookup) {
    if (resolve_ref(unit, 0xc) == lookup->node) {
        lookup->unit = unit;
        return 0;
    }
    return 1;
}

static int __fastcall EventRegistered_hook(void *self, void *edx, int id) {
    int registered = EventRegistered_orig(self, edx, id);
    return registered || (enable_event_probe && id == 0x80214) ||
           (enable_object_probe && probe_objects127_wants_event(id));
}

static int __fastcall EventDispatch_hook(void *self, void *edx, int id, BYTE *object) {
    if (enable_object_probe && object && probe_objects127_wants_event(id))
        probe_objects127_event(id, object);
    if (enable_event_probe && id == 0x80214 && object) {
        EventLookup lookup = {resolve_ref(object, P127_EVENT_UNIT_REF), NULL};
        if (lookup.node)
            ((void(__fastcall *)(int, void *, void *, int))(g_base + P127_ENUM_OBJECTS))(UNIT_CLASS, event_unit,
                                                                                         &lookup, 0);
        BYTE *expected =
            victim_handle ? ((BYTE * (__fastcall *)(int))(g_base + P127_HANDLE_UNIT))(victim_handle) : NULL;
        if (expected && lookup.unit == expected) {
            BYTE *owner = ((BYTE * (__fastcall *)(BYTE *))(g_base + P127_UNIT_OWNER))(lookup.unit);
            hook_log("native_death id=%lu type=%08lx owner=%d", *(DWORD *)(lookup.unit + 0xc),
                     *(DWORD *)(lookup.unit + P127_OBJECT_TYPE), owner ? owner[0x30] : -1);
            death_events++;
        } else {
            hook_log("event_death_unmatched node=%p unit=%p expected=%p", lookup.node, lookup.unit, expected);
        }
    }
    return EventDispatch_orig(self, edx, id, object);
}

static void stage_damage(void) {
    if (!victim_handle || !workers[0].handle) {
        hook_log("FAIL event fixture has no attacker/victim");
        ExitProcess(96);
    }
    float amount = 1000;
    typedef int(__cdecl * DamageFn)(int, int, float *, int, int, int, int, int);
    union {
        int bits;
        float real;
    } before, after;
    typedef int(__cdecl * StateFn)(int, int);
    before.bits = ((StateFn)(g_base + P127_GET_UNIT_STATE))(victim_handle, 0);
    int accepted = ((DamageFn)(g_base + P127_DAMAGE_TARGET))(workers[0].handle, victim_handle, &amount, 1, 0, 0, 4, 0);
    after.bits = ((StateFn)(g_base + P127_GET_UNIT_STATE))(victim_handle, 0);
    hook_log("damage_staged accepted=%d before=%.3f after=%.3f death_events=%d", accepted, before.real, after.real,
             death_events);
    if (before.real <= 0 || after.real > 0 || death_events != 1) {
        hook_log("FAIL staged native damage/death observation");
        ExitProcess(97);
    }
    signal_phase("wc3probe-events");
}

static int __fastcall snapshot_unit(BYTE *unit, Snapshot *snap) {
    float xyz[3], hp = 0;
    object127_position(unit, xyz);
    float *result =
        ((float *(__fastcall *)(BYTE *, void *, float *, int))(g_base + P127_UNIT_STATE))(unit, NULL, &hp, 0);
    hp = *result;
    BYTE *owner = ((BYTE * (__fastcall *)(BYTE *))(g_base + P127_UNIT_OWNER))(unit);
    DWORD *vtable = *(DWORD **)unit;
    int visible = ((int(__fastcall *)(BYTE *, void *, int, int, int))vtable[0xfc / 4])(unit, NULL, 0, 0, 4);
    int slot = owner ? owner[0x30] : -1;
    if (!owner || slot > 15 || !_finite(xyz[0]) || !_finite(xyz[1]) || !_finite(hp)) {
        hook_log("FAIL invalid object observation id=%lu slot=%d", *(DWORD *)(unit + 0xc), slot);
        ExitProcess(88);
    }
    DWORD values[7] = {*(DWORD *)(unit + 0xc), *(DWORD *)(unit + P127_OBJECT_TYPE), (DWORD)slot, 0, 0, 0, visible != 0};
    memcpy(values + 3, xyz, 8);
    memcpy(values + 5, &hp, 4);
    if (snap->log_objects)
        hook_log("unit_observation target=%lu id=%08lx type=%08lx owner=%d x=%08lx y=%08lx hp=%08lx visible=%d",
                 snap->target, values[0], values[1], slot, values[3], values[4], values[5], visible != 0);
    DWORD hash = 2166136261u;
    for (int i = 0; i < 7; i++)
        hash = (hash ^ values[i]) * 16777619u;
    snap->hash ^= hash; /* Enumeration order does not affect this diagnostic checksum. */
    snap->count++;
    snap->own += slot == 0;
    snap->visible += visible != 0;
    for (int p = 0; p < player_count; p++) {
        int handle = workers[p].handle;
        if (handle && unit == ((BYTE * (__fastcall *)(int))(g_base + P127_HANDLE_UNIT))(handle)) {
            if (xyz[0] != unit_real(handle, P127_GET_UNIT_X) || xyz[1] != unit_real(handle, P127_GET_UNIT_Y) ||
                slot != p || values[1] != (DWORD)((int(__cdecl *)(int))(g_base + P127_GET_UNIT_TYPE))(handle)) {
                hook_log("FAIL object accessor differs from player %d worker native", p);
                ExitProcess(89);
            }
            snap->matched_worker++;
        }
    }
    return 1;
}

static Snapshot snapshot_units(const char *phase, DWORD target) {
    Snapshot snap = {0};
    snap.target = target;
    snap.log_objects = !strcmp(phase, "update");
    ((void(__fastcall *)(int, void *, void *, int))(g_base + P127_ENUM_OBJECTS))(UNIT_CLASS, snapshot_unit, &snap, 0);
    hook_log("object_snapshot phase=%s target=%lu count=%lu hash=%08lx own=%lu visible=%lu worker=%lu", phase, target,
             snap.count, snap.hash, snap.own, snap.visible, snap.matched_worker);
    if (snap.count < 12 || (enable_action_probe && snap.matched_worker != (DWORD)player_count)) {
        hook_log("FAIL incomplete object enumeration");
        ExitProcess(90);
    }
    return snap;
}

void rpc_service_jobs_between_frames(void) {
    if (!frame_tls || !reached_at || serviced_target == step_targets[step_index])
        return;
    DWORD slot = *(DWORD *)(g_base + P127_TLS_SLOT);
    void *prior = TlsGetValue(slot);
    TlsSetValue(slot, frame_tls);
    Snapshot snap = snapshot_units("frame_wait", step_targets[step_index]);
    if (snap.hash != snapshot_hash || snap.count != snapshot_count) {
        hook_log("FAIL frozen frame-wait snapshot differs from update snapshot");
        ExitProcess(91);
    }
    serviced_target = step_targets[step_index];
    if (step_index + 1 == sizeof step_targets / sizeof step_targets[0] && episode < episode_limit)
        restart_probe();
    TlsSetValue(slot, prior);
}

void chat_key(UINT message, WPARAM key) {
    (void)message;
    (void)key;
}

void hook_log(const char *fmt, ...) {
    char line[2048];
    LARGE_INTEGER now;
    if (probe_clock_active)
        now.QuadPart = real_qpc();
    else
        QueryPerformanceCounter(&now);
    int prefix = _snprintf(line, sizeof line, "%.3f tid=%lu ",
                           1000.0 * (now.QuadPart - started.QuadPart) / frequency.QuadPart, GetCurrentThreadId());
    va_list ap;
    va_start(ap, fmt);
    int n = _vsnprintf(line + prefix, sizeof line - prefix - 2, fmt, ap);
    va_end(ap);
    if (n < 0)
        n = sizeof line - prefix - 2;
    line[prefix + n++] = '\n';
    DWORD written;
    if (log_file != INVALID_HANDLE_VALUE)
        WriteFile(log_file, line, prefix + n, &written, NULL);
}

static DWORD wall_ms(void) {
    LARGE_INTEGER now;
    if (probe_clock_active)
        now.QuadPart = real_qpc();
    else
        QueryPerformanceCounter(&now);
    return (DWORD)(1000 * (now.QuadPart - started.QuadPart) / frequency.QuadPart);
}

static DWORD WINAPI control_probe(LPVOID unused) {
    (void)unused;
    for (;;) {
        Sleep_orig(5);
        EnterCriticalSection(&probe_state_lock);
        DWORD reached = reached_at;
        if (reached && step_index + 1 < sizeof step_targets / sizeof step_targets[0] && wall_ms() - reached >= 500 &&
            !InterlockedCompareExchange(&probe_next, 1, 0))
            clock_freeze(0);
        LeaveCriticalSection(&probe_state_lock);
    }
}

MH_STATUS require_hook(MH_STATUS status, const char *name) {
    if (status != MH_OK) {
        hook_log("FAIL hook=%s error=%s", name, MH_StatusToString(status));
        ExitProcess(71);
    }
    return status;
}

static void signal_phase(const char *phase) {
    char name[80];
    _snprintf(name, sizeof name, "%s-%lu", phase, GetCurrentProcessId());
    HANDLE event = OpenEventA(EVENT_MODIFY_STATE, FALSE, name);
    if (event) {
        SetEvent(event);
        CloseHandle(event);
    }
    hook_log("phase=%s", phase);
}

/* RVAs independently recovered from the pinned Game.dll native registrations.
 * Cdecl ABI and float-pointer arguments checked in disassembly before this probe. */

static int __cdecl CreateUnit_hook(int player, int type, float *x, float *y, float *face) {
    int handle = CreateUnit_orig(player, type, x, y, face);
    LONG count = InterlockedIncrement(&units_seen);
    if (enable_event_probe && !victim_handle && handle && type == 0x6e6d6831)
        victim_handle = handle;
    if (enable_action_probe && handle &&
        (type == 0x68706561 || type == 0x6f70656f || type == 0x65777370 || type == 0x7561636f)) {
        int slot = ((int(__cdecl *)(int))(g_base + P127_GET_PLAYER_ID))(player);
        if (slot >= 0 && slot < player_count && !workers[slot].handle)
            workers[slot].handle = handle;
    }
    if (handle && count <= 24) {
        typedef int(__cdecl * N1)(int);
        typedef int(__cdecl * N2)(int, int);
        union {
            int i;
            float f;
        } ux, uy, hp;
        ux.i = ((N1)(g_base + P127_GET_UNIT_X))(handle);
        uy.i = ((N1)(g_base + P127_GET_UNIT_Y))(handle);
        hp.i = ((N2)(g_base + P127_GET_UNIT_STATE))(handle, 0);
        int actual_type = ((N1)(g_base + P127_GET_UNIT_TYPE))(handle);
        int slot = ((N1)(g_base + P127_GET_PLAYER_ID))(player);
        hook_log("native_unit count=%ld handle=%08x slot=%d requested=%08x actual=%08x x=%.3f y=%.3f hp=%.3f", count,
                 handle, slot, type, actual_type, ux.f, uy.f, hp.f);
        if (actual_type != type || hp.f <= 0) {
            hook_log("FAIL native readback");
            ExitProcess(72);
        }
    }
    if (count == 12)
        signal_phase("wc3probe-units");
    return handle;
}

static float unit_real(int handle, DWORD rva) {
    union {
        int i;
        float f;
    } value;
    value.i = ((int(__cdecl *)(int))(g_base + rva))(handle);
    return value.f;
}

static void __cdecl StartMeleeAI_hook(int player, int script) {
    int slot = ((int(__cdecl *)(int))(g_base + P127_GET_PLAYER_ID))(player);
    if (player_count == 2 && slot >= 0 && slot < 2) {
        hook_log("startup_ai_suppressed player=%d", slot);
        return;
    }
    StartMeleeAI_orig(player, script);
}

static BYTE command_identity(BYTE *game, int player) {
    BYTE *table = game + P127_PLAYER_TABLE;
    BYTE wire = ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_PLAYER_WIRE_ID))(table, NULL, player);
    if (wire || player == 0)
        return wire;
    BYTE used[256] = {0};
    for (int group = 0; group < 2; group++) {
        DWORD count = *(DWORD *)(table + 0x2c + group * 0x10);
        BYTE **entries = *(BYTE ***)(table + 0x30 + group * 0x10);
        if (count > 16) {
            hook_log("FAIL unexpected native command table size=%lu", count);
            ExitProcess(92);
        }
        for (DWORD i = 0; i < count; i++)
            if (entries[i])
                used[entries[i][0x18]] = 1;
    }
    int id = 1;
    while (id <= 12 && used[id])
        id++;
    if (id > 12) {
        hook_log("FAIL no free command identity");
        ExitProcess(93);
    }
    BYTE info[25] = {0};
    _snprintf((char *)info, 16, "Probe %d", player);
    BYTE waiting =
        ((BYTE(__fastcall *)(BYTE *, void *, int, BYTE *))(g_base + P127_REGISTER_PLAYER))(table, NULL, id, info);
    if (waiting != (BYTE)((id - 1) | 0x80)) {
        hook_log("FAIL native registration tag=%u", waiting);
        ExitProcess(94);
    }
    ((void(__fastcall *)(BYTE *, void *, int, int))(g_base + P127_ASSIGN_PLAYER))(table, NULL, waiting, player);
    wire = ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_PLAYER_WIRE_ID))(table, NULL, player);
    hook_log("command_identity player=%d wire=%u registered=%d", player, wire, id);
    if (wire != id)
        ExitProcess(95);
    registered_wire[player] = wire;
    return wire;
}

static void restart_probe(void) {
    EnterCriticalSection(&probe_state_lock);
    for (int p = 0; p < player_count; p++) {
        if (!registered_wire[p])
            continue;
        BYTE *table = probe_game + P127_PLAYER_TABLE;
        BYTE wire = ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_PLAYER_WIRE_ID))(table, NULL, p);
        if (wire == registered_wire[p]) {
            ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_UNREGISTER_PLAYER))(table, NULL, wire);
            BYTE after = ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_PLAYER_WIRE_ID))(table, NULL, p);
            hook_log("command_identity_removed player=%d wire=%u after=%u", p, wire, after);
            if (after) {
                hook_log("FAIL command identity survived unregister");
                ExitProcess(98);
            }
        }
        registered_wire[p] = 0;
    }
    ((void(__cdecl *)(int))(g_base + P127_RESTART_GAME))(0);
    restarting = 1;
    episode++;
    step_index = 0;
    reached_at = step_started_at = serviced_target = snapshot_hash = snapshot_count = 0;
    producer_target = 1000;
    InterlockedExchange(&probe_next, 0);
    memset(workers, 0, sizeof workers);
    victim_handle = death_events = 0;
    probe_objects127_clear();
    command127_clear();
    InterlockedExchange(&units_seen, 0);
    probe_game = NULL;
    frame_tls = NULL;
    g_game_tid = 0;
    clock_set_speed(1);
    clock_freeze(0);
    hook_log("restart_scheduled episode=%d", episode);
    LeaveCriticalSection(&probe_state_lock);
}

static void send_move(BYTE *game, int player) {
    Worker *worker = &workers[player];
    int worker_handle = worker->handle;
    if (!worker_handle) {
        hook_log("FAIL no player-0 worker for packet probe");
        ExitProcess(80);
    }
    int local = ((int(__cdecl *)(void))(g_base + P127_LOCAL_PLAYER))();
    local = ((int(__cdecl *)(int))(g_base + P127_GET_PLAYER_ID))(local);
    if (local != 0) {
        hook_log("FAIL local player is %d", local);
        ExitProcess(81);
    }
    BYTE *unit = ((BYTE * (__fastcall *)(int))(g_base + P127_HANDLE_UNIT))(worker_handle);
    if (!unit) {
        hook_log("FAIL missing worker object");
        ExitProcess(82);
    }
    worker->x = unit_real(worker_handle, P127_GET_UNIT_X);
    worker->y = unit_real(worker_handle, P127_GET_UNIT_Y);
    worker->target_x = worker->x + (player ? -512 : 512);
    worker->target_y = worker->y;
    BYTE wire = command_identity(game, player);
    if (!wire) {
        hook_log("FAIL missing local wire identity");
        ExitProcess(83);
    }
    int accepted = command127_target(game, wire, unit, 851986, NULL, worker->target_x, worker->target_y);
    worker->sent = 1;
    hook_log("move_queued accepted=%d player=%d handle=%08x wire=%u from=%.3f,%.3f target=%.3f,%.3f", accepted, player,
             worker_handle, wire, worker->x, worker->y, worker->target_x, worker->target_y);
}

static void check_move(int player) {
    Worker *worker = &workers[player];
    int worker_handle = worker->handle;
    float x = unit_real(worker_handle, P127_GET_UNIT_X), y = unit_real(worker_handle, P127_GET_UNIT_Y);
    float dx = x - worker->target_x, dy = y - worker->target_y;
    int order = ((int(__cdecl *)(int))(g_base + P127_UNIT_ORDER))(worker_handle);
    hook_log("move_observed player=%d handle=%08x x=%.3f y=%.3f target_distance=%.3f order=%d", player, worker_handle,
             x, y, sqrt(dx * dx + dy * dy), order);
    if ((!worker->sent && !replay_check) || dx * dx + dy * dy > 80 * 80) {
        hook_log("FAIL recorded move did not reach its target");
        ExitProcess(84);
    }
}

/* Focused stepping experiment, not a production RPC or whole-match determinism claim. */
static int __fastcall GameUpdate_hook(BYTE *game, void *edx, DWORD now) {
    if (!enable_step_probe || *(DWORD *)(game + P127_GAME_STATE) < 4)
        return GameUpdate_orig(game, edx, now);
    if (restarting) {
        if (*(DWORD *)(game + P127_GAME_TIME) > 25)
            return GameUpdate_orig(game, edx, now);
        restarting = 0;
        hook_log("restart_observed episode=%d", episode);
    }
    EnterCriticalSection(&probe_state_lock);
    g_game_tid = GetCurrentThreadId();
    frame_tls = TlsGetValue(*(DWORD *)(g_base + P127_TLS_SLOT));
    if (!probe_game) {
        probe_game = game;
        hook_log("game_object address=%08lx", (DWORD)game);
    }
    DWORD provider = *(DWORD *)(game + P127_GAME_PROVIDER);
    if (provider != 0x4c4f4f50 && provider != 0x4e4f4e45) {
        hook_log("FAIL refusing non-offline provider=%08lx", provider);
        ExitProcess(76);
    }
    DWORD gt = *(DWORD *)(game + P127_GAME_TIME), wall = wall_ms();
    if (!step_started_at)
        step_started_at = wall;
    DWORD target = step_targets[step_index];
    if (gt > target) {
        hook_log("FAIL step overshoot actual=%lu target=%lu", gt, target);
        ExitProcess(77);
    }
    if (reached_at && wall - reached_at >= 500 && step_index + 1 < sizeof step_targets / sizeof step_targets[0] &&
        (!probe_clock_active || InterlockedExchange(&probe_next, 0))) {
        hook_log("frozen actual=%lu wall_ms=%lu credit=%lu", gt, wall - reached_at,
                 *(DWORD *)(game + P127_GAME_TURN_CREDIT));
        target = step_targets[++step_index];
        reached_at = 0;
        step_started_at = wall;
        if (probe_clock_active)
            clock_set_speed(probe_speed);
        if (enable_action_probe && step_index == 1)
            for (int p = 0; p < player_count; p++) {
                /* Like production create_game, playback configures the same agent identities;
                 * only the recording supplies commands. */
                command_identity(game, p);
                if (!replay_check)
                    send_move(game, p);
            }
        if (enable_event_probe && step_index == 2)
            stage_damage();
    }
    *(DWORD *)(game + P127_GAME_PENDING) = target - gt;
    int result = GameUpdate_orig(game, edx, *(DWORD *)(game + P127_GAME_PREV_NOW));
    /* Publish only after the native update flushes newly queued commands. */
    producer_target = target;
    DWORD actual = *(DWORD *)(game + P127_GAME_TIME);
    if (actual > target) {
        hook_log("FAIL step overshoot after update actual=%lu target=%lu", actual, target);
        ExitProcess(78);
    }
    if (actual == target && !reached_at) {
        reached_at = wall_ms();
        if (probe_clock_active)
            clock_freeze(1);
        hook_log("step_target actual=%lu target=%lu wall_ms=%lu credit=%lu", actual, target,
                 reached_at - step_started_at, *(DWORD *)(game + P127_GAME_TURN_CREDIT));
        if (enable_object_probe) {
            if (!step_index)
                probe_objects127_begin(game);
            probe_objects127_checkpoint(target);
        }
        Snapshot snap = snapshot_units("update", target);
        snapshot_hash = snap.hash;
        snapshot_count = snap.count;
        hook_log("producer_budget enabled=%d target=%lu sent_ms=%lu credit=%lu", enable_budget_probe, producer_target,
                 sent_ms, *(DWORD *)(game + P127_GAME_TURN_CREDIT));
        if (enable_budget_probe && !replay_check && (sent_ms != target || *(DWORD *)(game + P127_GAME_TURN_CREDIT))) {
            hook_log("FAIL unconsumed or missing producer time at target");
            ExitProcess(87);
        }
        for (int p = 0; enable_action_probe && p < player_count; p++) {
            Worker *worker = &workers[p];
            int worker_handle = worker->handle;
            float x = unit_real(worker_handle, P127_GET_UNIT_X), y = unit_real(worker_handle, P127_GET_UNIT_Y);
            int order = ((int(__cdecl *)(int))(g_base + P127_UNIT_ORDER))(worker_handle);
            hook_log("%s game_ms=%lu x=%.3f y=%.3f order=%d", p ? "other_worker_state" : "worker_state", actual, x, y,
                     order);
            if (!step_index && replay_check) {
                worker->x = x;
                worker->y = y;
                worker->target_x = x + (p ? -512 : 512);
                worker->target_y = y;
            }
        }
        if (step_index + 1 == sizeof step_targets / sizeof step_targets[0]) {
            if (enable_action_probe) {
                for (int p = 0; p < player_count; p++)
                    check_move(p);
                signal_phase("wc3probe-action");
            }
            if (replay_path[0]) {
                int saved = ((int(__fastcall *)(BYTE *, void *, const char *))(g_base + P127_SAVE_REPLAY))(game, NULL,
                                                                                                           replay_path);
                hook_log("replay_saved result=%d path=%s", saved, replay_path);
                if (!saved) {
                    hook_log("FAIL native replay save");
                    ExitProcess(85);
                }
            }
            signal_phase("wc3probe-steps");
        }
    }
    LeaveCriticalSection(&probe_state_lock);
    return result;
}

static int __fastcall Packet_hook(BYTE *message, void *context) {
    if (message && (message[4] == 0x1e || message[4] == 0x1f)) {
        LONG count = InterlockedIncrement(&packet_count);
        if (count <= 3) {
            BYTE *data = *(BYTE **)(message + 8);
            DWORD size = *(DWORD *)(message + 12);
            hook_log("turn_packet count=%ld type=%02x bytes=%lu ms=%u", count, message[4], size,
                     data && size >= 2 ? *(WORD *)data : 0);
            if (count == 1) {
                void *frames[24];
                USHORT n = CaptureStackBackTrace(0, 24, frames, NULL);
                for (USHORT i = 0; i < n; i++) {
                    HMODULE module = NULL;
                    char path[MAX_PATH] = {0};
                    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                       (LPCSTR)frames[i], &module);
                    GetModuleFileNameA(module, path, MAX_PATH);
                    char *name = strrchr(path, '\\');
                    hook_log("packet_stack i=%u module=%s rva=%08lx", i, name ? name + 1 : path,
                             (DWORD)((BYTE *)frames[i] - (BYTE *)module));
                }
            }
        }
    }
    return Packet_orig(message, context);
}

static DWORD __cdecl GameTick_hook(void) {
    DWORD rva = (DWORD)((BYTE *)_ReturnAddress() - g_base);
    if (rva >= 0x780000 && rva < 0x860000 && !InterlockedCompareExchange(&tick_guard, 1, 0)) {
        for (int i = 0; i < 64; i++) {
            if (tick_callers[i] == rva)
                break;
            if (!tick_callers[i]) {
                tick_callers[i] = rva;
                hook_log("timer_caller rva=%08lx", rva);
                break;
            }
        }
        InterlockedExchange(&tick_guard, 0);
    }
    return GameTick_orig();
}

static void engine_loaded(HMODULE module) {
    if (!module || module != GetModuleHandleW(L"Game.dll"))
        return;
    if (InterlockedCompareExchange(&engine_seen, 1, 0))
        return;
    g_base = (BYTE *)module;
    hook_log("engine_loaded base=%p executable_base=%p", g_base, GetModuleHandleW(NULL));
    /* Fail closed if a different image was mapped after the host verified the file. */
    if (memcmp(g_base + P127_GET_UNIT_X, "\x55\x8b\xec\x8b\x4d\x08", 6) ||
        memcmp(g_base + P127_GET_PLAYER_ID, "\x55\x8b\xec\x8b\x4d\x08", 6) ||
        memcmp(g_base + P127_CREATE_UNIT, "\x55\x8b\xec\x51\x56", 5) ||
        memcmp(g_base + P127_GAME_UPDATE, "\x55\x8b\xec\x6a\xff", 5)) {
        hook_log("FAIL native prologue mismatch");
        ExitProcess(73);
    }
    MH_CreateHook(g_base + P127_CREATE_UNIT, CreateUnit_hook, (void **)&CreateUnit_orig);
    require_hook(MH_CreateHook(g_base + P127_EVENT_REGISTERED, EventRegistered_hook, (void **)&EventRegistered_orig),
                 "create event registration probe");
    require_hook(MH_CreateHook(g_base + P127_EVENT_DISPATCH, EventDispatch_hook, (void **)&EventDispatch_orig),
                 "create event dispatch probe");
    require_hook(MH_EnableHook(g_base + P127_EVENT_REGISTERED), "enable event registration probe");
    require_hook(MH_EnableHook(g_base + P127_EVENT_DISPATCH), "enable event dispatch probe");
    require_hook(MH_CreateHook(g_base + P127_START_MELEE_AI, StartMeleeAI_hook, (void **)&StartMeleeAI_orig),
                 "create AI suppression");
    require_hook(MH_EnableHook(g_base + P127_START_MELEE_AI), "enable AI suppression");
    MH_CreateHook(g_base + P127_GAME_UPDATE, GameUpdate_hook, (void **)&GameUpdate_orig);
    MH_CreateHook(g_base + P127_PACKET_DELIVER, Packet_hook, (void **)&Packet_orig);
    MH_CreateHook(g_base + P127_TICK_WRAPPER, GameTick_hook, (void **)&GameTick_orig);
    require_hook(MH_CreateHook(g_base + P127_TURN_PRODUCER, TurnProducer_hook, (void **)&TurnProducer_orig),
                 "create producer probe");
    require_hook(MH_CreateHook(g_base + P127_TURN_TIME_WRITE, TurnTime_hook, (void **)&TurnTime_orig),
                 "create time writer probe");
    require_hook(MH_EnableHook(g_base + P127_CREATE_UNIT), "enable CreateUnit probe");
    require_hook(MH_EnableHook(g_base + P127_GAME_UPDATE), "enable GameUpdate probe");
    require_hook(MH_EnableHook(g_base + P127_PACKET_DELIVER), "enable packet trace");
    require_hook(MH_EnableHook(g_base + P127_TICK_WRAPPER), "enable timer trace");
    require_hook(MH_EnableHook(g_base + P127_TURN_PRODUCER), "enable producer probe");
    require_hook(MH_EnableHook(g_base + P127_TURN_TIME_WRITE), "enable time writer probe");
    if (probe_speed > 0) {
        /* Both wait callers and their stack layout were independently disassembled. */
        const ClockBindings bindings = {P127_RDTSC_HELPER, P127_FRAME_WAIT_RET, P127_FRAME_LOOP_WAIT_RET};
        clock_init_hooks_for(&bindings);
        probe_clock_active = 1;
        g_wait_floor = 1;
        require_hook(MH_EnableHook(MH_ALL_HOOKS), "enable probe clock");
        HANDLE control = CreateThread(NULL, 0, control_probe, NULL, 0, NULL);
        if (!control)
            ExitProcess(79);
        CloseHandle(control);
    }
    signal_phase("wc3probe-engine");
}

static HMODULE WINAPI LoadLibraryA_hook(LPCSTR name) {
    HMODULE result = LoadLibraryA_orig(name);
    if (result == GetModuleHandleW(L"Game.dll") && result) {
        hook_log("LoadLibraryA returned name=%s module=%p", name, result);
        engine_loaded(result);
    }
    return result;
}

static LONG CALLBACK exception_log(EXCEPTION_POINTERS *e) {
    DWORD code = e->ExceptionRecord->ExceptionCode;
    if (code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_ILLEGAL_INSTRUCTION || code == EXCEPTION_STACK_OVERFLOW)
        hook_log("exception code=%08lx address=%p engine_rva=%08lx", code, e->ExceptionRecord->ExceptionAddress,
                 (DWORD)((BYTE *)e->ExceptionRecord->ExceptionAddress - g_base));
    return EXCEPTION_CONTINUE_SEARCH;
}

static DWORD WINAPI start_probe(LPVOID unused) {
    (void)unused;
    wchar_t dir[MAX_PATH], path[MAX_PATH];
    DWORD len = GetEnvironmentVariableW(L"WC3HOOK_LOG_DIR", dir, MAX_PATH);
    if (!len || len >= MAX_PATH)
        ExitProcess(74);
    _snwprintf(path, MAX_PATH, L"%s\\probe-%lu.log", dir, GetCurrentProcessId());
    path[MAX_PATH - 1] = 0;
    log_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, 0, NULL);
    QueryPerformanceCounter(&started);
    QueryPerformanceFrequency(&frequency);
    InitializeCriticalSection(&probe_state_lock);
    char value[8] = {0};
    GetEnvironmentVariableA("WC3PROBE_STEP", value, sizeof value);
    enable_step_probe = !strcmp(value, "1");
    GetEnvironmentVariableA("WC3PROBE_SPEED", value, sizeof value);
    probe_speed = atof(value);
    GetEnvironmentVariableA("WC3PROBE_ACTION", value, sizeof value);
    enable_action_probe = !strcmp(value, "1");
    GetEnvironmentVariableA("WC3PROBE_PLAYERS", value, sizeof value);
    player_count = !strcmp(value, "2") ? 2 : 1;
    GetEnvironmentVariableA("WC3PROBE_EVENTS", value, sizeof value);
    enable_event_probe = !strcmp(value, "1");
    GetEnvironmentVariableA("WC3PROBE_OBJECTS", value, sizeof value);
    enable_object_probe = !strcmp(value, "1");
    GetEnvironmentVariableA("WC3PROBE_EPISODES", value, sizeof value);
    episode_limit = atoi(value);
    if (episode_limit < 1 || episode_limit > 5)
        episode_limit = 1;
    GetEnvironmentVariableA("WC3PROBE_SAVE_REPLAY", replay_path, sizeof replay_path);
    GetEnvironmentVariableA("WC3PROBE_REPLAY", value, sizeof value);
    replay_check = !strcmp(value, "1");
    GetEnvironmentVariableA("WC3PROBE_BUDGET", value, sizeof value);
    enable_budget_probe = !strcmp(value, "1");
    hook_log("research_probe pid=%lu engine_at_bootstrap=%p", GetCurrentProcessId(), GetModuleHandleW(L"Game.dll"));
    AddVectoredExceptionHandler(1, exception_log);
    /* API-only isolation must precede the launcher. Miles has not opened its device yet. */
    if (!LoadLibraryW(L"shell32.dll") || !LoadLibraryW(L"Mss32.dll")) {
        hook_log("FAIL load bootstrap dependencies error=%lu", GetLastError());
        ExitProcess(75);
    }
    require_hook(MH_Initialize(), "initialize");
    instance_init_hooks();
    MH_CreateHookApi(L"kernel32", "LoadLibraryA", LoadLibraryA_hook, (void **)&LoadLibraryA_orig);
    require_hook(MH_EnableHook(MH_ALL_HOOKS), "enable bootstrap");
    engine_loaded(GetModuleHandleW(L"Game.dll"));
    signal_phase("wc3hook-ready"); /* Bootstrap only: Python can now resume the launcher. */
    return 0;
}

__declspec(dllexport) int WC3Probe127(void) {
    return 127;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        HANDLE thread = CreateThread(NULL, 0, start_probe, NULL, 0, NULL);
        if (!thread)
            return FALSE;
        CloseHandle(thread);
    }
    return TRUE;
}
