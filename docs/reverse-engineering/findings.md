# Findings

## Confirmed for the inspected fixture

- The `.band` file is a ZIP package, and its member list can be inventoried without executing project contents.
- `projectData` is an XML plist containing an `NSKeyedArchiver` graph.
- The graph connects a document logic model to a song object with an `NS.data` payload.
- `Output/metadata.plist` has named summary fields for tempo, meter, duration, and arrange-track count.
- `Output/assetsmetadata.plist` is a binary plist with separate global fields and resource-reference lists. Its track-count field differs from the arrange-track-count field in the inspected fixture.
- IDA MCP's raw view of the supplied archive agreed with the ZIP local header and member name reported by Python.
- IDA Python found the byte sequence `23 47 C0 AB` at three offsets in the extracted logic-song NSData payload: once as root magic and twice inside the first chunk payload. The two interior occurrences have unknown meaning.
- A sampler-resource basename appears twice as ASCII in that payload, while listed audio-resource basenames were not found as literal ASCII strings.
- The logic-song payload parses to its exact end as a 24-byte root header followed by 413 length-delimited 36-byte chunk headers in this fixture.
- All six asset audio basenames match one `AuFl` payload each as UTF-16LE; candidate group values link those chunks to all nine `AuRg` chunks, matching the metadata root-region count.
- Aligned `EvSq` records contain a group-zero 160 BPM candidate and a 4/4 candidate that match both summary plists; a distinct 120 BPM candidate exists in a nonzero group and remains unassigned.

## High confidence

- The tempo and signature metadata keys represent project-level tempo and time signature.
- The arrange-track-count metadata is only a count and cannot reconstruct track identity or arrangement.
- Asset resource references do not prove that the media is placed in a song arrangement.
- The chunk framing is shared with a described Logic Pro container format, but that does not validate its chunk semantics for iOS GarageBand.
- `AuFl`/`AuRg` source-to-region grouping is high confidence in this one fixture; the group-field semantics and timing fields need controlled validation.
- Group-zero 160 BPM and 4/4 records match both summary plists. Raw positions and the meaning of nonzero-group tempo records are unresolved.

## Hypotheses

- The duration summary may be in seconds. Its key and observed value suggest this, but controlled fixtures have not yet confirmed units or exact duration semantics.
- The large `NS.data` payload contains the serialized logic/song arrangement. Its reference path, chunk types, and exact chunk framing make it the primary candidate, but internal semantics have not yet been decoded.
