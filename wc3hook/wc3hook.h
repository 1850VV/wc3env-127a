/* wc3hook.dll: injected into Warcraft III.exe 1.29.2.9231 (32-bit) by inject.py, which
 * starts the game suspended and resumes it after this DLL signals `wc3hook-ready-<pid>`.
 *
 * One file per concern (docs/design.md):
 *   main.c        DllMain, hook installation order, the ready signal, heartbeat
 *   transport.c   the named pipe; RPC lines go to rpc.c, the rest is the diagnostic command set
 *   rpc.c         the JSON-lines RPC of docs/specs/protocol.md: lifecycle, jobs on the game thread
 *   clock.c       virtual QPC / GetTickCount / FILETIME / rdtsc, `speed` times wall time,
 *                 freezable, read lock-free; Sleep and wait timeouts scaled; the wait floor
 *   allocator.c   native free-space search and current-arena selection for reallocations
 *   step.c        GameUpdate hook and step mode, the hold at a fixed start time, render off,
 *                 turn packet delivery
 *   observe.c     the observation: accessors copied from the natives, fog, inventory, ground
 *                 items, destructables, the game result per player
 *   events.c      game events from a detour on the trigger-event dispatcher (0x245080)
 *   act.c         orders through the player command queue
 *   players.c     startup AI suppression and offline command identities
 *   stage.c       staging natives behind the `debug` ops (spawn, kill, give, ...)
 *   instance.c    per-process mutex/event names, per-instance Documents, focus immunity
 *   diag.c        scan, dump, watch, profile, where; exit and dialog logging
 *
 * Host -> DLL: a JSON object per line is an RPC request (docs/specs/protocol.md). Anything else is a
 * diagnostic command: ping | echo | info | where | pktlog <n> | scan <hex> | dump <addr> <n> |
 * watch <addr> [skip_game] [hits] | profile <n> [lo hi] | trace 0|1
 * DLL -> host: one JSON reply per request; diagnostic output as `scan ...`, `dump ...`,
 * `watch ...`, `queued ...` lines, which the RPC client skips.
 *
 * Every RVA below is into the pinned 1.27.0.52240 Game.dll (image base randomised; add g_base). The file
 * is pinned to that exact binary. tools/disasm.py, tools/imports.py and tools/natives.py read it. */
#pragma once
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <objbase.h>
#include <intrin.h>
#include <stdio.h>
#include <stdarg.h>
#include <tlhelp32.h>
#include "MinHook.h"
#include "json.h"

#define DLL_VERSION "0.8"
#define MAX_STEP_MS 60000
#define MAX_SPEED 2048.0
#define MAX_WAIT_FLOOR_MS 1000

/* ---- 1.27.0.52240 shared object/probe bindings: Game.dll e04d1716... -------------------------------
 * Shared by the formal adapter and the separately built reverse-engineering probe.
 * Native entries recovered with tools/natives.py and ABI disassembled before use.
 * GameUpdate fields recovered from its 25 ms loop (0x30ff00..0x31032a).
 * See docs/port-127a.md for which bindings have live evidence. */
#define P127_CREATE_UNIT 0x1deef0 /* cdecl(player, type, x*, y*, facing*) -> handle */
#define P127_GET_UNIT_X 0x1e66b0  /* cdecl(handle) -> float bits in EAX */
#define P127_GET_UNIT_Y 0x1e66f0
#define P127_GET_UNIT_TYPE 0x1e6670  /* cdecl(handle) -> rawcode */
#define P127_OBJECT_TYPE 0x30        /* GetUnitTypeId reads this field; 1.29 uses +0x34 */
#define P127_GET_UNIT_STATE 0x1e6600 /* cdecl(handle, unitstate) -> float bits */
#define P127_GET_PLAYER_ID 0x1e3d20  /* cdecl(player) -> 0..15 */
#define P127_GAME_UPDATE 0x30ff00    /* thiscall(this, now_ms), ret 4 */
#define P127_GAME_STATE 0x278        /* connection lifecycle; update simulates states 4/5 */
#define P127_GAME_TURN_CREDIT 0x284  /* network milliseconds available */
#define P127_GAME_CONNECTION 0x610   /* 0 live, 1 replay */
#define P127_GAME_TIME 0x1c70        /* simulation ms, incremented by 5 in each subturn */
#define P127_GAME_PREV_NOW 0x224c
#define P127_GAME_PENDING 0x2250     /* pending ms, clamped to 4000, consumed in 25 ms turns */
#define P127_GAME_PROVIDER 0x2288    /* checked by 0x30cd70: LOOP/NONE are offline */
#define P127_RDTSC_HELPER 0x154d20   /* rdtsc; ret; neighbouring timer wrappers at 0x154d10/30 */
#define P127_PACKET_DELIVER 0x30b8c0 /* fastcall(message*, context); event 0x18 at 0x30d68a */
#define P127_TICK_WRAPPER 0x154d30   /* jmp [GetTickCount IAT], used for caller tracing */
#define P127_HANDLE_UNIT 0x1d1550    /* fastcall(unit handle) -> object */
#define P127_UNIT_ORDER 0x1e5f80     /* cdecl(unit handle) -> order id */
#define P127_LOCAL_PLAYER 0x1e3150   /* cdecl() -> player handle */
#define P127_STORE_VTABLE 0x95211c   /* CDataStore: 0x18-byte header, native allocator owns buffer */
#define P127_STORE_CTOR 0x04df40     /* thiscall(store, &ptr, &base, &cap) */
#define P127_STORE_DTOR 0x04de90
#define P127_STORE_PUT_DATA 0x04e350  /* thiscall(store, bytes, count) */
#define P127_SEND_LOOPBACK 0x30ba60   /* thiscall(game, type, store, flags), transfers buffer */
#define P127_PLAYER_WIRE_ID 0x30c560  /* thiscall(player table, slot/tag) -> byte wire id */
#define P127_PLAYER_TABLE 0x290       /* live connection's command identities */
#define P127_LOCAL_WIRE_SLOT 0x2dc    /* slot/tag used by native outgoing-action flush at 0x311062 */
#define P127_SAVE_REPLAY 0x3122c0     /* thiscall(game, path): close recorder, stamp duration, move file */
#define P127_TURN_PRODUCER 0x874a10   /* thiscall(host): F7/0C time and F7/48 fragments */
#define P127_TURN_TIME_WRITE 0x8670b0 /* fastcall(store, const WORD *), returns store */
#define P127_TURN_TIME_RET 0x874be6   /* producer's time-word serializer return address */
#define P127_HOST_TIME_COUNT 0x1a8    /* positive-time packet counter, reset for a new game */
#define P127_ENUM_OBJECTS 0x02f230    /* fastcall(class, callback, context, 0); callback fastcall(object, context) */
#define P127_UNIT_OWNER 0x668890      /* thiscall(unit) -> player object */
#define P127_UNIT_STATE 0x669b40      /* thiscall(unit, output*, state) -> float* */
#define P127_POS_UNPACK 0x03b720      /* ECX=packed vector, shared stack output from virtual +0xb8; ret 4 */
#define P127_TLS_SLOT 0xbb8628        /* component TLS slot, read by 0x04efb0 */
#define P127_FRAME_WAIT_RET 0x15894e  /* thiscall event wait after WaitForSingleObject */
#define P127_FRAME_LOOP_WAIT_RET 0x05f7ed /* scheduler pacing, before component TLS installation */
#define P127_REGISTER_PLAYER 0x306e60     /* thiscall(table, wire id, info*) -> waiting slot tag */
#define P127_ASSIGN_PLAYER 0x312810       /* thiscall(table, waiting slot, game slot) */
#define P127_START_MELEE_AI 0x1f8150      /* cdecl(player handle, script string handle) */
#define P127_EVENT_REGISTERED 0x0566d0    /* thiscall(observer, event id) -> bool */
#define P127_EVENT_DISPATCH 0x245080      /* thiscall(player, event id, event object) */
#define P127_EVENT_UNIT_REF 0x2c          /* player-unit event's trigger-unit reference pair */
#define P127_RESOLVE_REF 0x037350         /* fastcall(id, salt) -> agent node */
#define P127_DAMAGE_TARGET                                                                                             \
    0x1fab70 /* cdecl(unit, target, amount*, attack, ranged, attackType, damageType, weaponType) */
#define P127_UNREGISTER_PLAYER 0x3078c0 /* thiscall(table, wire id) -> removed game slot; requires membership */
#define P127_RESTART_GAME 0x1f31e0      /* cdecl(bool): schedule map reload */
#define P127_RESOLVE_PAIR 0x044150      /* fastcall(&id/salt): live node +0x54 -> object */
#define P127_ITEM_IN_SLOT 0x6678b0      /* thiscall(unit, slot): inventory +0x1f8 -> item object */
#define P127_HANDLE_ITEM 0x1cfc50       /* fastcall(item handle) -> object */
#define P127_UNIT_FLAGS 0x5c            /* IsUnitPaused/Loaded/Illusion and IsUnitType */
#define P127_UNIT_HERO 0x1f0            /* GetHeroLevel -> 0x667a20 */
#define P127_HERO_LEVEL 0x6c            /* protected integer, zero based */
#define P127_PROTECTED_INT 0x039860     /* thiscall(protected integer) -> value */
#define P127_UNIT_ORDER_REF 0x19c       /* GetUnitCurrentOrder -> live pair, then order +0x24 */
#define P127_UNIT_ABILITIES 0x1dc       /* GetUnitAbilityLevel -> 0x46f440 */
#define P127_ABILITY_FIND 0x46f440      /* thiscall(unit, id, inherit, alias, abilities, buffs) */
#define P127_ABILITY_ID 0x34            /* alias read by 0x46f51c, class tag is virtual +0x1c */
#define P127_ABILITY_LEVEL 0x50         /* zero based, GetUnitAbilityLevel adds one */
#define P127_ITEM_CHARGES 0x84          /* GetItemCharges */
#define P127_ITEM_OWNER_REF 0x8c        /* IsItemOwned resolves this pair */
#define P127_N_PLAYER 0x1f1e70
#define P127_N_IS_UNIT_TYPE 0x1e8cc0
#define P127_N_HERO_LEVEL 0x1e2870
#define P127_N_ABILITY_LEVEL 0x1e5ef0
#define P127_N_ITEM_SLOT 0x1faf50
#define P127_N_ITEM_CHARGES 0x1e2be0
#define P127_N_ITEM_OWNED 0x1e7c30
#define P127_N_CREATE_ITEM 0x1de200
#define P127_N_ADD_ITEM 0x1fa610
#define P127_N_REMOVE_ITEM 0x1fb170 /* UnitRemoveItem(unit, item), does not destroy item */
#define P127_N_SET_ITEM_CHARGES 0x1f5b50
#define P127_N_SET_HERO_LEVEL 0x1f57e0
#define P127_N_ADD_ABILITY 0x1fa510
#define P127_N_SET_ABILITY_LEVEL 0x1f7140
#define P127_N_SET_UNIT_STATE 0x1f7a80
#define P127_N_PAUSE_UNIT 0x1f1b20
#define P127_N_SHOW_UNIT 0x1f7e70
#define P127_ABILITY_MANA 0x3f7380      /* thiscall(ability, zero-based level) -> int, level row +0x10 */
#define P127_ABILITY_COOLDOWN 0x3f6fd0  /* thiscall(ability, out*, zero-based level), row +0x14 */
#define P127_EVENT_SPELL_EFFECT 0x80312 /* common.j player-unit event 274; builder 0x244300 */
#define P127_EVENT_ITEM_DROP 0x80230    /* common.j 48 */
#define P127_EVENT_ITEM_PICKUP 0x80231  /* common.j 49 */
#define P127_EVENT_ARGUMENT 0x44        /* GetManipulatedItem and GetSpellAbilityId helpers */

/* ---- RVA table ------------------------------------------------------------------------------ */
#define RVA_RDTSC_HELPER 0x154d20 /* rdtsc; ret, calibrated against QPC at 0x396bd0 */
#define RVA_GAMEUPDATE 0x30ff00   /* GameUpdate(this, now_ms) thiscall, once per frame */
#define FRAME_LOOP_LO 0x05f710    /* the frame scheduler, for `profile` */
#define FRAME_LOOP_HI 0x05f944
#define RVA_PKT_DELIVER 0x30b8c0     /* Storm event handler (id 0x18): time-slot packet -> list game+0x1308 */
#define RVA_TURN_PRODUCER 0x874a10   /* offline host: build and send a time slot */
#define RVA_TURN_TIME_WRITE 0x8670b0 /* serialize a u16 by reference */
#define RVA_TURN_TIME_RET 0x874be6   /* only this producer call supplies turn time */
#define RVA_SAVE_REPLAY 0x3122c0     /* game->SaveReplay(path): close the recorder, move TempReplay.w3g */
#define RVA_TLS_SLOT 0xbb8628        /* the per-thread component table's TLS slot index */
#define RVA_FRAME_WAIT_RET 0x15894e  /* return address of the frame loop's pacing wait (clock.c) */
#define RVA_FRAME_LOOP_WAIT_RET                                                                                        \
    0x05f7ed /* where the frame loop's call of that wait wrapper returns; other                                        \
              * callers (0x575dcb) block inside game code */
/* game object (GameUpdate's this) */
#define GAME_TIME_MS 0x1c70      /* game time */
#define GAME_PREV_NOW 0x224c     /* previous now_ms */
#define GAME_PENDING_MS 0x2250   /* pending game ms */
#define GAME_TURN_CREDIT 0x284   /* turn ms available */
#define GAME_OUT_STORE 0x1c78    /* the outgoing action store */
#define GAME_CONNECTION 0x610    /* active connection: 0 live game, 1 replay */
#define GAME_REPLAY_LENGTH 0xac0 /* recorded duration from the native replay header */
/* natives (tools/natives.py) and the internals they call */
#define RVA_N_PLAYER 0x1f1e70       /* (I)Hplayer; */
#define RVA_N_LOCAL_PLAYER 0x1e3150 /* GetLocalPlayer: ()Hplayer; */
#define RVA_N_PLAYERID 0x1e3d20     /* GetPlayerId (Hplayer;)I */
#define RVA_N_UNITORDER 0x1e5f80    /* GetUnitCurrentOrder (Hunit;)I */
/* Ability levels use the native; mana/cooldown readback uses objects127 helpers. */
#define RVA_N_UNITABILITYLEVEL 0x1e5ef0 /* GetUnitAbilityLevel (Hunit;I)I */
#define RVA_N_STARTMELEEAI 0x1f8150     /* StartMeleeAI (Hplayer;S)V */
#define RVA_N_STARTCAMPAIGNAI 0x1f8100  /* StartCampaignAI (Hplayer;S)V */
#define RVA_N_GETPLAYERSTATE 0x1e4080   /* (Hplayer;Hplayerstate;)I */
#define RVA_N_PLAYERRACE 0x1e3d70       /* GetPlayerRace (Hplayer;)Hrace; */
#define RVA_N_PLAYERCONTROL 0x1e3cc0    /* GetPlayerController (Hplayer;)Hmapcontrol; */
#define RVA_N_PAUSECOMPAI 0x1f1ab0      /* PauseCompAI (Hplayer;B)V */
#define RVA_N_PLAYERSLOTSTATE 0x1e3fe0  /* GetPlayerSlotState (Hplayer;)Hplayerslotstate; */
#define RVA_N_ISVISIBLE 0x1e8f50        /* IsVisibleToPlayer (RRHplayer;)B; read-only point fog query */
#define RVA_N_REMOVEPLAYER 0x1f2db0     /* (Hplayer;Hplayergameresult;)V: what melee victory and defeat call */
#define RVA_HANDLE_OBJECT 0x1d1550      /* cdecl(Hunit) -> unit object: the lookup every unit native starts with */
#define RVA_PLAYER_OBJECT 0x1d03d0      /* cdecl(Hplayer) -> player object */
#define RVA_ENUM_OBJECTS 0x02f230       /* (class, cb, ctx, 0): for every live object of a registry class */
#define RVA_UNIT_OWNER 0x668890
#define RVA_UNIT_STATE 0x669b40
#define RVA_POS_UNPACK 0x03b720
#define RVA_ITEM_IN_SLOT 0x6678b0
#define RVA_PROTECTED_INT 0x039860
#define RVA_RESOLVE_REF 0x037350
#define RVA_RESOLVE_PAIR 0x044150 /* (ecx = &ref pair) -> object or 0: items' owners, abilities */
#define RVA_VM_GLOBAL 0xbe4238    /* the JASS VM, set whenever a map is loaded */
#define RVA_STORE_VTABLE 0x95211c /* CDataStore */
#define RVA_STORE_CTOR 0x04df40
#define RVA_STORE_DTOR 0x04de90
#define RVA_PUTBYTE 0x04df50 /* thiscall(store, byte), ret 4 */
#define RVA_PUTDATA 0x04e350
#define RVA_QUEUE_ACTION 0x30f1b0      /* fastcall(store, connection): append local UI records */
#define RVA_SEND_LOOPBACK 0x30ba60     /* game->SendPacket(type, store, flags) */
#define RVA_REGISTER_PLAYER 0x306e60   /* table->Register(wire id, name/info) -> 0x80 | (wire id - 1) */
#define RVA_ASSIGN_PLAYER 0x312810     /* table->Assign(waiting slot, game slot) */
#define RVA_UNREGISTER_PLAYER 0x3078c0 /* table->Unregister(wire id) */
#define RVA_N_RESTARTGAME 0x1f31e0
#define UNIT_CLASS 0x2b773375         /* '+w3u' */
#define DESTRUCTABLE_CLASS 0x2b773364 /* '+w3d' */
#define ITEM_CLASS 0x6974656d         /* 'item': what CreateItem's allocator (0x2c4d40) registers under */
/* second instance guard: CreateEventA("Warcraft III Game Application") 0x2e9ff -> 0x397c80.
 * game logger 0x3b8f0: hooking it stalls the simulation, do not. */

/* ---- shared state --------------------------------------------------------------------------- */
enum { ST_LAUNCHED, ST_IN_GAME, ST_ENDED }; /* the RPC lifecycle (docs/specs/protocol.md) */
extern volatile LONG g_status;
extern LONG g_step_frames_last;
extern char g_dir[MAX_PATH];
extern HANDLE g_log;
extern BYTE *g_base;
extern CRITICAL_SECTION g_lock; /* guards the pipe handle */

extern BYTE *g_game; /* GameUpdate's this, once seen */
extern DWORD g_game_tid;
extern volatile LONG g_stepmode, g_stepping, g_held;
extern DWORD g_step_target;
extern volatile LONG g_render, g_pktlog, g_wait_floor;
extern volatile LONG g_trace, g_trace_n;
extern int g_watch_skip_game, g_watch_hits;
extern double g_speed;
extern volatile LONG g_frozen;
extern LONGLONG g_qpc_freq;
extern DWORD g_exc_addr;

typedef VOID(WINAPI *SleepFn)(DWORD);
extern SleepFn Sleep_orig; /* the real Sleep, for the DLL's own threads */

/* ---- main.c ----------------------------------------------------------------------------------- */
void hook_log(const char *fmt, ...);
MH_STATUS require_hook(MH_STATUS status, const char *name);
#define MH_CreateHook(target, hook, original) require_hook(MH_CreateHook(target, hook, original), #target)
#define MH_CreateHookApi(module, name, hook, original)                                                                 \
    require_hook(MH_CreateHookApi(module, name, hook, original), name)

/* ---- transport.c ------------------------------------------------------------------------------ */
void pipe_send(const char *line);
DWORD WINAPI pipe_thread(LPVOID arg);

/* ---- clock.c ---------------------------------------------------------------------------------- */
LONGLONG real_qpc(void);
DWORD real_wait(HANDLE event, DWORD ms);
void clock_set_speed(double s);
void clock_freeze(int on);
void clock_init_hooks(void);
typedef struct {
    DWORD rdtsc_helper;
    DWORD frame_wait_ret;
    DWORD frame_loop_wait_ret;
} ClockBindings;
void clock_init_hooks_for(const ClockBindings *bindings);

/* ---- step.c ----------------------------------------------------------------------------------- */
DWORD game_time(void);
int game_is_offline(void);
int game_is_replay(void);
void step_mode(int on);
const char *step_request(DWORD ms);
void step_end_after_turn(void);
void step_restart(void);
extern const char *g_step_reason;
void step_init_hooks(void);
extern volatile LONG g_frames_seen;

/* ---- observe.c -------------------------------------------------------------------------------- */
typedef void(__fastcall *EnumObjectsFn)(int cls, void *cb, void *ctx, int zero);
typedef BYTE *(__fastcall *ResolveRefFn)(DWORD id, DWORD salt); /* RVA_RESOLVE_REF */
typedef int(__cdecl *NativeI_V)(void);
typedef int(__cdecl *NativeI_I)(int);
typedef int(__cdecl *NativeI_II)(int, int);
#define NATIVE(rva, T) ((T)(g_base + (rva)))
extern BYTE *g_fn_owner, *g_fn_state, *g_fn_unpack, *g_vm_global, *g_fn_slot, *g_fn_resolve_pair;
void accessors_init(void);
int __cdecl unit_xy_bits(BYTE *u, int idx);
int __cdecl unit_state_bits(BYTE *u, int state);
BYTE *__cdecl unit_owner(BYTE *u);
int __cdecl player_jass_id(BYTE *pl);
int __cdecl unit_visible(BYTE *u, int player_slot);
BYTE *__cdecl unit_item_in_slot(BYTE *u, int slot);
int __cdecl item_owned(BYTE *it);
int player_slot(int jass_id);
int object_visible(BYTE *object, int cls, int player);
float bits_to_f(int i);
int unit_hero_level(BYTE *u);
unsigned obs_id(BYTE *o);                        /* the RPC's id of a unit or item: the game's own object id [o+0xc] */
void obs_write_json(JW *w, int player, int seq); /* game thread snapshot */
const char *player_result(int jass_id);          /* "", "victory" or "defeat", from the game's own RemovePlayer */
void result_init_hooks(void);
void results_clear(void);
int agents_finished(void);

/* ---- metadata.c ----------------------------------------------------------------------------- */
void metadata_clear(void);
void metadata_write(JW *w, int observer);

/* ---- setup.c -------------------------------------------------------------------------------- */
void setup_init_hooks(void);
void setup_clear(void);
void setup_hold(void);
const char *setup_error(void);
int setup_random_race(int player);
void setup_write(JW *w);

/* ---- events.c --------------------------------------------------------------------------------- */
unsigned emit_events(JW *w, int player); /* returns the number lost to ring overflow */
void events_set_players(unsigned mask);  /* create_game: the players events are judged for; empties the log */
void events_init_hooks(void);

/* ---- act.c ------------------------------------------------------------------------------------ */
void act_flush(void);
const char *act_configure(unsigned agents);
void act_clear(void);
void players_init_hooks(void);
const char *players_configure(unsigned agents);
int player_is_agent(int player);
int player_wire_id(int player);
int player_prepared_agent(int player);
const char *player_arg(yyjson_val *args, int *handle);
void difficulty_init_hooks(void);
void difficulty_apply(int player);
const char *difficulty_read(yyjson_val *args, JW *w);
const char *overlay_show(yyjson_val *args, JW *w);
void chat_key(UINT msg, WPARAM wp); /* window thread: every key message the game window gets */
void chat_write_json(JW *w);        /* game thread: lines typed into the chat box since the last call */
void players_clear(void);
void players_unregister(void);
void act_init_hooks(void);
BYTE *object_by_rpc_id(long long id); /* game thread */
BYTE *unit_by_rpc_id(long long id);   /* unit-only lookup, game thread */

/* ---- stage.c ---------------------------------------------------------------------------------- */
typedef const char *(*StageOp)(yyjson_val *args, JW *w); /* game thread: NULL, or the bad_params detail */
StageOp stage_op(const char *name);
void stage_each_step(void);
void stage_clear(void);
int handle_of(BYTE *obj); /* game thread: the object's JASS handle, allocated if it has none */

/* ---- instance.c ------------------------------------------------------------------------------- */
void instance_init_hooks(void);

/* ---- allocator.c ------------------------------------------------------------------------------ */

/* ---- diag.c ----------------------------------------------------------------------------------- */
void mem_scan(const char *hex);
void mem_dump(DWORD addr, int n);
int watch_set(DWORD addr);
void profile(int n, DWORD lo, DWORD hi);
void where(void);
void log_addr(const char *prefix, DWORD addr);
void log_stack_from(const char *label, DWORD *frame);
void log_stack_here(const char *label);
int native_exc(EXCEPTION_POINTERS *e); /* the __except filter for game code called from the DLL */
void diag_init_hooks(void);

/* ---- rpc.c ------------------------------------------------------------------------------------ */
void rpc_init(void);
void rpc_handle(const char *line); /* one request line; replies on the pipe */
void rpc_service_jobs(void);       /* game thread, every frame */
int rpc_job_pending(void);
void rpc_service_jobs_between_frames(void); /* step.c: from the pacing wait, with the frame's TLS table installed */
void rpc_step_finished(void);
void rpc_set_ended(void);

typedef struct {
    long long unit_id;
    char command[16];
    int has_xy;
    double x, y;
    long long target;
    char type_id[8];
    char order[32];
    int slot;
    long long shop;
    char item_type[8];
    int reason, queued, auto_place;
} ActItem;
typedef struct {
    ActItem *items;
    int n;
    int player;
} ActJob;
enum { RJ_OK, RJ_NOT_YOURS, RJ_UNKNOWN_UNIT, RJ_UNKNOWN_COMMAND, RJ_BAD_ARGS, RJ_QUEUE_FULL, RJ_NO_BUILD_SITE };
void act_apply(ActJob *job); /* act.c: validate, encode and queue a batch; game thread */

/* Building search beneath the stock AI's 0x6d4970 wrapper; verified on 1.29.2. */
#define RVA_PLACEMENT_INIT 0x88bbd0     /* thiscall(scratch; slot, anchor x*, y*, type, density, worker) */
#define RVA_PLACEMENT_COPY 0x88ba10     /* thiscall(destination; source scratch) */
#define RVA_PLACEMENT_SEARCH 0x88d020   /* thiscall(scratch; score*, site[3], primary bool) */
#define RVA_PLACEMENT_ENUM 0x661060     /* cdecl(callback, scratch, flags, radius, x, y, 2, 31) */
#define RVA_PLACEMENT_OBSTACLE 0x891b70 /* engine footprint callback for the search */
#define RVA_PLACEMENT_RADIUS 0xbf181c   /* engine search radius, float bits */
#define RVA_PLACEMENT_NO_SITE 0xbb81d0  /* engine failure score */
#define RVA_PLAYER_TYPE_COUNT 0x2486d0  /* thiscall(player; type, counter kind) */
#define RVA_UNIT_PENDING_TYPE 0x66b1c0  /* thiscall(unit; type): pending production */
#define RVA_TYPE_IS_BUILDING 0x32df80   /* cdecl(type) -> building predicate */
#define PLACEMENT_SEARCH_SIZE 0x1947c   /* native scratch structure size from 0x6d4970 */
/* A structure already ordered but not yet standing: another search must not choose its ground. */
typedef struct {
    unsigned type;
    float x, y;
    BYTE *worker;
} PendingSite;
/* `ignore`: the worker whose own pending site this order replaces (NULL when the order is queued). */
int placement_find(BYTE *worker, unsigned type, float *x, float *y, const PendingSite *pending, int n_pending,
                   const BYTE *ignore);
int placement_pending(int player, PendingSite *out, int max);    /* the player's workers' current build orders */
int unit_order_point(BYTE *u, unsigned *id, float *x, float *y); /* observe.c: the current order's id and point */

/* Additional native entries and verified internal helpers. */
#define RVA_N_DROP_ITEM_TARGET 0x1facf0 /* UnitDropItemTarget (Hunit;Hitem;Hwidget;)B */
#define RVA_N_DROP_ITEM_POINT 0x1fac20  /* UnitDropItemPoint (Hunit;Hitem;RR)B */
#define RVA_FIRE_EVENT 0x245080
#define RVA_FIRE_SPELL_EFFECT 0x244300
#define RVA_EVENT_REGISTERED 0x0566d0 /* thiscall(this, eventid): [this+8] -> 0x43f100(mgr; id, 0), a pure query */
#define N_PLAYER_TEAM 0x1e4160
#define N_PLAYER_ALLIANCE 0x1e3c50
#define N_PLAYER_ALLY 0x1e8040
#define N_PLAYER_ENEMY 0x1e8090
#define N_PLAYER_SCORE 0x1e3d90
#define N_WORLD_BOUNDS 0x1e6810
#define N_RECT_MIN_X 0x1e45d0
#define N_RECT_MIN_Y 0x1e45f0
#define N_RECT_MAX_X 0x1e4590
#define N_RECT_MAX_Y 0x1e45b0
#define N_REMOVE_RECT 0x1f2dd0
#define RVA_VM_CONTEXT 0x1c3200 /* thiscall(this = *g_vm_global) -> the handle context */
#define RVA_HANDLE_FOR 0x2651d0 /* thiscall(ctx; obj, 0) -> handle, allocated if new */
#define RVA_ITEM_OBJECT                                                                                                \
    0x1cfc50 /* cdecl(Hitem) -> item object (the lookup is per class: units 0x1d1550, players 0x1d03d0) */
#define RVA_N_CREATEUNIT 0x1deef0                  /* (Hplayer;IRRR)Hunit; */
#define RVA_N_CREATEITEM 0x1de200                  /* (IRR)Hitem; */
#define RVA_N_KILLUNIT 0x1efcd0                    /* (Hunit;)V */
#define RVA_N_REMOVEUNIT 0x1f2f80                  /* (Hunit;)V */
#define RVA_N_SETHEROLEVEL 0x1f57e0                /* (Hunit;IB)V */
#define RVA_N_SETTECHRESEARCHED 0x1f6440           /* SetPlayerTechResearched (Hplayer;II)V */
#define RVA_N_ADDITEMBYID 0x1fa700                 /* UnitAddItemById (Hunit;I)Hitem; */
#define RVA_N_SETUNITSTATE 0x1f7a80                /* (Hunit;Hunitstate;R)V */
#define RVA_N_SETPLAYERSTATE 0x1f6320              /* (Hplayer;Hplayerstate;I)V */
#define RVA_N_INVULNERABLE 0x1f7690                /* SetUnitInvulnerable (Hunit;B)V */
#define RVA_AI_CONTEXT 0xbf1854                    /* Current AI script context */
#define RVA_N_MELEEDIFFICULTY 0x891e70             /* ()I */
#define RVA_N_GETAIDIFFICULTY 0x1e1500             /* (Hplayer;)Haidifficulty; */
#define RVA_DESTRUCTABLE_TARGET_MASK 0x6a44d0      /* thiscall(destructable) -> target category mask */
#define RVA_N_CLEARTEXTMESSAGES 0x1db520           /* ()V */
#define RVA_N_DISPLAYTIMEDTEXTTOPLAYER 0x1dfe70    /* (Hplayer;RRRS)V */
#define RVA_N_SETRANDOMSEED 0x1f64b0               /* (I)V */
#define RVA_PLAYER_REFRESH_CONTROL 0x24d8a0        /* thiscall(player): refresh controller dependency flags */
#define RVA_N_GETPLAYERSTARTLOCATION 0x1e4000      /* (Hplayer;)I */
#define RVA_N_SETPLAYERS 0x1f64a0                  /* (I)V */
#define RVA_N_SETPLAYERRACEPREFERENCE 0x1f62a0     /* (Hplayer;Hracepreference;)V */
#define RVA_N_SETPLAYERCONTROLLER 0x1f60f0         /* (Hplayer;Hmapcontrol;)V */
#define RVA_N_DEFINESTARTLOCATION 0x1df300         /* (IRR)V */
#define RVA_N_SETPLAYERSTARTLOCATION 0x1f6300      /* (Hplayer;I)V */
#define RVA_N_FORCEPLAYERSTARTLOCATION 0x1e0df0    /* (Hplayer;I)V */
#define RVA_RESOLVE_RACES 0x1cc390                 /* thiscall(player collection): lobby preferences resolve */
#define RVA_ASSIGN_STARTS 0x1cc590                 /* thiscall(lobby): assign starting locations */
#define RVA_WIDGET_ADJUST_MAX_LIFE 0x633000        /* thiscall(widget, delta*, mode): shared max-life adjustment */
#define RVA_N_CREATEDESTRUCTABLE 0x1ddc50          /* (IRRRRI)Hdestructable; */
#define RVA_HANDLE_DESTRUCTABLE 0x1cefd0           /* fastcall(handle) -> destructable object */
#define RVA_N_SETDESTRUCTABLEINVULNERABLE 0x1f4b00 /* (Hdestructable;B)V */
#define RVA_N_SETPLAYERALLIANCE 0x1f6030           /* (Hplayer;Hplayer;Halliancetype;B)V */
#define RVA_N_SETCAMERAPOSITION 0x1f4200           /* (RR)V */
