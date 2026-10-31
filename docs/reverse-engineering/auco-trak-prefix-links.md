# MIX-002: bounded AuCO/Trak word equality scan

Question: does a fixed word position in the channel-strip candidate family
provide a direct join to the previously observed `Trak +0x08` word?

Scan `AuCO` chunks with header variant bytes `07 00 0e 00`. At every byte
position in the 36-byte header and first 128 payload bytes, read an unsigned
32-bit little-endian candidate where four bytes fit. Compare against nonzero
`Trak +0x08` words separately in groups `0x00040000` and `0x00080000`.
Count repeated values separately; an equality is unique only when it occurs
once in each compared family. Variant selection does not prove strip roles.

Run `python -m research.scripts.auco_trak_word_probe logic-song.bin`.
The report gives counts and structural offsets without matching values,
labels, project identifiers or raw records.

## Results

The two local components contain 40 and 36 variant-selected `AuCO` chunks.
Neither component has a tested position joining a complete nonzero `Trak`
family. The largest distinct-word coverage occurs at payload-relative `-26`
(header `+0x0a`): three distinct matches in each component and each family.
That unaligned read overlaps the established group-field span `+0x08..+0x0b`
and the next header bytes. Treat it as a cross-field candidate, not an
independent object-ID field. Payload `+0x04` has one larger-family match in
each fixture; `+0x55` has one match in each family in the first fixture only.
These sparse equalities do not establish a track/channel-strip mapping.

Headless IDA independently read all 76 header/prefix ranges (up to 164 bytes
each). Every byte matches the Python-extracted components. This validates the
scan inputs and boundaries, not the semantic interpretation of any word.

CONFIRMED: the bounded comparisons and byte agreement for these components.
UNKNOWN: channel-strip identity, mixer fields, and whether real references
occur outside the scanned prefixes or use another representation. Coincidental
ordinal equality, overlapping serialized fields and scoped references remain
alternatives. No track or mixer mapping is added to the parser.

Synthetic tests cover unique matches, duplicate target words, zero exclusion,
separate family scope, short prefixes and rejection of truncated components.
This search tests direct four-byte equality only; it does not rule out another
width, transformed links, nested state or references deeper in the payload.
