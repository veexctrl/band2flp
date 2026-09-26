# Experiment log

## PKG-001 — supplied package inventory

**Question:** What is the outer `.band` container and which logical components are present?

**Fixture:** One supplied GarageBand `.band` project, kept outside this source tree.

**Observation:** Python `zipfile` enumerated nine ZIP members. `projectData` decompresses to an XML plist; output metadata is available in XML and binary plist forms; images are PNGs. The `projectData` ZIP local header was cross-checked through IDA MCP at the member's raw archive offset.

**Result:** ZIP package layout is directly confirmed for this fixture. No claim is made that all `.band` projects contain the same components.

**Confidence:** CONFIRMED for the inspected fixture.

**Next:** Inventory additional projects and compare their member sets and projectData wrappers.

## PD-001 — keyed archive wrapper

**Question:** Is `projectData` a plist and where is the main logic model referenced?

**Observation:** The plist root declares `NSKeyedArchiver`; `$top` includes `DfDocument logic model`; the referenced model has a `DfLogicModelLogicSong` reference; the song object includes `NS.data` (239,274 bytes in the inspected fixture).

**Result:** The wrapper and reference chain are directly visible. The contents and record layout of the `NS.data` bytes remain unknown.

**Confidence:** CONFIRMED for this fixture's serialized object graph; generality across GarageBand versions is untested.

**Next:** Collect controlled note/region fixtures and correlate changes in this payload.

## META-001 — summary metadata keys

**Question:** Which summary fields can be read without decoding the logic payload?

**Observation:** `Output/metadata.plist` contains tempo, signature numerator/denominator, duration, and arrange-track-count fields.

**Result:** The parser reads these named values but does not use the count to fabricate track objects. Duration units need validation against controlled projects.

**Confidence:** HIGH CONFIDENCE for field meaning from explicit names; duration units remain HYPOTHESIS.

**Next:** Compare known tempo/meter/duration projects and validate the values against GarageBand display/export behavior.

## CROSS-001 — output and asset metadata

**Question:** Do the output summary and asset plist expose matching track counts and media placement?

**Observation:** `Output/assetsmetadata.plist` is a binary plist with `NumberOfTracks`, global tempo/meter fields, and resource-list keys including `AudioFiles`, `PlaybackFiles`, and `UnusedAudioFiles`. Its track count differs from `Output/metadata.plist`'s arrange-track count in the inspected fixture. Some resource paths name external content; they are not project package members.

**Result:** The two track-count fields cannot be treated as interchangeable. Resource references are retained as asset metadata but are not interpreted as placed arrangement regions.

**Confidence:** CONFIRMED for the observed distinction in this fixture; intended meanings and generality remain unconfirmed.

**Next:** Compare both counts and asset lists across controlled empty, MIDI-only, and audio-region fixtures.

## BIN-001 — opaque payload markers and resource strings

**Question:** Does the logic-song NSData payload expose repeated candidate record markers or literal resource references?

**Fixture:** The same single supplied project; payload read through IDA Python from the mapped ZIP bytes and then through its `projectData` object graph.

**Observation:** The byte sequence `23 47 C0 AB` occurs at payload offsets 0, 60, and 760. The later two occurrences are inside the first `Song` chunk payload, not at top-level chunk boundaries. At least one sampler-resource basename from `assetsmetadata.plist` occurs twice as ASCII in the payload. No basename from its `AudioFiles` list was found as a raw ASCII substring.

**Result:** The sequence and string overlaps are observations only. They do not establish record boundaries, reference semantics, or audio placement. In particular, absence of literal basenames does not rule out IDs, indices, or transformed references.

**Confidence:** CONFIRMED for byte/string observations in this fixture; the two interior occurrences have no established meaning.

**Next:** Compare the payload from controlled changes and determine whether marker offsets or nearby values track a known property.

## BIN-002 — exact chunk-boundary parse

**Question:** Does the logic-song NSData value follow a length-delimited chunk layout?

**Fixture:** The single supplied iOS GarageBand project, read in IDA Python from the mapped raw ZIP bytes and resolved through its keyed-archive reference chain.

**Observation:** The 239,274-byte value starts with magic `23 47 C0 AB`. A 24-byte root header followed by 36-byte chunk headers parses exactly when each chunk length is read as unsigned 64-bit little-endian from header offset 28. The parse yielded 413 chunks and ended exactly at offset 239,274. At offset 24, reversed tag bytes decode to `Song`; its payload size is 13,916. Tags such as `MSeq`, `Trak`, and `EvSq` are also printable after reversing their four stored bytes. The container measurements agree with the published Logic Pro ProjectData description, although that documentation is for `.logicx` rather than this iOS `.band` fixture.

**Result:** The root/chunk boundary interpretation is CONFIRMED for this payload by complete consumption and plausible repeated tags. Chunk field meanings and cross-version behavior remain unknown.

**Confidence:** CONFIRMED for this fixture's boundaries and stated integer interpretation; HIGH CONFIDENCE that the outer chunk framing is shared with the Logic-family format; no claim that individual chunk decoders transfer across apps.

**Alternative considered:** A random length walk could occasionally produce printable tags, but exactly consuming all 413 headers/payloads with no leftover bytes, while yielding repeated plausible tags, makes that explanation unlikely.

**Next:** Compare the same tags and field patterns across additional `.band` versions and controlled arrangement changes before adding semantic decoding.

## CROSS-002 — audio references and grouped region tags

**Question:** Can asset-list entries be linked to binary audio-file and region chunks?

**Fixture:** The supplied project, comparing `Output/assetsmetadata.plist`, `Output/metadata.plist`, and the parsed `NS.data` chunk stream.

**Observation:** There are six `AudioFiles` references, six `AuFl` chunks, nine `AuRg` chunks, and a metadata root-region count of nine. Each of the six asset basenames occurs in exactly one `AuFl` payload as UTF-16LE. At chunk-header offset 8, the unsigned 32-bit little-endian value is shared between each `AuFl` and its related `AuRg` chunks. Observed groups are `0x00100000` (1 region), `0x00140000` (2), `0x00180000` (2), `0x001C0000` (2), `0x00200000` (1), and `0x00280000` (1). Each of the six `EvSq` chunks sharing those audio-resource group values is 16 bytes and begins with `0xF1`.

**Result:** The name and group matches provide strong evidence that `AuFl` carries audio-file references and `AuRg` carries related region data for this fixture. The parser emits these matches and candidate shared group values. Start, duration, source offset, trimming, looping, and exact group-field semantics are still unknown.

**Confidence:** HIGH CONFIDENCE for the cross-component audio-file-to-region grouping in this fixture; not confirmed across other projects or versions.

**Alternative considered:** Track/group IDs may identify a broader object cluster rather than a file-to-region relation. Exact UTF-16LE basename matches inside every `AuFl`, shared by `AuRg` chunks, make the file-reference interpretation more likely; the field name remains a candidate.

**Next:** Compare a minimal project with one audio region, then move/trim/loop it independently and diff the `AuRg` and grouped `EvSq` chunks. No timing interpretation is assigned to the `0xF1` records.

## EVT-001 — tempo and meter event candidates

**Question:** Do event-sequence records carry project tempo and meter values that agree with metadata?

**Fixture:** The supplied project, comparing aligned `EvSq` events with both output and asset plists.

**Observation:** Each of 33 `EvSq` chunks has a size divisible by 16; splitting atoms by byte 7's high-bit continuation marker yields 71 records. Two 32-byte type `0x60` records have unsigned 32-bit little-endian values at event offset 16 of 1,600,000 and 1,200,000. Dividing by 10,000 yields 160 and 120 BPM. The 160 BPM event is in group value zero and matches both metadata plists; the 120 BPM event is in group `0x00040000`. A 48-byte type `0x30` event in group zero carries numerator 4 and denominator power 2 (4/4), matching both metadata plists.

**Result:** The group-zero tempo and meter candidates are HIGH CONFIDENCE for this fixture because their independently decoded values match both summary sources. The nonzero-group 120 BPM event is retained with its group; it is not added to the global map. The raw event positions (38,400 for tempo; zero for meter) are preserved with unknown units.

**Confidence:** HIGH CONFIDENCE for field values and metadata agreement in this fixture; HYPOTHESIS that group zero is the global sequence until more projects confirm it.

**Alternative considered:** The 120 BPM event could be a local source tempo or another sequence-specific value. Its distinct group and disagreement with both project-level summaries argue against promoting it to the global tempo map.

**Next:** Create differential projects at known tempo/meter values and tempo-change positions; verify event positions, scaling, grouping, and completeness.
