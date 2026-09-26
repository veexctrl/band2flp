# Findings

## Confirmed for the inspected fixture

- The `.band` file is a ZIP package, and its member list can be inventoried without executing project contents.
- `projectData` is an XML plist containing an `NSKeyedArchiver` graph.
- The graph connects a document logic model to a song object with an `NS.data` payload.
- `Output/metadata.plist` has named summary fields for tempo, meter, duration, and arrange-track count.
- `Output/assetsmetadata.plist` is a binary plist with separate global fields and resource-reference lists. Its track-count field differs from the arrange-track-count field in the inspected fixture.
- IDA MCP's raw view of the supplied archive agreed with the ZIP local header and member name reported by Python.

## High confidence

- The tempo and signature metadata keys represent project-level tempo and time signature.
- The arrange-track-count metadata is only a count and cannot reconstruct track identity or arrangement.
- Asset resource references do not prove that the media is placed in a song arrangement.

## Hypotheses

- The duration summary may be in seconds. Its key and observed value suggest this, but controlled fixtures have not yet confirmed units or exact duration semantics.
- The large `NS.data` payload contains the serialized logic/song arrangement. The reference path and size make it the primary candidate, but internal semantics have not yet been decoded.
