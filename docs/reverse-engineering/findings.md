# Findings

## Confirmed for the inspected fixture

- The `.band` file is a ZIP package, and its member list can be inventoried without executing project contents.
- The supplied archive has nine members (3,795,565 bytes uncompressed): project data, two plists, package metadata, cache metadata, and three PNG images. No member is a nested archive or recognized audio media file; the six audio resources are references, not embedded audio in this saved package.
- `projectData` is an XML plist containing an `NSKeyedArchiver` graph.
- The graph connects a document logic model to a song object with an `NS.data` payload.
- The inspected `DfDocument arrange model` graph contains editor/UI settings and no track or region collection; this does not rule out arrangement data in other objects or the logic-song chunks.
- `Output/metadata.plist` has named summary fields for tempo, meter, duration, and arrange-track count.
- `Output/assetsmetadata.plist` is a binary plist with separate global fields and resource-reference lists. Its track-count field differs from the arrange-track-count field in the inspected fixture.
- IDA MCP's raw view of the supplied archive agreed with the ZIP local header and member name reported by Python.
- IDA Python found the byte sequence `23 47 C0 AB` at three offsets in the extracted logic-song NSData payload: once as root magic and twice inside the first chunk payload. The two interior occurrences have unknown meaning.
- A sampler-resource basename appears twice as ASCII in that payload, while listed audio-resource basenames were not found as literal ASCII strings.
- The logic-song payload parses to its exact end as a 24-byte root header followed by 413 length-delimited 36-byte chunk headers in this fixture.
- All six asset audio basenames match one `AuFl` payload each as UTF-16LE. Candidate values partition those six chunks with one or two same-value `AuRg` chunks each, totaling nine; this matches the metadata root-region count but does not independently prove the media-to-region relationship.
- The candidate header value at offset 8 is reused by 32 sequential `TxSt` entries, including numeric values also seen on `AuFl` and `AuRg`. It is not a globally unique identifier across chunk families.
- Aligned `EvSq` records contain a group-zero 160 BPM candidate and a 4/4 candidate that match both summary plists; a distinct 120 BPM candidate exists in a nonzero group and remains unassigned.
- Seventeen short `EvSq` chunks are identical 16-byte `0xF1` payloads in the inspected project; six share candidate group values with the audio-file/region groups. Their purpose is UNKNOWN.
- The 59 `Trak` chunks form at least two payload-size families (33 empty and 26 with 58 bytes); track identity and order are not established by this count.
- 23 `AuCO` chunks in the inspected project match a Logic Pro channel-strip marker and fixed-offset record shape; their unique header values form 0–22. This is a cross-format layout observation, not a confirmed GarageBand track mapping.

## High confidence

- The tempo and signature metadata keys represent project-level tempo and time signature.
- The arrange-track-count metadata is only a count and cannot reconstruct track identity or arrangement.
- Asset resource references do not prove that the media is placed in a song arrangement.
- The chunk framing is shared with a described Logic Pro container format, but that does not validate its chunk semantics for iOS GarageBand.
- Candidate `AuFl`/`AuRg` grouping is supported in this fixture by family-local shared values and the nine-region count, but remains an inference; the group-field scope and timing fields need controlled validation.
- Group-zero 160 BPM and 4/4 records match both summary plists. Raw positions and the meaning of nonzero-group tempo records are unresolved.
- The `AuCO` records likely represent channel strips based on the cross-format marker, padded-name record, and sequential strip values; their relationship to the seven arrange tracks is unknown.
- Applying the Logic Pro descriptor classifier to the `AuCO` candidates yields a mixture of channel kinds and more audio/instrument candidates than the arrange-track count. This classifier is not used to label GarageBand tracks.

## Hypotheses

- The duration summary may be in seconds. Its key and observed value suggest this, but controlled fixtures have not yet confirmed units or exact duration semantics.
- The large `NS.data` payload contains the serialized logic/song arrangement. Its reference path, chunk types, and exact chunk framing make it the primary candidate, but internal semantics have not yet been decoded.
