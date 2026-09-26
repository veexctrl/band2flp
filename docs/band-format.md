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

The parser now emits every observed tag, offset, payload size, and raw chunk-header bytes, while retaining the entire original NSData payload. It does not yet interpret chunk field offsets or decode tracks/regions/events.

## Audio resource cross-links

In this fixture, the six `AudioFiles` entries in `assetsmetadata.plist` each have one literal basename match in a UTF-16LE string inside one of six `AuFl` chunk payloads. Each matched `AuFl` and its associated `AuRg` chunks share the same unsigned 32-bit little-endian value at chunk-header offset 8. The six shared values and `AuRg` counts are:

| Header value | `AuRg` chunks sharing it |
| --- | ---: |
| `0x00100000` | 1 |
| `0x00140000` | 2 |
| `0x00180000` | 2 |
| `0x001C0000` | 2 |
| `0x00200000` | 1 |
| `0x00280000` | 1 |

Together these counts account for all nine `AuRg` chunks, matching the output metadata's root-region count. This is HIGH CONFIDENCE evidence that `AuFl` stores audio-file references and `AuRg` stores related audio-region data in this fixture. The parser records the literal name match and shared header value, but does not claim that this field's meaning is universal or decode region positions, source offsets, trim, or loop behavior.

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
