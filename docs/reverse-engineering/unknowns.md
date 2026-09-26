# Unknowns and required evidence

- Semantic field layouts and relationships for the observed chunk types inside the `DfLogicModelLogicSong` `NS.data` payload.
- Whether Logic Pro chunk decoders transfer unchanged to iOS GarageBand versions.
- Scope and semantics of the 32-bit header value at offset 8: it is reused by `TxSt` and audio chunk families, so it is not globally unique. Its role in source/region grouping needs validation with controlled projects and edits.
- Whether `AuRg +0x16` is source-frame length for all GarageBand versions versus another cached length. Its values are preserved as candidates, not used as timeline duration.
- ARR-020 compared `AuRg +0x16` against embedded source frame counts: only a subset of candidates in one project matched. The field is not a universal full-source length; trimming and region-length semantics remain unknown.
- Exact beat duration/source-offset/trim/loop fields in `AuRg`, exact mapping from each placement event to a specific same-source region object, and meaning of the extra 80-byte suffix on two placement events. Two suffix dwords match same-source region `+0x16` values, but starts and track/source placement links remain the only complete arrangement fields recovered with HIGH CONFIDENCE for this fixture.
- ARR-019's earlier nonzero/sentinel histogram was not reproducible. IDA and the parser both read zero at `0x24 +0x18` for the nine records in chunk 298; the field remains UNKNOWN and is not used for region length.
- Meaning of the repeated 16-byte `0xF1` `EvSq` payloads and the scope of their candidate group values.
- Tempo-event position units, meter pre-roll semantics, scope of nonzero-group tempo records, and whether the decoded event set is a complete tempo map.
- Track names, complete track ordering (including the unpopulated track slot), mixer settings, and mute/solo state. Audio placement track numbers 2 through 7 are recovered for this fixture.
- ARR-021 corroborated grouping and start positions against six preview rows, but numeric track labels are absent from the image; a controlled reorder/add-track experiment is still needed to confirm absolute track indices.
- Whether the 23 `AuCO` records with the Logic-like channel-strip shape correspond to GarageBand arrange tracks, mixer channels, auxiliary channels, or a mixture; validate the descriptor and ordering fields with controlled track-count fixtures.
- Meaning of the eight-byte `AuCO` descriptor for GarageBand and how arrange-track records can be distinguished from non-arrangement channel strips.
- Region durations, source offsets, trims, loops, and mute state. Audio placement start positions are decoded in beats for the supplied fixture.
- Whether the Logic-derived offsets on 80-byte GarageBand `0x90` events mean pitch, velocity, onset, and duration; candidate fields are exposed but remain unconfirmed pending controlled one-note GarageBand fixtures.
- Whether the shared-`MSeq` relation between `0x90` note-shaped events and `0x20` MIDI placements generalizes beyond the private fixture; MIDI-006 observed one unique shared chunk/placement link per note event there, but controlled note edits are still needed.
- GarageBand-specific `MSeq` record fields for MIDI region duration, internal start, and name. Logic Pro offsets are not yet independently validated in GarageBand.
- MIDI-005's linked-`MSeq` position scan was inconclusive because the fixture had too few distinct nonzero starts; no scanned payload offset is treated as region start.
- Whether `0x20` event `+0x14` values are direct arrange-track numbers and whether `+0x04` uses the Logic-derived 34,560/960 PPQ conversion in GarageBand. The `+0x20` cluster-to-`MSeq` association is now HIGH CONFIDENCE in two fixtures, but track and timing semantics still need controlled validation.
- MIDI-004's raw `Trak` chunk-order comparison did not establish a direct mapping for `0x20 +0x14`; repeated chunk groups make ordinal equality insufficient.
- Where the referenced live-loop audio is stored/resolved for this project; the supplied `.band` archive itself contains no audio payload members.
- Audio source references and region-to-media mapping.
- Tempo and time-signature changes, sections, automation, fades, and region gain.
- Whether output metadata and asset lists are complete, stale, or derived caches.
- Which structures differ across GarageBand versions and desktop/mobile projects.

The next useful inputs are sanitized or private local fixtures created by changing one property at a time: empty project, one track, one note, note pitch/duration/start changes, region position/length changes, tempo/meter changes, and a simple audio region. Do not add private song content to the public source repository.
- PROV-001 found GarageBand 2.3.19 in both inspected project archives. User confirms the initial audio-free and later private audio fixtures came from different iPhone models; exact model attribution is kept in local-only notes, and archive product-type strings do not independently establish the mapping. Device-specific serialization effects remain unknown because project contents differ.
- FLP-001/002 showed PyFLP can preserve an FL Studio 2025 blank template and serialize a playlist event under Python 3.10, but the tested version fails to parse that template under Python 3.14 and did not validate a playable clip. FLP exporter strategy and supported runtime remain open.
