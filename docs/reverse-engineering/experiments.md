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

## TRK-004 — falsify one-to-one `AuCO` arrange-track mapping

**Question:** Does each validated Logic-shaped `AuCO` candidate correspond to exactly one GarageBand arrange track?

**Fixtures:** Both locally supplied GarageBand projects. They contain different songs and are not a controlled pair. Project-specific names and media are omitted.

**Method:** Parsed each `DfLogicModelLogicSong` chunk stream and applied the TRK-002 marker, record-size, printable-name, and NUL-padding checks. Compared the candidate count with the `Output/metadata.plist` arrange-track count. Opened each extracted logic-song payload in IDA MCP; byte-pattern search found the same stored `AuCO` tag and marker. Direct IDA byte reads of representative candidate headers agreed with Python, including the little-endian field at header offset 14.

**Observation:** Fixture A has 23 validated candidates with unique contiguous field values 0–22 and 7 declared arrange tracks. Fixture B has 27 validated candidates with unique contiguous field values 0–26 and 12 declared arrange tracks. The same marker and fixed record shape occur in both. Representative header bytes read through IDA match the Python offsets and values.

**Result:** The one-record-per-arrange-track hypothesis is falsified for these fixtures: the candidate counts exceed the declared arrange-track counts in both. This does not establish whether the candidates represent mixer channels, auxiliary channels, or a mixture, nor whether arrange tracks are a subset. Because the projects differ in content, the count difference cannot identify how edits affect these records.

**Confidence:** CONFIRMED that the stated marker/record pattern occurs with those counts and that a direct one-to-one count mapping does not hold for these two fixtures. UNKNOWN which records, if any, map to arrange tracks.

**Alternative considered:** Metadata may count only arrange tracks while `AuCO` describes a broader set of channel strips. That would explain the excess records, but remains unverified without controlled track-count changes or authoritative track identifiers.

**Next:** Create otherwise matched projects with zero, one, and two added arrange tracks. Compare `AuCO` entries and candidate IDs, plus visible track names/types, against the changes.

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

**Fixture:** The supplied audio-free project. IDA Python and the independent parser both traversed `projectData` and decoded the nine recognized `0x24` placement records in `EvSq` chunk 298.

**Observation:** All nine records share the recognized 80-byte prefix. Interpreting `+0x18` as a little-endian unsigned 32-bit integer yields zero in all nine records. The same field is zero across the audio placements parsed from the second local project.

**Correction:** An earlier version of this entry recorded three nonzero values and six sentinel values. Re-parsing the same chunk in IDA and with the Python parser did not reproduce that histogram; those values are withdrawn as an extraction or offset error.

**Result:** Zero at `+0x18` does not reveal duration or end position. The raw word is exposed as `u32_at_0x18_candidate` with UNKNOWN semantics and is not used to set FLP clip length.

**Confidence:** CONFIRMED for nine zero-valued words in chunk 298, independently observed by IDA and the parser, and for zero values across the other current fixture's placements; UNKNOWN for field semantics.

**Alternative considered:** Zero may mean “unspecified,” or the field may be reserved for a different event variant. There is not yet a controlled fixture that changes duration while keeping the event variant fixed.

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

**Follow-up:** MIDI-006 links the four note-shaped events in this audio-bearing fixture to placed MIDI regions through shared `MSeq` chunks. Their track and individual field semantics remain unresolved.

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

**Result:** The ordinal comparison is inconclusive and is not evidence that `+0x14` is a direct `Trak` index. MIDI-009 additionally shows that the byte exceeds each fixture's declared arrange-track range. The parser exposes it as an uninterpreted `track_value_candidate` and does not use MIDI placements to create tracks.

**Confidence:** CONFIRMED for these aggregate counts and the absence of an established direct ordinal mapping; UNKNOWN for the field's GarageBand meaning.

**Alternative considered:** The value could identify an entry in a different object table or a scoped object; raw chunk order cannot distinguish these interpretations.

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

## ARR-021 — audio placement starts agree with preview rows

**Question:** Do the `0x24` event start and track candidates reproduce the visible audio arrangement row by row?

**Fixture:** The locally supplied project whose archive has no embedded audio payload. The comparison used its generated arrangement preview and parser output; neither the image nor the project is included here.

**Observation:** The preview shows six occupied audio rows. The parser found nine `0x24` placements across six distinct candidate track values, 2 through 7. In displayed row order, the visible region starts align with the corresponding event groups: row 1 at bar 1; rows 2 and 3 at bars 1 and 5; row 4 at bars 1 and 33; row 5 at bar 1; and row 6 at bar 9. With the summary meter of 4/4, these match the candidate starts 0, 16, 32, and 128 beats. The summary declares seven arrange tracks, while only six candidate track values have audio placements.

**Result:** The preview independently corroborates the decoded start positions and the grouping of placements into six occupied rows for this fixture. The correspondence supports using the event track byte to group these audio placements, but the preview does not expose numeric track indices, so it does not by itself confirm that the byte is a universal one-based arrange-track index. The unrepresented summary track could be empty, MIDI, hidden, or omitted from the preview.

**Confidence:** HIGH CONFIDENCE for preview agreement on the observed starts and row groupings in this fixture; HYPOTHESIS for the absolute track-number interpretation.

**Alternative considered:** A cached preview may be stale or may omit tracks. The matching row start pattern and project summary support the comparison, but a controlled track reorder/addition is still needed to resolve absolute indexing.

**Next:** Reorder or add one audio track in a controlled GarageBand project and compare the preview row order, `0x24 +0x14`, and declared track count.

## PROV-001 - GarageBand version and device provenance

**Question:** Which GarageBand version is represented by the supplied project archives, and do their package metadata establish the originating iPhone models?

**Fixtures:** Both locally supplied `.band` archives. Archive contents remain outside the repository.

**Method:** Inspected plist and `projectData` members in memory, emitting only version strings and aggregate counts. Compared the version with Apple's iOS/iPadOS GarageBand release notes published August 24, 2026.

**Observation:** Each archive contains one plist member with the literal version string `2.3.19`. Apple's release notes list 2.3.19 as the newest version as of September 26, 2026. Device product-type strings occur in package metadata, but their presence is mixed across internal records and does not independently identify the originating device. The user confirms that the initial audio-free and later audio-bearing projects came from different iPhone models. Exact model attribution is retained only in ignored local research notes under the repository privacy rules. Project titles and media are intentionally omitted.

**Result:** Record GarageBand 2.3.19 as archive-supported provenance and device models as user-reported fixture provenance. Device class is relevant to possible serialization differences, but the projects have different content and are not a controlled cross-device comparison. The later project's title and recorded audio remain private and are not included in this repository.

**Confidence:** HIGH CONFIDENCE for the version string present in both archives; USER-REPORTED for different-device fixture provenance; UNKNOWN for device-specific serialization effects.

**Source:** [Apple GarageBand for iOS and iPadOS release notes](https://support.apple.com/en-au/106346).

**Next:** Compare controlled projects with identical content created on the known devices, and identify authoritative creator metadata before drawing conclusions about device-dependent serialization.

## MIDI-006 - note-shaped events share linked `MSeq` chunks with placements

**Question:** Do the `0x90` note-shaped records in the audio-bearing fixture share their candidate `MSeq` records with MIDI placement events?

**Fixture:** The locally supplied audio-bearing project. Its project title, exact device model, audio, and note values are not included in this log. The project remains local.

**Method:** Compared each note candidate's event group with `MSeq` chunk groups, then compared those chunk indices with the unique `MSeq` targets of recognized `0x20` placements. Independently opened the decoded logic-song payload in IDA and read all candidate event records at the parser-reported offsets.

**Observation:** The parser found 19 recognized MIDI placement candidates, each uniquely linked to an `MSeq` chunk, and four `0x90` note-shaped events. Each note event's group matched one `MSeq` chunk, and that same chunk was targeted by exactly one placement candidate. IDA's bytes matched the Python parser's bytes exactly for all 23 candidate records. The private project contains audio payloads, but none were extracted for this experiment.

**Result:** The shared-`MSeq` relationship supports a note-event-to-placed-region candidate link in this fixture. The parser now exposes matching MIDI placement event indices in each note candidate's JSON. It still does not normalize note pitch, velocity, onset, duration, or track, and does not attach the candidates to the neutral model.

**Confidence:** HIGH CONFIDENCE for the shared-`MSeq` event relationship in this fixture and for byte agreement between IDA and the parser; HYPOTHESIS for note field semantics and generalization to other GarageBand projects.

**Alternative considered:** The shared group/chunk could be a broader container association rather than a direct note-to-region relationship. A controlled one-note project with the note added, moved, and removed independently would test that interpretation.

**Next:** Create controlled same-device fixtures that vary one note property at a time. Determine whether `0x90` fields track the GarageBand piano-roll values while preserving the `MSeq` and placement link.

## MIDI-007 - linked note positions are inconsistent with absolute timeline positions

**Question:** In the linked GarageBand MIDI candidate group, are note-position candidates more plausibly relative to their region than absolute song positions?

**Fixture:** The same locally supplied audio-bearing project as MIDI-006. Project name, audio, exact note values, and screenshots remain private and are not included here.

**Method:** Reparsed the project and matched note-shaped events to `MSeq` chunks and `0x20` placement candidates. Reopened the extracted logic-song payload in IDA and compared the four Python-reported 80-byte note-event ranges at their exact offsets. Consulted an independent Logic Pro 11.2.2 reverse-engineering write-up as a cross-format lead; it reports 32-byte `0x90` note records with note-position values relative to their MIDI region in controlled Logic projects. This is not treated as GarageBand evidence by itself.

**Observation:** All four note-shaped records matched IDA byte-for-byte. They share one uniquely matched `MSeq` chunk, and that chunk is linked to one `0x20` placement candidate. Under the Logic-derived candidate origins and PPQ, every note-position candidate falls before the linked placement if interpreted as an absolute song position. Treating the values as region-relative yields positions within the linked region. The GarageBand event records are 80 bytes, not the 32-byte Logic records described by the external spec.

**Result:** The parser now exposes `position_scope_candidate: region-relative` for a group only when it has one unique `MSeq`, one unique linked placement, and every note position would otherwise precede that placement. This is an evidence annotation, not a normalized MIDI onset; the GarageBand origins and the note/placement semantics still require controlled validation. Other groups remain `unknown`.

**Confidence:** HIGH CONFIDENCE in the byte agreement and unique shared-chunk/placement links in this fixture; HYPOTHESIS for region-relative position scope in this GarageBand group; UNKNOWN for pitch, velocity, duration, field layout beyond the candidate prefix, and generalization.

**Alternative considered:** The Logic-derived origin or GarageBand placement candidate may have a different meaning, or the `0x90` group may contain note-like data whose time fields are not ordinary MIDI onset. The unique linked region and the pre-region absolute positions favor the relative interpretation but do not settle it.

**Source lead:** [Logic Pro ProjectData note-region findings](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#85-midi-note-regions), based on controlled Logic Pro fixtures. Transfer to iOS GarageBand remains unconfirmed.

**Next:** Create a same-project GarageBand fixture with one MIDI region, record its displayed note positions, then move only the region. Check whether note-event positions stay unchanged while the placement moves, as the Logic model predicts.

## MIDI-008 - reject zero-only MSeq position matches

**Question:** Does the Logic-documented `MSeq +0x11c` start candidate match GarageBand's linked MIDI placement positions?

**Fixtures:** Both locally supplied projects. Project titles, media, and exact timing values are omitted from this log.

**Method:** Added `midi_region_timing_probe.py` to follow each recognized `0x20` placement to its uniquely linked `MSeq` chunk, then compare the little-endian 32-bit value at payload offset `+0x11c` with the placement position adjusted by the current `34,560`-tick origin candidate. Also counted zero-to-zero and nonzero equalities separately. Reopened the audio-bearing fixture's logic-song payload in IDA and read representative nonzero field candidates at parser-reported offsets.

**Observation:** Project 1 has 12 unique placement-to-`MSeq` links; all 12 proposed comparisons are zero-to-zero, and there are no nonzero placement tick candidates. Project 2 has 19 unique links; 15 comparisons are zero-to-zero, while the two nonzero placement tick candidates both differ from `MSeq +0x11c`. Both nonzero values occur somewhere in the wider aligned-word search window, but not at the proposed field offset. IDA bytes matched Python at the two inspected nonzero field offsets. No media was extracted.

**Result:** The apparent 12/12 and 15/19 exact matches are explained by the zero origin candidates and are not evidence that GarageBand stores placement starts at `MSeq +0x11c`. The cross-format Logic Pro field remains a lead only; the GarageBand field interpretation is UNKNOWN. The origin candidate and any wider-window coincidences also require controlled validation.

**Confidence:** HIGH CONFIDENCE in the aggregate comparisons and Python/IDA byte agreement for the two inspected nonzero offsets; UNKNOWN for GarageBand `MSeq +0x11c` semantics.

**Alternative considered:** The Logic-family record could retain a related start field in a different location or encoding, but the present observations do not identify it. Zero-valued fields and small/repeated integers can coincide without representing time.

**Source lead:** [Logic Pro ProjectData MIDI-region findings](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#85-midi-note-regions). This does not establish the iOS GarageBand layout.

**Next:** Use a controlled GarageBand fixture whose MIDI region begins after bar 1, move only that region, and compare linked `MSeq` payloads. Until then, do not use `+0x11c` as a GarageBand position field.

## MIDI-009 — placement `+0x14` is not a direct arrange-track number

**Question:** Can the byte at `+0x14` in recognized MIDI placement events safely be interpreted as a zero-based or one-based arrange-track index?

**Fixtures:** Both supplied projects, with seven and twelve declared arrange tracks respectively. The projects differ in content and are not a controlled pair; only aggregate candidate values are recorded.

**Method:** Compared `+0x14` from every recognized 80-byte MIDI placement with each project's arrange-track count. IDA MCP read all 19 candidate bytes in one payload and all 12 in the other; values matched Python's parser at the corresponding event offsets.

**Observation:** In the seven-track project, the 12 candidate events carry values spanning 1–14. In the twelve-track project, the 19 candidate events span 1–18. Both projects therefore contain values outside the valid range for either a zero-based or one-based direct arrange-track index. IDA and Python agree on every checked byte.

**Result:** Do not interpret `+0x14` as a direct arrange-track number or index. The parser now emits `track_value_candidate` and labels its semantics UNKNOWN. This does not rule out a track identifier, an index into another table, or a scoped value.

**Confidence:** CONFIRMED that the candidate values exceed both declared arrange-track ranges in these fixtures; UNKNOWN what the field identifies.

**Alternative considered:** The metadata count might omit some kinds of arrangement objects, but its key explicitly denotes arrange tracks and the out-of-range values occur in both projects. A distinct identifier/table interpretation remains plausible.

**Next:** Compare matched one-track/two-track software-instrument projects and move a single MIDI region between tracks. Identify the target through visible track identity or another stable cross-reference before adding MIDI placements to neutral tracks.

## MIDI-010 — MIDI placement groups also occur on empty `Trak` chunks

**Question:** Does the group value that uniquely links a MIDI placement to an `MSeq` chunk also occur on a `Trak` chunk?

**Fixtures:** Both supplied projects. Project-specific content is omitted.

**Method:** For every recognized MIDI placement, followed its `+0x20`-derived group candidate to the unique `MSeq` chunk, then searched `Trak` chunk headers for the same group candidate. Compared the event and chunk offsets in Python, then read every matching 36-byte `Trak` header through IDA MCP.

**Observation:** All 19 MIDI placements in one project and all 12 in the other link to exactly one `MSeq` and exactly one same-group `Trak` chunk. Each matched `Trak` payload has length zero. IDA verified the reversed `Trak` tag, matching little-endian group field, and zero payload-size field in all 31 headers.

**Result:** The parser now exposes `same_group_trak_chunk_indices_candidate` for inspection. This adds a structural cross-component association without treating the `Trak` chunk as an arrange-track record. Empty payloads cannot supply track names or other identity data, and group-value reuse elsewhere means the shared value is not a global object ID by itself.

**Confidence:** CONFIRMED for same-group co-occurrence with one zero-length `Trak` chunk per recognized MIDI placement in these two fixtures and IDA/Python header agreement; UNKNOWN for the semantic relationship to arrange tracks.

**Alternative considered:** A `Trak` chunk may be a group-scoped marker or a placeholder emitted alongside each `MSeq`, rather than the serialized arrange-track object. Its empty payload and overlap with MIDI-region group values leave both interpretations open.

**Next:** In a controlled track-move fixture, check whether this same-group `Trak` chunk changes with the MIDI region or remains associated with the same arrangement track. Locate any non-empty `Trak` records that share a stable track identifier before decoding fields.

## TRK-005 — distinguish the `Trak` header field at `+0x0E` from `AuCO` strip indices

**Question:** Does the 16-bit value at chunk-header offset `+0x0E` identify a `Trak` record or correspond to the sequential `AuCO` strip-index candidate?

**Fixtures:** The two locally inspected logic-song payloads, one with and one without recorded audio. Project names, track labels, media, and field values beyond this structural comparison remain private.

**Method:** Count little-endian 16-bit values at `+0x0E` across every `Trak` chunk, separated by payload size. In the same payloads, independently validate `AuCO` candidates by the observed marker and record layout, then compare their `+0x0E` values. Python read the fields from the raw files; IDA MCP `get_int` read the same field from representative empty and 58-byte `Trak` chunks in both files.

**Observation:** The audio-bearing payload has 70 `Trak` chunks (35 empty and 35 with 58-byte payloads); all 70 have `+0x0E = 0xFFFF`. The metadata-only payload has 59 `Trak` chunks (33 empty and 26 with 58-byte payloads); all 59 have the same value. IDA and Python agree on four representative headers. In these files the validated `AuCO` candidate values at the same header offset are instead unique, contiguous sequences of 27 and 23 values beginning at zero.

**Result:** The `Trak` header field at `+0x0E` is not the sequential `AuCO` strip-index candidate and cannot distinguish individual `Trak` records in these fixtures. The parser already preserves the complete opaque header bytes, so no semantic field is added. A sentinel or reserved-field interpretation is plausible but remains unproven.

**Confidence:** CONFIRMED for the repeated value and payload-size counts in these two files, including the IDA/Python spot checks; UNKNOWN for the field's meaning and generality.

**Alternative considered:** `0xFFFF` may be an unset reference, a constant flag, or a version-specific field value. Identical contents across a non-controlled pair cannot distinguish those possibilities.

**Next:** Compare controlled GarageBand saves after adding, deleting, renaming, and reordering a single track; check whether this field or either `Trak` payload family changes, while matching records through stable identifiers rather than chunk ordinal.

## TRK-006 — recheck the `Trak` payload-prefix hypothesis

**Question:** Do the non-empty 58-byte `Trak` payloads share one eight-byte prefix, as the initial TRK-001 note states?

**Fixtures:** Both available extracted logic-song payloads (one metadata-only and one audio-bearing). Original projects and all project-specific content remain local.

**Method:** Added `research/scripts/trak_probe.py` to count `Trak` payload sizes, the header `+0x0E` value, and prefix-shape statistics without emitting payload bytes or project names. Ran the same byte-level Python comparison over every 58-byte payload. For one record representing each distinct first-eight-byte variant, IDA MCP read both leading 32-bit words; these 32 integer reads were compared with Python.

**Observation:** The metadata-only payload has 26 58-byte records with three distinct first-eight-byte prefixes; the most frequent occurs 17 times. The audio-bearing payload has 35 such records with 13 prefix variants; the most frequent occurs 14 times. Within each file, the records share only their first two bytes. All 32 representative IDA/Python word comparisons agree.

**Result:** Withdraw the initial claim that all 58-byte `Trak` payloads share one eight-byte prefix. Payload size alone does not establish one record subtype, and the changing prefix bytes remain uninterpreted. The new probe reports counts only; raw payloads and labels are not included in its output.

**Confidence:** CONFIRMED for prefix counts in these two extracted payloads and the IDA/Python spot-checks; UNKNOWN whether these are multiple record variants, flags, or identifiers.

**Alternative considered:** The prefix variants may reflect separate `Trak` subtypes or small per-record fields rather than distinct layouts. Two unrelated projects cannot distinguish those interpretations.

**Next:** Repeat the probe on controlled track add/rename/reorder saves and correlate each changed payload with stable object identifiers before assigning a field meaning.

## TRK-007 — compare `MSeq` and empty-`Trak` group multiplicities

**Question:** Is the same-group empty `Trak` occurrence from MIDI-010 limited to the recognized MIDI placements, or does it repeat across the complete `MSeq` chunk inventory?

**Fixtures:** Both available extracted logic-song payloads, one metadata-only and one audio-bearing. Project names and project-specific group values are not published.

**Method:** Count candidate group values for every `MSeq` chunk and every zero-payload `Trak` chunk, then compare the group-value multisets rather than only unique sets. IDA MCP read the little-endian 32-bit candidate group field at header offset `+0x08` for all involved chunks in both files; each value was compared with Python.

**Observation:** The audio-bearing payload has 35 `MSeq` chunks and 35 empty `Trak` chunks across 29 distinct group values. The metadata-only payload has 33 of each across 27 distinct group values. In both files, the full group-value multisets match: each group's chunk multiplicity agrees between the two types, and there are no groups exclusive to either type. IDA and Python agree on all 136 header-field reads.

**Result:** The co-group pattern reported for recognized MIDI placements in MIDI-010 extends across the complete `MSeq` and empty-`Trak` inventories in these two payloads. This confirms a repeated chunk-family association, not that `Trak` means arrange track or that each pair represents a MIDI region. The new `trak_probe.py` reports this only as a candidate group-multiplicity match.

**Confidence:** CONFIRMED for the exact per-group multiplicities in these two payloads and the IDA/Python comparisons; UNKNOWN for why the serializer emits the paired group structure.

**Alternative considered:** The group value may scope a larger serialized object cluster, with empty `Trak` records acting as companions or placeholders rather than track definitions. Group-value reuse across chunk families prevents treating it as a globally unique object identifier.

**Next:** In a controlled project, add and remove one MIDI region while holding track count fixed, then move that region between tracks. Compare the `MSeq` and empty-`Trak` group multiplicities with visible regions and tracks before adding any track mapping.

## TRK-008 — test direct group joins from MIDI placements to `AuCO`

**Question:** Do the recognized MIDI placement groups that link to `MSeq` and empty `Trak` chunks also match validated `AuCO` candidate group values?

**Fixtures:** Both available extracted logic-song payloads, one metadata-only and one audio-bearing. Project-specific group values and labels are omitted.

**Method:** For every recognized `0x20` MIDI placement, read its cluster candidate at event offset `+0x20` and shift it left 16 bits, following the parser's existing candidate link to `MSeq`. Compare those candidate values with the chunk-header `+0x08` group values of validated `AuCO` candidates. IDA MCP read the event cluster and every relevant `AuCO` group field; the integer values were compared against Python before checking overlap.

**Observation:** The audio-bearing payload has 19 recognized MIDI placements and 27 validated `AuCO` candidates; the metadata-only payload has 12 placements and 23 candidates. None of the 31 MIDI placement group candidates equals an `AuCO` candidate group. All 81 IDA integer reads agree with Python.

**Result:** A direct shared-group join between the recognized MIDI placement/MSeq/empty-`Trak` cluster and the validated `AuCO` candidates is absent in both payloads. Do not use this group field to attach MIDI regions to `AuCO` records. This does not rule out another relationship through the MIDI placement's still-unknown `+0x14` byte or another identifier.

**Confidence:** CONFIRMED for the no-overlap result in these two payloads and the field-value cross-checks; UNKNOWN for the `+0x14` relationship and actual arrange-track identity.

**Alternative considered:** Group values may be reused within object families or scopes rather than serving as global IDs. A track relationship could also pass through a separate index or object table.

**Next:** Use matched projects with one MIDI region moved between known tracks. Test `+0x14` against visible track identities and any `AuCO` changes, without assuming either a group join or an ordinal mapping.

## ARR-023 - repeat placement suffix and source-region candidate comparison

**Question:** Does the extra data on longer `0x24` placement records consistently identify a same-source `AuRg` record?

**Fixtures:** Both locally supplied GarageBand projects. One has no embedded audio members; the other contains private recorded audio. No media was extracted or included in the comparison. The projects and their identifying details remain local.

**Method:** Used the Python parser to identify extended `0x24` placement records and compare each trailing 32-bit candidate with the `+0x16` frame-count candidate of same-source, filename-stem-matched `AuRg` records. Opened the second fixture's serialized logic-song payload in IDA and independently read the three extended event byte ranges at the parser-reported offsets.

**Observation:** The first fixture has two extended placement events and both suffix candidates equal one same-source `AuRg +0x16` candidate. The second fixture has three extended events; two suffix candidates match a same-source region candidate and one does not. IDA's bytes match Python's complete event bytes for all three second-fixture events.

**Result:** The numeric correlation repeats across the two fixtures but is not universal. It may be meaningful only for some region states or may be a coincidental value match; it does not establish a general region ordinal, region duration, trim, or source-offset encoding. The parser continues to preserve the suffix as unknown raw data.

**Confidence:** HIGH CONFIDENCE in the aggregate counts and byte-level IDA/Python agreement for the second fixture; HYPOTHESIS that the matched suffix values refer to region frame-count fields.

**Alternative considered:** A frame-count value can recur in multiple regions from one source, and equal values alone cannot prove object identity. The unmatched longer event also rules out treating this candidate as a universal placement-to-region link.

**Next:** Change only one region property in a controlled GarageBand project (first position, then trim/length) and compare the suffix and `AuRg` candidates before assigning semantics.

## ARR-024 - arrangement-preview boundaries constrain audio-duration hypotheses

**Question:** Can the cached arrangement preview corroborate audio-region lengths, and do the source-associated `AuRg +0x16` candidates directly represent those lengths?

**Fixture:** The local project used in ARR-021, with its generated arrangement-preview image. The image remains local and its track labels are omitted here.

**Method:** Read the four-bar ruler spacing and visible region edges from the preview, then compare those bar lengths with the parser's source-associated `AuRg +0x16` frame candidates. Used the summary meter (4/4), tempo (160 BPM), and sample rate (44.1 kHz) only to calculate what un-stretched PCM frame lengths would be for the visible durations.

**Observation:** In two rows, four adjacent clips span bar 1 to 5 and bar 5 to 9 (16 beats each). In another row, a clip spans bar 1 to 33 (128 beats), followed by another clip at bar 33. Other clips continue beyond the right edge of the image and have no visible end. At 160 BPM, the visible durations would correspond to 264,600 and 2,116,800 frames at 44.1 kHz if playback consumed source frames at the project tempo without looping or time stretching. None of the associated `AuRg +0x16` candidates equals those values.

**Result:** The preview supports concrete region-length observations for five clips in this fixture, but it does not reveal which serialized field stores those lengths. The frame-count candidate is not a direct match for visible beat duration under an un-stretched playback assumption; looping, time stretching, and cached source lengths remain alternatives. The parser continues to leave `duration_beats` unknown.

**Confidence:** HIGH CONFIDENCE for the visible grid-aligned boundaries in the preview; UNKNOWN for the serialized duration field and the behavior used to render those lengths.

**Alternative considered:** The generated preview may be stale or may draw looped/stretched audio whose source-frame count differs from its arrangement length. Its starts agree with ARR-021, but a controlled moved/trimmed project is still required to tie boundaries to binary fields.

**Next:** Save a simple single-source project, then change only region length while retaining its start and source. Compare preview edge, `AuRg` payload, and the full placement event.

## ARR-025 - compare candidate region frame counts and source sample rates

**Question:** Do same-source `AuRg +0x16` candidates fall within the complete source's frame range, and what sample rates were used for those comparisons?

**Fixture:** The locally supplied audio-bearing project. It and its audio remain private; no media was extracted, named, or included in this comparison.

**Method:** Extended `audio_frame_probe.py` to read WAVE, AIFF/AIFC extended-80, and CAF sample-rate metadata in memory. For every decoded source, compare same-source `AuRg +0x16` candidates with complete-source frame counts and aggregate whether each candidate is below, equal to, or above its source. The probe emits only aggregate counts and rate histograms.

**Observation:** Six embedded sources had decodable frame counts and sample rates; all six were 44.1 kHz. Eleven source-associated `AuRg +0x16` candidates were compared: nine were below the complete source frame count, two equaled it, and none were above. Two exact candidates belonged to one source.

**Result:** In this fixture, the candidates are numerically consistent with a per-source frame-count quantity that can be shorter than the full media. Combined with the independent Logic Pro layout lead, this supports (but does not prove) a GarageBand trimmed-region-frame-count hypothesis. It still does not map frame counts to arrangement beats or account for loop/stretch behavior.

**Confidence:** HIGH CONFIDENCE in the aggregate source-rate and comparison counts for this fixture; HYPOTHESIS that the candidate is GarageBand region frame length; UNKNOWN for how it relates to displayed region duration.

**Alternative considered:** `+0x16` could be another frame-based cache, edit quantity, or source-specific value. All sources sharing 44.1 kHz means this comparison does not test mixed-rate behavior.

**Next:** Use a controlled source at a known sample rate, record one region, then change only its trim and compare the candidate, source frame count, region display length, and project preview. Repeat with a second source rate if GarageBand permits it.

## EVT-004 - inventory event record families in both supplied projects

**Question:** Which event type/record-shape families are not covered by current candidate decoders, and what aggregate shapes should later controlled experiments target?

**Fixtures:** Both local GarageBand projects, summarized anonymously. No audio was extracted or decoded by this experiment.

**Method:** Run research/scripts/event_inventory.py over each parsed EvSq record list. Aggregate event type byte, record-size histogram, distinct candidate-group count, and zero-group count. The probe omits group values, raw records, and strings. The parser currently has candidate decoders for event types 0x20, 0x24, 0x30, 0x60, and 0x90. For each of the other 50 distinct type bytes in the audio-bearing payload, IDA MCP independently read the first byte at one representative parser-reported record offset; all 50 matched Python's event type. This spot-check validates representative type-byte offsets, not the remaining bytes or their meanings.

**Observation:** The audio-bearing payload has 347 parsed records across 55 distinct type bytes; 50 are outside the five event types with candidate decoders. Of those unclassified records, 129 use types 0x91-0x9e, with lengths 64 or 80 bytes. The payload also has unclassified families 0xd1-0xde (16/32/48 bytes), 0xe0-0xee (32/48 bytes), 0xb0 (16/32/48 bytes), 0xf1 (16 bytes), and 0x10, 0x11, 0x12, 0x32, and 0x70 (16/32/48 bytes). The metadata-only payload has 71 records across ten types; six (0x10, 0x11, 0x12, 0x32, 0x70, and 0xf1) are also outside the five candidate-decoded event types. Exact per-type counts and size histograms are reproducible with the aggregate probe.

**Result:** Unknown event families are retained by the parser and can be inventoried without publishing raw private-project data. Their differing prevalence across these unrelated projects is not evidence of semantics or project-version behavior. No MIDI-controller, automation, instrument, or track interpretation is assigned from event IDs or sizes alone.

**Confidence:** CONFIRMED for Python's record counts and lengths in these two payloads; HIGH CONFIDENCE for representative type-byte agreement with IDA for all 50 unclassified types in the audio-bearing payload; UNKNOWN for their semantics.

**Alternative considered:** These records may be instrument/plugin state, controller data, event-sequence delimiters, or other serialized content; each family could also contain more than one subtype. No controlled fixture currently distinguishes those explanations.

**Next:** Use a minimal controlled project and change one supported musical property at a time. Begin with one note and one instrument, then change pitch, velocity, onset, and duration separately; compare the event-family aggregate and corresponding MSeq group before decoding any currently unclassified event fields.

## MIDI-013 - profile MSeq payload framing and test a Standard MIDI hypothesis

**Question:** Are MSeq payloads Standard MIDI files, and do exploratory tail-relative words provide immediately stable field candidates?

**Fixtures:** Both supplied projects, inspected through their logic-song `projectData` payloads only. No audio members were opened or extracted.

**Method:** Added `research/scripts/mseq_probe.py` to report payload-size counts, common-prefix length, Standard MIDI `MThd` signature count, and aggregate profiles for two exploratory little-endian tail-relative word positions. The probe omits raw bytes, strings, paths, identifiers, and field values. The tail positions are research leads from a third-party Logic Pro parser and are not assumed to transfer to GarageBand.

**Source lead:** [loov/logicx MIDI decoder](https://github.com/loov/logicx/blob/main/midi.go); its interpretations describe Logic Pro and are not evidence of GarageBand semantics.

**Observation:** The two projects contain 33 and 35 MSeq payloads, respectively. Each project's payloads share exactly an 8-byte leading prefix before diverging; their sizes vary from 303 to 325 bytes and 297 to 325 bytes. None begins with `MThd`. The two exploratory trailing positions yielded multiple distinct values in both projects, without a controlled edit or independent link that would establish meaning.

**Result:** The payloads are not directly framed as Standard MIDI files. The inspected tail words remain UNKNOWN and must not be used as MIDI timing, duration, or naming fields. A privacy-safe aggregate probe and regression tests preserve these observations.

**Confidence:** CONFIRMED for counts, lengths, shared-prefix length, and lack of the `MThd` prefix in these two fixtures; UNKNOWN for the meaning of any internal MSeq field.

**Alternative considered:** A custom MIDI event serialization may live inside MSeq, while MIDI notes may instead be stored in associated event-sequence records. The absence of an SMF header does not distinguish these possibilities.

**Next:** Create a controlled one-note GarageBand project, then vary pitch, velocity, onset, and duration individually. Compare changes in MSeq payloads and their same-group event records before assigning any byte-field meanings.

## EVT-005 — identify opaque event families grouped with MIDI placements

**Question:** Do the opaque `0x91`–`0x9e` event families have a structural relationship to the recognized MIDI placement candidates?

**Fixtures:** Two supplied GarageBand projects, using their extracted logic-song payloads only. No audio payload was decoded or included in this experiment.

**Method:** Added `research/scripts/midi_event_family_probe.py` to aggregate record lengths and distinct candidate groups for event types `0x91`–`0x9e`, then compare those groups with the existing unique group-to-`MSeq` and MIDI-placement candidates. The report suppresses raw event bytes and all candidate group values. For one record of each type in the audio-bearing fixture, IDA MCP read the full parser-selected record range and Python compared the byte sequences. Separately counted recognized MIDI placement, `0x90` note-shaped, and `0x91`–`0x9e` records in both payloads.

**Observation:** The audio-bearing payload has 19 recognized MIDI placements, four `0x90` note-shaped records, and 129 records across 14 event types in the `0x91`–`0x9e` range. It has 2–5 distinct candidate groups per type and record lengths of 64 or 80 bytes (types `0x96`–`0x9e` are 64 bytes in this fixture). Every one of the 54 distinct type/group combinations has exactly one same-group `MSeq` and exactly one recognized MIDI-placement candidate, all within the 19 placement groups. Several event types share identical group-presence sets: `0x91`/`0x92`, `0x93`–`0x95`, `0x96`–`0x9a`, and `0x9b`–`0x9d`; `0x9e` has its own subset. The other payload has 12 recognized MIDI placements but no `0x90` or `0x91`–`0x9e` records. IDA's full bytes matched Python for all 14 representatives in the audio-bearing payload.

**Result:** In one payload, these opaque event families are structurally associated with a subset of MIDI-placement/MSeq clusters; the other payload has MIDI placements without these families or `0x90` note-shaped records. That co-occurrence is consistent with (but does not prove) the families being associated with serialized MIDI content. The projects are not controlled variants, so differences cannot be attributed to notes or any other single property. Group membership alone does not show whether the records are notes, controllers, instrument state, or other region-scoped data. No event fields are decoded or used by the converter.

**Confidence:** CONFIRMED for the per-type group counts and unique candidate links in this payload, and for exact IDA/Python byte agreement on the 14 representative records; HYPOTHESIS that these are MIDI-region-associated event families; UNKNOWN for their contents and semantics.

**Alternative considered:** A group may scope a larger serialized MIDI object cluster, with these records carrying region metadata or instrument state rather than musical events. Shared group-presence sets may reflect repeated serializer templates rather than matching semantic roles.

**Next:** In a controlled one-note project, change pitch, velocity, onset, and duration individually. Compare which of these event families change and whether changes follow the note, its `MSeq`, or its placement. Repeat with a second track before assigning meanings.
