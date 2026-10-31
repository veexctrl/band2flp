"""Synthetic package coverage for CAF metadata after a sized data chunk."""

import io
import plistlib
import zipfile

import pytest

from band2flp.caf import LOOP_METADATA_UUID
from band2flp.parser import parse_band


def chunk(tag, payload):
    return tag + len(payload).to_bytes(8, "big", signed=True) + payload


@pytest.mark.parametrize("compression,recovered", [
    (zipfile.ZIP_STORED, True), (zipfile.ZIP_DEFLATED, False),
])
def test_parser_recovers_post_data_tags_only_when_member_supports_fast_seek(tmp_path, compression, recovered):
    caf = b"caff\0\x01\0\0" + chunk(b"data", bytes(1024 * 1024))
    caf += chunk(b"uuid", LOOP_METADATA_UUID + (1).to_bytes(4, "big") + b"beat count\0" + b"4\0")
    archive = {
        "$archiver": "NSKeyedArchiver", "$version": 100000,
        "$top": {"DfDocument logic model": {"CF$UID": 1}},
        "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}},
                     {"NS.data": bytes.fromhex("2347c0ab") + bytes(20)}],
    }
    path = tmp_path / "synthetic.band"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("fixture.band/projectData", plistlib.dumps(archive))
        package.writestr("fixture.band/Output/assetsmetadata.plist", plistlib.dumps({
            "AudioFiles": ["${CONTENT:loops/synthetic.caf"],
        }))
        package.writestr("fixture.band/Audio Files/synthetic.caf", caf, compress_type=compression)
    project = parse_band(path)
    assert len(project.media_references) == 1
    metadata = project.media_references[0].source_loop_metadata
    if recovered:
        assert metadata["beat_count"] == 4
    else:
        assert metadata is None


def test_stored_member_seek_skips_bulk_payload_reads():
    from band2flp.caf import inspect_caf_loop_metadata

    class TrackedFile(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.read_bytes = 0

        def read(self, size=-1):
            data = super().read(size)
            self.read_bytes += len(data)
            return data

    stream = TrackedFile()
    caf = b"caff\0\x01\0\0" + chunk(b"data", bytes(1024 * 1024))
    caf += chunk(b"uuid", LOOP_METADATA_UUID + (1).to_bytes(4, "big") + b"beat count\0" + b"4\0")
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("synthetic.caf", caf)
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        with archive.open("synthetic.caf") as member:
            stream.read_bytes = 0
            result = inspect_caf_loop_metadata(member, allow_data_seek=True)
            assert result["beat_count"] == 4
            # Permit ZIP buffering while rejecting a seek implemented by
            # reading the complete 1 MiB synthetic sample payload.
            assert stream.read_bytes < 64 * 1024
