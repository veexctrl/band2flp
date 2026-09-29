from __future__ import annotations

from io import BytesIO
import struct
import unittest

from band2flp.caf import LOOP_METADATA_UUID, inspect_caf_loop_metadata


def chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + len(payload).to_bytes(8, "big", signed=True) + payload


def fixture(fields: dict[str, str], *, uuid: bytes = LOOP_METADATA_UUID) -> bytes:
    pairs = b"".join(
        key.encode() + b"\0" + value.encode() + b"\0"
        for key, value in fields.items()
    )
    desc = struct.pack(">d", 44100) + b"aac " + bytes(20)
    pakt = (1).to_bytes(8, "big") + (302400).to_bytes(8, "big") + bytes(8)
    return (
        b"caff\0\x01\0\0"
        + chunk(b"desc", desc)
        + chunk(b"pakt", pakt)
        + chunk(b"data", bytes(30))
        + chunk(b"uuid", uuid + len(fields).to_bytes(4, "big") + pairs)
    )


class CafMetadataTests(unittest.TestCase):
    def test_source_beat_count_and_tempo_candidate(self) -> None:
        data = fixture({"time signature": "4/4", "beat count": "8", "category": "Drums"})
        result = inspect_caf_loop_metadata(BytesIO(data))
        assert result is not None
        self.assertEqual(result["beat_count"], 8)
        self.assertEqual(result["source_tempo_bpm_from_frames_candidate"], 70)
        self.assertEqual(result["fields"]["time signature"], "4/4")
        self.assertNotIn("arrangement_loop", result)

    def test_unknown_uuid_is_not_interpreted(self) -> None:
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(fixture({"beat count": "8"}, uuid=bytes(16)))))

    def test_malformed_pair_count_is_rejected(self) -> None:
        data = fixture({"beat count": "8"}).replace(
            LOOP_METADATA_UUID + (1).to_bytes(4, "big"),
            LOOP_METADATA_UUID + (2).to_bytes(4, "big"),
        )
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(data)))

    def test_short_chunk_is_rejected(self) -> None:
        data = b"caff\0\x01\0\0" + b"uuid" + (30).to_bytes(8, "big") + b"short"
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(data)))


if __name__ == "__main__":
    unittest.main()

