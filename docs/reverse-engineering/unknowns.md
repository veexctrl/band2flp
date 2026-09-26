# Unknowns and required evidence

- Binary record format inside the `DfLogicModelLogicSong` `NS.data` payload.
- Track identifiers, ordering, names, types, mixer settings, and mute/solo state.
- Region record boundaries, timing units, starts, durations, trims, loops, and mute state.
- MIDI note encoding and timing resolution.
- Audio source references and region-to-media mapping.
- Tempo and time-signature changes, sections, automation, fades, and region gain.
- Whether output metadata and asset lists are complete, stale, or derived caches.
- Which structures differ across GarageBand versions and desktop/mobile projects.

The next useful inputs are sanitized or private local fixtures created by changing one property at a time: empty project, one track, one note, note pitch/duration/start changes, region position/length changes, tempo/meter changes, and a simple audio region. Do not add private song content to the public source repository.
