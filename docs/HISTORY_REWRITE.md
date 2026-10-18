# Scheme B: historical media removal

The user approved scheme B on 2026-10-18. The original four-commit development
sequence remains, with new commit IDs. Only `docs/media/**` and
`tests/fixtures/*.w3g` are removed from historical trees. Original local
repositories remain unchanged.

| 原始 SHA | 过滤后 SHA |
|---|---|
| `e45a6ae3802a31866f74186ce0e669a58a7ea45f` | `68c5cf741137fe8491dd1ff0fe26e7645e6c598e` |
| `2f7ddf1639fc038691ff0bd20403b11e5a97497d` | `b0e1858ee66b2d5f33b83f69f622aa97955293b5` |
| `dc2ca7bd17d332b3b31355fe087c5cc1a5b340e1` | `bad0278a39ea1b1ea1233c230677f83f5ecd86a7` |
| `85fcefdf1f9019dd92a40e109d544ec656d0d158` | `4f2b66179fa766c9228b35990b815386d8edcf08` |

Built-in Git `fast-export --full-tree --show-original-ids --reencode=no` with
excluded pathspecs, followed by `fast-import` into a fresh repository, performs
the filtering. No new dependency was installed. Export/import marks form the
mapping above.

For each pair, verification asserts equality of retained blob IDs/file modes,
author and committer identities/dates, commit messages and mapped parent order.
Original SSH signatures on the last two commits cannot attest rewritten hashes,
so they are removed. The first strict metadata comparison stopped at this
signature change; explicit signature handling then verified retained metadata.

See [history-rewrite.json](evidence/2026-10-18/history-rewrite.json) for per-commit
checks and excluded paths, and
[filtered-history-audit.json](evidence/2026-10-18/filtered-history-audit.json) for
the new object database scan. The four-commit baseline contains 411 retained text
blobs, no binary blobs, and none of the 14 excluded old binary object IDs.
The publication commit adds text documentation/tools only.

The earlier [publication-audit.json](evidence/2026-10-18/publication-audit.json)
is a **pre-filter** audit: its media inventory is historical evidence, not a list
of objects uploaded under scheme B. Old SHAs in native validation evidence refer
to the unchanged original source used for those tests; this table links it to
the filtered graph. No unfiltered backup ref is published.
