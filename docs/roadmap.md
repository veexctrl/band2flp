# band2flp roadmap

This roadmap prioritizes faithful song structure over instrument recreation. It is evidence-driven rather than date-based: a milestone advances when its exit criteria are demonstrated and documented. The progress graphic estimates format knowledge recovered; it is not a completion forecast or a measure of how much of the converter is finished.

## Current state

- **Package parsing and inspection — working:** `.band` ZIP inventory, keyed-archive/project metadata, bounded logic-song chunk parsing, event records, raw unknown data, and JSON inspection are implemented. The identical F1 event family has an exact ordered group-candidate match with `MSeq` and empty `Trak` chunks in two projects; IDA independently verified all 68 F1 event ranges and 204 associated group fields. The ordinal relation is structural only, and F1 semantics remain unknown.
- **Audio arrangement — partial:** source references, placement candidates, and starts are exposed in the neutral model; start decoding agrees with one arrangement preview. `AuRg +0x06/+0x16` source-frame-window candidates and a nonzero `AuRg +0x8a` / placement `+0x28` equality are preserved as metadata. Two of three fixed-field links also intersect ambiguous placement-suffix/frame candidates in one fixture. A second fixture has six external CAF references containing an `Apple Loops` path component, but this does not distinguish ordinary audio placement from Live Loops cell use. CROSS-004 gives HIGH CONFIDENCE that four matching source names in `SngO`/`GenM` records have `IsFamilyLoop=true` and `LoopFamilyName` fields; their order follows `AuFl` source-chunk order, but the records' relation to arrange tracks remains unknown. The remaining candidates do not decode timeline duration, trim, loops, or unique region identity. The finite placement word at `+0x1c` remains unconfirmed: it falls on a 960-tick grid in two fixtures and matches one preview-measured clip. None of these candidates populates exported duration.
- **MIDI — early research:** MIDI placement candidates link to `MSeq` chunks, note-shaped records are retained, and optional FL Studio preview notes are confirmed editable in FL Studio 25 after setting the note flag validated by a one-field synthetic probe. A uniquely linked printable `MSeq` text candidate can label the preview pattern, but the label's track-versus-region role remains unknown. EVT-005 found opaque `0x91`–`0x9e` families clustered with unique placement/`MSeq` candidates; EVT-006 profiles byte offsets that vary among grouped records and IDA cross-checks the four observed `0x90` records. These offsets are leads only: GarageBand-specific event meanings, note fields, position units, and track mapping lack controlled validation.
- **FL Studio output (experimental):** audio-region FLP export and optional provisional MIDI-note pattern previews work with PyFLP round-trip checks. FLP-027 identified channel definitions appended after the playlist as the cause of the invalid-clips warning in the test project. Both the reordered song probe and a fresh two-source exporter output opened in FL Studio 25 with clips visible. A synthetic one-field note-flag probe made the MIDI preview notes editable in FL Studio 25; this validates the FLP note record, not GarageBand note interpretation. A WAV relink from a CAF byte-matched to the supplied project archive loads fully in FL Studio 25 according to the user. `extract-audio` and `export-flp` now support opt-in FFmpeg conversion to 16-bit PCM WAV; conversion flow has synthetic unit coverage, but FFmpeg is unavailable in the current environment. Playback remains unverified, and full-source placeholder lengths remain unresolved.
- **Track metadata — unresolved:** `AuCO` candidates resemble a broader channel-strip collection. TRK-004 rules out a one-to-one count mapping to arrange tracks in the two inspected projects; no specific candidate-to-track mapping is established.

See [progress.json](progress.json) and [progress.svg](progress.svg) for the current rough estimate and its workstream breakdown.

## Milestones

### 1. Identify arrange tracks and channel relationships

**Work:** Create matched GarageBand projects with zero, one, and two added tracks, then vary track type and ordering. Compare `Trak`, `AuCO`, `EvSq`, asset metadata, names, and visible track rows. Determine how audio and MIDI placement fields map to arrange tracks, including empty tracks.

**Exit criteria:** Track order, stable identity, type, and placement-to-track mapping are demonstrated across controlled fixtures. Mixer/channel-strip records are distinguished from arrange tracks. Unrecognized fields remain available in debug output.

### 2. Recover audio region boundaries and edits

**Work:** Use a single audio source and vary one property per fixture: position, duration, trim, loop, copy, mute, gain, and stretch where available. Correlate `AuRg`, placement records, media references, and preview/audio-export boundaries. Revisit frame-count and extended placement suffix candidates only against these controlled changes.

**Exit criteria:** Region start, duration, source offset, and supported edit flags have validated units and behavior. Each field has evidence, confidence, regression coverage, and a documented unsupported case where decoding is not possible.

### 3. Decode MIDI regions and notes

**Work:** Create minimal one-note fixtures and change only pitch, velocity, start, or duration. Separately move and resize the MIDI region. Compare the resulting `EvSq` and `MSeq` data, then validate candidate records in IDA and ordinary Python tooling.

**Exit criteria:** MIDI placement and note pitch, onset, duration, velocity, and region-relative/absolute timing are confirmed across multiple controlled values. Supported controllers and transposition are represented; unknown event bytes are preserved.

### 4. Recover the song time map and global structure

**Work:** Vary tempo, meter, tempo changes, meter changes, section length, and song sections independently. Establish event position units, event completeness, duration semantics, and the relation between summary metadata and the logic-song event stream.

**Exit criteria:** The neutral model represents the validated tempo/meter timeline and song length/sections without converting unknown units. Changes are covered by controlled fixtures and tests.

### 5. Stabilize the neutral model and inspection interface

**Work:** Promote only validated fields from raw candidates into typed model attributes. Keep candidate values, confidence, source offsets, identifiers, and unknown structures accessible in JSON. Add diagnostics for ambiguous links and unsupported structures.

**Exit criteria:** JSON inspection can explain each recovered track, region, note, and media reference, including provenance and uncertainty. Round-trip model serialization and regression fixtures cover supported fields.

### 6. Export and validate full arrangements in FL Studio

**Work:** Extend the exporter from audio-only output to validated audio and MIDI arrangement data, tempo/meter changes, track structure, and supported mixer/automation state. Keep FLP writing separate from GarageBand parsing. Verify PyFLP behavior and use a current FL Studio version for GUI load and playback checks.

**Exit criteria:** A controlled mixed audio/MIDI fixture opens without invalid playlist warnings, preserves the expected arrangement and timing, and plays the linked media in FL Studio. Unknown durations or unsupported features fail with clear diagnostics instead of silently producing misleading clips.

### 7. Package and release

**Work:** Keep the Python package and CLI as the reference implementation. After conversion behavior and dependencies stabilize, evaluate a standalone Windows executable as an additional distribution option. Publish sanitized fixtures or synthetic tests only; never publish private recordings or proprietary application files.

**Exit criteria:** Installation, inspect/JSON, audio extraction, and supported FLP export are documented and reproducible from a clean environment. License, dependency notices, tests, and privacy review are complete.

## Immediate next work

1. Run the optional FFmpeg conversion with an available FFmpeg build and validate generated WAVs in FL Studio; do not use WAV frame counts as GarageBand region durations.
2. Create one single-source GarageBand project and change only its region length twice to test the `+0x1c` hypothesis; keep duration inference independent from AAC decoder padding before replacing full-source placeholders.
3. Prepare minimal GarageBand fixtures for track-count/order changes, audio trim/loop edits, and one-note MIDI differences. Continue to label fixture-dependent and cross-format observations as hypotheses.
