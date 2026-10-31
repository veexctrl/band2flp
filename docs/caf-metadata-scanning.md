# CAF metadata scan boundaries

The parser inspects CAF headers and recognized UUID metadata for source-level
loop tags. These tags do not establish arrangement looping or region length.

For an unencrypted `ZIP_STORED` package member, the parser permits seeking
over a sized CAF `data` chunk to inspect later metadata chunks. Python's
`ZipExtFile` uses a fast underlying seek for this case. Small adjacent buffers
may be prefetched during metadata reads; this is not a zero-audio-byte-read
guarantee. The complete sample payload is not intentionally read or decoded.

For compressed or encrypted members, the scan stops at the `data` chunk,
because seeking can read or decompress the complete intervening payload.
Metadata located after it therefore remains unavailable. A missing result
does not prove that the source lacks loop tags.

Synthetic package tests cover stored and deflated members with post-data
metadata. A tracked backing stream verifies that the stored-member scan reads
less than 64 KiB while skipping a 1 MiB synthetic payload. This validates the
available Python implementation; portability to a different ZIP reader must
preserve the fast-seek behavior or disable this opt-in.
