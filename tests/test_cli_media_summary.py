import io
from contextlib import redirect_stdout
from unittest.mock import patch

from band2flp.cli import main
from band2flp.model import MediaReference, Project, Region, Track


def test_text_inspection_breaks_media_references_down_by_category():
    project = Project(media_references=[
        MediaReference(index=0, category="AudioFiles", reference="sample-a.caf", package_member="AudioFiles/sample-a.caf"),
        MediaReference(index=1, category="AudioFiles", reference="external/sample-b.caf"),
        MediaReference(index=2, category="SamplerInstrumentsFiles", reference="instrument.dat", package_member="Sampler/instrument.dat"),
    ])
    output = io.StringIO()

    with patch("band2flp.cli.parse_band", return_value=project), redirect_stdout(output):
        result = main(["inspect", "synthetic.band"])

    assert result == 0
    assert "Media references: 3 (2 matched to package members)" in output.getvalue()
    assert "AudioFiles: 2 (1 matched)" in output.getvalue()
    assert "SamplerInstrumentsFiles: 1 (1 matched)" in output.getvalue()
    assert "sample-a.caf" not in output.getvalue()


def test_text_inspection_labels_provisional_track_index_confidence():
    project = Project(
        tracks=[Track(index=2, kind="audio", index_confidence="HYPOTHESIS", regions=[
            Region(kind="audio", name="clip", source="AudioFiles/clip.caf", start_beats="4"),
        ])],
        project_data={"audio_placements": [{}]},
    )
    output = io.StringIO()

    with patch("band2flp.cli.parse_band", return_value=project), redirect_stdout(output):
        result = main(["inspect", "synthetic.band"])

    assert result == 0
    assert "Track 3 (index confidence: HYPOTHESIS): clip at beat 4" in output.getvalue()
