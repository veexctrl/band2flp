# Unknowns and required evidence

- Semantic field layouts and relationships for the observed chunk types inside the `DfLogicModelLogicSong` `NS.data` payload.
- Whether Logic Pro chunk decoders transfer unchanged to iOS GarageBand versions.
- Scope and semantics of the 32-bit header value at offset 8: it is reused by `TxSt` and audio chunk families, so it is not globally unique. Its role in source/region grouping needs validation with controlled projects and edits.
- Exact start/duration/source-offset/trim/loop fields in `AuRg` and placement information in associated `EvSq` chunks. Source-name-to-region-chunk links have HIGH CONFIDENCE in the supplied fixture, but placement and timing remain undecoded.
- Meaning of the repeated 16-byte `0xF1` `EvSq` payloads and the scope of their candidate group values.
- Tempo-event position units, meter pre-roll semantics, scope of nonzero-group tempo records, and whether the decoded event set is a complete tempo map.
- Track identifiers, ordering, names, types, mixer settings, and mute/solo state.
- Whether the 23 `AuCO` records with the Logic-like channel-strip shape correspond to GarageBand arrange tracks, mixer channels, auxiliary channels, or a mixture; validate the descriptor and ordering fields with controlled track-count fixtures.
- Meaning of the eight-byte `AuCO` descriptor for GarageBand and how arrange-track records can be distinguished from non-arrangement channel strips.
- Region record boundaries, timing units, starts, durations, trims, loops, and mute state.
- MIDI note encoding and timing resolution.
- Where the referenced live-loop audio is stored/resolved for this project; the supplied `.band` archive itself contains no audio payload members.
- Audio source references and region-to-media mapping.
- Tempo and time-signature changes, sections, automation, fades, and region gain.
- Whether output metadata and asset lists are complete, stale, or derived caches.
- Which structures differ across GarageBand versions and desktop/mobile projects.

The next useful inputs are sanitized or private local fixtures created by changing one property at a time: empty project, one track, one note, note pitch/duration/start changes, region position/length changes, tempo/meter changes, and a simple audio region. Do not add private song content to the public source repository.
