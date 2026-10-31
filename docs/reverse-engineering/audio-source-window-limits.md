# Source-window candidates do not determine placement extent

## ARR-047: repeated source-window candidates

Question: can the two `AuRg` words at payload offsets `+0x06` and
`+0x16` alone determine a placement's extent?

Method: group uniquely field-linked audio placements by source reference and
the pair of little-endian unsigned 32-bit words. Use the existing candidate
`AuRg +0x8a` / placement `+0x28` equality; do not substitute serialized order
for missing or ambiguous links. Compare placement start candidates and the
raw extent word at `+0x1c` within each repeated pair group.

Run `python -m research.scripts.audio_window_repeat_probe example.band`.
The command reports aggregate counts and skips missing, ambiguous, or
incomplete links. Synthetic tests cover repeated windows, separate sources,
ambiguous links, absent words, duplicate metadata and equal rational starts.

In the local audio-bearing fixture, four linked records form two repeated
source/pair groups. Both groups contain different placement starts. One
group also contains different extent words: one finite word and one
`0x3fffffff` sentinel. Thus the same source and pair do not uniquely determine
the raw placement extent word in this fixture.

IDA MCP reads covering both words in all four linked region payloads match
the Python extraction byte for byte. The complete associated placement
records were independently checked against the same current component.
Exact source values, names, and project media remain local.

CONFIRMED: the byte comparisons and within-group variation in this fixture.
HYPOTHESIS: the links identify corresponding region instances, and the pair
represents a source offset and remaining window. UNKNOWN: actual clip
duration, sentinel semantics, and the behavior in controlled trim/copy edits.

This comparison rules out a deterministic mapping from the source and pair
to the raw extent word under the candidate links. It does not prove that the
actual durations differ: the sentinel might mean a default or implicit
duration equal to the finite case. Other possibilities include contextual
loop/stretch state, cached fields, or an incorrect instance-link hypothesis.

Keep source-window and placement-extent candidates separate. Do not derive
confirmed `duration_beats` or source trimming from the pair. A controlled
GarageBand fixture changing only region length or copy/loop state is still
needed to distinguish the alternatives.
