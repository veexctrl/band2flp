import json
import unittest

from band2flp.parser import BandFormatError
from research.scripts.mseq_event_scope_probe import inventory_scope


class MseqEventScopeProbeTests(unittest.TestCase):
    @staticmethod
    def _raw_event(event_type: int, length: int) -> str:
        raw = bytearray(length)
        raw[0] = event_type
        return bytes(raw).hex()

    def test_separates_unique_ambiguous_and_unplaced_mseq_groups(self) -> None:
        chunks = [
            {"type": "MSeq", "index": 1, "group_id_candidate": 0xD001},
            *[
                {"type": "MSeq", "index": index, "group_id_candidate": 0xD002}
                for index in range(2, 7)
            ],
            {"type": "MSeq", "index": 7, "group_id_candidate": 0xD003},
            {"type": "MSeq", "index": 8, "group_id_candidate": 0xD004},
            {"type": "MSeq", "index": 9, "group_id_candidate": 0xD004},
            {"type": "MSeq", "index": 10, "group_id_candidate": 0xD005},
        ]
        placements = [
            {"candidate_mseq_chunk_indices": [1]},
            {"candidate_mseq_chunk_indices": [2, 3, 4, 5, 6]},
            {"candidate_mseq_chunk_indices": [7]},
            {"candidate_mseq_chunk_indices": [8, 9]},
            {"candidate_mseq_chunk_indices": [8]},
            {"candidate_mseq_chunk_indices": [7]},
        ]
        records = [
            {"group_id_candidate": 0xD001, "type_byte": 0x32, "length": 32,
             "raw_hex": self._raw_event(0x32, 32)},
            {"group_id_candidate": 0xD001, "type_byte": 0x90, "length": 32},
            {"group_id_candidate": 0xD002, "type_byte": 0x32, "length": 48,
             "raw_hex": self._raw_event(0x32, 48)},
            {"group_id_candidate": 0xD003, "type_byte": 0xF1, "length": 16},
            {"group_id_candidate": 0xD004, "type_byte": 0x32, "length": 32,
             "raw_hex": self._raw_event(0x32, 32)},
            {"group_id_candidate": 0xD005, "type_byte": 0x32, "length": 32,
             "raw_hex": self._raw_event(0x32, 32)},
        ]

        result = inventory_scope(records, chunks, placements, {0xD001})

        categories = result["scope_categories"]
        self.assertEqual(result["mseq_group_count"], 5)
        self.assertEqual(categories["unique_placement"]["mseq_group_count"], 1)
        self.assertEqual(categories["unique_placement"]["groups_with_type_32"], 1)
        self.assertEqual(categories["unique_placement"]["groups_with_note_candidates"], 1)
        self.assertEqual(categories["ambiguous_placement"]["groups_with_type_32"], 2)
        self.assertEqual(categories["ambiguous_placement"]["mseq_group_count"], 3)
        self.assertEqual(categories["ambiguous_placement"]["type_32_record_length_counts"], {"32": 1, "48": 1})
        self.assertEqual(categories["ambiguous_placement"]["mseq_chunk_multiplicity_counts_for_type_32_groups"], {"2": 1, "5": 1})
        self.assertEqual(categories["no_placement_candidate"]["groups_with_type_32"], 1)
        self.assertNotIn("D001", json.dumps(result))
        self.assertNotIn("53249", json.dumps(result))

    def test_rejects_placement_that_references_missing_mseq(self) -> None:
        with self.assertRaises(BandFormatError):
            inventory_scope([], [], [{"candidate_mseq_chunk_indices": [5]}])

    def test_profiles_repeated_payloads_and_varying_bytes_without_emitting_payloads(self) -> None:
        groups = [0xD101, 0xD202, 0xD303, 0xD404]
        chunks = [
            {"type": "MSeq", "index": index, "group_id_candidate": group}
            for index, group in enumerate(groups, 1)
        ]
        placements = [{"candidate_mseq_chunk_indices": [index]} for index in range(1, 5)]
        first = bytearray(32)
        first[0] = 0x32
        first[5] = 1
        second = bytearray(first)
        second[5] = 2
        payloads = [first, first, first, second]
        records = [
            {
                "group_id_candidate": group,
                "chunk_index": index,
                "event_index": index + 10,
                "type_byte": 0x32,
                "length": 32,
                "raw_hex": bytes(payload).hex(),
            }
            for index, (group, payload) in enumerate(zip(groups, payloads), 1)
        ]

        profile = inventory_scope(records, chunks, placements)["type_32_payload_profiles"]["32"]

        self.assertEqual(profile["record_count"], 4)
        self.assertEqual(profile["distinct_payload_count"], 2)
        self.assertEqual(profile["duplicate_record_count"], 2)
        self.assertEqual(profile["distinct_payload_multiplicity_counts"], {"1": 1, "3": 1})
        self.assertEqual(profile["varying_byte_positions"], [5])
        self.assertEqual(profile["varying_byte_candidate_field_matches"], [])
        self.assertNotIn(bytes(first).hex(), json.dumps(profile))

    def test_rejects_type_32_length_that_disagrees_with_raw_bytes(self) -> None:
        chunk = {"type": "MSeq", "index": 1, "group_id_candidate": 0xD001}
        placement = {"candidate_mseq_chunk_indices": [1]}
        record = {
            "group_id_candidate": 0xD001,
            "type_byte": 0x32,
            "length": 32,
            "raw_hex": "00",
        }
        with self.assertRaises(BandFormatError):
            inventory_scope([record], [chunk], [placement])

    def test_rejects_type_32_record_without_raw_bytes(self) -> None:
        chunk = {"type": "MSeq", "index": 1, "group_id_candidate": 0xD001}
        placement = {"candidate_mseq_chunk_indices": [1]}
        record = {"group_id_candidate": 0xD001, "type_byte": 0x32, "length": 32}
        with self.assertRaises(BandFormatError):
            inventory_scope([record], [chunk], [placement])

    def test_counts_fractional_position_matches_only_as_candidates(self) -> None:
        groups = [0xD101, 0xD202, 0xD303]
        chunks = [
            {"type": "MSeq", "index": index, "group_id_candidate": group}
            for index, group in enumerate(groups, 1)
        ]
        placements = [{"candidate_mseq_chunk_indices": [index]} for index in range(1, 3)]
        records = []
        for index, (group, fraction) in enumerate(zip((groups[0], groups[2]), (7, 8)), 1):
            raw = bytearray(32)
            raw[0] = 0x32
            raw[2:4] = fraction.to_bytes(2, "little")
            raw[4:8] = (100).to_bytes(4, "little")
            records.append({
                "group_id_candidate": group,
                "chunk_index": index,
                "event_index": index,
                "type_byte": 0x32,
                "length": 32,
                "raw_hex": bytes(raw).hex(),
            })
        control_raw = bytearray(32)
        control_raw[0] = 0xB0
        control_raw[2:4] = (7).to_bytes(2, "little")
        control_raw[4:8] = (100).to_bytes(4, "little")
        records.append({
            "group_id_candidate": groups[0],
            "chunk_index": 1,
            "event_index": 4,
            "type_byte": 0xB0,
            "length": 32,
            "raw_hex": bytes(control_raw).hex(),
        })
        other_chunk_raw = bytearray(control_raw)
        other_chunk_raw[0] = 0xE0
        records.append({
            "group_id_candidate": groups[0],
            "chunk_index": 9,
            "event_index": 1,
            "type_byte": 0xE0,
            "length": 32,
            "raw_hex": bytes(other_chunk_raw).hex(),
        })
        notes = [
            {
                "source_group_id_candidate": groups[0],
                "source_chunk_index": 1,
                "source_event_index": 2,
                "position_raw": 100,
                "position_fraction_raw": 7,
                "event_type_byte": 0x91,
            },
            {
                "source_group_id_candidate": groups[0],
                "source_chunk_index": 1,
                "source_event_index": 3,
                "position_raw": 100,
                "position_fraction_raw": 7,
                "event_type_byte": 0x90,
            },
            {
                "source_group_id_candidate": groups[1],
                "source_chunk_index": 2,
                "source_event_index": 2,
                "position_raw": 100,
                "position_fraction_raw": 8,
                "event_type_byte": 0x90,
            },
        ]

        result = inventory_scope(records, chunks, placements, {groups[0], groups[1]}, notes)

        self.assertEqual(
            result["type_32_timestamp_candidate_counts"],
            {
                "eligible_record_count": 2,
                "same_group_note_candidate_record_count": 1,
                "same_group_position_word_match_record_count": 1,
                "same_group_exact_fractional_position_match_record_count": 1,
                "any_group_position_word_match_record_count": 2,
                "any_group_exact_fractional_position_match_record_count": 2,
            },
        )
        self.assertEqual(
            result["type_32_matching_note_event_type_counts"],
            {"0x90": 1, "0x91": 1},
        )
        self.assertEqual(
            result["non_note_event_position_candidate_order"],
            {
                "0x32": {
                    "matching_event_count": 1,
                    "same_chunk_pairs": 2,
                    "before_note_pairs": 2,
                },
                "0xb0": {
                    "matching_event_count": 1,
                    "same_chunk_pairs": 2,
                    "after_note_pairs": 2,
                },
                "0xe0": {
                    "matching_event_count": 1,
                    "different_chunk_pairs": 2,
                },
            },
        )
        self.assertEqual(
            result["type_32_timestamp_counts_by_placement_scope"],
            {
                "ambiguous_placement": {},
                "no_placement_candidate": {
                    "eligible_record_count": 1,
                    "same_group_exact_fractional_position_match_record_count": 0,
                    "any_group_exact_fractional_position_match_record_count": 1,
                },
                "unique_placement": {
                    "eligible_record_count": 1,
                    "same_group_exact_fractional_position_match_record_count": 1,
                    "any_group_exact_fractional_position_match_record_count": 1,
                },
            },
        )
        self.assertEqual(
            result["non_note_event_position_candidate_matches"],
            {
                "0x32": {
                    "eligible_record_count": 1,
                    "same_group_position_word_match_record_count": 1,
                    "same_group_exact_fractional_position_match_record_count": 1,
                },
                "0xb0": {
                    "eligible_record_count": 1,
                    "same_group_position_word_match_record_count": 1,
                    "same_group_exact_fractional_position_match_record_count": 1,
                },
                "0xe0": {
                    "eligible_record_count": 1,
                    "same_group_position_word_match_record_count": 1,
                    "same_group_exact_fractional_position_match_record_count": 1,
                },
            },
        )
        self.assertIn("HYPOTHESIS", result["type_32_timestamp_candidate_interpretation"])
        self.assertNotIn("D101", json.dumps(result))
        self.assertNotIn(bytes(records[0]["raw_hex"], "ascii").decode(), json.dumps(result))

    def test_profiles_nonunique_type32_slices_across_event_groups(self) -> None:
        groups = [0xD101, 0xD202, 0xD303]
        chunks = [
            {"type": "MSeq", "index": index, "group_id_candidate": group}
            for index, group in enumerate(groups, 1)
        ]
        placements = [{"candidate_mseq_chunk_indices": [index]} for index in range(1, 4)]
        raw_slice = b"\x01\x00\x05\x00\x00\x00"

        def event(event_type: int, group: int, candidate_slice: bytes) -> dict[str, object]:
            raw = bytearray(32)
            raw[0] = event_type
            raw[2:8] = candidate_slice
            return {
                "group_id_candidate": group,
                "chunk_index": 1,
                "event_index": 1,
                "type_byte": event_type,
                "length": len(raw),
                "raw_hex": bytes(raw).hex(),
            }

        records = [
            event(0x32, groups[0], raw_slice),
            event(0x32, groups[1], raw_slice),
            event(0x32, groups[2], bytes(6)),
            event(0xB0, groups[0], raw_slice),
            event(0x91, groups[2], raw_slice),
        ]

        result = inventory_scope(records, chunks, placements)
        profile = result["type_32_shared_byte_slice_counts"]

        self.assertEqual(profile["type_32_record_count"], 3)
        self.assertEqual(profile["nonzero_candidate_record_count"], 2)
        self.assertEqual(profile["distinct_nonzero_candidate_slice_count"], 1)
        self.assertEqual(profile["records_with_same_group_non_type32_match"], 1)
        self.assertEqual(profile["records_with_other_group_non_type32_match"], 2)
        self.assertEqual(profile["records_with_same_group_note_family_match"], 0)
        self.assertEqual(profile["records_with_other_group_note_family_match"], 2)
        self.assertNotIn(raw_slice.hex(), json.dumps(profile))
        self.assertNotIn("D101", json.dumps(profile))


if __name__ == "__main__":
    unittest.main()

