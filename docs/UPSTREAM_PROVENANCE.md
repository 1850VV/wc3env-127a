# Upstream provenance and licenses

This is an unofficial, offline-only Warcraft III **1.27a** adaptation of
[pwang724/wc3env](https://github.com/pwang724/wc3env). Its independent private
distribution is [1850VV/wc3env-127a](https://github.com/1850VV/wc3env-127a).

## Source history and filtering

The user approved **scheme B** on 2026-10-18: remove historical demo media and
obsolete replay fixtures, accepting changed commit IDs. All four original
development commits were exported into a new independent object database,
excluding `docs/media/**` and `tests/fixtures/*.w3g`. All published branches use
the filtered graph. The original local repositories remain intact.

| 原始 SHA | 过滤后 SHA |
|---|---|
| `e45a6ae3802a31866f74186ce0e669a58a7ea45f` | `68c5cf741137fe8491dd1ff0fe26e7645e6c598e` |
| `2f7ddf1639fc038691ff0bd20403b11e5a97497d` | `b0e1858ee66b2d5f33b83f69f622aa97955293b5` |
| `dc2ca7bd17d332b3b31355fe087c5cc1a5b340e1` | `bad0278a39ea1b1ea1233c230677f83f5ecd86a7` |
| `85fcefdf1f9019dd92a40e109d544ec656d0d158` | `4f2b66179fa766c9228b35990b815386d8edcf08` |

The rows correspond to the upstream root, upstream baseline, native 1.27a port,
and subsequent Archmage kiting/Footman surround MVPs. For every pair, retained
file modes and Git blob IDs, author/committer identities and timestamps, commit
messages and mapped parent relationships were verified equal. Two old SSH
signatures were removed because they attest old hashes, not the rewritten ones.
See [history verification](HISTORY_REWRITE.md).

Old hashes in earlier reports identify the unchanged local source and native
evidence. Use the table to locate the corresponding filtered commits. Newer
upstream `d45a7b5` VectorSession/binary APIs were not merged; see the
[API compatibility matrix](API_COMPATIBILITY_127A.md).

## Licenses retained

| Component | License and retained notice |
|---|---|
| wc3env and port source | [MIT](../LICENSE), copyright 2026 wc3env contributors |
| MinHook | [BSD 2-Clause notices](../wc3hook/minhook/LICENSE.txt), including Hacker Disassembler Engine notices |
| yyjson | [MIT](../wc3hook/yyjson/LICENSE), copyright YaoYuan |

These source-code licenses do not grant rights to distribute Warcraft III game
files. Users supply their own installation. No installation binary, game archive,
map, activation file, private configuration or credential is included. The project
is not affiliated with Blizzard Entertainment.

## Data boundary

- Twelve demo media files (116,660,027 bytes) and two obsolete replay fixtures
  (4,825 bytes) are excluded from every published historical tree and object set.
- The removed replays are unchanged upstream version 29/build 6060 recordings;
  the 1.27 parser rejects them. Current native replay tests create temporary
  recordings, and do not use these old recordings as evidence for 1.27a.
- Generated reference JSON used by tests/agent is retained under project rules,
  without maps or extracted artwork.
- Original local raw validation logs stay local. Small derived summaries,
  artifact hashes and filtering evidence are in
  [docs/evidence/2026-10-18](evidence/2026-10-18/README.md).

Fetching original upstream history reintroduces historical media locally. Do not
push such refs or merge them directly: review/filter any future upstream import.
