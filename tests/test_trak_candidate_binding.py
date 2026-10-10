"""Candidate track links must preserve uncertainty and complete provenance."""

import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
import zipfile

from band2flp.model import Project
from band2flp.parser import (
    BandFormatError,
    _attach_unplaced_midi_region_candidates,
    _candidate_midi_track_binding,
    _link_trak_word_candidates,
    _parse_trak_reference_candidates,
    parse_band,
)


def source_record(group=0x40000, word=100, ordinal=1, index=7):
    return {"source_group_id_candidate": group, "word_at_payload_0x08_raw": word,
            "record_order_within_group_1_based": ordinal, "source_chunk_index": index,
            "word_logic_song_offset": 68}


def chunk(tag, group, payload):
    header = bytearray(36)
    header[:4] = tag[::-1].encode()
    struct.pack_into("<I", header, 8, group)
    struct.pack_into("<Q", header, 28, len(payload))
    return bytes(header) + payload


class TrakCandidateBindingTests(unittest.TestCase):
    def test_unique_matching_ordinal_is_provisional(self):
        p = _link_trak_word_candidates([{"event_id_candidate": 100, "track_value_candidate": 1}],
                                       [source_record(), source_record(group=0x80000)])[0]
        result = _candidate_midi_track_binding(p, 1)
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["track_index_candidate"], 0)
        self.assertEqual(result["source_trak_chunk_index"], 7)
        self.assertTrue(result["confidence"].startswith("HYPOTHESIS"))
        self.assertEqual(len(p["candidate_trak_word_links"]), 2)

    def test_duplicate_smaller_family_is_ambiguous(self):
        p = _link_trak_word_candidates([{"event_id_candidate": 100, "track_value_candidate": 1}],
                                       [source_record(), source_record(index=8)])[0]
        self.assertEqual(_candidate_midi_track_binding(p, 2)["status"], "ambiguous")

    def test_mismatch_or_declared_range_prevents_binding(self):
        p = _link_trak_word_candidates([{"event_id_candidate": 100, "track_value_candidate": 2}],
                                       [source_record()])[0]
        self.assertEqual(_candidate_midi_track_binding(p, 2)["reason"], "ordinal_disagrees_with_track_byte")
        p["track_value_candidate"] = 1
        self.assertEqual(_candidate_midi_track_binding(p, 0)["reason"], "ordinal_exceeds_declared_track_count")
        self.assertFalse(_candidate_midi_track_binding(p, None)["declared_track_range_checked"])

    def test_zero_and_other_families_cannot_establish_binding(self):
        for word, records in ((0, [source_record(word=0)]), (100, [source_record(group=0x80000)])):
            p = _link_trak_word_candidates([{"event_id_candidate": word, "track_value_candidate": 1}], records)[0]
            self.assertEqual(_candidate_midi_track_binding(p, 1)["status"], "unavailable")

    def test_excessive_fanout_is_reported_and_cannot_hide_ambiguity(self):
        records = [source_record()] + [source_record(group=0x80000, index=i) for i in range(129)]
        p = _link_trak_word_candidates([{"event_id_candidate": 100, "track_value_candidate": 1}], records)[0]
        self.assertEqual(p["candidate_trak_word_link_count"], 130)
        self.assertTrue(p["candidate_trak_word_links_truncated"])
        self.assertLess(len(p["candidate_trak_word_links"]), len(records))
        self.assertEqual(_candidate_midi_track_binding(p, 1)["reason"], "link_fanout_exceeds_inspection_limit")
        self.assertEqual(len(records), 130)

    def test_record_order_is_scoped_to_each_family(self):
        payload = bytearray(58 * 3)
        groups = (0x40000, 0x80000, 0x40000)
        chunks = []
        for index, group in enumerate(groups):
            struct.pack_into("<I", payload, index * 58 + 8, 100 + index)
            chunks.append({"type": "Trak", "index": index, "group_id_candidate": group,
                           "payload_offset": index * 58, "payload_size": 58})
        records = _parse_trak_reference_candidates(payload, {"chunks": chunks})
        self.assertEqual([r["record_order_within_group_1_based"] for r in records], [1, 1, 2])
        self.assertEqual([r["word_logic_song_offset"] for r in records], [8, 66, 124])

    def test_invalid_trak_bounds_are_rejected(self):
        with self.assertRaises(BandFormatError):
            _parse_trak_reference_candidates(bytes(58), {"chunks": [{
                "type": "Trak", "payload_offset": 1, "payload_size": 58,
            }]})

    def test_two_regions_keep_the_same_candidate_track_in_neutral_json(self):
        raw = bytes.fromhex("2347c0ab") + bytes(20)
        trak = bytearray(58)
        struct.pack_into("<I", trak, 8, 100)
        raw += chunk("Trak", 0x40000, trak) + chunk("Trak", 0x80000, trak)
        for cluster in (1, 2):
            raw += chunk("MSeq", cluster << 16, bytes(300))
            note = bytearray(32)
            note[0], note[11], note[12], note[23] = 0x90, 64, 60, 0x89
            struct.pack_into("<I", note, 4, 38400)
            struct.pack_into("<I", note, 28, 480)
            raw += chunk("EvSq", cluster << 16, note)
            placement = bytearray(80)
            placement[0], placement[20] = 0x20, 1
            struct.pack_into("<I", placement, 4, 34560 + 960 * cluster)
            struct.pack_into("<I", placement, 16, 100)
            struct.pack_into("<I", placement, 32, cluster)
            for index, marker in ((23, 0x89), (39, 0x88), (55, 0x8A), (71, 0x88)):
                placement[index] = marker
            raw += chunk("EvSq", 0, placement)
        archive = {"$archiver": "NSKeyedArchiver", "$version": 100000,
                   "$top": {"DfDocument logic model": {"CF$UID": 1}},
                   "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}}, {"NS.data": raw}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.band"
            with zipfile.ZipFile(path, "w") as package:
                package.writestr("synthetic.band/projectData", plistlib.dumps(archive))
                package.writestr("synthetic.band/Output/metadata.plist", plistlib.dumps({
                    "com_apple_garageband_metadata_numberOfArrangeTracks": 1,
                }))
            result = json.loads(json.dumps(parse_band(path).to_dict()))
        bindings = [r["unknown"]["candidate_track_binding"] for r in result["unplaced_midi_regions"]]
        self.assertEqual(len(bindings), 2)
        self.assertEqual([b["track_index_candidate"] for b in bindings], [0, 0])
        self.assertTrue(all(b["declared_track_range_checked"] for b in bindings))
        self.assertEqual([len(r["unknown"]["candidate_trak_word_links"])
                          for r in result["unplaced_midi_regions"]], [2, 2])
        self.assertEqual(result["tracks"], [])

    def test_placements_without_recognized_notes_are_preserved_as_candidates(self):
        def placement(chunk, event, mseqs):
            return {
                "source_chunk_index": chunk,
                "source_event_index": event,
                "candidate_mseq_chunk_indices": mseqs,
                "start_beats_candidate": str(event * 2),
                "track_value_candidate": 1,
                "candidate_trak_word_links": [],
                "candidate_trak_word_links_truncated": False,
                "u32_at_0x1c_candidate": 960,
                "position_ticks_from_origin_candidate": event * 1920,
            }

        project = Project(project_data={
            "midi_region_placement_candidates": [
                placement(20, 1, [4]),
                placement(21, 2, [5, 6]),
            ],
            "midi_note_event_candidates": [],
            "mseq_tail_word_candidates": [],
        })
        _attach_unplaced_midi_region_candidates(project)

        self.assertEqual(len(project.unplaced_midi_regions), 2)
        self.assertEqual([region.source_mseq_chunk_index for region in project.unplaced_midi_regions], [4, None])
        self.assertTrue(all(region.notes == [] for region in project.unplaced_midi_regions))
        self.assertTrue(all(region.unknown["note_content_status"] == "no_recognized_note_candidates"
                            for region in project.unplaced_midi_regions))
        self.assertTrue(all("does not establish that the region is empty"
                            in region.unknown["note_content_note"]
                            for region in project.unplaced_midi_regions))


if __name__ == "__main__":
    unittest.main()
