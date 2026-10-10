# TRK-019 — join the saved selected-track UUID to placement word candidates

## Question

Can the `previousCurrentTrackUUID` state linked to a `Trak +0x18` UUID be joined through the same record's `+0x08` word to recognized audio or MIDI placements, and do those placement track-byte candidates agree with the selected `Trak`'s within-family ordinal?

## Method

Resolve the selected UUID from each private project's `projectData` keyed archive. Match it to exactly one 58-byte `Trak +0x18` field, read that record's little-endian word at `+0x08`, and compare the nonzero value to recognized audio/MIDI event `+0x10` candidate words within the same `Trak` family. For unique joins, compare the placement `+0x14` byte with the selected record's one-based ordinal in that family. The reusable probe reports aggregate counts only; it emits no UUID, raw word, identifier, project path, label, or media data.

IDA independently matched both selected UUID fields and all five numeric fields used by the unique placement joins. The two logic-song inputs were byte-matched to the corresponding projectData payloads before comparing the IDA reads. No audio data was read.

## Observations

The selected UUID resolves to one `Trak` record in each of two uncontrolled fixtures. Its nonzero `+0x08` word is unique within that record's family in both, but the same word also occurs in the other family in each fixture, so it is not a unique cross-family identity. The word matches one MIDI placement and no audio placements in the first fixture; that MIDI `+0x14` candidate differs from the selected `Trak` ordinal. In the second fixture, the word matches one audio and one MIDI placement, and both placement bytes equal the selected `Trak` ordinal.

## Result

The UUID-to-`Trak` lookup and the within-family word equalities are confirmed associations in these fixtures. Because the word is also present in the other family in both, it cannot uniquely identify a `Trak` object across the serialized collection. Their inconsistent placement/ordinal relationships do not establish a universal selected-track-to-placement identity or prove that `+0x08` is a track identifier. No track assignment or FLP row policy is changed.

## Confidence and alternatives

**CONFIRMED:** unique UUID-to-record matches, candidate word equalities, the observed ordinal comparison, and IDA/Python byte agreement for the inspected fields.

**HYPOTHESIS:** the selected `Trak` record and placements joined through `+0x08` represent the same arrange track.

**UNKNOWN:** whether `previousCurrentTrackUUID` is current, whether the word is a track/channel/object reference, what distinguishes the two families, and how they map to visible arrangement rows. Cross-family duplicate words may represent paired records, shared parent objects, or coincidental values; this comparison does not decide among them.

## Next evidence

In a controlled project, select a track and save; move one audio or MIDI region to another track without changing its content; then save again. Compare selected UUID, `Trak +0x08/+0x18`, placement `+0x10/+0x14`, and visible row order to determine which fields follow selection and which follow the region or track.
