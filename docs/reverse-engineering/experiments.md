Warning: truncated output (original token count: 35031)
Total output lines: 1144

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

**Result:** The one-record-per-arrange-track hypothesis is falsified for these fixtures: the candidate counts exceed the declared arrange-track count…15031 tokens truncated…ng prefix before diverging; their sizes vary from 303 to 325 bytes and 297 to 325 bytes. Combining all 68 payloads still gives the same exact 8-byte common prefix, with no variation among those prefix bytes. That prefix contains five zero bytes and three nonzero bytes, so it is not all-zero padding. IDA and Python agree on all 68 separately selected prefix ranges. Across each complete logic-song stream, the exact prefix occurs 33 and 35 times, respectively, every occurrence at an MSeq payload start and none at any other offset, including chunk headers and payload interiors. None of the MSeq payloads begins with `MThd`. The two exploratory trailing positions yielded multiple distinct values in both projects, without a controlled edit or independent link that would establish meaning.

**Result:** The payloads are not directly framed as Standard MIDI files. Within these two logic-song streams, the shared prefix occurs only at MSeq payload starts, consistent with an MSeq-specific preamble or default data. Its contents and role are UNKNOWN; other package components were not searched in this experiment. It is not merely an eight-byte zero fill. The inspected tail words also remain UNKNOWN and must not be used as MIDI timing, duration, or naming fields. A privacy-safe aggregate probe and regression tests preserve these observations.

**Confidence:** CONFIRMED for counts, lengths, common 8-byte prefix across both fixtures, IDA/Python agreement on all 68 prefixes, and lack of the `MThd` prefix; UNKNOWN for the meaning of the prefix and all internal MSeq fields.

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

## MIDI-014 — compare placed MSeq sizes with event-family presence

**Question:** Do MSeq chunk payload sizes differ between MIDI-placement groups with and without note-shaped or opaque `0x91`–`0x9e` events?

**Fixtures:** The same two supplied GarageBand logic-song payloads used in EVT-005. No audio payloads were decoded or included.

**Method:** Extended `research/scripts/midi_event_family_probe.py` to aggregate MSeq chunk payload sizes for uniquely linked MIDI-placement groups, partitioned by presence of `0x90` note candidates and `0x91`–`0x9e` event families. IDA MCP read the 8-byte payload-size fields at header offset `+0x1C` for all 19 linked MSeq chunks in one fixture and all 12 in the other; Python compared the values byte-for-byte.

**Observation:** In the audio-bearing fixture, all 19 MIDI placements have unique MSeq links. Fourteen linked groups with neither event category have 309-byte MSeq payloads. Five groups have `0x91`–`0x9e` events: four opaque-family-only groups have payload sizes 311, 315, 317, and 317 bytes, and the group that also has the four `0x90` note candidates has a 307-byte payload. In the other fixture, all 12 placements have unique links; none has either event category, and all 12 linked MSeq payloads are 309 bytes. IDA and Python agree on all 31 size fields.

**Result:** In these fixtures, a 309-byte MSeq payload co-occurs with placed groups lacking the observed note-shaped and `0x91`–`0x9e` events, while the groups containing those event types have other sizes. This is a reproducible structural correlation, not evidence that payload length encodes note count, region duration, or any particular property. The projects are not controlled variants.

**Confidence:** CONFIRMED for linked payload sizes and event-presence counts in these two payloads, and IDA/Python agreement on the 31 size fields; HYPOTHESIS that the size variation reflects serialized MIDI content; UNKNOWN for the meaning of the bytes or length differences.

**Alternative considered:** MSeq size may reflect instrument/program state, serializer options, or another project difference unrelated to musical note content. The placement and event candidates themselves also retain cross-format semantic uncertainty.

**Next:** Create a project with one MIDI region, then add and remove one note without changing track, instrument, region placement, or duration. Compare the linked MSeq header size, full payload, and associated event families. Repeat by changing one note property at a time.

## EVT-006 — profile byte variation within grouped MIDI-like records

**Question:** Which byte offsets vary among repeated event records of the same type and size within one candidate group, and can this narrow future controlled MIDI experiments?

**Fixture:** The local audio-bearing logic-song payload. Audio data, project title, group values, and event bytes remain private.

**Method:** Added `research/scripts/midi_event_variation_probe.py` to group event records by type, size, and candidate group, then count offsets that vary among multiple records in each group. The output includes record/group counts and offsets only; it does not print values or identifiers. Ran the same parser-selected four 80-byte `0x90` records through IDA MCP at their exact logic-song offsets and compared all 80 bytes per record with Python.

**Observation:** The four `0x90` records form one repeated type/size/group bucket. Fourteen byte offsets vary within this bucket: offsets 3–5, 11, 26–29, 48–50, and 64–66. This includes offsets corresponding to Logic-derived velocity (`+0x0b`), pitch (`+0x0c`), and the lower half of the candidate duration word (`+0x1c`–`+0x1d`); other offsets vary as well. IDA and Python agree byte-for-byte on all four complete records. The unmodified metadata-only fixture has no `0x90` records.

**Result:** The profiler narrows offsets worth observing in controlled one-note variants, but within-record variation does not establish that a byte is pitch, velocity, timing, or duration. Some candidate fields are constant in this four-record set, and the event family could contain additional fields or subtypes. No parser field semantics or normalized MIDI notes were changed.

**Confidence:** CONFIRMED for the record counts, varying offsets, and IDA/Python byte agreement in this fixture; UNKNOWN for all GarageBand meanings of these offsets.

**Alternative considered:** The four records could differ in other event attributes, and any observed variation may be correlated with note data without being caused by pitch, velocity, or duration. Shared-group association does not prove the four records are otherwise equivalent.

**Next:** In a controlled one-note project, change pitch, velocity, onset, and duration separately. Compare these offsets and their surrounding bytes while holding instrument, region, and all other settings fixed.

## MIDI-015 — translate Logic region-field offsets across the chunk header

**Question:** Do Logic Pro's record-relative MIDI-region length (`+0x78`) and internal-start (`+0x11c`) candidates transfer to GarageBand `MSeq` payloads when the 36-byte chunk header is accounted for?

**Cross-format lead:** The [Logic Pro ProjectData MIDI-region notes](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#85-midi-note-regions) describe fields relative to a record. GarageBand's observed chunk header is 36 bytes, so these locations would be payload-relative `+0x54` and `+0xf8` if the same record layout applied. This offset translation is a hypothesis, not evidence that GarageBand `MSeq` chunks contain Logic MIDI-region records.

**Fixtures:** Both supplied GarageBand logic-song payloads. No audio payloads were decoded or included.

**Method:** Added `profile_record_relative_mseq_candidates` to `research/scripts/midi_region_timing_probe.py`. For every uniquely linked placement, compared payload `+0xf8` with the existing placement-tick candidate and profiled payload `+0x54` without assigning duration meaning. IDA MCP read the four-byte candidate fields at both offsets for all 19 and 12 linked `MSeq` chunks; Python compared every read.

**Observation:** All 31 reads at payload `+0x54` are zero. At payload `+0xf8`, the audio-bearing fixture has 15 zero fields among 19 linked chunks; the other fixture has 12 zero fields among 12. The first fixture has two nonzero placement-tick candidates, and neither matches its `+0xf8` field. Its 14 equalities are all zero-to-zero; the second fixture's 12 equalities are also all zero-to-zero. IDA and Python agree on all 62 field reads.

**Result:** The translated Logic candidates do not provide positive evidence for GarageBand region length or start fields at these locations. In particular, the audio-bearing fixture's note-bearing candidate group still has zero at payload `+0x54`; do not use it as a MIDI-region length. The corresponding GarageBand fields may be elsewhere, differently encoded, or absent from `MSeq`.

**Confidence:** CONFIRMED for the measured zero/nonzero/equality counts and exact IDA/Python agreement at the tested bytes; UNKNOWN for whether the Logic record layout transfers to GarageBand and for all `MSeq` timing semantics.

**Alternative considered:** The `MSeq` chunk may be a distinct GarageBand structure despite sharing a tag and broadly similar size with Logic MIDISeq records. A different offset, enclosing record, or external region object may carry length and start.

**Next:** A controlled one-note project with an independently moved and resized region is still required. Compare the full changed records rather than probing additional Logic-derived offsets in isolation.

## META-002 — compare song-duration summary with recovered audio extent candidates

**Question:** Does `com_apple_garageband_metadata_songDuration` equal the last recovered audio start, or the latest end estimated from finite audio-placement `+0x1c` candidates after converting candidate ticks to seconds?

**Fixtures:** The two supplied `.band` archives, summarized anonymously. No audio samples or source names were read for this comparison.

**Method:** For each project, use the parser's existing audio-placement start candidate and project tempo to estimate the final recovered audio start in seconds. Where `+0x1c` has a finite, nonzero value rather than the observed sentinel, also estimate a candidate end assuming the existing 960-tick-per-beat hypothesis. Compare these quantities with the numeric `songDuration` summary, allowing 1% relative difference and 0.05 seconds. This is a falsification check of simple equality only; neither the timing conversion nor completeness of recovered placements is assumed.

**Observation:** Both archives have a `songDuration` value and recovered audio placements. One has 10 placements with one finite duration candidate; the other has 9 placements with four. In neither archive does the summary match the last recovered start in seconds, a finite-candidate end in seconds, or that candidate end interpreted as milliseconds.

**Result:** The comparison does not support treating `songDuration` as a direct copy of the last recovered audio boundary under these candidate conversions. It does not establish another unit or refute a time-based interpretation: audio durations are incomplete, MIDI and unrecognized regions may extend farther, and the `+0x1c` timing conversion remains a hypothesis. The parser continues to preserve the summary without assigning a unit.

**Confidence:** CONFIRMED for the tested comparisons and aggregate placement counts in these two archives; UNKNOWN for the summary's unit and completeness semantics.

**Alternative considered:** The summary may include MIDI, count-in or tail time, project-level padding, or a different duration origin. Placement starts and finite `+0x1c` values may also use different units or represent properties other than timeline boundaries.

**Next:** Compare projects with known exported song durations and controlled audio-only, MIDI-only, and trailing-silence edits. Until then, keep `songDuration` as an uninterpreted numeric summary.

## MIDI-016 — compare `MSeq` label candidates with the cached arrangement image

**Question:** Do the length-framed strings in `MSeq` match labels visible on MIDI tracks in the project's own cached arrangement image?

**Fixture:** One supplied project with a local arrangement screenshot. Track labels and the screenshot are not included in the repository.

**Method:** Compare five manually observed visible track labels to the parser's `MSeq +0x12` string candidates without printing or saving the names. For each exact match, check whether the candidate belongs to one unique `MSeq` chunk, whether a recognized MIDI placement links to that chunk, and whether note-shaped events link to it. The screenshot shows MIDI note-pattern blocks on two of the five compared rows. The `MSeq` string framing and representative bytes were separately verified with IDA/Python in MIDI-011.

**Observation:** Three of the five visible labels exactly match candidate strings. Each matched string occurs on one `MSeq` chunk; each chunk is linked to one recognized MIDI placement and to note-shaped event candidates. Both rows with visible MIDI note-pattern blocks are among the exact matches.

**Result:** The co-occurrence provides fixture-specific evidence that these `MSeq` strings preserve labels associated with MIDI arrangement content, and it strengthens the hypothesis that some are displayed track or sequence names. It does not show whether the string is a track name, region name, or instrument/preset label; nor does it establish that every `MSeq` label has the same role. The parser continues to expose the text as a candidate and does not populate `Track.name` from it.

**Confidence:** CONFIRMED for the three exact string matches and their chunk/placement/note-candidate links in this fixture; HIGH CONFIDENCE that the two visible MIDI rows have corresponding `MSeq` label candidates; HYPOTHESIS for the general track-name interpretation.

**Alternative considered:** A MIDI track name may be duplicated as an instrument or sequence label. Screenshot state could also be stale relative to other project components. Exact co-occurrence alone cannot distinguish these roles.

**Next:** Compare multiple cached screenshots and controlled rename/copy variants. Check whether renaming only a track changes the same `MSeq` string while leaving instrument state and region placement unchanged.

## MIDI-017 — compare MIDI placement track-byte order with visible row order

**Question:** For MIDI rows whose displayed labels match `MSeq` labels, does the placement byte at `+0x14` preserve their visible vertical order?

**Fixture:** The same private cached arrangement image and logic-song payload used in MIDI-016. No track labels or byte values are published.

**Method:** Select the three visible rows whose labels exactly match unique `MSeq` candidates and whose chunks link to one MIDI placement each. In screenshot top-to-bottom order, compare each placement's `+0x14` candidate with the next row's candidate. Also compare the fixture-wide candidate values with its declared arrange-track count, as MIDI-009 requires.

**Observation:** The three matched rows' candidate byte values increase by exactly one at both adjacent row transitions. Across all 19 recognized MIDI placements in this fixture, four candidate values exceed the declared arrange-track count.

**Result:** The consecutive values support a fixture-specific hypothesis that `+0x14` preserves relative order for these three visible MIDI rows. Because it does not hold as a direct in-range arrange-track index for all recognized placements, and only three labeled rows are available, do not promote the byte to a track index or use it to place MIDI regions on FL playlist rows.

**Confidence:** CONFIRMED for the two adjacent-value comparisons and the fixture-wide out-of-range count; HYPOTHESIS for a relative track-order role; UNKNOWN for the field's global identity, base, and scope.

**Alternative considered:** Three consecutive values may be coincidental, or may index a MIDI-specific ordered list rather than all arrange tracks. Cached screenshot state may not fully reflect the serialized project.

**Next:** Check another project's cached arrangement image for at least three exact label/MSeq/placement matches, then compare after a controlled track reorder if such a fixture becomes available. Keep this byte uninterpreted in the neutral model meanwhile.

## EVT-007 — compare repeated `0xF1` event groups with `MSeq` and empty `Trak`

**Question:** Do the repeated 16-byte `0xF1` event records have the same group multiplicities as `MSeq` and zero-payload `Trak` chunks?

**Fixtures:** Both supplied project archives, inspected through event/chunk metadata in `projectData`. Audio samples, names, group values, and event bytes are omitted.

**Method:** Added `research/scripts/f1_group_probe.py` to compare anonymous group-value multisets for `0xF1` event records, `MSeq` chunks, and empty-payload `Trak` chunks. The probe obtains only the retained logic-song NSData payload from parsed project data, verifies each event's raw bytes at its reported payload offset, and scans that payload for every occurrence of the distinct `0xF1` record. It reports aggregate occurrence counts only. Cross-fixture raw-record equality is computed internally but only emitted as a boolean. Regression tests verify the relationships, offset validation, occurrence behavior, and that output omits raw bytes and group values. This probe used Python for the payload-wide scan; IDA MCP independently re-read all 68 parser-reported 16-byte `0xF1` ranges across both fixtures, and every range matched exactly.

**Observation:** One payload contains 35 `0xF1` records and the other 33; all are 16 bytes long. Within each payload, every `0xF1` record has identical bytes, and the exact record is the same across both payloads. The per-group multiplicities exactly match both `MSeq` chunks and empty-payload `Trak` chunks in each payload: 35 versus 35 across 29 groups, and 33 versus 33 across 27 groups. Five records in each payload use group zero.

The full-payload occurrence scan found exactly 35 and 33 instances of the distinct raw record respectively, with every occurrence starting at one of the parsed `0xF1` event offsets. This rules out an accidental match elsewhere in either logic-song payload, but does not reveal the record's purpose.

The ordered group-value sequence of `0xF1` event records also exactly matches the serialized `MSeq` chunk order and the empty-payload `Trak` chunk order in each fixture. The families therefore have the same count and per-ordinal group candidate across these two payloads. This is an ordinal structural relationship only; the shared groups do not identify the represented object.

**Result:** The repeated `0xF1` record family is structurally co-grouped with the complete `MSeq` and empty-`Trak` inventories in these two payloads. This strengthens the evidence that these three record families participate in a shared serialized grouping pattern, but does not identify the group field's scope, why the `0xF1` bytes are constant, or whether a group corresponds to a track, region, or another object. No MIDI or track semantics are assigned.

**Confidence:** CONFIRMED for the Python-parsed counts, byte identity, cross-fixture payload equality, full-payload occurrence scan, and per-group multiset matches in these two payloads; UNKNOWN for `0xF1` record meaning and the semantic role of group values.

**Alternative considered:** The group field may scope a container or serializer template rather than identify related musical objects. The identical `0xF1` payload could be a generic marker, but its function cannot be inferred from repetition alone.

**Next:** Seek controlled track-add, region-copy, or track-reorder fixtures and compare whether `0xF1` records are added, removed, or moved with a specific object. If additional IDA raw reads become available, verify representative and repeated group ranges there before raising confidence beyond Python.


## EVT-008 — compare F1, MSeq, and empty-Trak group order

**Question:** Does the F1-to-MSeq/empty-Trak group correspondence preserve serialized order, or only group multiplicities?

**Fixtures:** The same two supplied projects as EVT-007. The probe emits aggregate counts and equality booleans only; group values, media, names, and paths are omitted.

**Method:** Extended `research/scripts/f1_group_probe.py` to compare the ordered group-candidate sequence for parsed F1 event records with the chunk-order sequences for all `MSeq` chunks and zero-payload `Trak` chunks. The existing multiset comparisons remain separate so an ordering mismatch is distinguishable from a multiplicity mismatch. A synthetic regression test reverses the related group order while preserving multiplicities. IDA MCP also read the little-endian 32-bit group candidate at chunk-header `+0x08` for every F1 source `EvSq` chunk, `MSeq` chunk, and empty `Trak` chunk in both fixtures. All 204 fields (99 in the 33-record fixture and 105 in the 35-record fixture) matched the Python parser.

**Observation:** In both fixtures, the F1 event count equals the number of `MSeq` chunks and empty-payload `Trak` chunks (33 or 35). The F1 group sequence matches both chunk sequences exactly, including repeated groups and group zero. In both fixtures, each F1 record comes from a distinct `EvSq` chunk. Each matching sequence has three adjacent decreases, so the exact alignment is not explained by simple numeric sorting of group values.

**Result:** CONFIRMED ordinal group-candidate correspondence among these three record families in the two inspected payloads, independently checked at the group fields through IDA MCP. Because the aligned sequences are not numerically sorted, the result is not a trivial consequence of a shared sorted group list. It supports a parallel serialized inventory/order, but does not establish that each ordinal represents the same musical object or give the `F1` record, empty `Trak`, or group field a semantic name.

**Confidence:** CONFIRMED for exact sequence equality in both fixtures and IDA/Python agreement on the underlying F1 event bytes and group fields; HYPOTHESIS for an intentional ordinal/parallel-table relationship; UNKNOWN for object identity and event meaning.

**Alternative considered:** All three families may be emitted from a common serializer traversal or sorted by another shared key, without denoting the same object. Repeated groups mean ordinal equality alone is not a unique-object key.

**Next:** Compare a controlled track-add, MIDI-region-add, or reorder edit and check whether insertions/reordering remain synchronized across all three sequences. Until then, keep the ordinal relationship as a structural observation only.


## ARR-027 — audio placement `+0x1c` tick-grid and preview-length candidate

**Question:** Does the little-endian word at `0x24` placement offset `+0x1c` carry a region-length candidate?

**Fixtures:** Two supplied project archives, labeled A and B. Fixture A is the archive with the previously analyzed arrangement preview; fixture B is the audio-bearing archive. No audio bytes were opened for this test.

**Method:** Added `research/scripts/audio_placement_timing_probe.py` to count recognized placements, the `0x3fffffff` value, and finite nonzero `+0x1c` values divisible by the Logic-derived 960-PPQ candidate. The script omits project paths, event values, tracks, and source references. For the direct preview comparison, correlate the already preview-matched `+0x04` start and track grouping from ARR-021 with visible clip boundaries from ARR-024. Independently read the finite `+0x1c` words through IDA MCP at the parser-reported event offsets.

**Observation:** Fixture A has 9 placements: 5 carry `0x3fffffff`; all 4 finite nonzero words lie on the 960-tick grid. Fixture B has 10 placements: 9 carry `0x3fffffff`; its single finite nonzero word also lies on that grid. IDA bytes match Python at all four finite offsets in A and the finite offset in B. In the preview-linked row starting at beat zero and ending at beat 128, the finite candidate equals 128 beats at 960 ticks per beat. Another visible row starts at beat 32, has a finite candidate of 104 beats on the same grid, and continues beyond the preview's right edge; adding the candidate to the start places its possible end beyond the displayed 128-beat span. The candidate word remains at event-relative `+0x1c`; its byte order is little-endian and size four bytes.

**Result:** The observations make a tick-scaled duration a useful HYPOTHESIS for finite `+0x1c` values and a better fit than absolute end position for the beat-32 row. They do not prove that interpretation: the direct 128-beat match is one clip, the second relation depends on the preview extent, and most events carry `0x3fffffff`, including clips whose visible lengths are 16 beats. No value is transferred into `Region.duration_beats`.

**Confidence:** HIGH CONFIDENCE that the finite words in these two fixtures lie on the candidate 960-tick grid and that IDA agrees with the parser offsets. HYPOTHESIS that finite `+0x1c` words encode region duration; UNKNOWN what the sentinel means and how visible 16-beat clips with that sentinel derive their boundaries.

**Alternatives:** The field could be an end/extent in another origin, a loop or edit quantity, or a tick-valued property that happens to agree with one preview length. The sentinel might denote an unset value, a special loop mode, or a large valid extent. The cross-format [Logic Pro ProjectData specification](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#81-track-identity-for-multiple-tracks) describes the 0x24 event in terms of position, track, and region link, and marks nearby fields as constants. That Logic layout does not establish the GarageBand layout, but it cautions against transferring a Logic duration interpretation. The projects are not controlled variants.

**Next:** Create a single-source GarageBand fixture, hold source and start constant, and change only the region length twice. Compare `+0x1c`, all placement suffix bytes, related `AuRg` chunks, and the preview edges. Do not decode this word into the neutral duration field until the value follows both controlled edits.

## BIN-003 — nested logic-stream marker candidate

**Question:** Do `23 47 C0 AB` markers inside top-level `Song` payloads begin recursively framed chunk streams?

**Fixtures:** Two locally inspected logic-song payloads, independently reopened in IDA MCP.

**Method:** `research/scripts/nested_chunk_probe.py` tries the validated 24-byte root / 36-byte chunk framing at candidate markers on payload boundaries. It emits only counts and chunk type tags. IDA MCP reads at the start of each `Song` payload and at the second marker within it agree with Python's bytes.

**Observation:** Both fixtures contain two marker occurrences inside the `Song` payload. Treating either occurrence as a new complete chunk stream fails the existing framing bounds check; neither fixture yields a valid nested stream. The probe reports one malformed magic-start candidate per fixture because its recursive search reaches the `Song` payload start, while the deeper marker is not a child payload boundary recognized by the outer framing.

**Result:** The repeated magic alone is insufficient evidence for recursive chunk framing. No child semantics, song sections, or song-length structure are assigned. This falsifies the simple “every marker starts another copy of the top-level stream” hypothesis for these fixtures; other framing schemes remain possible.

**Confidence:** CONFIRMED for the candidate count and failed framing checks in these two payloads; UNKNOWN whether the marker has another structural role.

**Next:** Identify the `Song` payload's actual record boundaries from controlled project changes or a separately validated framing rule before interpreting its fields.


## EVT-009 — complete IDA check of MIDI-status-shaped event records

**Question:** Does IDA confirm the exact bytes of every event selected by the current `0x90`–`0x9e` MIDI-status-shaped candidate filter in the audio-bearing fixture?

**Fixture:** One locally inspected logic-song payload. No audio bytes or note values are reported.

**Method:** Selected event records whose first byte is in the `0x90`–`0x9e` range, whose record is at least 32 bytes, and whose byte at `+0x17` is `0x89`. Read every parser-reported event range through IDA MCP and compared the full bytes with Python. Reports retain only aggregate record counts by size.

**Observation:** The filter selects 133 records: 108 are 64 bytes and 25 are 80 bytes. IDA MCP and Python agree on all 133 complete byte ranges.

**Result:** Full-byte extraction and event-boundary offsets are independently validated for this selected family in this fixture. The result does not prove the records are all MIDI notes or confirm the Logic-derived pitch, velocity, onset, duration, or channel fields. Both sizes remain exposed as unconfirmed event candidates.

**Confidence:** CONFIRMED for record counts, sizes, and exact IDA/Python byte agreement; UNKNOWN for musical field semantics and generality across projects.

**Next:** Use controlled GarageBand one-note edits to separate actual note records from other members of the status-shaped family and validate each field before converting them to normalized notes.


## AUD-003 — retain CAF packet-table timing metadata

**Question:** Can the CAF source inspector preserve the codec frame accounting needed to distinguish valid audio duration from AAC packet padding?

**Evidence:** Apple's Core Audio Format Specification 1.0 defines `desc` fields for format ID, frames per packet, and channel count. Its `pakt` header contains packet count, valid frames, priming frames, and remainder frames; valid frames divided by sample rate gives file duration, while priming and remainder describe frames trimmed during decode.

**Method:** Extended the bounded CAF metadata reader to expose these `desc` and `pakt` fields alongside the existing UUID loop-metadata candidates. It skips the audio-data chunk without decoding or retaining its payload. A synthetic AAC fixture exercises a packet-table accounting identity, and IDA MCP reads of the `desc` and `pakt` headers from locally available CAF sources matched the Python byte reads.

**Observation:** The reader retains sample rate, format ID, frame count per packet, channel count, packet count, valid frame count, priming count, and remainder count. The synthetic fixture's packet-frame total equals valid frames plus priming and remainder. The parser keeps valid frames as the duration basis for its source-tempo candidate; it does not treat encoded packet frames as playable frames.

**Result:** CAF metadata can now explain the distinction between valid decoded duration and AAC packet overhead without inspecting audio samples. This improves source metadata fidelity but provides no evidence for GarageBand arrangement duration, region trimming, or Live Loops behavior.

**Confidence:** CONFIRMED for the CAF field layout and timing definitions from Apple's specification, the implementation's synthetic test, and IDA/Python header-byte agreement on the locally inspected files; UNKNOWN for how GarageBand maps CAF source metadata to arrangement regions.

**Next:** Keep source duration separate from region timing. Test arrangement trim/loop behavior with controlled GarageBand projects before using any CAF field to set FL Studio playlist lengths.

## ARR-033 — compare finite placement candidates with CAF frame windows

**Question:** Can the finite audio-placement word at `+0x1c` be cross-checked against candidate source windows in the same source's `AuRg` records using CAF loop timing metadata?

**Fixtures:** The two supplied projects, inspected locally. No audio samples were decoded, played, or included in the repository.

**Method:** Match audio placements to package media references, then compare finite `+0x1c` candidates with same-source `AuRg +0x16` frame candidates. Test both elapsed-frame conversion at project tempo and proportional scaling from CAF valid frames to the tagged beat count. Do not accept ambiguous placement-to-region links as unique matches.

**Observation:** The only finite placement candidate associated with a CAF source carrying beat metadata had an ambiguous source-region link. No candidate window could be uniquely attributed to that placement, and neither tested conversion produced a match.

**Result:** INCONCLUSIVE. This does not falsify a duration interpretation for `+0x1c`; the fixture does not provide an unambiguous region link, and the tested conversions may not model GarageBand's source tempo, trims, or looping.

**Confidence:** HIGH CONFIDENCE in this negative result for the inspected candidate set; UNKNOWN for the meaning of `+0x1c` and the `AuRg +0x16` values.

**Next:** Use a controlled same-source, same-start region-length or trim edit, then test whether the placement word or selected source-window candidate changes predictably.

## BIN-004 — repeated Song payload prefix and marker position

**Question:** Are the unexplained magic markers inside the `Song` payload positioned consistently across the two supplied projects, and does the payload begin with a stable prefix?

**Fixtures:** Two locally inspected logic-song payloads. The vocal project's audio was not read or decoded for this test.

**Method:** Parse the top-level chunk stream, locate its `Song` payload, compare the payload-relative marker positions and common prefix, then independently read the payload prefix and marker windows through IDA MCP and compare those bytes with Python.

**Observation:** Each payload begins with the marker and contains another occurrence at the same relative offset, 700 bytes into the `Song` payload. The first 33 payload bytes match across the two fixtures; the following byte differs. IDA MCP and Python agree byte-for-byte on the inspected prefix and marker windows in both fixtures.

**Result:** The repeated prefix and marker position suggest a stable internal layout candidate, but no field meanings are assigned. The markers still fail the validated top-level chunk framing checks; this does not establish a nested stream or identify song sections.

**Confidence:** CONFIRMED for the marker positions, shared prefix length, and IDA/Python byte agreement in these two fixtures; UNKNOWN for the marker's structural role and the prefix fields.

**Next:** Compare a controlled project with one song-section property changed, or find another independent boundary rule before interpreting the payload.

## AUD-004 — validate CAF unknown-size chunk placement

**Question:** Does the source metadata reader accept unknown-size chunk markers only in the CAF position where the format permits them?

**Evidence:** Apple's Core Audio Format Specification 1.0 allows `-1` as an unknown chunk size only for the Audio Data (`data`) chunk, and only when that chunk is last. Other chunk sizes must be valid; a sized Audio Data chunk may appear before later chunks.

**Method:** Review the reader's signed 64-bit chunk-size handling and add synthetic CAF cases for an unknown-size non-data chunk, a `data` chunk with an invalid negative size, and a final `data` chunk with size `-1`. No source audio is decoded or copied.

**Observation:** The reader previously stopped at every negative size, allowing malformed non-data chunks and values other than `-1` on the data chunk to be treated as an ordinary end of scan. The revised reader rejects those cases and accepts `-1` only on `data`; a final unknown-size data section ends scanning as specified.

**Result:** Metadata extraction now distinguishes the sole CAF unknown-size case from malformed negative lengths while retaining the supported sized-data-then-metadata layout.

**Confidence:** CONFIRMED against the CAF specification and synthetic regression cases; real-world generality is limited to the specified CAF v1 rule.

**Next:** Keep the CAF scanner bounded and validate malformed chunk lengths without decoding or retaining audio payloads.

