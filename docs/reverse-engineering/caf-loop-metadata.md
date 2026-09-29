# CAF source loop metadata

## AUD-002 — beat-tagged source metadata in a CAF UUID chunk

**Question:** Can a referenced CAF retain musical loop information even when its standard chunk tags contain no `loop` or `tempo` tag?

**Fixture:** One supplied CAF source kept outside the public repository. No source name, audio, recording, raw UUID payload, or project identifier is published.

**Method:** Parse CAF chunk boundaries, inspect a 16-byte UUID followed by a four-byte big-endian entry count and NUL-terminated UTF-8 key/value pairs, then read the standard `desc` sample rate and `pakt` valid frame count. IDA MCP independently read the complete 152-byte UUID payload and the `desc`/`pakt` numeric fields at the computed offsets; its bytes agreed with Python. Compare the implied beats-per-duration tempo. The audio was not decoded or played. Apple documents the CAF UUID extension mechanism and the `desc`/`pakt` chunk layout in its [Core Audio Format specification](https://developer.apple.com/library/archive/documentation/MusicAudio/Reference/CAFSpec/CAF_spec/CAF_spec.html); the key/value schema of this particular UUID is inferred from this one source.

**Observation:** The UUID metadata has six complete pairs, including literal keys `beat count` and `time signature`. Their values are eight beats and 4/4 in this fixture. The CAF reports 44,100 frames per second and 302,400 valid frames. Eight beats over 302,400 / 44,100 seconds yields exactly 70 BPM. Other keys describe music category and feel; they are not needed for arrangement reconstruction. A second UUID chunk has a different identifier and remains opaque.

**Result:** This source is musically tagged and a 70 BPM source-tempo interpretation is compelling. The parser now exposes source metadata on the neutral media reference, separately from region placement and duration. It does **not** assign an eight-beat FL Studio clip, a GarageBand Live Loops cell, a repeat count, or a tempo-following rule. The project tempo differs from the inferred source tempo, so source length in frames cannot be mapped directly to arrangement beats without testing GarageBand's playback/edit behavior.

**Confidence:** CONFIRMED for the literal beat count, time signature, sample rate, valid frame count, and arithmetic in this source. HIGH CONFIDENCE that the metadata describes a musical audio loop. HYPOTHESIS for the generic UUID key/value schema and 70 BPM as the source's intended tempo; UNKNOWN whether this source was used through Live Loops, Apple Loops, or ordinary audio placement.

**Alternative explanations:** The valid-frame count could include codec or edit padding, although the exact 70 BPM result argues against a large discrepancy. Beat tags could be attached to an imported audio file without Live Loops cell semantics. Region repeats and stretching may be stored entirely in the `.band` project.

**Next:** Compare controlled CAF sources tagged with different beat counts and source tempos. Separately create a GarageBand project that uses the same source first as an ordinary audio region and then as a Live Loops cell, changing only one property per save. Compare project data, arrangement preview, and CAF metadata before mapping loop or stretch behavior to FL Studio.

**Earlier scan correction:** AUD-001 searched chunk tags and selected strings for literal `loop`/`tempo` markers and left the UUID chunks uninterpreted. It therefore missed the structured `beat count` and `time signature` pairs. Its negative result applies only to explicit chunk tags and labels, not to musical metadata within the UUID payload.

