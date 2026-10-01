# Audio region-to-placement window scan

## CROSS-005 — search for alternate equal-byte region links

**Question:** If the `AuRg +0x8a` to audio-placement `+0x28` candidate is unset in one fixture, does another aligned four- or eight-byte field pair give varying, one-to-one region-to-placement links?

**Fixtures:** The two supplied `.band` archives. One has embedded audio; the other has audio references but no embedded media. Audio, source names, project identifiers, and field values remain private.

**Method:** Use exact filename-stem matches and the already decoded source group to collect `AuRg` payloads and `0x24` placement records. Keep only source groups with at least two region records and two placement records. Scan every two-byte-aligned window of widths four and eight in each region payload against every corresponding placement event. Exclude zero values and constant equalities. Count only matches that are one-to-one within the source group and have at least two distinct values. `research/scripts/audio_window_link_probe.py` reports offset/count aggregates only. The previously identified fixed field was independently checked in IDA MCP (CROSS-004); this broader exhaustive-window scan is reproducible in Python.

**Observation:** In the embedded-audio fixture, one source group qualifies. For both window widths, the only qualifying pair starts at region payload offset `+0x8a` and placement event offset `+0x28`, with three one-to-one matches. In the audio-free fixture, three source groups qualify, and none yields a qualifying four- or eight-byte equality at the scanned alignment.

**Result:** The existing candidate pair is distinctive within this scan for the embedded-audio fixture. Its absence in the other fixture is consistent with an optional or media-origin-specific field. No alternate equal-byte link was found under these search rules. The parser continues to expose the candidate match only; it does not assign duration, trimming, loop state, or a general region identity.

**Confidence:** CONFIRMED for the scan output and exact comparisons on these two fixtures; HIGH CONFIDENCE that the first fixture's candidate pair is structurally meaningful; HYPOTHESIS that it identifies a region object; UNKNOWN why the second fixture lacks it.

**Alternatives:** A link may be encoded, hashed, split across noncontiguous fields, unaligned, or mediated by another chunk. Repeated or constant values are deliberately excluded, so this scan can miss valid links. The source grouping and filename-stem association are themselves evidence-backed candidates rather than a complete format specification.

**Next:** Create controlled ordinary-audio and Live Loops fixtures using the same source. Move, duplicate, trim, and loop one region at a time, then compare whether the candidate field follows its placement or remains zero by media origin.

## ARR-031 — paired region/placement instance candidates

**Question:** Do the three exact window matches connect individual `AuRg` region chunks to individual `0x24` placement events, rather than only identifying a matching field location?

**Method:** In the one qualifying source group, order four filename-matched region chunks by logic-song offset and four placements by event offset. Compare only the eight-byte windows at `AuRg +0x8a` and placement `+0x28`. Reopen the extracted logic-song payload (not the CAF audio) in IDA MCP and read both windows for each of the three Python-matched pairs.

**Observation:** Three nonzero values match uniquely. In file order, region records 2, 3, and 4 match placement records 3, 2, and 4; region 1 and placement 1 remain unmatched. All six IDA reads agree byte-for-byte with Python. The three multi-region source groups in the second fixture have no equality at these exact positions.

**Result:** This is evidence for a partial per-instance link candidate in the embedded-source fixture, with a nontrivial 2↔3 ordering that is inconsistent with a simple shared ordinal. The parser retains these exact-equality candidate chunk indices but does not choose one region as authoritative, synthesize a missing pair, or assign length/trim/loop semantics.

**Confidence:** CONFIRMED for offsets, width, nonzero equality, one-to-one matching, file-order mapping, and IDA/Python agreement in this fixture. HYPOTHESIS that the values are shared region-instance identifiers. UNKNOWN why one pair is absent and why the other fixture has no match.

**Alternatives:** The values could identify another shared object or relationship and happen to be unique among these records. The fixtures are uncontrolled, and exact equality in one source group is not enough to generalize the field semantics.

**Next:** Use same-source controlled projects with one, two, and three placed copies; reorder the copies, then change one trim at a time. A stable identity that follows the same region through reordering would support the instance-link interpretation.
