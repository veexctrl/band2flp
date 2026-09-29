# MSeq label candidates

## MIDI-011 — GarageBand length-framed strings in `MSeq`

**Question:** Does the Logic Pro track-name location at `MSeq +0x34` apply to the supplied iOS GarageBand projects, and where are readable sequence labels stored?

**Fixtures:** Both supplied archives. Project and label strings remain private; only aggregate counts and offsets are reported here.

**Method:** Parse all validated `MSeq` payloads. Test the Logic Pro `+0x34` two-byte length lead, then scan each payload for readable strings and nearby little-endian length words. Validate candidate bounds, UTF-8 decoding, and printable text. IDA MCP independently read representative length/string bytes in both projects and one empty candidate; its bytes matched Python. The [independent Logic Pro format write-up](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#7-track-names) describes a different track-name offset for Logic Pro, so its interpretation is not transferred without GarageBand evidence.

**Observation:** Every inspected `MSeq +0x34` length word is zero. At payload `+0x10`, a two-byte little-endian length frames a UTF-8 string beginning at `+0x12`. In the embedded-audio fixture, 34 of 35 records produce nonempty printable strings and one has zero length; in the audio-free fixture, all 33 records do. The embedded fixture has 12 distinct strings and the other has eight, with repeated strings across multiple `MSeq` chunks. None exactly matches an `AudioFiles` basename stem. The string counts are close to the declared arrange-track counts but do not establish a one-to-one track mapping.

**Result:** The parser preserves each `MSeq` length and decoded text as a candidate with chunk/group provenance. It does not assign `Track.name`, create MIDI regions, or treat these strings as instrument names. MIDI placement groups can be joined to the existing `MSeq` candidate links for later tests.

**Confidence:** CONFIRMED for the observed length framing, decoding, record counts, and Python/IDA byte agreement; HYPOTHESIS that the strings name sequences or tracks; UNKNOWN whether they correspond to arrange tracks, MIDI regions, presets, or UI labels.

**Alternatives:** The strings could be region labels duplicated across sequence records, cached instrument/preset labels, or track labels copied into multiple serialized objects. A controlled rename and region-copy experiment is needed to distinguish these roles.

**Next:** Save controlled variants changing only one track name, one MIDI region name, and one instrument preset name. Compare which `MSeq` strings change and whether each follows a stable chunk/group association or a placement.

