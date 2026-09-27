/* A native command-stream primitive, shared by live 1.27a experiments.
 * The return value is delivery acceptance; only subsequent readback proves execution. */
#include "objects127.h"

static DWORD selected[256][2]; /* Native command identity, not Warcraft player slot. */

void command127_clear(void) {
    memset(selected, 0, sizeof selected);
}

int command127_target(BYTE *game, BYTE wire, BYTE *unit, DWORD order, BYTE *target, float x, float y) {
    if (!game || !wire || !unit || *(DWORD *)(game + P127_GAME_CONNECTION) == 1)
        return 0;
    DWORD provider = *(DWORD *)(game + P127_GAME_PROVIDER);
    if (provider != 0x4c4f4f50 && provider != 0x4e4f4e45)
        return 0;
    BYTE records[57] = {0x16, 1, 1, 0};
    memcpy(records + 4, unit + 0xc, 8);
    records[12] = 0x1a;
    records[13] = 0x19;
    memcpy(records + 14, unit + P127_OBJECT_TYPE, 4);
    memcpy(records + 18, unit + 0xc, 8);
    records[26] = 0x12;
    memcpy(records + 29, &order, 4);
    memset(records + 33, 0xff, 8);
    memcpy(records + 41, &x, 4);
    memcpy(records + 45, &y, 4);
    if (target)
        memcpy(records + 49, target + 0xc, 8);
    else
        memset(records + 49, 0xff, 8);
    BYTE payload[74] = {0}, store[0x18] = {0};
    payload[2] = wire;
    int length = 5;
    if (selected[wire][0]) {
        /* 0x16/1 ADDS to selection. Without /2, a later worker move can cancel
         * a previously selected hero's cast even though the subgroup changed. */
        BYTE deselect[12] = {0x16, 2, 1, 0};
        memcpy(deselect + 4, selected[wire], 8);
        memcpy(payload + length, deselect, sizeof deselect);
        length += sizeof deselect;
    }
    memcpy(payload + length, records, sizeof records);
    length += sizeof records;
    payload[3] = (BYTE)(length - 5);
    DWORD *f = (DWORD *)store;
    f[0] = (DWORD)(g_base + P127_STORE_VTABLE);
    f[5] = (DWORD)-1;
    typedef void(__fastcall * StoreFn)(BYTE *, void *, DWORD *, DWORD *, DWORD *);
    ((StoreFn)(g_base + P127_STORE_CTOR))(store, NULL, &f[1], &f[2], &f[3]);
    ((void(__fastcall *)(BYTE *, void *, void *, DWORD))(g_base + P127_STORE_PUT_DATA))(store, NULL, payload, length);
    int accepted = ((int(__fastcall *)(BYTE *, void *, int, BYTE *, int))(g_base + P127_SEND_LOOPBACK))(game, NULL,
                                                                                                        0x1f, store, 2);
    if (f[3] != (DWORD)-1)
        ((StoreFn)(g_base + P127_STORE_DTOR))(store, NULL, &f[1], &f[2], &f[3]);
    if (accepted)
        memcpy(selected[wire], unit + 0xc, 8);
    return accepted;
}
