/* Verified 1.27a object accessors. Game-thread only; never create a JASS handle.
 * This is a component of the port, not a complete adapter or a public support claim. */
#pragma once
#include "wc3hook.h"

typedef struct {
    DWORD id, type, flags;
    int owner, hero, structure, level;
    float x, y, life[4];
} Unit127;

BYTE *object127_pair(BYTE *pair);
void object127_position(BYTE *object, float xyz[3]);
void unit127_read(BYTE *unit, Unit127 *out);
BYTE *unit127_order(BYTE *unit);
BYTE *unit127_item(BYTE *unit, int slot);
BYTE *unit127_ability(BYTE *unit, DWORD id);
int item127_owned(BYTE *item);
int ability127_mana(BYTE *ability, int level);
float ability127_cooldown(BYTE *ability, int level);
float ability127_remaining(BYTE *ability, DWORD order);
int command127_target(BYTE *game, BYTE wire, BYTE *unit, DWORD order, BYTE *target, float x, float y);
void command127_clear(void);

/* Separate live fixture; mutations here are test staging, never replayed game commands. */
void probe_objects127_begin(BYTE *game);
void probe_objects127_checkpoint(DWORD target);
void probe_objects127_clear(void);
int probe_objects127_wants_event(int event);
void probe_objects127_event(int event, BYTE *object);
