"""Synthetic coverage for unknown timing fields in inspection and the IR."""

import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
import zipfile

from band2flp.parser import BandFormatError, _parse_mseq_tail_word_candidates, parse_band


def chunk(tag, group, payload):
    header = bytearray(36)
    header[:4] = tag[::-1].encode("ascii")
    struct.pack_into("<I", header, 8, group)
    struct.pack_into("<Q", header, 28, len(payload))
    return bytes(header) + payload


class MidiTimingProvenanceTests(unittest.TestCase):
    def test_parser_and_json_preserve_raw_fraction_and_tail_fields(self):
        mseq = bytearray(300)
        struct.pack_into("<I", mseq, 81, 100)
        struct.pack_into("<i", mseq, 245, -15)
        note = bytearray(32)
        note[0] = 0x9E
        struct.pack_into("<H", note, 2, 32768)
        struct.pack_into("<I", note, 4, 38410)
        note[11:13] = bytes((64, 60))
        note[23] = 0x89
        struct.pack_into("<I", note, 28, 20)
        placement = bytearray(80)
        placement[0] = 0x20
        struct.pack_into("<I", placement, 4, 34545)
        struct.pack_into("<I", placement, 32, 1)
        for index, marker in ((23, 0x89), (39, 0x88), (55, 0x8A), (71, 0x88)):
            placement[index] = marker
        raw = bytes.fromhex("2347c0ab") + bytes(20)
        raw += chunk("MSeq", 65536, mseq)
        raw += chunk("EvSq", 65536, note)
        raw += chunk("EvSq", 0, placement)
        archive = {
            "$archiver": "NSKeyedArchiver", "$version": 100000,
            "$top": {"DfDocument logic model": {"CF$UID": 1}},
            "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}}, {"NS.data": raw}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.band"
            with zipfile.ZipFile(path, "w") as package:
                package.writestr("synthetic.band/projectData", plistlib.dumps(archive))
            project = parse_band(path)
        result = json.loads(json.dumps(project.to_dict()))
        words = result["project_data"]["mseq_tail_word_candidates"][0]
        self.assertEqual(words["status"], "candidate")
        self.assertEqual([field["raw_value"] for field in words["fields"]], [100, -15])
        self.assertEqual([field["logic_song_offset"] for field in words["fields"]], [141, 305])
        self.assertTrue(all(field["confidence"].startswith("UNKNOWN") for field in words["fields"]))
        note_ir = result["unplaced_midi_regions"][0]["notes"][0]
        self.assertEqual(note_ir["unknown"]["position_raw"], 38410)
        self.assertEqual(note_ir["unknown"]["position_fraction_raw"], 32768)
        self.assertEqual(note_ir["unknown"]["event_type_byte"], 0x9E)
        self.assertIn("UNKNOWN", note_ir["unknown"]["onset_precision_note"])
        self.assertEqual(note_ir["onset_beats_candidate"], "1/96")
        self.assertTrue(any("nonzero fractional words" in warning for warning in project.warnings))
        self.assertEqual(project.tracks, [])

    def test_partial_tail_fields_respect_each_minimum_size(self):
        for size, expected_fields in ((54, 0), (55, 1), (218, 1), (219, 2)):
            with self.subTest(size=size):
                records = _parse_mseq_tail_word_candidates(bytes(size), {"chunks": [{
                    "type": "MSeq", "index": 0, "payload_offset": 0, "payload_size": size,
                }]})
                self.assertEqual(len(records[0]["fields"]), expected_fields)
                self.assertEqual(records[0]["status"], "candidate" if size == 219 else "partial")

    def test_invalid_mseq_bounds_fail_before_reading(self):
        for start, size in ((-1, 219), (0, -1), (1, 219), (0, 220)):
            with self.subTest(start=start, size=size), self.assertRaises(BandFormatError):
                _parse_mseq_tail_word_candidates(bytes(219), {"chunks": [{
                    "type": "MSeq", "index": 0, "payload_offset": start, "payload_size": size,
                }]})

    def test_non_mseq_chunks_do_not_produce_tail_candidates(self):
        self.assertEqual(_parse_mseq_tail_word_candidates(b"", {"chunks": [{"type": "Trak"}]}), [])


if __name__ == "__main__":
    unittest.main()
