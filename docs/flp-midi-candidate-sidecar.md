# MIDI candidate export sidecar

`export-flp --include-midi-candidates` emits one `midi_candidates` entry for each MIDI region candidate that contains recognized note candidates. The JSON sidecar records the provisional pattern/channel/playlist assignment, candidate start and note-bounded clip length, note count, source event references, and any candidate track-binding decision.

When present in the neutral model, `source_duration_beats_candidate` and `placement_extent_beats_candidate` are copied into the sidecar unchanged. They do not determine pattern or playlist clip length. The exporter uses the latest recognized note end so these previews remain inspectable without choosing whether an extent means duration, absolute end, repeat, or stretch. The sidecar includes a warning that the extent semantics are unresolved.

These MIDI records are hypotheses derived from GarageBand project data. FL Studio editability validates only the generated FLP note structure; it does not confirm GarageBand note, track, or extent semantics.

