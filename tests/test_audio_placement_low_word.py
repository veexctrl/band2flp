import struct

import pytest

from band2flp.model import MediaReference, Project
from band2flp.parser import _attach_audio_placements, _parse_audio_placements


def record(low_word=0, byte1=0, bad_marker=False):
    raw = bytearray(80)
    raw[0:2] = bytes((0x24, byte1))
    struct.pack_into("<H", raw, 2, low_word)
    struct.pack_into("<I", raw, 4, 34560 + 16 * 960)
    raw[0x14] = 2
    for offset, marker in zip((0x17, 0x27, 0x37, 0x47), (0x89, 0xBC, 0x8A, 0x89)):
        raw[offset] = marker
    struct.pack_into("<I", raw, 0x2C, 3)
    if bad_marker:
        raw[0x37] = 0
    return {"type_byte": 0x24, "raw_hex": raw.hex(),
            "chunk_index": 1, "event_index": 0, "group_id_candidate": 0}


@pytest.mark.parametrize("low_word", [0, 1, 65535])
def test_unknown_low_word_is_preserved_without_becoming_fractional_timing(low_word):
    placements = _parse_audio_placements({"records": [record(low_word)]})
    assert len(placements) == 1
    assert placements[0]["u16_at_0x02_candidate"] == low_word
    assert "UNKNOWN" in placements[0]["u16_at_0x02_interpretation"]
    assert placements[0]["start_beats"] == "16"
    project = Project(media_references=[MediaReference(
        index=0, category="AudioFiles", reference="synthetic.caf", group_id_candidate=3 << 16,
    )])
    _attach_audio_placements(project, placements)
    assert project.tracks[0].index == 1
    region = project.tracks[0].regions[0]
    assert region.source == "synthetic.caf"
    assert region.start_beats == "16"
    assert region.duration_beats is None
    assert region.source_offset_beats is None
    assert region.unknown["placement"]["u16_at_0x02_candidate"] == low_word


@pytest.mark.parametrize("item", [record(1, bad_marker=True), record(1, byte1=1)])
def test_relaxation_keeps_other_family_filters(item):
    assert _parse_audio_placements({"records": [item]}) == []
