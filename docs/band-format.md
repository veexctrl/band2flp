# GarageBand package observations

## Package container

The supplied `.band` item is a ZIP archive. Standard ZIP central-directory metadata is sufficient to list members and decompress them; no project code is executed. In the inspected package, members included `projectData`, `Contents/PkgInfo`, XML plists, a binary plist, PNG cache/output images, and cache metadata. This observation describes the inspected package only; it does not establish a universal member list.

The local ZIP header for `projectData` was also read through IDA MCP from the loaded raw archive. Its signature and member name matched Python's `zipfile` inventory. The project data is compressed in the ZIP, so raw offsets in that archive do not directly address its decompressed plist or its nested data.

## `projectData` wrapper

The inspected `projectData` member is an XML property list using `NSKeyedArchiver`. Its archive graph contains top-level document keys for a logic model and an arrange model. The logic model points to a song object that contains an `NS.data` byte string. The parser retains `NS.data` as base64 in JSON alongside its length, SHA-256, and leading bytes; it does not interpret the byte string as events.

The arrange-model wrapper exposes editor and UI state in the inspected fixture. Its presence does not demonstrate that it contains arrangement regions. The opaque logic-song bytes are the next primary target for structure and timing analysis.

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
