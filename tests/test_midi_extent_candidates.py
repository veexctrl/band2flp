"""Extent candidates retain raw evidence without choosing duration or loops."""

import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from band2flp.model import MidiNoteCandidate, Project, UnplacedMidiRegionCandidate
from band2flp.cli import main as cli_main
from band2flp.parser import _midi_region_extent_candidates, parse_band


def inputs(source=1920, shift=480, extent=2880, start=480, ppq=960):
    placement = {"u32_at_0x1c_candidate": extent, "extent_word_logic_song_offset": 492,
                 "position_ticks_from_origin_candidate": start, "ppq_candidate": ppq}
    tail = {"source_chunk_index": 0, "fields": [
        {"offset_from_payload_end": -219, "raw_value": source, "logic_song_offset": 141,
         "encoding": "u32le", "size": 4},
        {"offset_from_payload_end": -55, "raw_value": shift, "logic_song_offset": 305,
         "encoding": "i32le", "size": 4},
    ]}
    notes = [MidiNoteCandidate("0", "1", 60, 64, 1, 1, 0)]
    return placement, tail, notes


def chunk(tag, group, payload):
    header = bytearray(36)
    header[:4] = tag[::-1].encode()
    struct.pack_into("<I", header, 8, group)
    struct.pack_into("<Q", header, 28, len(payload))
    return bytes(header) + payload


class MidiExtentCandidateTests(unittest.TestCase):
    def test_source_and_placement_candidates_are_separate_and_provisional(self):
        result = _midi_region_extent_candidates(*inputs())
        self.assertEqual(result["source_duration_beats_candidate"], "2")
        self.assertEqual(result["placement_extent_beats_candidate"], "3")
        self.assertEqual(result["source_word"]["logic_song_offset"], 141)
        self.assertEqual(result["placement_word_logic_song_offset"], 492)
        self.assertTrue(result["confidence"].startswith("HYPOTHESIS"))
        self.assertIn("repeat", result["placement_extent_semantics"])
        self.assertIn("UNKNOWN", result["placement_extent_semantics"])

    def test_fractional_beats_are_exact_and_whole_ppq_is_not_required(self):
        p, tail, _ = inputs(source=40, extent=60)
        notes = [MidiNoteCandidate("0", "1/48", 60, 64, 1, 1, 0)]
        result = _midi_region_extent_candidates(p, tail, notes)
        self.assertEqual(result["source_duration_beats_candidate"], "1/24")
        self.assertEqual(result["placement_extent_beats_candidate"], "1/16")

    def test_special_and_zero_placement_words_stay_raw(self):
        for word in (0, 0x3FFFFFFF):
            with self.subTest(word=word):
                result = _midi_region_extent_candidates(*inputs(extent=word))
                self.assertEqual(result["source_duration_beats_candidate"], "2")
                self.assertIsNone(result["placement_extent_beats_candidate"])
                self.assertEqual(result["placement_word_raw"], word)

    def test_failed_note_bounds_or_shift_do_not_normalize_source(self):
        for source, shift in ((480, 480), (1920, 0)):
            with self.subTest(source=source, shift=shift):
                result = _midi_region_extent_candidates(*inputs(source=source, shift=shift))
                self.assertIsNone(result["source_duration_beats_candidate"])
                self.assertEqual(result["source_word"]["raw_value"], source)
                self.assertEqual(result["placement_extent_beats_candidate"], "3")

    def test_zero_source_or_missing_metadata_remains_unknown(self):
        result = _midi_region_extent_candidates(*inputs(source=0))
        self.assertIsNone(result["source_duration_beats_candidate"])
        self.assertEqual(result["source_word"]["raw_value"], 0)
        p, _, notes = inputs()
        result = _midi_region_extent_candidates(p, None, notes)
        self.assertIsNone(result["source_duration_beats_candidate"])
        self.assertIsNone(result["shift_equals_placement_start_candidate"])
        self.assertEqual(result["placement_extent_beats_candidate"], "3")

    def test_invalid_ppq_never_divides_or_discards_raw_words(self):
        result = _midi_region_extent_candidates(*inputs(ppq=0))
        self.assertIsNone(result["source_duration_beats_candidate"])
        self.assertIsNone(result["placement_extent_beats_candidate"])
        self.assertEqual(result["placement_word_raw"], 2880)

    def test_large_non_special_word_is_a_scalar_candidate_not_a_repeat_allocation(self):
        result = _midi_region_extent_candidates(*inputs(extent=0xFFFFFFFF))
        self.assertEqual(result["placement_extent_beats_candidate"], "286331153/64")
        self.assertEqual(result["placement_word_raw"], 0xFFFFFFFF)

    def test_archive_to_neutral_json_preserves_both_extents_and_offsets(self):
        mseq = bytearray(300)
        struct.pack_into("<I", mseq, 81, 1920)
        struct.pack_into("<i", mseq, 245, 480)
        note = bytearray(32)
        note[0], note[11], note[12], note[23] = 0x90, 64, 60, 0x89
        struct.pack_into("<I", note, 4, 38400)
        struct.pack_into("<I", note, 28, 960)
        placement = bytearray(80)
        placement[0], placement[20] = 0x20, 1
        struct.pack_into("<I", placement, 4, 35040)
        struct.pack_into("<I", placement, 28, 2880)
        struct.pack_into("<I", placement, 32, 1)
        for index, marker in ((23, 0x89), (39, 0x88), (55, 0x8A), (71, 0x88)):
            placement[index] = marker
        raw = bytes.fromhex("2347c0ab") + bytes(20)
        raw += chunk("MSeq", 65536, mseq) + chunk("EvSq", 65536, note) + chunk("EvSq", 0, placement)
        archive = {"$archiver": "NSKeyedArchiver", "$version": 100000,
                   "$top": {"DfDocument logic model": {"CF$UID": 1}},
                   "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}}, {"NS.data": raw}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.band"
            with zipfile.ZipFile(path, "w") as package:
                package.writestr("synthetic.band/projectData", plistlib.dumps(archive))
            result = json.loads(json.dumps(parse_band(path).to_dict()))
        region = result["unplaced_midi_regions"][0]
        self.assertEqual(region["source_duration_beats_candidate"], "2")
        self.assertEqual(region["placement_extent_beats_candidate"], "3")
        self.assertEqual(region["unknown"]["extent_candidates"]["source_word"]["logic_song_offset"], 141)
        self.assertEqual(region["unknown"]["extent_candidates"]["placement_word_logic_song_offset"], 492)
        self.assertEqual(result["tracks"], [])
        self.assertNotIn("duration_beats", region)

    def test_text_inspection_counts_extents_without_raw_word_values(self):
        candidate = UnplacedMidiRegionCandidate(
            "0", None, [MidiNoteCandidate("0", "1", 60, 64, 1, 1, 0)], 0, 2, 0,
            unknown={"extent_candidates": {"source_word": {"raw_value": 1920}, "placement_word_raw": 2880}},
            source_duration_beats_candidate="2", placement_extent_beats_candidate="3",
        )
        output = io.StringIO()
        with patch("band2flp.cli.parse_band", return_value=Project(unplaced_midi_regions=[candidate])), redirect_stdout(output):
            code = cli_main(["inspect", "synthetic.band"])
        self.assertEqual(code, 0)
        self.assertIn("MIDI extent candidates: source=1, placement=1 (semantics unconfirmed)", output.getvalue())
        self.assertNotIn("1920", output.getvalue())
        self.assertNotIn("2880", output.getvalue())


if __name__ == "__main__":
    unittest.main()
