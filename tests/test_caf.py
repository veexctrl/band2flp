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
    desc = struct.pack(">d4sIIIII", 48000, b"aac ", 2, 0, 1024, 2, 0)
    pakt = struct.pack(">qqii", 190, 192000, 2112, 448)
    return (
        b"caff\0\x01\0\0"
        + chunk(b"desc", desc)
        + chunk(b"pakt", pakt)
        + chunk(b"data", bytes(30))
        + chunk(b"uuid", uuid + len(fields).to_bytes(4, "big") + pairs)
    )


class ReadTrackingStream(BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.read_ranges: list[tuple[int, int]] = []

    def read(self, size: int = -1) -> bytes:
        start = self.tell()
        result = super().read(size)
        self.read_ranges.append((start, self.tell()))
        return result


class CafMetadataTests(unittest.TestCase):
    def test_source_beat_count_and_tempo_candidate(self) -> None:
        data = fixture({"time signature": "4/4", "beat count": "4", "category": "Drums"})
        result = inspect_caf_loop_metadata(BytesIO(data))
        assert result is not None
        self.assertEqual(result["beat_count"], 4)
        self.assertEqual(result["source_tempo_bpm_from_frames_candidate"], 60)
        self.assertIn("half/double-time", result["tempo_confidence"])
        self.assertIn("HYPOTHESIS", result["tempo_confidence"])
        self.assertEqual(result["fields"]["time signature"], "4/4")
        self.assertEqual(result["sample_rate_hz"], 48000)
        self.assertEqual(result["valid_frames"], 192000)
        self.assertEqual(result["audio_format"], {
            "format_id": "aac ",
            "frames_per_packet": 1024,
            "channels_per_frame": 2,
        })
        self.assertEqual(result["packet_table"], {
            "number_packets": 190,
            "valid_frames": 192000,
            "priming_frames": 2112,
            "remainder_frames": 448,
        })
        self.assertEqual(
            result["packet_table"]["number_packets"] * result["audio_format"]["frames_per_packet"],
            result["packet_table"]["valid_frames"]
            + result["packet_table"]["priming_frames"]
            + result["packet_table"]["remainder_frames"],
        )
        self.assertNotIn("arrangement_loop", result)

    def test_known_size_data_payload_is_skipped_without_reading_samples(self) -> None:
        data = fixture({"beat count": "4"})
        data_header = data.index(b"data", 8)
        sample_start = data_header + 12
        sample_end = sample_start + 30
        stream = ReadTrackingStream(data)

        result = inspect_caf_loop_metadata(stream)

        self.assertIsNotNone(result)
        self.assertTrue(
            all(
                end <= sample_start or start >= sample_end
                for start, end in stream.read_ranges
            )
        )
        self.assertGreaterEqual(stream.tell(), sample_end)

    def test_unknown_uuid_is_not_interpreted(self) -> None:
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(fixture({"beat count": "4"}, uuid=bytes(16)))))

    def test_malformed_pair_count_is_rejected(self) -> None:
        data = fixture({"beat count": "4"}).replace(
            LOOP_METADATA_UUID + (1).to_bytes(4, "big"),
            LOOP_METADATA_UUID + (2).to_bytes(4, "big"),
        )
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(data)))

    def test_short_chunk_is_rejected(self) -> None:
        data = b"caff\0\x01\0\0" + b"uuid" + (30).to_bytes(8, "big") + b"short"
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(data)))

    def test_unknown_size_is_only_accepted_for_final_data_chunk(self) -> None:
        header = b"caff\0\x01\0\0"
        metadata = chunk(b"uuid", LOOP_METADATA_UUID + (1).to_bytes(4, "big") + b"beat count\0" + b"4\0")
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(header + metadata + b"free" + (-1).to_bytes(8, "big", signed=True))))

    def test_data_chunk_rejects_negative_size_other_than_minus_one(self) -> None:
        header = b"caff\0\x01\0\0"
        metadata = chunk(b"uuid", LOOP_METADATA_UUID + (1).to_bytes(4, "big") + b"beat count\0" + b"4\0")
        malformed_data_header = b"data" + (-2).to_bytes(8, "big", signed=True)
        self.assertIsNone(inspect_caf_loop_metadata(BytesIO(header + metadata + malformed_data_header)))

    def test_unknown_size_final_data_chunk_keeps_prior_metadata(self) -> None:
        header = b"caff\0\x01\0\0"
        metadata = chunk(b"uuid", LOOP_METADATA_UUID + (1).to_bytes(4, "big") + b"beat count\0" + b"4\0")
        data_header = b"data" + (-1).to_bytes(8, "big", signed=True)
        result = inspect_caf_loop_metadata(BytesIO(header + metadata + data_header))
        self.assertIsNotNone(result)
        self.assertEqual(result["beat_count"], 4)


if __name__ == "__main__":
    unittest.main()

