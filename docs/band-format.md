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

Together these counts account for all nine `AuRg` chunks, matching the output metadata's root-region count. Although the same candidate header values are used by a 32-entry `TxSt` sequence at `0x00000000` through `0x007C0000` in `0x00040000` increments (so offset 8 is not a globally unique ID), each of the nine same-value `AuRg` payloads also contains an exact NUL-delimited filename stem matching its `AudioFiles` basename after removing `.caf`. This independently supports the six-to-nine source/region-chunk links in this fixture (CROSS-003). The parser reports all same-value `AuRg` chunks and the subset with a filename-stem match in `MediaReference`. These are media-to-region-chunk links, not placed timeline regions: no track placement, start/duration, source offset, trim, or loop behavior is decoded.

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

The inspected package's `Output/assetsmetadata.plist` is a binary plist and includes audio-resource lists and global song fields. Its `NumberOfTracks` value differs from `numberOfArrangeTracks` in `Output/metadata.plist` for the inspected project. The count definitions are therefore kept separate; the parser reports the discrepancy and does not choose one as the number of decoded tracks. The resource lists are references to media/resources; they do not by themselves establish that an item is placed in the arrangement. PNGs and `_cacheInfo` files appear to be generated output/cache data in this fixture. Their role and authority need validation against controlled changes.
