import io
import struct
import unittest

from research.scripts.audio_frame_probe import audio_frame_metadata_stream


class AudioFrameStreamProbeTests(unittest.TestCase):
    def test_wave_probe_stops_at_sample_data_header(self) -> None:
        samples = b"X" * 4096
        fmt = struct.pack("<HHIIHH", 1, 2, 44_100, 176_400, 4, 16)
        data = b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(samples))
        data += b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt
        data += b"data" + struct.pack("<I", len(samples)) + samples
        stream = io.BytesIO(data)

        result = audio_frame_metadata_stream(stream, len(data))

        self.assertEqual(result, (1024, "WAVE", 44_100))
        self.assertEqual(stream.tell(), len(data) - len(samples))

    def test_aiff_probe_stops_after_common_chunk(self) -> None:
        samples = b"X" * 4096
        common = struct.pack(">HIH", 2, 1234, 16) + bytes.fromhex("400eac44000000000000")
        body = b"AIFF" + b"COMM" + struct.pack(">I", len(common)) + common
        body += b"SSND" + struct.pack(">I", len(samples) + 8) + bytes(8) + samples
        data = b"FORM" + struct.pack(">I", len(body)) + body
        stream = io.BytesIO(data)

        result = audio_frame_metadata_stream(stream, len(data))

        self.assertEqual(result, (1234, "AIFF", 44_100))
        self.assertLess(stream.tell(), len(data) - len(samples))

    def test_caf_probe_stops_at_data_chunk_header(self) -> None:
        samples = b"X" * 4096
        desc = struct.pack(">d4sIIIII", 44_100.0, b"lpcm", 0, 4, 1, 4, 2)
        pakt = struct.pack(">qqii", 2048, 9876, 0, 0)
        chunks = b"desc" + struct.pack(">q", len(desc)) + desc
        chunks += b"pakt" + struct.pack(">q", len(pakt)) + pakt
        chunks += b"data" + struct.pack(">q", len(samples) + 4) + bytes(4) + samples
        data = b"caff" + struct.pack(">HH", 1, 0) + chunks
        stream = io.BytesIO(data)

        result = audio_frame_metadata_stream(stream, len(data))

        self.assertEqual(result, (9876, "CAF-packet-table", 44_100))
        self.assertEqual(stream.tell(), len(data) - len(samples) - 4)


if __name__ == "__main__":
    unittest.main()
