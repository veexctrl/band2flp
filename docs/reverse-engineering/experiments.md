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
