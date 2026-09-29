# CAF source loop metadata

## AUD-002 — beat-tagged source metadata in a CAF UUID chunk

**Question:** Can a referenced CAF retain musical loop information even when its standard chunk tags contain no `loop` or `tempo` tag?

**Fixture:** One supplied CAF source kept outside the public repository. No source name, audio, recording, raw UUID payload, or project identifier is published.

**Method:** Parse CAF chunk boundaries, inspect a UUID followed by a big-endian entry count and NUL-terminated UTF-8 key/value pairs, then read the standard `desc` sample rate and `pakt` valid frame count. IDA MCP independently read the UUID payload and the `desc`/`pakt` fields at the computed offsets; its bytes agreed with Python. Compare the implied beats-per-duration tempo. The audio was not decoded or played. Apple documents the CAF UUID extension mechanism and the `desc`/`pakt` chunk layout in its [Core Audio Format specification](https://developer.apple.com/library/archive/documentation/MusicAudio/Reference/CAFSpec/CAF_spec/CAF_spec.html); the key/value schema of this particular UUID is inferred from this one source.

**Observation:** The UUID metadata contains complete key/value pairs, including literal keys `beat count` and `time signature`. The CAF sample rate and valid-frame count imply a musically plausible source tempo when combined with the beat tag. Same-source `AuRg` frame candidates include both full-source and shorter values, but their arrangement meaning is unknown. Another UUID chunk has a different identifier and remains opaque. Exact values from this private source are retained only in local research notes.

**Result:** This source is musically tagged, and a source-tempo interpretation is plausible. The parser now exposes source metadata on the neutral media reference, separately from region placement and duration. It does **not** assign an FL Studio clip length, a GarageBand Live Loops cell, a repeat count, or a tempo-following rule. Source length in frames cannot be mapped directly to arrangement beats without testing GarageBand's playback/edit behavior.

**Confidence:** CONFIRMED for the literal beat and meter keys, sample rate, valid frame count, and arithmetic in this source. HIGH CONFIDENCE that the metadata describes a musical audio loop. HYPOTHESIS for the generic UUID key/value schema and the calculated value as the source's intended tempo; UNKNOWN whether this source was used through Live Loops, Apple Loops, or ordinary audio placement.

**Alternative explanations:** The valid-frame count could include codec or edit padding. Beat tags could be attached to an imported audio file without Live Loops cell semantics. Region repeats and stretching may be stored entirely in the `.band` project.

**Next:** Compare controlled CAF sources tagged with different beat counts and source tempos. Separately create a GarageBand project that uses the same source first as an ordinary audio region and then as a Live Loops cell, changing only one property per save. Compare project data, arrangement preview, and CAF metadata before mapping loop or stretch behavior to FL Studio.

**Earlier scan correction:** AUD-001 searched chunk tags and selected strings for literal `loop`/`tempo` markers and left the UUID chunks uninterpreted. It therefore missed the structured `beat count` and `time signature` pairs. Its negative result applies only to explicit chunk tags and labels, not to musical metadata within the UUID payload.

