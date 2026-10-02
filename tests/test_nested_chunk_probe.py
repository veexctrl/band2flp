from __future__ import annotations

import struct
import unittest

from band2flp.parser import BandFormatError
from research.scripts.nested_chunk_probe import profile_nested_chunk_streams


MAGIC = bytes.fromhex("2347c0ab")


def make_chunk(tag: str, payload: bytes = b"") -> bytes:
    header = bytearray(36)
    header[:4] = tag.encode("ascii")[::-1]
    struct.pack_into("<Q", header, 28, len(payload))
    return bytes(header) + payload


def make_stream(*chunks: bytes) -> bytes:
    return MAGIC + bytes(20) + b"".join(chunks)


class NestedChunkProbeTests(unittest.TestCase):
    def test_counts_nested_streams_without_exposing_payload(self) -> None:
        nested = make_stream(make_chunk("Leaf", b"private-value"))
        root = make_stream(make_chunk("Song", nested))

        result = profile_nested_chunk_streams(root)

        self.assertEqual(result["root_chunk_count"], 1)
        self.assertEqual(result["nested_stream_count"], 1)
        self.assertEqual(result["nested_streams_by_depth"]["1"]["type_counts"], {"Leaf": 1})
        self.assertNotIn("private-value", repr(result))

    def test_counts_malformed_magic_candidate_without_interpreting_it(self) -> None:
        malformed = MAGIC + bytes(20) + b"short"
        root = make_stream(make_chunk("Song", malformed))

        result = profile_nested_chunk_streams(root)

        self.assertEqual(result["nested_stream_count"], 0)
        self.assertEqual(result["malformed_magic_candidate_count"], 1)

    def test_rejects_malformed_root_stream(self) -> None:
        with self.assertRaises(BandFormatError):
            profile_nested_chunk_streams(b"not a stream")


if __name__ == "__main__":
    unittest.main()