#include "objects127.h"

BYTE *object127_pair(BYTE *pair) {
    if ((*(DWORD *)pair & *(DWORD *)(pair + 4)) == 0xffffffff)
        return NULL;
    return ((BYTE * (__fastcall *)(BYTE *))(g_base + P127_RESOLVE_PAIR))(pair);
}

/* The two engine calls share ONE stack argument: virtual +0xb8 leaves it on the
 * stack and the unpack helper consumes it (ret 4). Neither call may be expressed
 * independently as ordinary thiscall/fastcall. Copy GetUnitX's complete sequence;
 * unlike the 1.29 accessor, read the caller's output rather than relying on EAX. */
__declspec(naked) void object127_position(BYTE *object, float xyz[3]) {
    __asm {
        mov ecx, [esp + 4]
        push dword ptr [esp + 8]
        mov eax, [ecx]
        call dword ptr [eax + 0xb8]
        mov ecx, eax
        mov eax, g_base
        add eax, P127_POS_UNPACK
        call eax
        ret
    }
}

void unit127_read(BYTE *unit, Unit127 *out) {
    float xyz[3];
    object127_position(unit, xyz);
    out->id = *(DWORD *)(unit + 0xc);
    out->type = *(DWORD *)(unit + P127_OBJECT_TYPE);
    out->flags = *(DWORD *)(unit + P127_UNIT_FLAGS);
    out->x = xyz[0];
    out->y = xyz[1];
    BYTE *owner = ((BYTE * (__fastcall *)(BYTE *))(g_base + P127_UNIT_OWNER))(unit);
    out->owner = owner ? owner[0x30] : -1;
    for (int s = 0; s < 4; s++) {
        float value;
        float *result =
            ((float *(__fastcall *)(BYTE *, void *, float *, int))(g_base + P127_UNIT_STATE))(unit, NULL, &value, s);
        out->life[s] = *result;
    }
    BYTE first = (BYTE)(out->type >> 24);
    out->hero = first >= 'A' && first <= 'Z' && !(out->flags & 0x40000000);
    out->structure = (out->flags & 0x10000) != 0;
    out->level = 0;
    BYTE *hero = *(BYTE **)(unit + P127_UNIT_HERO);
    if (out->hero && hero)
        out->level = ((int(__fastcall *)(BYTE *))(g_base + P127_PROTECTED_INT))(hero + P127_HERO_LEVEL) + 1;
}

BYTE *unit127_order(BYTE *unit) {
    return object127_pair(unit + P127_UNIT_ORDER_REF);
}

BYTE *unit127_item(BYTE *unit, int slot) {
    if (slot < 0 || slot >= 6)
        return NULL;
    return ((BYTE * (__fastcall *)(BYTE *, void *, int))(g_base + P127_ITEM_IN_SLOT))(unit, NULL, slot);
}

BYTE *unit127_ability(BYTE *unit, DWORD id) {
    return ((BYTE * (__fastcall *)(BYTE *, void *, DWORD, int, int, int, int))(g_base + P127_ABILITY_FIND))(
        unit, NULL, id, 0, 1, 1, 1);
}

int item127_owned(BYTE *item) {
    return object127_pair(item + P127_ITEM_OWNER_REF) != NULL;
}

int ability127_mana(BYTE *ability, int level) {
    return ((int(__fastcall *)(BYTE *, void *, int))(g_base + P127_ABILITY_MANA))(ability, NULL, level - 1);
}

float ability127_cooldown(BYTE *ability, int level) {
    float value = 0;
    ((void(__fastcall *)(BYTE *, void *, float *, int))(g_base + P127_ABILITY_COOLDOWN))(ability, NULL, &value,
                                                                                         level - 1);
    return value;
}

/* Virtual +0x2dc reads the cooldown timer in seconds; +0x2e0 instead returns the
 * normalized progress displayed by the command UI. The second argument is the order id.
 * Holy Light is checked against elapsed native cooldown after a real command.
 * Item/multi-order abilities still need their own command-context validation. */
float ability127_remaining(BYTE *ability, DWORD order) {
    float value = 0;
    DWORD *vt = *(DWORD **)ability;
    ((void(__fastcall *)(BYTE *, void *, float *, DWORD))vt[0x2dc / 4])(ability, NULL, &value, order);
    return value;
}
