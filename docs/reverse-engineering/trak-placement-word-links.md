# TRK-016 — numeric links between Trak families and placements

## Question and method

UUID searches in TRK-011 and TRK-012 did not supply a full arrangement mapping. Do other fields relate the 58-byte `Trak` payload family to recognized audio and MIDI placements?

Read a four-byte unsigned little-endian word at `Trak` payload `+0x08`, excluding the UUID field at `+0x18`. Compare it with the four-byte little-endian word at recognized `0x24` and `0x20` event `+0x10`. The parser currently calls the latter `event_id_candidate`; that name is provisional and does not establish an event-unique identifier. Test uniqueness separately within each chunk-group family. Exclude zero from candidate joins.

Run `python -m research.scripts.trak_placement_link_probe example.band`. The report contains counts and structural family values, without identifiers, labels, raw records or music. Chunk payload bounds are checked before reads. Synthetic tests cover unique joins, duplicated words, zero exclusions, unmatched words and conflicts between the separate placement track-byte candidates.

## Observations

The two supplied uncontrolled fixtures contain 35 and 26 `Trak` payloads of length 58. Each has one zero-word record in group `0x00000000` and one in group `0x00100000`. The remaining records split into two families:

| Measurement | Note-bearing fixture | Other fixture |
| --- | ---: | ---: |
| group `0x00040000` records | 14 | 9 |
| group `0x00080000` records | 19 | 15 |
| nonzero words shared by both families | 14 | 9 |
| unique pairs within their respective families | 14 | 9 |
| declared arrangement tracks | 12 | 7 |

Thus the smaller family's count is the declared arrangement-track count plus two in both fixtures. This correlation is uncontrolled. No meaning is assigned to the additional records or to either family.

An additional lookup using the existing `selected_track_uuid` helper from `track_uuid_probe.py` matches each archive's saved `previousCurrentTrackUUID` to exactly one `Trak +0x18` field. Both matches belong to group `0x00040000`. This extends the earlier selected-UUID evidence to a specific family; it does not identify every member as a visible arrangement track.

| Placement comparison | Note-bearing fixture | Other fixture |
| --- | ---: | ---: |
| recognized audio placements | 10 | 9 |
| audio words with a unique smaller-family match | 10 | 9 |
| recognized MIDI placements | 19 | 12 |
| MIDI words with a unique smaller-family match | 19 | 9 |
| MIDI words with a unique larger-family match | 19 | 12 |

All 50 recognized placement words have unique larger-family matches. The smaller family matches 47 placements; the three remaining MIDI records occur in the other fixture. No nonzero within-family word ambiguity occurs in either fixture.

Combine placements by their `+0x10` word and inspect the separate `+0x14` track-byte candidates. In the note-bearing fixture, nine of 14 word groups have more than one track-byte value. In the other fixture, all 12 groups have one value. Therefore the numeric link must not be treated as a universal one-to-one mapping to the existing placement track byte.

## IDA validation

The current archive logic-song payloads match the two local raw files byte for byte. Headless IDA independently read all 61 `Trak +0x08` words and all 50 recognized placement `+0x10` words. All **111** reads matched Python. The investigation uses data inspection and does not open, decode or extract audio.

## Confidence and alternatives

**CONFIRMED for these fixtures:** family multiplicities, unique nonzero equality joins and conflicting track-byte group counts; all IDA/Python word matches.

**HIGH CONFIDENCE:** a shared numeric association relates placement records to the two `Trak` families in these fixtures. The one-to-one within-family pairing is stronger evidence than an unscoped search for a coincidental small integer.

**HYPOTHESIS:** the word is an object or channel reference. Its exact role, lifetime and authority are unknown. The shared reference could identify a channel, parent object, editor state or related record cluster used by several arrangement representations. Differences between audio and MIDI track-byte scopes could explain the conflicts. Chunk-group values are not assigned track-kind semantics.

**UNKNOWN:** how to map these records to visible arrangement order, names, mute/solo state or mixer controls. The count-plus-two observation does not identify auxiliary or special tracks. This experiment does not change neutral track assignment or FLP arrangement placement.

## Next evidence

Preserve candidate links with both source and target provenance. Compare a controlled track reorder or move of a region between tracks to determine whether `+0x10` follows the region, its track, a channel or another object. Cross-check other components for these words with structure-aware joins; an arbitrary four-byte match alone is insufficient.
