# Audio source-window candidates

## ARR-030 — `AuRg` frame offset plus frame count

**Question:** Do the little-endian 32-bit words at `AuRg` payload `+0x06` and `+0x16` describe a window into source audio?

**Fixtures:** Two supplied `.band` archives. One contains embedded audio; the other has external audio references. Audio, source names, project identifiers, and field values remain private.

**Method:** For each `AudioFiles` reference, select only same-group `AuRg` chunks whose NUL-delimited filename stem matches the source. Read four bytes at each candidate offset. In the embedded fixture, independently count complete source frames from CAF metadata and test whether the word sum equals that count. In both fixtures, compare nonzero `+0x06` records against a same-source zero-`+0x06` record, when there is one unambiguous baseline. The aggregate probe reports counts only. IDA MCP independently read both words from the four embedded-source region records and the four relevant external-source region records; the integer values agreed with Python. The [independent Logic Pro ProjectData write-up](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md#8-audio-regions) identifies `AuRg +0x16` as a frame count in Logic, but does not establish GarageBand's `+0x06` meaning.

**Observation:** The embedded fixture has four filename-matched region records for one decoded source. Two have zero at `+0x06`, two have a nonzero value; all four sums equal the complete source frame count. The two nonzero records carry a shorter `+0x16` value by exactly the amount added at `+0x06`. In the audio-free fixture, nine filename-matched regions span six references. Two records have nonzero `+0x06`. Each has a same-source zero-field baseline: one word sum equals that baseline's `+0x16`, while the other is below it. Without the external source bytes, neither baseline can be independently checked against the complete audio length.

**Result:** A source-start frame offset at `+0x06` plus source-window frame count at `+0x16` is a useful interpretation in both fixtures. A lower sum can represent trimming at both ends, but other serialized interpretations remain possible. The parser preserves both numbers as metadata candidates and does not convert them into `Region.source_offset_beats`, `duration_beats`, or FL Studio clip lengths. Timeline length also depends on repeat and tempo-following behavior.

**Confidence:** CONFIRMED for the byte locations, little-endian readings, arithmetic relationships, and Python/IDA agreement. HIGH CONFIDENCE that `+0x06` and `+0x16` jointly describe a source-frame window in the embedded fixture. HYPOTHESIS that `+0x06` is the left trim/source start and `+0x16` is the playable window length across GarageBand projects; UNKNOWN how either maps to arrangement beats.

**Alternatives:** `+0x06` could be an edit offset in another origin, and `+0x16` could include codec padding or a cached extent. The audio-free fixture lacks source bytes, so its zero-field record need not equal a whole file. Same-source records may include pool and arrange variants rather than independent timeline clips.

**Next:** Save controlled fixtures that trim the left edge, right edge, and both edges independently while keeping the source and placement start fixed. Check that the two words change according to the predicted source-frame differences, then test a repeated/tempo-following loop and compare visible arrangement bounds.

