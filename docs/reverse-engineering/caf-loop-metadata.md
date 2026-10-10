# CAF source loop metadata

## AUD-002 — beat-tagged source metadata in a CAF UUID chunk

**Question:** Can a referenced CAF retain musical loop information even when its standard chunk tags contain no `loop` or `tempo` tag?

**Fixture:** One supplied CAF source kept outside the public repository. No source name, audio, recording, raw UUID payload, or project identifier is published.

**Method:** Parse CAF chunk boundaries, inspect a UUID followed by a big-endian entry count and NUL-terminated UTF-8 key/value pairs, then read `desc` format fields and the `pakt` packet count, valid frames, priming frames, and remainder frames. IDA MCP independently read the UUID payload and the previously checked `desc`/`pakt` fields; the new reader preserves all standard packet-table header values. Compare the source beat tag with valid-frame duration. The audio-data chunk is skipped and is neither decoded nor played. Apple's [Core Audio Format specification](https://developer.apple.com/library/archive/documentation/MusicAudio/Reference/CAFSpec/CAF_spec/CAF_spec.html) defines valid frames as the audio duration and priming/remainder as frames to trim when decoding; the key/value schema of this particular UUID is inferred from this one source.

**Observation:** The UUID metadata contains complete key/value pairs, including literal keys `beat count` and `time signature`. Combining the beat tag with the CAF sample rate and valid-frame count yields a source-tempo candidate, but AUD-007 shows that the beat-count convention remains ambiguous by a half/double-time factor when compared with the frame-only hypothesis and an approximate cached preview. Its packet count and AAC frames-per-packet account for valid audio frames plus codec priming and the trailing remainder. Same-source `AuRg` frame candidates include both full-source and shorter values, but their arrangement meaning is unknown. Another UUID chunk has a different identifier and remains opaque. Exact values from this private source are retained only in local research notes.

**Result:** This source is musically tagged, and a source-tempo interpretation is plausible but ambiguous. The parser exposes the standard CAF packet-table fields alongside the beat-tagged source metadata, so codec priming and remainder are distinguishable from valid playback frames. It still does **not** assign an FL Studio clip length, a GarageBand Live Loops cell, a repeat count, or a tempo-following rule. Source length in frames cannot be mapped directly to arrangement beats without testing GarageBand's playback/edit behavior.

**Confidence:** CONFIRMED for the literal beat and meter keys, CAF header fields, and valid-frame-duration arithmetic in this source. HIGH CONFIDENCE that the metadata describes a musical audio loop. HYPOTHESIS for the generic UUID key/value schema and either calculated value as the source's intended tempo; UNKNOWN which half/double-time interpretation is intended and whether this source was used through Live Loops, Apple Loops, or ordinary audio placement.

**Alternative explanations:** Beat tags could be attached to an imported audio file without Live Loops cell semantics. Region repeats and stretching may be stored entirely in the `.band` project. The actual GarageBand region may also use only a trimmed portion of the source.

**Next:** Compare controlled CAF sources tagged with different beat counts and source tempos. Separately create a GarageBand project that uses the same source first as an ordinary audio region and then as a Live Loops cell, changing only one property per save. Compare project data, arrangement preview, and CAF metadata before mapping loop or stretch behavior to FL Studio.

**Earlier scan correction:** AUD-001 searched chunk tags and selected strings for literal `loop`/`tempo` markers and left the UUID chunks uninterpreted. It therefore missed the structured `beat count` and `time signature` pairs. Its negative result applies only to explicit chunk tags and labels, not to musical metadata within the UUID payload.
