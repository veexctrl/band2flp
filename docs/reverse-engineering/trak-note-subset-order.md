# TRK-017 — separate note-bearing MIDI from other placement-shaped records

## Question

TRK-016 found a numeric placement/Trak association, but nine shared-word groups had conflicting track-byte candidates. Does that conflict persist for the subset linked to note-shaped data, and does Trak file order agree with the separate placement track byte?

## Method

Extend `trak_placement_link_probe.py` to classify MIDI placements independently of the ordering comparison. A placement must have exactly one MSeq link. Its linked MSeq is then checked for the parser's existing `0x90`–`0x9f` note-shaped candidates. Placements with missing or ambiguous MSeq links have a separate category. Absence of recognized note candidates is descriptive and does not establish that a region is empty or nonmusical.

Within each 58-byte Trak group family, enumerate records in validated chunk-stream file order. For nonzero placement words with exactly one matching Trak word in that family, compare the one-based ordinal with placement `+0x14`. A duplicate Trak word cannot establish an ordinal match. Preserve counts for all MIDI placements and each subset; nothing is removed from parser output.

## Observations

| Smaller-family comparison (`0x00040000`) | Note-bearing fixture | Other fixture |
| --- | ---: | ---: |
| audio placements | 10 | 9 |
| audio placement byte equals unique Trak one-based ordinal | 10 | 9 |
| MIDI placements with recognized note candidates | 5 | 0 |
| note-bearing MIDI byte equals unique Trak one-based ordinal | 5 | 0 |
| other uniquely MSeq-linked MIDI placements | 14 | 12 |
| other MIDI byte equals unique Trak one-based ordinal | 0 | 7 |
| ambiguous or missing MIDI MSeq links | 0 | 0 |

All **24 audio or note-bearing MIDI placements** across both fixtures agree with their unique smaller-family Trak ordinal. The five note-bearing MIDI placements reference four distinct nonzero words. Combined audio/note-bearing MIDI data has nine reference-word groups in the first fixture and six in the other, with no conflicting track-byte values. Including the other MIDI-shaped records restores the nine conflicting groups from TRK-016 in the first fixture. The other fixture still has no shared-word conflicts, but three MIDI records lack smaller-family matches and two matching records disagree with the ordinal.

Thus the raw conflict does not prevent a consistent association for the observed audio/note-bearing subset. It does prevent applying that interpretation indiscriminately to all `0x20` records.

## Independent validation and tests

The current archive payloads again match the two IDA input files byte for byte. IDA read all 61 relevant Trak header group words and all 50 recognized placement track bytes. All **111 additional reads** match Python, complementing TRK-016's numeric-word checks. These are metadata reads; no audio is opened or extracted.

Synthetic tests introduce a note-bearing and a note-free MSeq placement referencing the same word but with different track bytes. The full-set conflict is retained, while the audio/note-bearing subset is consistent. A duplicated MSeq link remains ambiguous and cannot enter the note-bearing subset. Existing tests preserve duplicate-word and zero exclusions. The complete suite has 143 passing tests.

## Confidence and alternatives

**CONFIRMED for these fixtures:** subset counts, 24 byte/ordinal equalities, four note-bearing reference groups, and the additional IDA/Python reads.

**HIGH CONFIDENCE:** the smaller family's file order and `+0x14` agree for the observed audio and note-bearing MIDI placements. The independent note-shape selection and exact reference join make this stronger than fitting an order to the values after filtering for equality.

**HYPOTHESIS:** this is the original one-based arrangement-track order. Controlled track reorder/move fixtures are still unavailable. The agreement could instead reflect another ordered track/channel representation that currently parallels the arrangement.

**UNKNOWN:** the role of other MIDI-shaped records, the larger family, special records, and tracks without recognized content. Missing note candidates may represent other event encodings, control data, muted or empty regions, cached state, or a different placement scope. These alternatives are not resolved by the subset comparison.

## Next implementation

Preserve the unique smaller-family link and agreeing ordinal as explicit candidates at the neutral-model boundary. Use this evidence to develop a separately labeled arrangement preview that groups the five MIDI regions into four candidate tracks. Preserve all unclassified records and retain the existing track identity caveats until controlled or independent visual evidence establishes the mapping.
