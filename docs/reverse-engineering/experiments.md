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

## PD-002 — arrange-model branch contents

**Question:** Does the keyed archive's `DfDocument arrange model` object contain arrangement track or region collections?

**Fixture:** The supplied project, resolved through the `NSKeyedArchiver` object graph in IDA Python.

**Observation:** The referenced object has scalar editor/arrange settings such as zoom indices, snap/quantize state, visibility flags, count-in and metronome settings, media properties, and active song-part indices. Its `CBData` reference resolves to a dictionary of UI state keys, including panel visibility, importer page, scroll offset, and a previously selected track UUID. No track or region collection is present in this object or dictionary.

**Result:** This archive branch is not a decoded arrangement source in the inspected fixture. Its UI state is still preserved in the original keyed-archive plist. The absence of a collection here does not prove that all other archive objects or chunk structures lack arrangement data.

**Confidence:** CONFIRMED for the keys and references in this object's serialized graph; UNKNOWN for whether another object uses these UI identifiers to refer to arrangement records.

**Alternative considered:** Track-panel visibility and the previous-track UUID could appear related to track data, but they are scalar UI state and do not enumerate track identity or region placement.

**Next:** Continue examining the logic-song chunk stream, especially validated `AuCO` channel-strip candidates and arrangement-bearing chunk families.

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

**Result:** The name matches establish that `AuFl` carries audio-file references in this fixture. Initially, the same-value `AuRg` count match alone was treated as strong evidence. ID-001 showed that the numeric value is reused by `TxSt`, so group matching alone is insufficient. CROSS-003 later found the exact filename stem in every same-value `AuRg` payload, strengthening the source-to-region link for this fixture. Start, duration, source offset, trimming, looping, and exact group-field semantics remain unknown.

**Confidence:** HIGH CONFIDENCE that the asset basenames identify audio-file references in `AuFl`; see CROSS-003 for the additional `AuRg` filename-stem evidence.

**Alternative considered:** The `AuFl` and `AuRg` values may be type-scoped or identify a broader object cluster, so the field alone does not establish a file-to-region relation. See ID-001 and CROSS-003.

**Next:** Compare a minimal project with one audio region, then move/trim/loop it independently and diff the `AuRg` and grouped `EvSq` chunks. No timing interpretation is assigned to the `0xF1` records.

## EVT-001 — tempo and meter event candidates

**Question:** Do event-sequence records carry project tempo and meter values that agree with metadata?

**Fixture:** The supplied project, comparing aligned `EvSq` events with both output and asset plists.

**Observation:** Each of 33 `EvSq` chunks has a size divisible by 16; splitting atoms by byte 7's high-bit continuation marker yields 71 records. Two 32-byte type `0x60` records have unsigned 32-bit little-endian values at event offset 16 of 1,600,000 and 1,200,000. Dividing by 10,000 yields 160 and 120 BPM. The 160 BPM event is in group value zero and matches both metadata plists; the 120 BPM event is in group `0x00040000`. A 48-byte type `0x30` event in group zero carries numerator 4 and denominator power 2 (4/4), matching both metadata plists.

**Result:** The group-zero tempo and meter candidates are HIGH CONFIDENCE for this fixture because their independently decoded values match both summary sources. The nonzero-group 120 BPM event is retained with its group; it is not added to the global map. The raw event positions (38,400 for tempo; zero for meter) are preserved with unknown units.

**Confidence:** HIGH CONFIDENCE for field values and metadata agreement in this fixture; HYPOTHESIS that group zero is the global sequence until more projects confirm it.

**Alternative considered:** The 120 BPM event could be a local source tempo or another sequence-specific value. Its distinct group and disagreement with both project-level summaries argue against promoting it to the global tempo map.

**Next:** Create differential projects at known tempo/meter values and tempo-change positions; verify event positions, scaling, grouping, and completeness.

## EVT-002 — repeated short event-sequence chunks

**Question:** Do short `EvSq` chunks in audio-resource groups contain event data or a common marker?

**Fixture:** The same supplied project, inspected through IDA MCP and checked against the Python chunk inventory.

**Observation:** Seventeen `EvSq` chunks have 16-byte payloads beginning with `0xF1`. All seventeen payloads are byte-identical (`f1 00 00 00 ff ff ff 3f 00 00 00 00 00 00 00 00`). Six of them have the same candidate group values as the six `AuFl` chunks and their linked `AuRg` chunks. The remaining eleven occur in other groups.

**Result:** These chunks are retained as raw events. Identical contents across multiple groups do not identify the marker's meaning or establish a one-to-one track/region relationship.

**Confidence:** CONFIRMED for the count, bytes, and group-value overlap in this fixture; UNKNOWN for semantics.

**Alternative considered:** The shared group may denote a containing track or object cluster rather than a media region. The repetition across audio and non-audio groups is consistent with a generic sequence marker.

**Next:** Compare empty, MIDI-only, and audio-only projects and observe whether these chunks appear, change, or disappear.

## TRK-001 — observed `Trak` payload families

**Question:** Are `Trak` chunks uniform records in the inspected logic-song stream?

**Fixture:** The same supplied project, read through the validated chunk inventory in IDA MCP.

**Observation:** The 59 `Trak` chunks split into 33 with zero-byte payloads and 26 with 58-byte payloads. The latter family shares an eight-byte payload prefix; their following bytes vary. These records are distributed across multiple candidate group values. The empty-payload family has varying opaque chunk-header bytes.

**Result:** Chunk type and payload size alone are insufficient to treat every `Trak` chunk as a track object. The parser preserves each header, payload size, and offset without assigning track identities or order.

**Confidence:** CONFIRMED for counts and payload-size families in this fixture; UNKNOWN for record semantics.

**Alternative considered:** `Trak` may identify nested track-related records or references rather than one chunk per arrange track. The 59 observed chunks also exceed the summary's arrange-track count, so the counts cannot be equated.

**Next:** Compare track-only fixtures and determine which chunk family changes when a track is added, renamed, reordered, or changes type.

## TRK-002 — cross-format `AuCO` channel-strip candidate

**Question:** Does the GarageBand chunk stream contain records shaped like Logic Pro channel-strip records?

**Fixture:** The supplied GarageBand project, examined in IDA MCP and independently re-counted from parser output with Python. Cross-format reference: [`tracks.go` in loov/logicx](https://raw.githubusercontent.com/loov/logicx/main/tracks.go).

**Observation:** The external Logic parser identifies `AuCO` channel-strip chunks by header bytes 4–7 `07 00 0e 00`, then reads a 24-byte record at payload offset 60: a leading byte, a 15-byte NUL-padded printable name, and an eight-byte descriptor. In this GarageBand fixture, 23 of 36 `AuCO` chunks match the marker and minimum length; all 23 contain printable NUL-padded name fields. The little-endian 16-bit value at chunk-header offset 14 is unique and contiguous from 0 through 22 across those records.

**Result:** The layout is a strong cross-format candidate for GarageBand channel-strip records. It is not yet implemented as arrangement tracks: the fixture's summary reports seven arrange tracks, and the 23 records may include mixer, auxiliary, or other channel strips. The external Logic Pro interpretation is not direct evidence that every descriptor field or track kind transfers to GarageBand.

**Confidence:** HIGH CONFIDENCE that this exact marker/record pattern occurs in the inspected GarageBand payload; HYPOTHESIS that it has the same channel-strip meaning as in Logic Pro.

**Alternative considered:** `AuCO` may contain another GarageBand object family with a coincidentally similar record shape. The exact marker, fixed record offset, printable padded names, and sequential strip values make a shared layout plausible, but controlled track-count changes are needed to test it.

**Next:** Compare an empty project and projects with one and two added tracks. Check which `AuCO` records and strip IDs are added, and compare the extracted names to GarageBand's visible track list without committing private project content.

## TRK-003 — cross-format channel-kind discriminator

**Question:** Does the Logic Pro channel-strip descriptor classifier directly provide GarageBand arrange-track types?

**Fixture:** The same GarageBand project. Descriptor categories were evaluated from the 23 `AuCO` candidates identified in TRK-002. Cross-format reference: [`trackKind` in `tracks.go`](https://github.com/loov/logicx/blob/main/tracks.go#L1119-L1162).

**Observation:** Applying the Logic Pro descriptor rules to the eight-byte records gives 12 audio, two instrument, three input, two bus, one master, and three unknown candidates. The project summary reports seven arrange tracks. No track-kind field in the GarageBand summary independently confirms these categories.

**Result:** The Logic Pro descriptor classifier cannot be used directly to create GarageBand arrange tracks: it yields a broader set of channel-strip categories and more audio/instrument candidates than the arrange-track count. The parser continues to preserve the descriptor bytes without mapping them to GarageBand track kinds. No Logic Pro code was copied.

**Confidence:** CONFIRMED for the observed descriptor-byte distribution and summary count in this fixture; UNKNOWN for GarageBand meanings of these descriptor values.

**Alternative considered:** The extra channel strips may represent mixer, auxiliary, input, output, or other non-arrange entities. This would allow the Logic-like channel-strip structure to coexist with a smaller arrange-track list, but the current evidence does not identify the subset.

**Next:** Use controlled track-count fixtures and visible track names/types to determine whether arrange tracks can be distinguished from the full `AuCO` channel-strip set.

## ID-001 — candidate group-value reuse across chunk families

**Question:** Is the chunk-header value at offset 8 a globally unique object or track identifier?

**Fixture:** The supplied project, inspected through IDA Python and re-counted with the parser's chunk inventory.

**Observation:** There are 32 `TxSt` chunks, one each at candidate values `0x00000000` through `0x007C0000` in `0x00040000` increments. Their payloads contain text-style context labels, including score-display labels. The six `AuFl` chunks use six values in that same range (`0x00100000` through `0x00280000`, omitting `0x00240000`); their `AuRg` chunks reuse those values. An exact UTF-16LE search for each audio basename found it in its `AuFl` payload but in none of the same-value `AuRg` payloads.

**Result:** The candidate group value cannot be treated as a globally unique track ID across chunk types. It partitions each `AuFl` with one or two `AuRg` chunks in this fixture, totaling the metadata's nine root regions. At this stage, source-to-region association was still uncertain; CROSS-003 subsequently found matching filename stems in the region payloads.

**Confidence:** CONFIRMED for the `TxSt` value sequence, numeric overlap, and absence of full basenames in `AuRg` in this fixture; UNKNOWN for the header field's scope.

**Alternative considered:** The field may be a group identifier whose namespace or meaning depends on chunk type; text-style entries and media objects may reuse numeric values. Alternatively, same-value media grouping may be a real local relationship while unrelated chunk families use the field differently.

**Next:** Use controlled projects with one audio file and one or two regions, then change only region count or source assignment. Check whether the same group value follows the media relationship while `TxSt` indices remain fixed.

## CROSS-003 — audio filename stems inside region chunks

**Question:** Can audio references be associated with individual `AuRg` chunks independently of the reused header value?

**Fixture:** The supplied project. IDA Python read the validated chunk payloads; Python parser implementation and a synthetic regression fixture reproduce the matching rule.

**Observation:** Each of nine `AuRg` payloads contains an exact ASCII/UTF-8 NUL-delimited string equal to one `AudioFiles` basename with its `.caf` extension removed. Every match is inside an `AuRg` whose offset-8 candidate value also matches the `AuFl` chunk containing that asset's full UTF-16LE basename. The six source names correspond to nine region chunks (three source names occur twice, three occur once). The full basename including `.caf` is not present in the `AuRg` payload.

**Result:** The combination of an exact filename-stem string match and same-value `AuFl` association supports mapping all nine `AuRg` records to the six media references in this fixture. The parser now emits same-group `AuRg` indices separately from those that also match the filename stem. This does not establish track placement or decode timing, trimming, looping, or source offsets.

**Confidence:** HIGH CONFIDENCE for the nine source-to-region-chunk links in this fixture. The serialization rule and field scope require validation on other projects and controlled edits.

**Alternative considered:** A matching region label could be descriptive text rather than a source pointer; the independent same-group match to the uniquely basename-matched `AuFl` strengthens, but does not universally prove, the link.

**Next:** Investigate `AuRg` fields and adjacent event chunks with minimal projects that move, trim, duplicate, and loop a single source region.

## ARR-017 — audio placement events and timeline positions

**Question:** Where are audio-region timeline starts and track assignments stored?

**Fixture:** The supplied project. The nine `AuRg` entries and GarageBand-generated arrangement preview were compared with IDA Python and the independent chunk/event parser. The Logic Pro ProjectData specification was used only to form a cross-format hypothesis.

**Observation:** `EvSq` chunk 298 contains nine `0x24` event records. Each starts with at least 80 bytes and has marker bytes `89 BC 8A 89` at event offsets `0x17`, `0x27`, `0x37`, and `0x47`. At `+0x04`, the little-endian position values are 34,560 (five events), 49,920 (two), 65,280 (one), and 157,440 (one). At `+0x14`, the track bytes are 2 through 7. At `+0x2C`, link values shifted left 16 bits match the audio groups found through `AuFl` names and `AuRg` filename stems. Seven records are 80 bytes and two are 160 bytes; the latter contain 80 trailing bytes beyond the common placement structure. The preview shows corresponding audio regions beginning at bars 1, 5, 9, and 33.

**Result:** The Logic Pro model predicts `position = 34,560 + tick@960`. This converts the GarageBand values to 0, 16, 32, and 128 beats, matching the preview's bar positions. The embedded track byte and media link recover six populated audio tracks and all nine placements. The parser emits these as neutral audio regions with source reference, one-based track number normalized to zero-based `Track.index`, and exact beat-string start; raw fields and unparsed suffix bytes are preserved. Region duration and exact placement-to-`AuRg` object ordinal remain unknown.

**Confidence:** HIGH CONFIDENCE for the positions, track values, and source links in this fixture: all three fields agree with the project preview/resource names. HYPOTHESIS that the same origin, PPQ, markers, and one-based track convention generalize across GarageBand versions, supported by the [Logic Pro ProjectData specification](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#3-the-unifying-model).

**Alternative considered:** The offset-`+0x04` value inside `AuRg` records varies for regions that visibly begin at the same bar, so it is not accepted as a global arrangement start. The `EvSq` placement field is better supported by the preview match. The 80-byte suffix in longer event records may carry additional region state, but no meaning is assigned.

**Next:** Differential fixtures should move one audio region by one beat and one bar, change the meter, and alter trim/loop state separately. Then decode duration, source offset, region-object linkage, and the 80-byte suffix.

## ARR-018 — region frame-count and extended placement correlation

**Question:** Does `AuRg` contain a source-frame count, and does the extra placement-event data identify a particular region object?

**Fixture:** The supplied project. IDA and Python compared all nine `AuRg` payloads to the nine `0x24` placement events. The Logic Pro ProjectData specification was used as an independent structural reference.

**Observation:** Each `AuRg` has a little-endian 32-bit value at payload offset `0x16`; the values are plausible frame counts at the project summary sample rate of 44.1 kHz. A readable filename stem occurs at payload offset `0x4C`, preceded by a 16-bit length at `0x4A`, matching the Logic Pro audio-region layout. Two placement events are 160 bytes, with an 80-byte suffix. The first suffix dword equals the `+0x16` value of one same-source `AuRg` chunk in each case (the second of two chunks in its group). The other seven placements have no suffix dword that matches a same-source region candidate.

**Result:** The `AuRg +0x16` field is retained as a `frame_count_candidate`, not as an arrangement duration in beats. The two suffix correlations are exposed as candidate region-object links. They do not establish a universal event-to-object link encoding or placement duration. The source spec describes `+0x16` as a frame count and `+0x4A` as the region-name length, but it targets Logic Pro 11.2.2; the matching framing and plausible values in GarageBand are corroborating evidence only ([specification](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#8-audio-regions)).

**Confidence:** HIGH CONFIDENCE for the observed offsets, values, label framing, and two cross-record matches in this fixture; HYPOTHESIS that `+0x16` represents frame count in all GarageBand versions; UNKNOWN for what the matching suffix dword references.

**Alternative considered:** The `+0x16` integers or suffix values could be cached lengths/identifiers rather than source frame counts. The recognized Logic-style layout and plausible duration-at-44.1-kHz values support the frame-count interpretation but do not prove region timeline length.

**Next:** Use a controlled audio region with a known source duration, then trim it without moving it and move it without trimming. Compare `AuRg +0x16`, event suffixes, and placement positions. Verify whether displayed duration changes in source frames, beats, or both.

## ARR-019 — placement word at `+0x18` is unresolved

**Question:** Does the 32-bit word at placement-event offset `+0x18` encode an audio-region end or duration?

**Fixture:** The supplied project. IDA Python independently traversed the `projectData` package and decoded the nine `0x24` events in `EvSq` chunk 298; the existing Python parser supplied the cross-check for event boundaries and starts.

**Observation:** Interpreted as little-endian unsigned 32-bit values, the word at `+0x18` is `130560` once, `122880` once, `99840` once, and `1073741823` six times. All nine events share the same recognized 80-byte prefix; the three non-sentinel values occur on events at different source/track groupings, while several bar-one events have the sentinel.

**Result:** The observed values do not support a single general rule that `+0x18` is the region duration or end position. The field remains unknown and the raw event is preserved. No value is used to set FLP clip length.

**Confidence:** CONFIRMED for the observed values and event offsets in this fixture; UNKNOWN for field semantics.

**Alternative considered:** The field may be a source-specific offset/end cache, a state discriminator, or a value meaningful only with other event data. The single fixture cannot distinguish these possibilities.

**Next:** In a controlled project, compare the same region after changing only its timeline length, then after changing only its trim or source. Check both `+0x18` and the associated `AuRg` payload before assigning semantics.

## MIDI-001 — unclassified `0x20` event records

**Question:** Do `0x20` event records represent MIDI-region placements in this GarageBand project?

**Fixture:** The supplied project; all 71 parsed `EvSq` records and the 33 `MSeq` chunks were inventoried. The Logic Pro ProjectData specification was consulted as a cross-format reference.

**Observation:** One `EvSq` chunk contains 12 records of 80 bytes, each beginning with `0x20 00 00 00`. All have raw position 34,560 and link field zero; the track-number byte ranges from 1 to 14 with gaps. Their marker bytes differ slightly from the nine audio-placement candidates. No `0x90` MIDI-note event records occur in the fixture. The 12 events are not in one-to-one correspondence with the seven arrange-track summary count or the nine audio placements.

**Result:** The published Logic Pro spec uses `0x20` for MIDI-region placements, but this GarageBand fixture does not provide enough independent evidence to assign that meaning here. They remain preserved as unknown event records and are not emitted as MIDI regions. No MIDI notes have been recovered from this fixture.

**Confidence:** CONFIRMED for the observed counts, sizes, positions, track bytes, zero link values, and absence of `0x90` records; HYPOTHESIS that `0x20` denotes MIDI placement in GarageBand.

**Alternative considered:** These may be empty MIDI-region placements, internal arrangement objects, or another sequence type that shares the Logic event marker. Their repeated bar-one position and zero links do not establish usable MIDI content.

**Next:** Compare a GarageBand project with one software-instrument track and a known MIDI region, then add one note and compare the region's `MSeq` and `EvSq` chunks. Determine whether a `0x20` event changes and whether any `0x90` note records appear.

## MIDI-002 — Logic-shaped note fields in a local GarageBand project

**Question:** Can the Logic Pro note-event field layout identify MIDI note candidates in another GarageBand project?

**Fixture:** A second locally supplied `.band` project, inspected locally with IDA Python and the independent package parser. The project and its media are excluded from the repository; no note values or audio content are recorded here.

**Observation:** `EvSq` contains records beginning with event byte `0x90`. These records are 80 bytes in this fixture, rather than the 32-byte records described by the Logic Pro reference. Their `+0x17` marker matches the reference, and the bytes at `+0x0B`, `+0x0C`, and `+0x1C` fall within plausible velocity, pitch, and duration ranges. The note-event sequence shares a candidate group value with one `MSeq` chunk. Its note-region placement and track association were not established. The cross-format field map is described in [Logic Pro ProjectData specification §8.5](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#85-midi-note-regions).

**Result:** The parser exposes the reference-layout fields as `midi_note_event_candidates` in inspection JSON, preserving raw bytes and same-group `MSeq` chunk indices. It does not attach these candidates to a track or normalized MIDI region.

**Confidence:** HIGH CONFIDENCE that the fixture contains the observed 80-byte `0x90` records and same-group `MSeq` record; HYPOTHESIS for pitch/velocity/duration field meanings transferred from Logic Pro; UNKNOWN for placement and track association.

**Alternative considered:** `0x90` may be a GarageBand-specific event family whose fields only resemble Logic MIDI notes. The longer record size and lack of a controlled one-note fixture leave this possible.

**Next:** Create or obtain a one-note GarageBand fixture, vary pitch, velocity, onset, and duration independently, then compare the corresponding `EvSq` and `MSeq` records. Separately identify the `0x20` placement link to the correct `MSeq` region and arrange track.

## MIDI-003 — MIDI placement cluster links to `MSeq`

**Question:** Which field in a `0x20` event links a MIDI placement to its `MSeq` region record?

**Fixtures:** The original locally inspected project and the additional locally supplied project. Both were independently traversed through IDA Python and checked by the Python parser. The second project and its media remain local and are not included in the repository.

**Observation:** The recognized `0x20` placement records are 80 bytes and share the marker-byte pattern `+0x17=0x89`, `+0x27=0x88`, `+0x37=0x8A`, `+0x47=0x88`. Interpreting the little-endian word at event `+0x20` as a low-order cluster value and shifting it left 16 bits produces a chunk-header group value present on exactly one `MSeq` chunk for every recognized placement in both fixtures. In the original fixture this matched all 12 recognized events; no target was missing or ambiguous. The same unique-match property held in the second fixture. The relationship is also described by the Logic Pro reference's MIDI region synthesis notes, where the MIDI placement carries the region-cluster value at `+0x20` ([specification §10.9.5](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#L630-L635)).

**Result:** The parser emits `midi_region_placement_candidates` with the raw event, candidate position and track fields, transformed group value, and matching `MSeq` chunk index. The unique cluster-to-`MSeq` relation is HIGH CONFIDENCE for these fixtures. It does not yet attach MIDI regions to neutral tracks because GarageBand track-index and position semantics have not been independently validated.

**Confidence:** HIGH CONFIDENCE for the cluster transform and unique `MSeq` match in these two fixtures; HYPOTHESIS for transferring the marker and position/track field meanings from Logic Pro to GarageBand.

**Alternative considered:** The `MSeq` chunk-group match could be a coincidence if candidate group values were a small common set. Each placement instead yields a distinct target, with one matching `MSeq` record and no ambiguous or missing matches in either fixture, which makes coincidence less likely.

**Next:** Make one software-instrument region in GarageBand, then move it and change its track independently. Verify which event fields change, whether the cluster transform remains stable, and whether the position and track candidates match GarageBand's visible arrangement.

## MIDI-004 — placement track byte does not map directly to `Trak` chunk order

**Question:** Can the `0x20` placement byte at `+0x14` be matched to arrange tracks by its ordinal among `Trak` chunks?

**Fixtures:** The two locally inspected projects used for MIDI-003. The second project remains private; only aggregate counts are recorded.

**Observation:** In the second project, IDA found 59 `Trak` chunks, 27 distinct candidate group values among them, and 19 recognized `0x20` placements. The placement byte had 14 distinct values ranging from 1 through 18. Comparing those byte values with raw `Trak` chunk ordinals gave nearby ordinal hits because the placement values are small, but the chunk stream contains repeated `Trak` group values and substantially more `Trak` chunks than placements. No stable one-to-one mapping to a track record was established.

**Result:** The ordinal comparison is inconclusive and is not evidence that `+0x14` is a direct `Trak` index. The parser continues to expose it as `track_number_1_based_candidate` only; it does not use MIDI placements to create tracks.

**Confidence:** CONFIRMED for these aggregate counts and the absence of an established direct ordinal mapping; UNKNOWN for the field's GarageBand meaning.

**Alternative considered:** The value could be a one-based arrange-track number, an index in a different object table, or a scoped identifier. Raw chunk order alone cannot distinguish these interpretations.

**Next:** Use controlled projects with one software-instrument track, then add a second track and move the same MIDI region between them. Compare the `+0x14` byte with visible track order and any associated track identifiers before normalizing it.

## MIDI-005 — `MSeq` position scan is dominated by origin-position regions

**Question:** Does a fixed 32-bit field in a linked `MSeq` payload reproduce the start position from its `0x20` placement event?

**Fixture:** The additional local project used for MIDI-003. No project name, note data, or media is included in the repository.

**Method:** For each uniquely linked placement, compare its origin-adjusted raw position against little-endian 32-bit values throughout the linked `MSeq` payload. Repeat the count after excluding placements whose adjusted position is zero, since zero values can match default or padding fields.

**Observation:** A byte-level scan appeared to produce a high match rate at one payload offset. That result was dominated by zero-position placements. After excluding those, only two nonzero placement positions remained; no single aligned 32-bit field matched both. The corresponding fixture does not provide enough independent position variation to identify an `MSeq` start field.

**Result:** No `MSeq` start offset is assigned. The apparent match is treated as an inconclusive zero-value coincidence, and MIDI position remains a candidate on the placement event only.

**Confidence:** CONFIRMED that this fixture lacks enough varying nonzero placements for the scan to establish a field; UNKNOWN for `MSeq` internal-start semantics.

**Next:** Use two or more controlled MIDI regions at distinct nonzero starts, then move each region independently and compare the linked `MSeq` payloads.

## ARR-020 — compare `AuRg` frame candidates with embedded source frame counts

**Question:** Does the little-endian integer at `AuRg` payload `+0x16` always equal the complete embedded source file's frame count?

**Fixture:** One locally supplied package with embedded audio. The project and its audio remain outside the repository. `research/scripts/audio_frame_probe.py` reads the embedded file members in memory, inspects WAVE, AIFF, or CAF frame-count metadata, and emits only aggregate counts; it does not extract or output audio.

**Observation:** The probe decoded the embedded audio references and compared same-source `AuRg +0x16` candidates. Only a subset matched a complete source frame count, and the matches were associated with one source. Other candidates did not match their complete source length. Exact project-specific counts are kept out of this public log.

**Result:** `AuRg +0x16` cannot be used as a universal complete-source frame count or arrangement duration. Exact matches on a subset leave open whether the field is a trim/region length for some records, a source length for those records, or another value with coincidental equality.

**Confidence:** CONFIRMED that matching is not consistent across the compared candidates in this package; UNKNOWN for the field semantics.

**Alternative considered:** The comparison could be affected by format-specific valid-frame, priming, or packet-count conventions. The probe uses the WAVE data size and block alignment, AIFF/AIFC `COMM` sample-frame count, or CAF packet-table valid-frame count; this does not establish GarageBand's treatment of priming or edit lists.

**Next:** Make a controlled audio fixture with a known source length, then trim without moving, move without trimming, and compare the source frame count, `AuRg +0x16`, and placement suffix independently.
