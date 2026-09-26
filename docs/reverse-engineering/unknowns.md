# Unknowns and required evidence

- Semantic field layouts and relationships for the observed chunk types inside the `DfLogicModelLogicSong` `NS.data` payload.
- Whether Logic Pro chunk decoders transfer unchanged to iOS GarageBand versions.
- Scope and semantics of the 32-bit header value at offset 8: it is reused by `TxSt` and audio chunk families, so it is not globally unique. Its role in source/region grouping needs validation with controlled projects and edits.
- Whether `AuRg +0x16` is source-frame length for all GarageBand versions versus another cached length. Its values are preserved as candidates, not used as timeline duration.
- Exact beat duration/source-offset/trim/loop fields in `AuRg`, exact mapping from each placement event to a specific same-source region object, and meaning of the extra 80-byte suffix on two placement events. Two suffix dwords match same-source region `+0x16` values, but starts and track/source placement links remain the only complete arrangement fields recovered with HIGH CONFIDENCE for this fixture.
- Meaning of the repeated 16-byte `0xF1` `EvSq` payloads and the scope of their candidate group values.
- Tempo-event position units, meter pre-roll semantics, scope of nonzero-group tempo records, and whether the decoded event set is a complete tempo map.
- Track names, complete track ordering (including the unpopulated track slot), mixer settings, and mute/solo state. Audio placement track numbers 2 through 7 are recovered for this fixture.
- Whether the 23 `AuCO` records with the Logic-like channel-strip shape correspond to GarageBand arrange tracks, mixer channels, auxiliary channels, or a mixture; validate the descriptor and ordering fields with controlled track-count fixtures.
- Meaning of the eight-byte `AuCO` descriptor for GarageBand and how arrange-track records can be distinguished from non-arrangement channel strips.
- Region durations, source offsets, trims, loops, and mute state. Audio placement start positions are decoded in beats for the supplied fixture.
- MIDI note encoding and timing resolution.
- Meaning of the 12 `0x20` event records: Logic Pro uses this marker for MIDI-region placement, but this fixture lacks `0x90` note events and the `0x20` records do not independently map to the arrange-track count. Do not treat them as MIDI regions without a controlled software-instrument fixture.
- Where the referenced live-loop audio is stored/resolved for this project; the supplied `.band` archive itself contains no audio payload members.
- Audio source references and region-to-media mapping.
- Tempo and time-signature changes, sections, automation, fades, and region gain.
- Whether output metadata and asset lists are complete, stale, or derived caches.
- Which structures differ across GarageBand versions and desktop/mobile projects.

The next useful inputs are sanitized or private local fixtures created by changing one property at a time: empty project, one track, one note, note pitch/duration/start changes, region position/length changes, tempo/meter changes, and a simple audio region. Do not add private song content to the public source repository.
