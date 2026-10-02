# GarageBand package observations

## Package container

The supplied `.band` item is a ZIP archive. Standard ZIP central-directory metadata is sufficient to list members and decompress them; no project code is executed. In the inspected package, members included `projectData`, `Contents/PkgInfo`, XML plists, a binary plist, PNG cache/output images, and cache metadata. This observation describes the inspected package only; it does not establish a universal member list.

The local ZIP header for `projectData` was also read through IDA MCP from the loaded raw archive. Its signature and member name matched Python's `zipfile` inventory. The project data is compressed in the ZIP, so raw offsets in that archive do not directly address its decompressed plist or its nested data.

## `projectData` wrapper

The inspected `projectData` member is an XML property list using `NSKeyedArchiver`. Its archive graph contains top-level document keys for a logic model and an arrange model. The logic model points to a song object that contains an `NS.data` byte string. The parser retains `NS.data` as base64 in JSON alongside its length, SHA-256, and leading bytes; it does not interpret the byte string as events.

The arrange-model wrapper exposes editor and UI state in the inspected fixture. Its presence does not demonstrate that it contains arrangement regions. The opaque logic-song bytes are the next primary target for structure and timing analysis.

## Logic-song chunk stream

An independent parse of the inspected fixture's 239,274-byte `NS.data` value found the header magic `23 47 C0 AB`, followed by a 24-byte root header. Starting at offset 24, the data parses as consecutive 36-byte chunk headers plus payloads. The payload size is an unsigned 64-bit little-endian value at header offset 28. Advancing by `36 + payload_size` consumed the stream exactly: 413 chunks, ending at byte 239,274, with no truncated header or out-of-bounds length. The first chunk begins at offset 24, its reversed four-byte tag is `Song`, and its payload length is 13,916. Later observed tags include `MSeq`, `Trak`, and `EvSq`.

This layout agrees with the published description of Logic Pro's [ProjectData container](https://pkg.go.dev/github.com/loov/logicx#ParseProjectData). That parser targets `.logicx`, while this fixture is an iOS GarageBand keyed archive. The exact boundary consumption in this fixture independently confirms the outer chunk layout for this payload; it does not establish that Logic Pro chunk meanings or record decoders apply unchanged. The implementation here was written independently and uses the external description as corroboration, not as code.

The parser emits every observed tag, offset, payload size, and raw chunk-header bytes, while retaining the entire original NSData payload. It splits aligned `EvSq` atoms into event records and preserves their raw bytes. Track and region fields are not yet decoded.

## Audio payload presence

The supplied archive has nine members totaling 3,795,565 uncompressed bytes. They are `projectData`, package/plist metadata, cache metadata, and PNG images; none is a nested archive or recognized audio media file. The audio names and paths found in metadata and `AuFl` payloads therefore identify references available to the project, not audio payloads embedded in this `.band` file. Dragged-in GarageBand live loops may be resolved from a library outside the saved project package. This conclusion concerns the supplied archive only.

## CAF source beat tags

One embedded CAF in a separate private fixture carries a UUID chunk with NUL-delimited metadata keys for `beat count` and `time signature`. Its sample rate and valid-frame count support a source-tempo candidate. The parser preserves these tags on the media reference rather than treating them as region duration or a Live Loops cell flag. It also retains standard CAF `desc` and `pakt` metadata (format, packet, valid-frame, priming, and remainder fields); audio samples are not decoded. The measurements and limits are recorded without private source values in [AUD-002](reverse-engineering/caf-loop-metadata.md) and [AUD-003](reverse-engineering/experiments.md).

## Audio resource cross-links

In this fixture, the six `AudioFiles` entries in `assetsmetadata.plist` each have one literal basename match in a UTF-16LE string inside one of six `AuFl` chunk payloads. Each matched `AuFl` and one or two candidate-related `AuRg` chunks share the same unsigned 32-bit little-endian value at chunk-header offset 8. The six values and same-value `AuRg` counts are:

| Header value | `AuRg` chunks sharing it |
| --- | ---: |
| `0x00100000` | 1 |
| `0x00140000` | 2 |
| `0x00180000` | 2 |
| `0x001C0000` | 2 |
| `0x00200000` | 1 |
| `0x00280000` | 1 |

Together these counts account for all nine `AuRg` chunks, matching the output metadata's root-region count. Although the same candidate header values are used by a 32-entry `TxSt` sequence at `0x00000000` through `0x007C0000` in `0x00040000` increments (so offset 8 is not a globally unique ID), each of the nine same-value `AuRg` payloads also contains an exact NUL-delimited filename stem matching its `AudioFiles` basename after removing `.caf`. This independently supports the six-to-nine source/region-chunk links in this fixture (CROSS-003). The parser reports all same-value `AuRg` chunks and the subset with a filename-stem match in `MediaReference`.

## Audio placement events

Nine event records with marker `0x24` occur in `EvSq` chunk 298. Each begins with an 80-byte placement structure; two records have an additional 80-byte suffix that remains uninterpreted and is preserved. The observed structure has a little-endian 32-bit position at event offset `+0x04`, a track-number byte at `+0x14`, and a little-endian link value at `+0x2C`. All nine pass the repeated marker-byte pattern `+0x17=0x89`, `+0x27=0xBC`, `+0x37=0x8A`, `+0x47=0x89`.

The published [Logic Pro ProjectData specification](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#3-the-unifying-model) describes the same event marker and offsets, and uses 960 PPQ with a region position origin of 34,560. Applied as a hypothesis to this GarageBand fixture, subtracting 34,560 and dividing by 960 yields starts of 0, 16, 32, or 128 beats (bars 1, 5, 9, and 33 in the observed 4/4 project). These positions match the package's GarageBand arrangement preview. The track byte values are 2 through 7; the link values shifted left 16 bits match the corresponding audio-resource group candidates. This independently connects each placement to a source and supports the one-based track interpretation.

Do not transfer Logic's meaning for `+0x2c` directly: Logic Pro documents that offset as a link to an individual audio-region object, but in this GarageBand fixture the converted value is shared by multiple placements and multiple filename-matched `AuRg` chunks within a source group. It is a source-group candidate here, not a unique region ID (CROSS-007). The separate `+0x28` / `AuRg +0x8a` equality is only a partial region-instance candidate and remains unconfirmed across projects.

The cross-format specification places an audio-region frame count at `AuRg` payload offset `+0x16` and a 16-bit display-name length at `+0x4A`. The supplied GarageBand records have a readable label beginning at `+0x4C`, consistent with that name framing. Reading a little-endian 32-bit candidate at `+0x16` yields plausible sample-frame counts at the package's 44.1 kHz rate. This is retained as a source-frame-length candidate and is not converted into timeline beats: same-source regions can have nearly equal source frame counts while their arrangement start is controlled separately by `0x24` events. For the two 160-byte placement records, the first trailing 32-bit value exactly matches one same-source `AuRg` candidate at `+0x16` in each case. The parser exposes these two matching chunk indices as candidate object links; other placements remain linked only to the source group, and the field's specific relationship is not generalized.

Position, track, and source-link recovery are HIGH CONFIDENCE for this fixture. The external Logic specification targets Logic Pro 11.2.2, so it is corroboration rather than proof of universal GarageBand behavior. The parser exposes the placements as audio regions with exact beat-string starts and external source references. It does not yet decode arrangement duration, source offset, trim, loop, mute, or track names/settings. Unknown event suffix bytes remain in the raw project data and are also attached to their neutral regions; the candidate frame-count correlation is diagnostic only.

ARR-027 profiles another placement word, a little-endian 32-bit value at event offset `+0x1c`. Every finite nonzero value in the two inspected fixtures is divisible by the candidate 960 PPQ, and IDA MCP matches Python's bytes at all five finite offsets. One finite value matches a preview-measured 128-beat clip; another, added to its preview-matched beat-32 start, predicts an end beyond the preview edge. Both duration and absolute-end alternatives remain possible, and most placements use `0x3fffffff` at this offset, including visibly bounded 16-beat clips. The parser preserves the word as `u32_at_0x1c_candidate`, but never converts it to a duration. A controlled region-length edit is required before promoting the field.

## MIDI placement and region candidates

Two locally inspected projects contain 80-byte `0x20` `EvSq` records with marker bytes `89 88 8A 88` at event offsets `+0x17`, `+0x27`, `+0x37`, and `+0x47`. In both, the little-endian value at event `+0x20`, shifted left 16 bits, matches a chunk-header group value belonging to exactly one `MSeq` chunk for each recognized placement. This is HIGH CONFIDENCE for the cluster-to-`MSeq` relation in those fixtures and agrees with the [Logic Pro MIDI placement description](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#L630-L635).

The parser reports these as `midi_region_placement_candidates`, with the corresponding `MSeq` chunk index, raw event, position candidate, and uninterpreted `track_value_candidate`. In both inspected projects this byte exceeds the declared arrange-track range, so it is not treated as a direct track number or index (MIDI-009). Position origin and units remain hypotheses. The parser also does not use unvalidated `MSeq` offsets for region duration or attach note events to placements. Controlled GarageBand edits are still needed before these records populate the neutral track/region model or an FLP.

For every recognized MIDI placement in both inspected projects, the candidate group value that selects its unique `MSeq` chunk also occurs on exactly one zero-payload `Trak` chunk. IDA MCP verified the tag, group value, and empty payload for all 19 and 12 corresponding headers in the two payloads (MIDI-010). This is a reproducible same-group co-occurrence; it does not establish that the empty `Trak` chunk represents the arrange track, nor does it decode track identity.

## Event records and global timing candidates

All 33 `EvSq` payloads in the inspected fixture have lengths divisible by 16. Splitting atoms where byte 7 has its continuation bit clear yields 71 complete event records. The event summaries retain every record's bytes, chunk index, group value, type byte, and raw offset.

Two `0x60` tempo-like records were observed. Reading a 32-bit little-endian field at event offset 16 and dividing by 10,000 yields 160 BPM for group value `0x00000000` and 120 BPM for group value `0x00040000`. The group-zero value matches both output and asset summary tempo. The parser exposes the group-zero event as a HIGH CONFIDENCE global-tempo candidate and preserves the nonzero-group value separately because its scope is unknown.

A 48-byte `0x30` event in group zero decodes to 4/4 using an 8-bit numerator and a denominator power (2 means denominator 4). It matches both summary metadata sources. Its raw position is zero; the parser keeps that value and does not assign a beat/tick unit. The global tempo event's raw position is 38,400, also retained without a local unit assignment.

The event-family interpretation is corroborated by the published Logic ProjectData descriptions of [event atom boundaries](https://raw.githubusercontent.com/loov/logicx/main/event.go), [tempo fields](https://raw.githubusercontent.com/loov/logicx/main/tempo.go), and [time-signature fields](https://raw.githubusercontent.com/loov/logicx/main/signature.go). Those sources target Logic Pro. This fixture independently reproduces their chunk layout and summary values, but controlled GarageBand tempo/meter changes are still needed to establish position units, event-group scope, and tempo-map completeness.

## `Output/metadata.plist`

Observed key names include:

| Key | Current interpretation | Confidence |
| --- | --- | --- |
| `com_apple_garageband_metadata_songTempo` | Project tempo summary | HIGH CONFIDENCE |
| `com_apple_garageband_metadata_songSignatureNominator` | Time-signature numerator | HIGH CONFIDENCE |
| `com_apple_garageband_metadata_songSignatureDeNominator` | Time-signature denominator | HIGH CONFIDENCE |
| `com_apple_garageband_metadata_songDuration` | Numeric duration summary; unit unresolved | HYPOTHESIS |
| `com_apple_garageband_metadata_numberOfArrangeTracks` | Summary arrange-track count | HIGH CONFIDENCE |

These names and values are summary metadata. They do not provide track identities, region locations, or MIDI events. Duration units and summary consistency need additional fixture validation.

## Other observed components

The inspected package's `Output/assetsmetadata.plist` is a binary plist and includes audio-resource lists and global song fields. Its `NumberOfTracks` value differs from `numberOfArrangeTracks` in `Output/metadata.plist` for the inspected project. The count definitions are therefore kept separate; the parser reports the discrepancy and does not choose one as the number of decoded tracks. The resource lists are references to media/resources; they do not by themselves establish that an item is placed in the arrangement. PNG cache/output images and the duplicated extensionless CacheInfo plist appear to be generated/cache data. CROSS-006 confirmed that both 276-byte copies in one fixture are byte-identical to each other and to the IDA-loaded component; the second fixture also carries two identical but different copies. The only key observed in the loaded plist, `cachesValidationUUID`, did not match strings or UUID byte forms in `projectData`, summary, or asset plists. This supports a cache-validation role, while the UUID scope and authority remain unverified.

The `Song` payload itself contains repeated `23 47 C0 AB` byte markers in two inspected fixtures. Applying the outer 24-byte-root / 36-byte-chunk framing at those marker positions fails the payload-bounds check; no nested chunk stream is currently recognized. See BIN-003 in the [experiment log](reverse-engineering/experiments.md). The markers may use another encoding or serve another role, so the result does not mean the `Song` payload is unstructured.
