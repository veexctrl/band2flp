Warning: truncated output (original token count: 51054)
Total output lines: 1621

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

## TRK-014 — compare selected-track UUID order with the cached arrangement preview

**Question:** Does the saved `previousCurrentTrackUUID` identify a `Trak` record whose serialized order directly matches its visible arrangement-row order?

**Fixture:** The audio-only fixture from TRK-009 and its local cached arrangement preview. The UUID, track labels, and image are not published; no audio samples were read.

**Method:** Resolve the saved UUID through the keyed archive, find the matching 58-byte `Trak +0x18` field, and compare its ordinal among all such `Trak` records with the visually highlighted track header in the cached arrangement preview. Verify the selected UUID field bytes independently in IDA and Python; report no identifier value.

**Observation:** The UUID matches one `Trak +0x18` field at logic-song offset 210,618, chunk index 294. It is the eighth of 26 58-byte `Trak` records in serialized order; IDA and Python agree on the 16 field bytes. The cached preview shows six visible rows, with a distinct highlighted header background on row 2.

**Result:** The saved UUID and visible highlighted row cannot be equated by direct `Trak` ordinal in this fixture. The archive key is specifically `previousCurrentTrackUUID`, and the cached preview may not represent the same selection state. This does not establish which track UUID belongs to row 2, or whether `Trak` order maps to arrangement order at all.

**Confidence:** CONFIRMED for the UUID-to-field match, its serialized ordinal, the IDA/Python byte agreement, and the visible row-background difference; UNKNOWN whether the background encodes selection and whether the archive field and preview share a save state.

**Alternative considered:** The preview highlight may be focus/scroll styling rather than track selection, or the stored UUID may be stale by design. Either would break the proposed selection-to-row join without disproving that `Trak +0x18` is a track-related identifier.

**Next:** Compare multiple saves of one project after selecting different tracks, and verify whether the highlighted row moves with `previousCurrentTrackUUID` while UUIDs remain attached to the same `Trak` records.

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

**Obser…43054 tokens truncated…d. Save/reparse validation now checks MIDI playlist rows as well as existing clip/note/channel fields. The CLI requires MIDI export to be enabled when grouping is requested.

**Validation:** The audio-free local CLI output retains all five project-derived patterns on four rows/channels, with no fallbacks. Static event inspection finds no nonempty sample path. A synthetic full exporter test groups two patterns on one channel/row and preserves an unbound third region separately. Tests also cover ordinal row gaps, later-bound row reservations, default separate behavior, malformed bindings, source conflicts, bounds and CLI propagation. All 161 tests pass with the local optional PyFLP/template integration enabled. Existing dependencies were reused; no package was installed. No song audio is extracted or decoded, and no source MIDI or generated FLP is committed.

**Confidence:** CONFIRMED for static round-trip consistency and synthetic policy behavior. Original GarageBand track identity and timing remain HYPOTHESIS. GUI acceptance and audible playback of the grouped output remain unverified; the user cannot perform GUI checks today.

**Next:** Compare the grouped output in FL Studio when interactive validation becomes available. Continue static research on region extents, fine timing and unclassified placement-shaped records meanwhile.

The same-input separate/grouped policy comparison preserves all 133 note positions, lengths, pitches, velocities and flags, plus all five clip starts and extents. Only grouping/channel routing changes: five rows/channels become four.


## MIDI-024 - correct shifted bounds and compare source/placed extents

See [the detailed experiment](midi-source-extent-relations.md). MIDI-022's shifted comparison mixed placed positions with an origin-zero end; the consistent placed-frame comparison contains all five note-bearing groups. Two finite placement words are three halves of their source-word candidates, and one adjacent same-reference start gap equals the preceding source word rather than its last note end. IDA confirms 286 relevant words. A byte-matched cached image is too cropped to establish complete extents or repeats. These are source/placement-extent leads; loops, stretch, units and duration semantics remain unresolved. No export timing rule changes.


## MIDI-025 - preserve distinct source and placement extent candidates in the IR

**Question:** Can MIDI-024's extent leads be represented without choosing repeat/stretch behavior or silently replacing note-bounded preview lengths?

**Implementation:** Expose MIDI placement +0x1c and its source offset. Join MSeq tail fields into each note-bearing neutral region. Separate optional exact source-duration and placement-extent strings carry HYPOTHESIS confidence, raw source/shift/placement words, offsets and consistency diagnostics. Source normalization requires positive length, integer-note containment and shift/start agreement. Zero/special placement words remain raw. Other positive u32 words are scalar candidates, not instructions to expand notes.

**Validation:** Synthetic tests cover exact fractional beats, special/zero words, missing metadata, bound/shift failures, invalid PPQ, maximum-width scalar input and full archive-to-neutral JSON provenance. The note-bearing archive retains five source-duration candidates, two placement-extent candidates and all 133 original note candidates. No actual duration is assigned and no repeat/stretch edit is applied. Supporting raw-word validation is recorded in MIDI-024. Text inspection reports candidate counts without printing raw extent words. All 172 tests pass with local optional FLP integration enabled; no package is installed.

**Confidence:** CONFIRMED for field retention, bounds/shift checks and JSON serialization. Source/placement meanings, PPQ, original duration and editing behavior remain HYPOTHESIS/UNKNOWN. The exporter still uses note bounds.

**Next:** Develop an explicitly labeled extent preview only after defining how it should represent unknown longer extents without choosing unverified repeats or stretch. Seek a controlled region-length/loop edit or independent full timeline view for semantic validation.

## MIDI-026 - compare cached note starts with timing hypotheses

**Question:** Does GarageBand's cached arrangement preview independently constrain the candidate MIDI tick scale?

**Method:** Calibrate pixels per beat from two ruler ticks, detect note glyph starts in two visible track rows, and compare them one-to-one with integer-onset projections at 480, 960 and 1,920 ticks per beat. Test single-pass, 3:2 stretch and repeated-source hypotheses, clipped to candidate placement extent and viewport. For duration, compare only matched bars above the six-pixel display minimum and away from crop edges. The image, labels and per-note values remain local.

**Observation:** At 960 ticks per beat, the single-pass projection matches all 19 visible starts in one row and all seven in the other within six pixels; mean residuals are 1.912 and 2.693 pixels. At 480 ticks, four and two starts match. At 1,920 ticks, two and two match for single pass; repeating at 1,920 matches 11 and four, with extra predictions. A 3:2 stretch at 960 matches three and one. At 960, single-pass and repeat are identical in the crop because the viewport ends before the candidate 64-beat source boundary.

Five interior bars above the minimum display width in the second row agree with the 960-tick duration projection to a mean absolute width error of 2.579 pixels (maximum 4.434). No first-row bars qualify after the crop/minimum-width filters. This adds limited duration support; it does not resolve the repeat interpretation.

Every start-matched note within each visible row has the same raw fractional-word value, so there is no within-row variation to fit a fractional scale independently of the row offset. The tested Q16 tick conversion changes mean absolute residuals by 0.000 and 0.003 pixels in the two rows, beneath raster precision; a larger tested fraction scale worsens the fit. Fractional timing remains unknown.

**IDA validation:** After discovering that `source_event_index` is a variable-length logical record ordinal rather than a fixed-width slot, byte reads at the parser's actual event offsets match all 75 note records in the two displayed rows. The headless IDA database is raw data and has no functions.

**Confidence:** HIGH CONFIDENCE for the combined 960-tick/integer-onset hypothesis on visible rows of this fixture. Not universal: preview freshness, manual ruler calibration, integer origin and the uncontrolled fixture limit the result. Note durations, fractional scale, full region ends, and repeat/stretch semantics remain UNKNOWN or HYPOTHESIS. No exporter policy changes.

**Next:** Compare a controlled one-beat note move or obtain an un-cropped current preview before promoting the timing inference beyond fixture-specific evidence. See [MIDI-026](midi-preview-timing.md) for the method, residuals, script, and limits.

## MIDI-027 - compare candidate pitch byte with vertical preview position

**Question:** Does the note candidate byte at event `+0x0c` predict vertical note positions in the cached GarageBand arrangement preview, independently of velocity?

**Method:** First associate visible note glyphs with candidate notes by horizontal start using the MIDI-026 scale. Regress each row's glyph vertical center against candidate `+0x0c`, velocity, and fine-velocity values. Use a separate line per row to allow different vertical zoom settings, and report leave-one-candidate-value-out error to reduce in-sample fitting risk. No pitch value, pixel coordinate, screenshot, label, or audio is published.

**Observation:** In the first row, 19 horizontal matches spanning four `+0x0c` values yield R² 0.99991 and leave-one-value-out mean absolute error 0.8004 pixels. The second row has seven matches and five values, R² 0.99986 and error 0.3432 pixels. Velocity and fine velocity each have R² below 0.008 in both rows. The independent row slopes differ, indicating different vertical zoom; there is no common pixel-to-pitch conversion.

**IDA validation:** IDA reads at the parsed variable-length event offsets match all 75 candidate note records byte-for-byte; the `+0x0c` byte is present in every checked record.

**Confidence:** HIGH CONFIDENCE that `+0x0c` orders visible notes by vertical pitch in these two rows of this fixture. UNKNOWN for its absolute MIDI key convention, semitone spacing, generality across event types, and exact GarageBand semantics. The screenshot may be stale and no controlled GarageBand pitch edit is available; this visual correlation does not replace one.

**Next:** Change one note by a known semitone in a minimal GarageBand project and compare its corresponding event byte and preview position, then repeat at a second pitch.

## ARR-038 - compare complete audio-region and placement records in IDA

**Question:** Do every Python-reported `AuRg` and recognized audio-placement byte range in the metadata-only fixture correspond to the same bytes at the same addresses in its raw logic-song component?

**Fixture and method:** Use the private metadata-only `.band` fixture and its extracted raw logic-song data. The archive payload and saved IDA input were independently hash-matched locally. Open the raw component in headless IDA and read all nine complete `AuRg` payloads and all nine recognized type-`0x24` placement records at Python-reported offsets. Compare bytes in memory; do not decode or emit audio data, record contents, names, or field values.

**Observation:** All 9 of 9 `AuRg` payload reads and all 9 of 9 placement-record reads are byte-identical to Python's ranges. IDA reports one raw data segment and no functions, so disassembly is not applicable to this component.

**Result:** The parser's chunk and record offsets are directly corroborated for every recognized audio region and placement in this fixture. This is byte-extraction validation only. It does not establish the semantics of `AuRg +0x16`, placement `+0x1c`, suffix fields, source offsets, trims, or duration.

**Confidence:** CONFIRMED for the complete-range equality and candidate counts in this fixture; UNKNOWN for audio-region boundary semantics.

**Next:** Seek controlled same-source region-length and trim changes; the current archive has no embedded audio source members for this fixture, so source-frame comparisons are not possible here.

## ARR-039 - validate audio-region extraction in the audio-bearing fixture

**Question:** Do Python-reported `AuRg` payloads and recognized audio-placement records match the same byte ranges in IDA's raw view of the audio-bearing fixture's logic-song component?

**Fixture and method:** Use the private audio-bearing project and its extracted logic-song component. Enumerate every `AuRg` chunk payload and every event matching the parser's existing type-`0x24` placement candidate filter. Read each complete range through IDA MCP and compare it in memory with the parser's source bytes. Do not decode audio or emit record contents, names, or field values.

**Observation:** IDA and Python agree byte-for-byte for all 11 `AuRg` payloads and all 10 recognized placement records. IDA reports a raw data segment with no functions; byte comparison is appropriate here, not disassembly.

**Result:** The parser's offsets and complete-range boundaries are corroborated for every candidate in this fixture. This validates extraction only; it does not identify the meaning of any `AuRg` or placement field.

**Confidence:** CONFIRMED for candidate counts and byte-range equality in this fixture. UNKNOWN for region/source identity, timing, trimming, looping, and field semantics.

**Next:** Use controlled GarageBand edits that change only one audio-region property to test candidate fields against the resulting source-frame and timeline differences.

## MIDI-028 - preserve placements without recognized note events

**Question:** Does building neutral MIDI regions only from recognized note events omit placements that otherwise link to an `MSeq` chunk?

**Fixture and method:** Re-run the parser's placement, `MSeq`, and note-candidate linking stages on two private raw logic-song components loaded in IDA. Compare candidate counts and linkage cardinalities, without emitting payload bytes, names, note values, or audio. For each placement group without recognized note candidates, read the associated event range through IDA MCP and compare all bytes with Python.

**Observation:** One component has 19 recognized MIDI placements, each linked to exactly one `MSeq`; five placements have uniquely linked note candidates and 14 do not. The second has 12 placements, each linked to exactly one `MSeq`, but no events match the current note-candidate filter. Each of the 26 groups without note candidates contains exactly one 16-byte `0xF1` event; all 26 ranges match IDA byte-for-byte, and their payloads are identical. The `0xF1` role remains UNKNOWN. Before the change, the neutral model contained five and zero MIDI-region candidates respectively.

**Change:** Retain every recognized placement as a neutral MIDI-region candidate. Regions with no uniquely linked recognized notes have `notes: []` and `note_content_status: no_recognized_note_candidates`; ambiguous `MSeq` links remain represented as candidate indices, with no source chunk invented. The FLP preview exporter skips these regions and reports their count rather than creating blank patterns.

**Result:** The neutral model now preserves all 31 placements across these two components. This repairs information loss at the parser/model boundary; it does not show that a region is actually empty or establish the meanings of any placement fields.

**Confidence:** CONFIRMED for the observed candidate counts, link cardinalities, `0xF1` range equality, and model retention in these components. UNKNOWN whether regions without recognized note candidates contain musical content in another structure, are empty, or are stale candidates; the repeated `0xF1` event does not resolve this.

**Next:** Add fixtures with known empty and populated MIDI regions, then change only one note property to validate note-event recognition and timing independently.

## MIDI-029 — test whether F1 events mark MIDI groups without note candidates

**Question:** Is the repeated `0xF1` event exclusive to placement groups that have no recognized note-event candidates?

**Fixtures and method:** Revisit the two private raw logic-song components used for MIDI-028. Compare `0xF1` event group candidates against the parser's current note-candidate filter (`0x90`–`0x9f` event types with the established marker byte). Report only group-count aggregates. Independently read one `0xF1` record from a note-candidate group through IDA MCP; do not publish group values or raw bytes.

**Observation:** In the component with note candidates, all five note-candidate groups also contain an `0xF1` event. IDA independently confirms the 16-byte event range for one such group. The second component has no note-candidate groups. The repeated event therefore occurs both alongside note candidates and in MIDI placement groups without them.

**Result:** `0xF1` presence does not distinguish empty MIDI regions from regions with note candidates. It remains an unknown event in a parallel serialized group sequence, not evidence that a placement is empty or populated.

**Confidence:** CONFIRMED for the group overlap under the current parser filter and the representative IDA byte read in these fixtures. UNKNOWN for event meaning and for whether note-candidate groups correspond to musically populated GarageBand regions.

**Next:** Compare a controlled empty MIDI region with a one-note region and track whether the `0xF1` event persists while only the note-event family changes.
