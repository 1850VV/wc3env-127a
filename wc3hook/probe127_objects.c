/* Cross-check raw object accessors against the pinned engine's native getters.
 * The fixture stages heroes and an item. It is excluded from record/playback runs. */
#include "objects127.h"

typedef int(__cdecl *N1)(int);
typedef int(__cdecl *N2)(int, int);
typedef int(__cdecl *N3)(int, int, int);
static int heroes[4], soldier, item, staged;
static int spell_events, item_pickups, item_drops;
static const DWORD hero_types[4] = {'Hpal', 'Obla', 'Udea', 'Edem'};

static void demand(int ok, const char *check) {
    if (!ok) {
        hook_log("FAIL object127 %s", check);
        ExitProcess(101);
    }
}

static BYTE *unit_of(int handle) {
    return ((BYTE * (__fastcall *)(int))(g_base + P127_HANDLE_UNIT))(handle);
}

static BYTE *item_of(int handle) {
    return ((BYTE * (__fastcall *)(int))(g_base + P127_HANDLE_ITEM))(handle);
}

static void check_unit(int handle, DWORD type, int hero, int level) {
    BYTE *unit = unit_of(handle);
    demand(unit != NULL, "unit handle resolution");
    Unit127 read;
    unit127_read(unit, &read);
    demand(read.type == type && read.hero == hero && read.level == level && read.owner == 0, "type/hero/level/owner");
    demand(read.structure == !!((N2)(g_base + P127_N_IS_UNIT_TYPE))(handle, 2), "structure native comparison");
    demand(read.hero == !!((N2)(g_base + P127_N_IS_UNIT_TYPE))(handle, 0), "hero native comparison");
    if (hero)
        demand(read.level == ((N1)(g_base + P127_N_HERO_LEVEL))(handle), "hero level native comparison");
    for (int s = 0; s < 4; s++) {
        int bits = ((N2)(g_base + P127_GET_UNIT_STATE))(handle, s);
        demand(!memcmp(&bits, read.life + s, 4), "unitstate native comparison");
    }
    DWORD rvas[] = {P127_GET_UNIT_X, P127_GET_UNIT_Y};
    float xy[] = {read.x, read.y};
    for (int s = 0; s < 2; s++) {
        int bits = ((N1)(g_base + rvas[s]))(handle);
        demand(!memcmp(&bits, xy + s, 4), "position native comparison");
    }
    BYTE *order = unit127_order(unit);
    DWORD id = order ? *(DWORD *)(order + 0x24) : 0;
    demand(id == (DWORD)((N1)(g_base + P127_UNIT_ORDER))(handle), "order native comparison");
    hook_log("object127_unit type=%08lx id=%lu hero=%d level=%d hp=%.3f maxhp=%.3f mana=%.3f maxmana=%.3f order=%lu",
             read.type, read.id, read.hero, read.level, read.life[0], read.life[1], read.life[2], read.life[3], id);
}

static void check_item(int owned) {
    BYTE *object = item_of(item);
    demand(object != NULL, "item handle resolution");
    demand(*(DWORD *)(object + P127_OBJECT_TYPE) == 'phea', "item rawcode");
    demand(*(int *)(object + P127_ITEM_CHARGES) == 7, "item charges after staging");
    demand(*(int *)(object + P127_ITEM_CHARGES) == ((N1)(g_base + P127_N_ITEM_CHARGES))(item),
           "charges native comparison");
    demand(item127_owned(object) == owned && !!((N1)(g_base + P127_N_ITEM_OWNED))(item) == owned,
           "ownership native comparison");
    int found = 0;
    for (int slot = 0; slot < 6; slot++) {
        BYTE *raw = unit127_item(unit_of(heroes[0]), slot);
        int handle = ((N2)(g_base + P127_N_ITEM_SLOT))(heroes[0], slot);
        demand(raw == (handle ? item_of(handle) : NULL), "inventory native comparison");
        found += raw == object;
    }
    demand(found == owned, "item inventory presence");
    hook_log("object127_item owned=%d charges=7 inventory_matches=%d", owned, found);
}

void probe_objects127_begin(BYTE *game) {
    demand(!staged, "fixture staged twice");
    int player = ((N1)(g_base + P127_N_PLAYER))(0);
    typedef int(__cdecl * CreateFn)(int, int, float *, float *, float *);
    for (int i = 0; i < 5; i++) {
        float x = -1000.0f + i * 150.0f, y = -1000, facing = 270;
        int h = ((CreateFn)(g_base + P127_CREATE_UNIT))(player, i < 4 ? hero_types[i] : 'hfoo', &x, &y, &facing);
        demand(h != 0, "create fixture unit");
        if (i < 4) {
            heroes[i] = h;
            check_unit(h, hero_types[i], 1, 1);
            ((N3)(g_base + P127_N_SET_HERO_LEVEL))(h, 3, 0);
            check_unit(h, hero_types[i], 1, 3);
        } else {
            soldier = h;
            check_unit(h, 'hfoo', 0, 0);
        }
    }
    ((N2)(g_base + P127_N_PAUSE_UNIT))(soldier, 1);
    demand((*(DWORD *)(unit_of(soldier) + P127_UNIT_FLAGS) & 0x200000) != 0, "paused flag set");
    ((N2)(g_base + P127_N_PAUSE_UNIT))(soldier, 0);
    demand((*(DWORD *)(unit_of(soldier) + P127_UNIT_FLAGS) & 0x200000) == 0, "paused flag cleared");
    ((N2)(g_base + P127_N_SHOW_UNIT))(soldier, 0);
    demand((*(DWORD *)(unit_of(soldier) + 0x20) & 1) != 0, "hidden flag set");
    ((N2)(g_base + P127_N_SHOW_UNIT))(soldier, 1);
    demand((*(DWORD *)(unit_of(soldier) + 0x20) & 1) == 0, "hidden flag cleared");
    float x = -1100, y = -1000;
    item = ((int(__cdecl *)(int, float *, float *))(g_base + P127_N_CREATE_ITEM))('phea', &x, &y);
    demand(item != 0, "create item");
    ((N2)(g_base + P127_N_SET_ITEM_CHARGES))(item, 7);
    check_item(0);
    ((N2)(g_base + P127_N_ADD_ITEM))(heroes[0], item);
    check_item(1);
    ((N2)(g_base + P127_N_REMOVE_ITEM))(heroes[0], item);
    check_item(0);
    ((N2)(g_base + P127_N_ADD_ITEM))(heroes[0], item);
    check_item(1);
    ((N2)(g_base + P127_N_ADD_ABILITY))(heroes[0], 'AHhb');
    ((N3)(g_base + P127_N_SET_ABILITY_LEVEL))(heroes[0], 'AHhb', 2);
    BYTE *ability = unit127_ability(unit_of(heroes[0]), 'AHhb');
    demand(ability && *(DWORD *)(ability + P127_ABILITY_ID) == 'AHhb', "ability lookup and alias id");
    demand(*(int *)(ability + P127_ABILITY_LEVEL) + 1 == ((N2)(g_base + P127_N_ABILITY_LEVEL))(heroes[0], 'AHhb'),
           "ability level native comparison");
    demand(*(int *)(ability + P127_ABILITY_LEVEL) == 1, "ability level two readback");
    int found = 0, count = 0;
    BYTE *a = object127_pair(unit_of(heroes[0]) + P127_UNIT_ABILITIES);
    for (; a && count < 64; a = object127_pair(a + 0x24), count++)
        found += a == ability;
    demand(!a && found == 1, "ability chain terminates with single matching ability");
    hook_log("object127_ability id=41486862 level=2 chain_count=%d vtable_rva=%08lx", count,
             (DWORD)(*(BYTE **)ability - g_base));
    demand(ability127_mana(ability, 2) == 65, "Holy Light mana cost");
    demand(ability127_cooldown(ability, 2) == 5, "Holy Light cooldown duration");
    demand(ability127_remaining(ability, 852092) == 0, "Holy Light initially ready");
    float hp = 20;
    ((void(__cdecl *)(int, int, float *))(g_base + P127_N_SET_UNIT_STATE))(soldier, 0, &hp);
    BYTE wire =
        ((BYTE(__fastcall *)(BYTE *, void *, int))(g_base + P127_PLAYER_WIRE_ID))(game + P127_PLAYER_TABLE, NULL, 0);
    float point[3];
    object127_position(unit_of(soldier), point);
    int accepted = command127_target(game, wire, unit_of(heroes[0]), 852092, unit_of(soldier), point[0], point[1]);
    hook_log("holybolt_queued accepted=%d wire=%u target_hp=20 mana_cost=65 cooldown=5", accepted, wire);
    staged = 1;
    hook_log("phase=wc3probe-objects-staged");
}

void probe_objects127_checkpoint(DWORD target) {
    demand(staged, "fixture not staged");
    for (int i = 0; i < 4; i++)
        check_unit(heroes[i], hero_types[i], 1, 3);
    check_unit(soldier, 'hfoo', 0, 0);
    check_item(1);
    BYTE *ability = unit127_ability(unit_of(heroes[0]), 'AHhb');
    demand(ability != NULL, "Holy Light still exists");
    Unit127 caster, patient;
    unit127_read(unit_of(heroes[0]), &caster);
    unit127_read(unit_of(soldier), &patient);
    float remaining = ability127_remaining(ability, 852092);
    hook_log("holybolt_state target=%lu hp=%.3f mana=%.3f remaining=%.6f", target, patient.life[0], caster.life[2],
             remaining);
    if (target == 2275) {
        demand(patient.life[0] >= 400 && caster.life[2] >= 235 && caster.life[2] < 250,
               "command executed: healed target and spent mana");
        demand(remaining > 3 && remaining < 5, "running native cooldown after cast");
    }
    if (target == 7275)
        demand(patient.life[0] >= 400 && remaining == 0 && spell_events == 1 && item_pickups == 2 && item_drops == 1,
               "cooldown elapsed and exactly matching spell/item events");
    hook_log("object127_checkpoint target=%lu", target);
    if (target == 7275)
        hook_log("phase=wc3probe-objects");
}

void probe_objects127_clear(void) {
    memset(heroes, 0, sizeof heroes);
    soldier = item = staged = 0;
    spell_events = item_pickups = item_drops = 0;
}

int probe_objects127_wants_event(int event) {
    return event == P127_EVENT_SPELL_EFFECT || event == P127_EVENT_ITEM_DROP || event == P127_EVENT_ITEM_PICKUP;
}

void probe_objects127_event(int event, BYTE *object) {
    if (!heroes[0])
        return;
    BYTE *caster = object127_pair(object + P127_EVENT_UNIT_REF);
    BYTE *argument = object127_pair(object + P127_EVENT_ARGUMENT);
    hook_log("object127_event kind=%x caster=%p expected=%p argument=%p", event, caster, unit_of(heroes[0]), argument);
    if (caster != unit_of(heroes[0]))
        return;
    if (event == P127_EVENT_SPELL_EFFECT) {
        BYTE *ability = argument ? object127_pair(argument + 0x2c) : NULL;
        DWORD id = ability ? *(DWORD *)(ability + P127_ABILITY_ID) : 0;
        hook_log("object127_spell ability=%08lx", id);
        demand(id == 'AHhb', "spell event ability id");
        spell_events++;
    } else if (argument && argument == item_of(item)) {
        if (event == P127_EVENT_ITEM_DROP)
            item_drops++;
        else
            item_pickups++;
    }
}
