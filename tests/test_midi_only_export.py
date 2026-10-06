import io
import json
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from band2flp.cli import main
from band2flp.model import Project, Region, Track


class MidiOnlyExportTests(unittest.TestCase):
    def test_midi_only_export_drops_audio_regions_and_skips_extraction(self) -> None:
        project = Project(
            tracks=[Track(index=0, regions=[Region(kind="audio", source="private-audio")])],
            unplaced_midi_regions=[SimpleNamespace(notes=[object()])],
        )
        captured: dict[str, object] = {}

        def fake_export_flp(actual_project: Project, **kwargs: object) -> dict[str, object]:
            captured["project"] = actual_project
            captured["kwargs"] = kwargs
            return {"audio_channels": 0, "midi_candidate_patterns": 1}

        output = io.StringIO()
        with (
            patch("band2flp.cli.parse_band", return_value=project),
            patch("band2flp.cli.extract_referenced_audio", side_effect=AssertionError("audio extraction called")),
            patch("band2flp.cli.export_flp", side_effect=fake_export_flp),
            redirect_stdout(output),
        ):
            result = main([
                "export-flp", "synthetic.band", "preview.flp",
                "--template", "blank.flp", "--midi-only",
            ])

        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(captured["project"].tracks, [])
        self.assertTrue(captured["kwargs"]["include_midi_candidates"])
        self.assertEqual(report["audio_channels"], 0)
        self.assertEqual(report["media_extraction"], {
            "skipped": True,
            "file_count": 0,
            "unresolved_reference_count": 0,
        })

    def test_midi_only_export_rejects_audio_options(self) -> None:
        output = io.StringIO()
        with (
            patch("band2flp.cli.parse_band", return_value=Project()),
            patch("band2flp.cli.extract_referenced_audio") as extract,
            redirect_stderr(output),
        ):
            result = main([
                "export-flp", "synthetic.band", "preview.flp",
                "--template", "blank.flp", "--midi-only", "--to-wav",
            ])

        self.assertEqual(result, 2)
        self.assertIn("cannot be combined with audio export options", output.getvalue())
        extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
