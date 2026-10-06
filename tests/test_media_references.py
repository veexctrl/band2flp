from band2flp.parser import _media_references


def _resolve(members):
    return _media_references(
        {"AudioFiles": ["${CONTENT:loops/example.caf"]},
        [{"path": name} for name in members],
        [{
            "asset_reference_index": 0,
            "chunk_index": 7,
            "group_id_candidate": 0x140000,
            "related_AuRg_chunk_indices": [8],
            "name_matched_AuRg_chunk_indices": [8],
            "related_AuRg_metadata_candidates": [],
        }],
    )[0]


def test_unique_embedded_audio_basename_resolves():
    reference = _resolve(["fixture/Audio Files/example.caf"])

    assert reference.package_member == "fixture/Audio Files/example.caf"
    assert reference.unknown == {}


def test_duplicate_embedded_audio_basenames_stay_ambiguous():
    reference = _resolve([
        "fixture/Audio Files/example.caf",
        "fixture/Alternative/example.caf",
    ])

    assert reference.package_member is None
    assert len(reference.unknown["ambiguous_package_member_matches"]) == 2
