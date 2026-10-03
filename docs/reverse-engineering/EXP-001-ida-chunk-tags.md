# EXP-001 — Verify logic-song chunk tags in IDA

**Question:** Does IDA's raw byte search independently reproduce the Python parser's chunk-header offsets for the observed four-byte tags?

**Fixtures:** Two supplied GarageBand project archives, identified only by generic fixture numbers. The experiment extracted the keyed-archive `NS.data` payloads; no audio members were used.

**Method:** Open each raw logic-song payload in IDA without autoanalysis. Search for the on-disk tag bytes, which store the displayed four-character tags in reverse byte order:

| Displayed tag | Raw bytes |
| --- | --- |
| `AuRg` | `67 52 75 41` |
| `AuFl` | `6C 46 75 41` |
| `MSeq` | `71 65 53 4D` |
| `Trak` | `6B 61 72 54` |
| `EvSq` | `71 53 76 45` |

Compare each complete sorted IDA hit-offset set with the Python parser's header offsets for the corresponding type.

**Observation:** All five tag searches in both payloads returned exactly the same offset sets as the parser: no missing header offsets and no extra hits for these tags.

**Result:** This independently confirms the tag byte order and the parser's chunk-header offsets for these five types in these two fixtures. It does not confirm the meaning of the other header fields or establish that every GarageBand version uses the same layout.

**Confidence:** CONFIRMED for the byte patterns and exact offset-set agreement in these two fixtures; UNKNOWN for broader version coverage and the semantics of other fields.

**Next:** Repeat the check on a controlled fixture from another GarageBand version and compare all recognized and unrecognized chunk tags.
