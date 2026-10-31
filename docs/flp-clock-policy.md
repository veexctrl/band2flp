# Tempo and meter export policy

The exporter writes `Project.tempo_bpm` and `Project.time_signature` as the
FL project's static tempo and meter, then verifies those values after a
save/parse round trip. It does not yet create tempo automation or meter-change
markers. That round trip does not validate an entire song's clock timeline.

The JSON sidecar declares `clock_policy: "project-summary-only"` and preserves
the neutral model's `tempo_map` and `time_signatures` lists as
`source_tempo_map_candidates` and `source_time_signature_candidates`.
When either list is populated, a warning explicitly states that these
candidates are not written as timeline changes. Even one candidate may be
unresolved clock metadata; its presence does not prove a change occurred.

Candidate positions and confidence fields are retained without normalization.
GarageBand position units, nonzero-group scope and map completeness remain
unresolved. Other raw projectData diagnostics remain available through the
inspection command; these lists do not claim to contain every source record.

An export round-trip test supplies distinct synthetic tempo candidates and
a meter candidate differing from the project summary. The sidecar retains
them exactly while the FLP keeps the summary clock and reports the limitation.
