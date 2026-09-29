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

## PD-003 - compare the arrange-model archive branch across two projects

**Question:** Does the `DfDocument arrange model` keyed-archive branch expose arrange tracks or regions in both supplied projects, or is its observed content limited to editor state?

**Fixtures:** The supplied audio-free and audio-bearing GarageBand projects. Project titles, media, track labels, and field values are omitted.

**Method:** Resolve the top-level `DfDocument arrange model` UID in each `projectData` NSKeyedArchiver graph. Compare field names and value types without printing values. Follow its `CBData` UID and compare the generic-data key/value list lengths and types. Independently opened the audio-bearing XML `projectData` component in IDA MCP; at byte offset 734177, the 24-byte serialized key `DfDocument arrange model` matched Python's bytes exactly.

**Observation:** Both arrange-model objects have the same 28 fields and field-type profile: 13 integers, 9 booleans, 3 floats, and 3 dictionaries. The fields describe arrange/editor state such as zoom, snap/quantize, visibility, count-in, metronome, media settings, and active song-part indices. In each fixture, `CBData` has parallel `NS.keys` and `NS.objects` lists whose entries resolve to 14 and 27 dictionaries respectively; these hold variable UI/editor state, including scroll offset, importer page, panel visibility, and a previously selected track UUID. Neither list is an arrange-track or region collection.

**Result:** This negative finding repeats across two unrelated projects: the top-level arrange-model branch preserves UI/editor settings but does not enumerate arrangement tracks or regions. Track reconstruction must continue to use evidence from the logic-song payload or another authoritative component; the previous-track UUID remains a UI reference, not an established track mapping.

**Confidence:** CONFIRMED for the branch key/type profiles and CBData list shapes in these two fixtures; HIGH CONFIDENCE for the IDA/Python byte agreement at the stated audio-bearing `projectData` offset. This does not establish the absence of track data from other archive branches or package components.

**Alternative considered:** The UI state includes track-related identifiers and visibility fields, but these are scalars or editor-state entries and do not provide a complete track collection. Such identifiers could still correlate with tracks if independently matched to logic-song records.

**Next:** Use a controlled rename/reorder fixture to test whether the UUID-to-`Trak` link observed in TRK-009 maps to an arrange track and visible order.

## TRK-009 - saved selected-track UUID matches a `Trak` payload

**Question:** Does `previousCurrentTrackUUID` in the keyed-archive UI state directly identify a record in the logic-song chunk stream?

**Fixtures:** Both supplied projects (audio-free and audio-bearing). UUID values, project titles, media, and track labels are not published.

**Method:** Resolve the `previousCurrentTrackUUID` string from `DfDocument arrange model` → `CBData`, parse its canonical UUID representation, then scan every logic-song chunk payload for all occurrences of its 16-byte canonical and mixed-endian forms plus lower/upper-case ASCII and UTF-16 string forms, with and without braces. Profile the 16-byte field at `+0x18` in every 58-byte `Trak` payload. An initial probe version recorded only the first occurrence per encoding and chunk; it was corrected to enumerate every occurrence before accepting uniqueness. A regression test places the same UUID twice in one chunk. The reusable `research/scripts/track_uuid_probe.py` emits only aggregate field profiles and match shapes, never the identifiers. IDA MCP read all 61 parser-selected `+0x18` fields across both extracted logic-song components and matched Python's bytes exactly.

**Observation:** The audio-free fixture has 26 58-byte `Trak` payloads and the audio-bearing fixture has 35; every 16-byte field at `+0x18` is unique within its fixture. All 61 fields have the RFC UUID variant and version 1 bit pattern, and IDA agrees with Python on all 61 byte ranges. In each fixture, exactly one serialized form of `previousCurrentTrackUUID` matched, using canonical UUID byte order; the sole hit is in a 58-byte `Trak` payload at offset `+0x18` (24 decimal). The audio-free payload hit is at logic-song offset 210618; the audio-bearing payload hit is at offset 405106. No ASCII, UTF-16, or mixed-endian UUID hit was found.

**Result:** The `+0x18` field is a unique UUID-shaped value across every observed 58-byte `Trak` payload, and the saved previous-current-track UI UUID links uniquely to one such chunk in each project. This supports interpreting that field as a track-related identifier in these fixtures. It does not establish that every 58-byte `Trak` is an arrange track, recover ordering or names, or prove the selection is current rather than stale UI state.

**Confidence:** CONFIRMED for the 61 unique version-1 UUID-shaped field values, the selected-UUID cross-link in both fixtures, and IDA/Python agreement for every field. HIGH CONFIDENCE that `Trak +0x18` carries track-related identifiers in these fixtures; whether these records enumerate arrange tracks remains UNKNOWN.

**Alternative considered:** The UUID may identify an editor selection or another track-like object rather than the full arrangement track record. The `previousCurrentTrackUUID` key and `Trak` tag support a track-related interpretation, but no controlled track mutation yet proves the record's role.

**Next:** Use a controlled track rename/reorder/add fixture to determine whether all of these identifiers enumerate arrange tracks and to map them to visible track order.

## PD-004 - inspect the saved track-inspector UI state shape

**Question:** Does `CbTrackInspectorInternalState` in the arrange-model `CBData` branch contain track identities or an arrange-track collection?

**Fixtures:** Both supplied projects, examined through `projectData` only. Project values, identifiers, paths, media, and inspector values are omitted.

**Method:** Resolve the keyed archive's `DfDocument arrange model` and its `CBData` dictionary, locate the `CbTrackInspectorInternalState` entry, then report only its immediate field names and value types. The reusable `research/scripts/arrange_ui_probe.py` does not emit scalar values, object identifiers, project paths, or media.

**Observation:** The audio-free project has no entry with this key. The audio-bearing project's entry has three fields: `CbTrackInspectorTopControllerClassKey` (string), `CbMasterEffectsEchoSectionOpen` (boolean), and `CbMasterEffectsReverbSectionOpen` (boolean). No track identifier or track/region collection appears among these immediate fields.

**Result:** In the observed audio-bearing project, this inspector-state object describes UI/controller state and does not itself enumerate arrangement tracks. This is consistent with PD-003, but says nothing about other archive branches or Logic-song chunks.

**Confidence:** CONFIRMED for the observed presence/absence and immediate field shape in these two projectData archives; UNKNOWN whether the controller-class value or nested references elsewhere could provide additional indirect links.

**Next:** Keep using the TRK-009 UUID cross-link as a candidate and seek a controlled rename/reorder fixture to associate its `Trak` record with visible arrangement order.

## PD-005 - inventory keyed-archive classes and fields without values

**Question:** Do either inspected `projectData` keyed archives contain class-typed track or region objects outside the already inspected arrange-model branch?

**Fixtures:** The two supplied `.band` archives, identified here only as fixture 1 and fixture 2. The probe reads each ZIP member ending in `projectData` only; it does not read or extract audio/media members.

**Method:** Added `research/scripts/keyed_archive_inventory.py`. It counts serialized object classes, schema field names, value types, and dictionary key lengths. The report omits dictionary key text, all project values, identifiers, user strings, paths, media, and object indices. Regression tests verify both the schema report and omission of a synthetic private track name. Extracted only fixture 1's logic-song `NS.data` payload to an ignored local file and opened it in IDA MCP; the first 60 bytes (stream header plus first chunk header) matched the Python read byte-for-byte. No audio member was opened or extracted.

**Observation:** Both archives contain one `DfArrangeModel`, one `DfLogicModel`, and one `NSMutableData` song payload. Other class-typed objects are Foundation mutable dictionaries and strings (three/four dictionaries and one/two strings respectively); no additional custom class instances appear. The arrange-model field profile matches PD-003. The dictionary key-length distributions differ, but the probe intentionally does not emit key text and the difference is not assigned semantic meaning.

**Result:** This independently checks the full keyed-archive object table and finds no separate class-typed track/region collection in either fixture. Arrangement reconstruction remains focused on the opaque logic-song chunk stream. This does not rule out records encoded inside dictionaries, data blobs, or another project component.

**Confidence:** HIGH CONFIDENCE for the class/field inventory of these two `projectData` archives; UNKNOWN for arrangement semantics embedded in dictionaries or `NS.data`.

**Alternative considered:** Track objects could be represented as generic dictionaries or nested byte payloads rather than dedicated Objective-C classes; this inventory does not decode those values.

**Next:** Continue correlating chunk families against controlled track-add/reorder fixtures; preserve the inventory command as a quick check for future GarageBand versions.

## ARR-026 - audio placement track-index bounds across two projects

**Question:** Do the recovered audio-placement indices, after the parser's candidate one-based-to-zero-based conversion, fall within each project's declared arrange-track count?

**Fixtures:** Both supplied projects, read through `projectData` and summary metadata only. No audio was extracted or read.

**Method:** Added `research/scripts/audio_track_index_probe.py` to report the declared count, number of audio-bearing track indices, index minimum/maximum, and audio-region count without names, starts, identifiers, or sources. The current parser subtracts one from the placement track-number byte when constructing neutral `Track.index` values.

**Observation:** Fixture A declares 7 arrange tracks and has 9 audio regions on 6 audio-bearing indices spanning 1 through 6. Fixture B declares 12 arrange tracks and has 10 audio regions on 5 audio-bearing indices spanning 1 through 10. Every observed index is nonnegative and below its project's declared count; neither fixture has an audio-bearing index 0. The audio-bearing index counts are lower than the declarations.

**Result:** The current index conversion is internally in-bounds in both fixtures. This is a consistency check, not independent proof that the placement byte maps to visible track order, nor that the parser has recovered all declared tracks; MIDI-only, empty, or otherwise unrepresented tracks remain possible.

**Confidence:** CONFIRMED for the aggregate counts and bounds in these two archives; HIGH CONFIDENCE only for the current one-based track-number interpretation already supported by the preview comparison in ARR-021.

**Alternative considered:** The summary count and placement track-number field could cover different sets of track-like objects, and no controlled track reorder/add fixture is available to verify visible row identity.

**Next:** Use a project with a known added or reordered audio track and compare the raw placement byte, the preview row, and the declared track count.

## TRK-010 - test `Trak` group values as direct placement-track links

**Question:** Does a shared chunk-header group value provide a one-to-one link between 58-byte `Trak` records and audio or MIDI placement events?

**Fixtures:** Both supplied projects. Group values, UUIDs, names, media, and project paths are omitted.

**Method:** Added `research/scripts/trak_group_probe.py` to bucket 58-byte `Trak` groups anonymously and count same-group type-`0x20`/type-`0x24` events and `AuCO`, `AuFl`, `AuRg`, and `MSeq` chunks. For each fixture, Python selected a 58-byte `Trak` and an `EvSq` chunk from the group shared by the type-`0x24` audio records. IDA MCP read the little-endian 32-bit group field at header offset `+0x08` in both chunks and matched Python's bytes in both fixtures.

**Observation:** Each fixture has four distinct group values among 58-byte `Trak` chunks. In the group containing the audio placement records, the metadata-only fixture has 9 type-`0x24` records, 9 58-byte `Trak` chunks, and 3 `MSeq` chunks; the audio-bearing fixture has 11 type-`0x24` records, 14 58-byte `Trak` chunks, and 3 `MSeq` chunks. In the group containing `AuFl`/`AuRg` source chunks, each fixture has one 58-byte `Trak`, while the number of `AuRg` chunks differs (1 versus 4). No 58-byte `Trak` group overlaps a validated `AuCO` group in either fixture. Other group buckets contain 15/19 58-byte `Trak` chunks alongside 12/14 type-`0x20` events, respectively.

**Result:** Chunk-group equality is not a one-to-one mapping from these records to individual placements or channel strips. In particular, the shared group containing all observed audio placement events contains many 58-byte `Trak` chunks. The result does not rule out group-scoped relationships or another identifier inside the event/payload; it rules out treating group equality alone as the track-object join.

**Confidence:** CONFIRMED for the anonymous group counts and IDA/Python agreement on the representative group fields in both fixtures; UNKNOWN for the semantic meaning and scope of these group values.

**Alternative considered:** The group may scope an event stream, collection, or serialized subgraph rather than identify a single object. Counts differ because these projects are unrelated, not controlled variants.

**Next:** In a controlled project, move one audio region between tracks without changing its source and compare the placement byte, chunk group, and `Trak +0x18` identifiers.

## TRK-011 - search track UUIDs across keyed-archive strings and companion plists

**Question:** Do the UUID-shaped fields in all observed 58-byte `Trak` payloads recur in archive-level strings or companion plist components, potentially exposing a fuller track mapping?

**Fixtures:** Both supplied `.band` packages. UUID values, project paths, media, and plist component names are omitted.

**Method:** Added `research/scripts/trak_uuid_archive_probe.py`. It extracts UUID-shaped values at `Trak +0x18`, searches plain strings and `NS.string` values in the projectData keyed archive, and searches scalar strings and byte values in other plist components for binary, mixed-endian, ASCII, and UTF-16 forms. The logic-song `NS.data` bytes are not searched as an archive-level reference because those bytes contain the fields being investigated. Output is aggregate only.

**Observation:** The two archives contain 26 and 35 unique `Trak +0x18` UUID-shaped values. Exactly one UUID per archive matches a keyed-archive string; in both cases the saved `previousCurrentTrackUUID` matches a `Trak` field. No other track UUID matches any string or byte value in either archive's two companion plist components.

**Result:** The keyed-archive strings and inspected companion plists expose the saved selected-track UUID, but provide no additional text/binary UUID joins for the other observed `Trak` records. These components therefore do not supply a full UUID-to-arrange-track mapping for these fixtures. Other non-plist package components and non-UUID reference encodings have not been excluded.

**Confidence:** CONFIRMED for the reported counts and unique selected-track cross-link in these two packages; UNKNOWN whether track records are referenced elsewhere or by another representation.

**Alternative considered:** The IDs may be local to the logic-song graph, generated for objects not exposed in metadata, or referenced through numeric ordinals or a different identifier field.

**Next:** Find a controlled renamed/reordered project pair, then compare which `Trak +0x18` UUID stays stable and whether any non-plist component or changed UI field exposes the edited track identity.

## TRK-012 - search all chunk payloads for `Trak +0x18` UUID references

**Question:** Do the UUID-shaped values at `Trak +0x18` appear in other logic-song chunks as direct references to related objects or placements?

**Fixtures:** Both supplied logic-song payloads. UUID values, payload bytes, paths, names, and media are omitted.

**Method:** Added `research/scripts/trak_uuid_logic_probe.py` to extract every 16-byte field at `+0x18` from 58-byte `Trak` chunks, then scan every chunk payload for every occurrence of each field in canonical and mixed-endian binary, lower/upper-case ASCII, braced ASCII, and UTF-16LE/BE forms. The source field itself is excluded from the additional-occurrence count. The probe emits aggregate counts and chunk-type totals only.

**Observation:** The metadata-only payload has 26 UUID fields and 26 distinct values; the audio-bearing payload has 35 fields and 35 distinct values. No UUID had any additional occurrence in any chunk payload in either project, in the searched representations.

**Result:** Within these two logic-song payloads, `Trak +0x18` UUIDs are not reused as direct binary or textual links in other chunk payloads. This does not exclude indirect ordinal references, transformed/hash representations, or references outside the logic-song component.

**Confidence:** CONFIRMED for the field counts, uniqueness, and exhaustive scan of the listed representations in these two payloads; UNKNOWN for indirect or undiscovered encodings.

**Alternative considered:** The field may be a record-local UUID consumed by UI/document state rather than a shared reference key; only the saved selected-track UUID has an observed cross-component match (TRK-009/TRK-011).

**Next:** Use controlled track creation/deletion/reordering fixtures to determine whether these UUID values are regenerated with records or whether arrangement relationships use another field.

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

## EVT-003 - replicate group-zero tempo and meter agreement

**Question:** Does the group-zero tempo/meter agreement from EVT-001 repeat in the other supplied project, and do the parser-reported event bytes match the IDA-loaded payload?

**Fixtures:** Both locally supplied `.band` projects. Project names and project-specific tempo values are omitted here.

**Method:** Compared each project's unique group-zero `0x60` tempo candidate and `0x30` meter candidate against `Output/metadata.plist` and `Output/assetsmetadata.plist`. Confirmed that exactly one group-zero candidate of each kind was found in both. For the audio-bearing fixture, compared the extracted logic-song payload hash in memory with the already loaded IDA input, then read the parser-reported meter and tempo event byte ranges from IDA.

**Observation:** In both projects, the two summary plists agree on tempo and meter, and the unique group-zero event candidates agree with those summaries. The audio-bearing fixture's extracted payload is byte-identical to the IDA-loaded file; IDA bytes at both candidate events match the parser. The tempo event raw position is preserved as a nonzero integer and the meter event raw position as zero; neither position unit is identified.

**Result:** HIGH CONFIDENCE that the observed group-zero tempo and meter candidates carry project-level values in these two fixtures. This repeats value agreement across projects, but it does not establish that the event lists are complete, that group zero always means global, or what event position units mean. No tempo-change map behavior is inferred.

**Alternative considered:** The global-looking group may be conventional for these projects but could differ in other project variants. A matching summary value does not prove that every change event has been found or decoded.

**Next:** Create a controlled tempo-change project and compare the change value and position against the serialized candidates and GarageBand display. Vary a meter independently to establish value and timeline behavior.

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

**Observation:** The 59 `Trak` chunks split into 33 with zero-byte payloads and 26 with 58-byte payloads. The original note described one shared eight-byte prefix for the latter family. A later per-record recheck did not reproduce that claim; see TRK-006. These records are distributed across multiple candidate group values. The empty-payload family has varying opaque chunk-header bytes.

**Result:** Chunk type and payload size alone are insufficient to treat every `Trak` chunk as a track object. The parser preserves each header, payload size, and offset without assigning track identities or order.

**Confidence:** CONFIRMED for counts and payload-size families in this fixture; UNKNOWN for record semantics.

**Alternative considered:** `Trak` may identify nested track-related records or references rather than one chunk per arrange track. The 59 observed chunks also exceed the summary's arrange-track count, so the counts cannot be equated.

**Next:** Compare track-only fixtures and determine which chunk family changes when a track is added, renamed, reordered, or changes type.

## TRK-002 — cross-format `AuCO` channel-strip candidate

**Question:** Does the GarageBand chunk stream contain records shaped like Logic Pro channel-strip records?

**Fixture:** The supplied GarageBand project, examined in IDA MCP and independently re-counted from parser output with Python. Cross-format reference: [`tracks.go` in loov/logicx](https://raw.githubusercontent.com/loov/logicx/main/tracks.go).

**Observation:** The external Logic parser identifies `AuCO` channel-strip chunks by header bytes 4–7 `07 00 0e 00`, then reads a 24-byte record at payload offset 60: a leading byte, a 15-byte NUL-padded printable name, and an eight-byte descriptor. In this GarageBand fixture, 23 of 36 `AuCO` chunks match the marker and minimum length; all 23 contain printable NUL-padded name fields. The little-endian 16-bit value at chunk-header offset 14 is unique and contiguous from 0 through 22 across those records.

**Result:** The layout is a strong cross-format candidate for GarageBand channel-strip records. It is not yet implemented as arrangement tracks: the fixture's summary repo…20620 tokens truncated… binary plist with separate global fields and resource-reference lists. Its track-count field differs from the arrange-track-count field in the inspected fixture.
- IDA MCP's raw view of the supplied archive agreed with the ZIP local header and member name reported by Python.
- IDA Python found the byte sequence `23 47 C0 AB` at three offsets in the extracted logic-song NSData payload: once as root magic and twice inside the first chunk payload. The two interior occurrences have unknown meaning.
- A sampler-resource basename appears twice as ASCII in that payload, while listed audio-resource basenames were not found as literal ASCII strings.
- The logic-song payload parses to its exact end as a 24-byte root header followed by 413 length-delimited 36-byte chunk headers in this fixture.
- All six asset audio basenames match one `AuFl` payload each as UTF-16LE. In all nine same-value `AuRg` chunks, an exact NUL-delimited string matches one of those basenames after removing `.caf`; this independently supports the six-to-nine source/region-chunk links in this fixture.
- Nine `0x24` event records in one `EvSq` chunk carry audio placements. Their position, track, and source-link fields agree with the GarageBand arrangement preview and audio references; starts decode to 0, 16, 32, or 128 beats using the cross-format 34,560 origin and 960 PPQ.
- ARR-021 compared decoded starts per candidate track group with the generated preview: six occupied preview rows align with six event groups at bars 1, 1/5, 1/5, 1/33, 1, and 9 respectively. This supports per-row placement grouping in that fixture; because the preview has no numeric track labels, absolute `+0x14` track indexing remains a hypothesis.
- `AuRg` payload offset `+0x16` holds plausible little-endian sample-frame counts, and `+0x4A/+0x4C` frames a 16-bit name length plus the matching source filename stem. Two extended placement suffixes begin with values that match a same-source region's `+0x16` candidate; the reference meaning is not confirmed.
- ARR-023 repeated the extended-placement-suffix correlation in a second fixture: two of three extended suffix values matched a same-source `AuRg +0x16` candidate; both extended events in the first fixture also matched. IDA independently read all three second-fixture events byte-for-byte at the parser offsets. The suffix still does not identify a region universally and is not used as duration.
- ARR-024 measured grid-aligned ends for five clips in the cached preview: four are 16 beats and one is 128 beats. None of their associated `AuRg +0x16` candidates equals the corresponding un-stretched 44.1 kHz frame duration at the project tempo. This is visual evidence for those clip lengths, not a decoding of a binary duration field; parser durations remain unknown.
- ARR-027 found that finite little-endian words at audio placement `+0x1c` lie on the candidate 960-tick grid in both supplied fixtures; IDA MCP matches Python at all five finite field locations. In the preview-linked fixture, one candidate matches a visible 128-beat clip, and another candidate plus a beat-32 start places a clip end beyond the preview edge, which disfavors an absolute-end interpretation. This makes `+0x1c` a duration HYPOTHESIS only: the sample is small, most events carry `0x3fffffff`, and the word is not used as `Region.duration_beats`.
- Twelve 80-byte `0x20` records occur in another `EvSq` chunk. No `0x90` note events were observed in that fixture. MIDI-003 later established a unique cluster-to-`MSeq` match for every recognized `0x20` placement in two projects.
- The candidate header value at offset 8 is reused by 32 sequential `TxSt` entries, including numeric values also seen on `AuFl` and `AuRg`. It is not a globally unique identifier across chunk families.
- Aligned `EvSq` records contain a group-zero 160 BPM candidate and a 4/4 candidate that match both summary plists; a distinct 120 BPM candidate exists in a nonzero group and remains unassigned.
- Seventeen short `EvSq` chunks are identical 16-byte `0xF1` payloads in the inspected project; six share candidate group values with the audio-file/region groups. Their purpose is UNKNOWN.
- The 59 `Trak` chunks form at least two payload-size families (33 empty and 26 with 58 bytes); track identity and order are not established by this count.
- 23 `AuCO` chunks in the inspected project match a Logic Pro channel-strip marker and fixed-offset record shape; their unique header values form 0–22. This is a cross-format layout observation, not a confirmed GarageBand track mapping.

## Additional private-fixture observations

- The private, audio-bearing fixture contains four 80-byte `0x90` note-shaped `EvSq` events. Each event group matches one `MSeq` chunk, and that same chunk is the unique target of one recognized `0x20` MIDI placement event. IDA and the Python parser read identical bytes for all 19 placement candidates and four note-shaped events (MIDI-006). This is HIGH CONFIDENCE for the shared-chunk relation in this fixture; note-field meanings, track mapping, and generality remain unresolved. The fixture, project title, audio, and note values are not included in the repository.
- EVT-005 found 129 opaque `0x91`–`0x9e` events grouped into 54 type/group pairs in the same payload; every pair shares exactly one candidate `MSeq` and one MIDI-placement candidate. The other supplied payload has 12 MIDI-placement candidates but neither these event families nor `0x90` note-shaped events. IDA and Python agree on all bytes in one representative event per type. This is evidence of event-cluster co-occurrence, not a decoder or a controlled causal link.
- MIDI-014 found 309-byte linked `MSeq` payloads for all 14 groups without observed `0x90`/`0x91`–`0x9e` events in one fixture and all 12 groups in the other. In the audio-bearing fixture, the five groups with `0x91`–`0x9e` events have payload sizes 307, 311, 315, or 317 bytes; one also contains the four `0x90` note candidates. IDA and Python agree on the 31 linked chunk-header size fields. This is a cross-fixture size correlation only; the payload length and contents remain uninterpreted.
- EVT-006 profiled all four grouped 80-byte `0x90` records in the audio-bearing fixture: 14 offsets vary across the records, including offsets previously borrowed from Logic's velocity, pitch, and duration layout. IDA and Python agree on every byte of all four records. This provides controlled-fixture target offsets only; the event meanings remain UNKNOWN.
- MIDI-013 compared all 68 MSeq payloads together and found the same exact 8-byte leading prefix across both fixtures. It contains five zero and three nonzero bytes, so it is not all-zero padding. Across the full logic-song streams, its 33 and 35 occurrences are all at MSeq payload starts; there are no matches in headers or other offsets. IDA and Python agree on each MSeq prefix range. This confirms a prefix specific to MSeq starts in these two streams, not its meaning or a Standard MIDI header.
- MIDI-015 translated Logic's record-relative MIDI-region fields through the observed 36-byte GarageBand chunk header. At the corresponding GarageBand payload offsets (`+0x54` and `+0xf8`), IDA and Python agree on all 62 reads; the candidate length field is zero in all 31 chunks, and the candidate start field does not match any nonzero placement tick. These Logic offsets are not supported as GarageBand fields.
- MIDI-007 rechecked the four note-event byte ranges in IDA and Python and compared their candidate positions with the unique linked placement. Under Logic-derived origins, an absolute interpretation would place them before the region; a region-relative interpretation places them inside it. This raises region-relative note timing to a fixture-specific HYPOTHESIS, not a GarageBand-confirmed field meaning.
- ARR-025 decoded sample rates for six embedded sources in the same private fixture: all were 44.1 kHz. Of eleven source-associated `AuRg +0x16` candidates, nine were smaller than the complete source frame count, two equaled it, and none exceeded it. This supports a possible region-frame-length role but does not establish beat duration, trim behavior, or loop/stretch handling.
- MIDI-008 tested a payload-relative `MSeq +0x11c` start candidate against linked placements in both supplied projects. The apparent 12/12 and 15/19 matches were all zero-to-zero comparisons; the two nonzero placement candidates in the second project did not equal that field. Python and IDA agreed on two inspected nonzero field locations. MIDI-015 separately tested the actual translated Logic record-relative candidate at payload `+0xf8`; it also failed to match nonzero placement positions. GarageBand semantics at these offsets remain UNKNOWN.
- MIDI-009 independently checked the byte at MIDI placement offset `+0x14` in both supplied projects with IDA MCP. Candidate values reach 14 in the seven-arrange-track fixture and 18 in the twelve-arrange-track fixture, so this byte cannot be a direct zero-based or one-based arrange-track index in either. The parser exposes it as `track_value_candidate`; its identifier/table semantics remain UNKNOWN.
- MIDI-010 found that every recognized MIDI placement's candidate group selects one `MSeq` and also one same-group zero-payload `Trak` chunk in both fixtures (19/19 and 12/12). IDA MCP verified every corresponding chunk header against Python. The parser exposes the candidate chunk indices; whether this co-grouped empty chunk identifies an arrange track is UNKNOWN.
- EVT-003 repeated the project-summary comparison in both supplied projects: each had one group-zero tempo candidate and one group-zero meter candidate, and both candidates agreed with both summary plists. The second fixture's logic-song payload was byte-identical to the payload loaded in IDA, where both event records were independently byte-checked. Group-zero value semantics are HIGH CONFIDENCE for these two fixtures; event completeness, other project variants, and position units remain unknown.
- TRK-004 repeated the `AuCO` marker/record-shape check across both supplied projects. One has 23 validated candidates against seven declared arrange tracks; the other has 27 against twelve. The candidate field at chunk-header offset `+0x0E` is unique and contiguous from zero in each. IDA MCP search and representative raw-header reads agreed with Python in both payloads. This falsifies a one-to-one candidate-to-arrange-track count mapping for these fixtures, but the projects are not controlled and do not identify the actual arrange-track subset.
- TRK-005 found that the little-endian 16-bit field at `Trak` chunk-header offset `+0x0E` equals `0xFFFF` for all 129 `Trak` chunks in the two inspected payloads, including both zero-byte and 58-byte payload families. IDA MCP and Python agree on representative empty and non-empty records from both payloads. At the same offset, the validated `AuCO` candidates use distinct contiguous strip-index candidates instead. This separates the observed `Trak` header pattern from the `AuCO` candidate field but does not identify the `Trak` field's semantics.
- TRK-006 retracts the initial observation that 58-byte `Trak` payloads share a uniform eight-byte prefix. A repeatable aggregate probe finds three such prefix variants among 26 records in one payload and 13 variants among 35 records in another; only the first two bytes are common within either file. IDA MCP and Python agree on both leading words for every distinct prefix sampled. Prefix semantics and whether the variants are distinct record types remain unknown.
- TRK-007 found an exact multiset match between candidate group values on all `MSeq` chunks and all zero-payload `Trak` chunks in both inspected payloads: 35 of each across 29 group values in one, and 33 of each across 27 values in the other. IDA MCP and Python agree on all 136 group-field reads. This confirms co-grouping, while leaving `Trak` identity and the group field's semantics unknown.
- TRK-008 checked the recognized MIDI placement group candidates against every validated `AuCO` candidate group in both payloads. None of 19 and 12 MIDI placement groups overlaps the 27 and 23 `AuCO` candidate groups, respectively. IDA MCP and Python agree on all 81 event/`AuCO` integer reads. This rules out a direct same-group join for these candidates but does not resolve the MIDI track byte or exclude another mapping.
- Exact one-note GarageBand differential fixtures are still required before treating the candidate pitch, velocity, onset, or duration fields as confirmed GarageBand semantics.

## High confidence

- The tempo and signature metadata keys represent project-level tempo and time signature.
- The arrange-track-count metadata is only a count and cannot reconstruct track identity or arrangement.
- Asset resource references do not prove that the media is placed in a song arrangement.
- The chunk framing is shared with a described Logic Pro container format, but that does not validate its chunk semantics for iOS GarageBand.
- Audio source-to-`AuRg` chunk links have HIGH CONFIDENCE in this fixture from both group-value agreement and exact filename-stem strings. The group field's general scope and the region placement/timing fields need controlled validation.
- MIDI `0x20` placement-to-`MSeq` group linkage has HIGH CONFIDENCE for two fixtures: the low-order cluster value at event `+0x20`, shifted left 16 bits, uniquely selects one `MSeq` chunk group for each recognized placement. Track-number and position-unit interpretations remain unconfirmed.
- MIDI-006 established a HIGH CONFIDENCE note-event-to-shared-`MSeq` candidate relation for four note-shaped events in the private audio-bearing fixture. All four link through a unique `MSeq` chunk to exactly one recognized `0x20` placement; this does not confirm note fields or arrangement timing.
- The nine audio placement positions, track numbers, and source links are HIGH CONFIDENCE for this fixture because they match the arrangement preview and audio-resource mappings. Region durations and generalization across project versions remain unverified.
- The two extended-event correlations are fixture-specific and do not yet decode region identity generally.
- Group-zero 160 BPM and 4/4 records match both summary plists. Raw positions and the meaning of nonzero-group tempo records are unresolved.
- The `AuCO` records likely represent a broader channel-strip collection based on the cross-format marker, padded-name record, and sequential strip values. TRK-004 falsifies a one-to-one count mapping against the seven- and twelve-track metadata values in two different projects; which records correspond to arrange tracks remains unknown.
- Applying the Logic Pro descriptor classifier to the `AuCO` candidates yields a mixture of channel kinds and more audio/instrument candidates than the arrange-track count. This classifier is not used to label GarageBand tracks.

## Hypotheses

- The duration summary may be in seconds. Its key and observed value suggest this, but controlled fixtures have not yet confirmed units or exact duration semantics.
- The large `NS.data` payload contains the serialized logic/song arrangement. Its reference path, chunk types, and exact chunk framing make it the primary candidate, but internal semantics have not yet been decoded.
- An independent Logic Pro 11.2.2 format write-up identifies `AuRg +0x16` as a region frame-count field in controlled Logic projects. This is a cross-format lead for GarageBand only: ARR-020 found that it does not consistently equal complete source-file frame counts, and ARR-024 found no match to preview-measured durations under an un-stretched playback assumption.
- The four linked GarageBand note-position candidates may be region-relative, consistent with controlled Logic Pro note-region behavior. Their timing origins and placement interpretation remain cross-format candidates requiring controlled GarageBand validation.
