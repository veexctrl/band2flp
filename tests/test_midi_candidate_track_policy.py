"""Preview grouping is explicit, preserves regions and uses neutral bindings."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from band2flp.cli import main
from band2flp.flp_export import FLPExportError, _plan_midi_candidate_tracks, export_flp
from band2flp.model import MidiNoteCandidate, Project, UnplacedMidiRegionCandidate


def region(index=None, *, source=7, status="candidate", reason=None):
    binding = {"status": status, "track_index_candidate": index, "source_trak_chunk_index": source}
    if reason is not None:
        binding["reason"] = reason
    return SimpleNamespace(unknown={"candidate_track_binding": binding})


class MidiCandidateTrackPolicyTests(unittest.TestCase):
    def test_shared_binding_reuses_row_and_channel_slot(self):
        plans = _plan_midi_candidate_tracks([region(2), region(2), region(0, source=5)], [], 500,
                                           "candidate-bindings")
        self.assertEqual([p["playlist_track_index"] for p in plans], [3, 3, 1])
        self.assertEqual([p["channel_slot"] for p in plans], [0, 0, 1])
        self.assertTrue(all(p["track_policy_applied"] == "candidate-binding" for p in plans))

    def test_fallback_reserves_later_bound_and_audio_rows(self):
        plans = _plan_midi_candidate_tracks([region(status="ambiguous", reason="duplicate"), region(4)],
                                           [2], 500, "candidate-bindings")
        self.assertEqual([p["playlist_track_index"] for p in plans], [6, 5])
        self.assertEqual(plans[0]["fallback_reason"], "duplicate")
        self.assertEqual(plans[0]["track_policy_applied"], "separate-fallback")

    def test_default_separate_policy_does_not_group_bindings(self):
        plans = _plan_midi_candidate_tracks([region(2), region(2)], [4], 500, "separate")
        self.assertEqual([p["playlist_track_index"] for p in plans], [5, 6])
        self.assertEqual([p["channel_slot"] for p in plans], [0, 1])

    def test_missing_or_invalid_binding_remains_visible(self):
        plans = _plan_midi_candidate_tracks([SimpleNamespace(), region(True), region(-1)], [], 500,
                                           "candidate-bindings")
        self.assertEqual([p["playlist_track_index"] for p in plans], [1, 2, 3])
        self.assertTrue(all(p["track_policy_applied"] == "separate-fallback" for p in plans))

    def test_conflicting_source_identity_is_rejected(self):
        with self.assertRaises(FLPExportError):
            _plan_midi_candidate_tracks([region(2, source=7), region(2, source=8)], [], 500,
                                        "candidate-bindings")

    def test_playlist_storage_range_is_checked_for_bound_and_fallback_rows(self):
        for regions, audio, policy in (([region(2)], [], "candidate-bindings"),
                                      ([region()], [2], "separate")):
            with self.subTest(policy=policy), self.assertRaises(FLPExportError):
                _plan_midi_candidate_tracks(regions, audio, 4, policy)

    def test_invalid_policy_is_rejected(self):
        with self.assertRaises(FLPExportError):
            _plan_midi_candidate_tracks([], [], 500, "invalid")

    def test_cli_passes_policy_and_keeps_midi_only_audio_free(self):
        with (patch("band2flp.cli.parse_band", return_value=Project()),
              patch("band2flp.cli.extract_referenced_audio") as extract,
              patch("band2flp.cli.export_flp", return_value={}) as export,
              redirect_stdout(io.StringIO())):
            result = main(["export-flp", "synthetic.band", "preview.flp", "--template", "blank.flp",
                           "--midi-only", "--midi-track-policy", "candidate-bindings"])
        self.assertEqual(result, 0)
        self.assertEqual(export.call_args.kwargs["midi_track_policy"], "candidate-bindings")
        self.assertTrue(export.call_args.kwargs["include_midi_candidates"])
        extract.assert_not_called()

    def test_cli_rejects_grouping_when_midi_export_is_disabled(self):
        with (patch("band2flp.cli.parse_band", return_value=Project()),
              patch("band2flp.cli.extract_referenced_audio") as extract,
              patch("band2flp.cli.export_flp") as export,
              redirect_stderr(io.StringIO())):
            result = main(["export-flp", "synthetic.band", "preview.flp", "--template", "blank.flp",
                           "--midi-track-policy", "candidate-bindings"])
        self.assertEqual(result, 2)
        extract.assert_not_called()
        export.assert_not_called()

    @unittest.skipUnless(os.environ.get("BAND2FLP_TEST_TEMPLATE"), "local blank FLP template required")
    def test_real_export_roundtrip_groups_two_patterns_and_preserves_unbound_region(self):
        regions = []
        for index in range(2):
            regions.append(UnplacedMidiRegionCandidate(
                start_beats_candidate=str(index * 4), label_candidate="Synthetic",
                notes=[MidiNoteCandidate("0", "1", 60 + index, 64, 1, 8, index)],
                source_mseq_chunk_index=index + 1, source_placement_chunk_index=8,
                source_placement_event_index=index,
                unknown=region(2).unknown,
            ))
        regions.append(UnplacedMidiRegionCandidate(
            start_beats_candidate="8", label_candidate="Synthetic unbound",
            notes=[MidiNoteCandidate("0", "1", 64, 64, 1, 8, 2)],
            source_mseq_chunk_index=3, source_placement_chunk_index=8,
            source_placement_event_index=2,
            unknown={"candidate_track_binding": {"status": "unavailable", "reason": "synthetic_missing_link"}},
        ))
        project = Project(tempo_bpm=120, time_signature=(4, 4), unplaced_midi_regions=regions)
        with tempfile.TemporaryDirectory() as directory:
            result = export_flp(project, template_path=os.environ["BAND2FLP_TEST_TEMPLATE"],
                                output_path=Path(directory) / "synthetic.flp", media_by_reference={},
                                include_midi_candidates=True, midi_track_policy="candidate-bindings")
            summary = result["summary"]
        self.assertEqual(summary["midi_candidate_patterns"], 3)
        self.assertEqual(summary["midi_candidate_channels"], 2)
        self.assertEqual(summary["midi_candidate_track_rows"], 2)
        self.assertEqual(summary["midi_track_fallback_count"], 1)
        self.assertEqual(summary["audio_channels"], 0)
        self.assertEqual([item["channel_iid"] for item in summary["midi_candidates"]], [0, 0, 1])
        self.assertEqual([item["playlist_track_index"] for item in summary["midi_candidates"]], [3, 3, 4])
        self.assertEqual(summary["midi_candidates"][2]["fallback_reason"], "synthetic_missing_link")
        self.assertTrue(any("unconfirmed" in warning for warning in summary["warnings"]))


if __name__ == "__main__":
    unittest.main()
