"""Synthetic FLP round-trip for multiple clips sharing one audio channel."""

import os
from pathlib import Path
import tempfile
import unittest
import wave

from band2flp.flp_export import export_flp
from band2flp.model import MediaReference, Project, Region, Track


@unittest.skipUnless(os.environ.get("BAND2FLP_TEST_TEMPLATE"), "local blank FLP template required")
class AudioSharedSourceRoundtripTests(unittest.TestCase):
    def test_clips_with_one_source_keep_separate_lengths_and_positions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "synthetic.wav"
            with wave.open(str(media), "wb") as output:
                output.setparams((1, 2, 44_100, 44_100, "NONE", "not compressed"))
                output.writeframes(bytes(88_200))

            reference = "AudioFiles/synthetic.wav"
            project = Project(
                tempo_bpm=120,
                media_references=[MediaReference(
                    index=0,
                    category="AudioFiles",
                    reference=reference,
                    package_member="synthetic.wav",
                )],
                tracks=[Track(index=0, regions=[
                    Region(kind="audio", source=reference, start_beats="0", duration_beats="2"),
                    Region(kind="audio", source=reference, start_beats="4", duration_beats="3"),
                ])],
            )

            result = export_flp(
                project,
                template_path=os.environ["BAND2FLP_TEST_TEMPLATE"],
                output_path=root / "synthetic.flp",
                media_by_reference={reference: media},
            )

        items = result["summary"]["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["item_index"], items[1]["item_index"])
        self.assertEqual(
            [(item["start_ticks"], item["length_ticks"]) for item in items],
            [(0, 192), (384, 288)],
        )
        self.assertTrue(all(item["length_basis"] == "region-duration" for item in items))


if __name__ == "__main__":
    unittest.main()

