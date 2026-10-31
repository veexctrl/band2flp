from research.scripts.placement_word_layout_probe import profile_records


def row(event_type, markers, low_word=0, byte1=0, extent_low=0):
    raw = bytearray(80)
    raw[0], raw[1] = event_type, byte1
    raw[2:4] = low_word.to_bytes(2, "little")
    raw[0x1A:0x1C] = extent_low.to_bytes(2, "little")
    for offset, marker in zip((0x17, 0x27, 0x37, 0x47), markers):
        raw[offset] = marker
    return {"raw_hex": raw.hex()}


def test_word_audit_does_not_select_only_zero_prefixes():
    markers = (0x89, 0x88, 0x8A, 0x88)
    report = profile_records([
        row(0x20, markers),
        row(0x20, markers, low_word=123, extent_low=456),
        row(0x20, markers, byte1=1),
        row(0x20, (0, 0, 0, 0), low_word=1),
        {"raw_hex": "20"},
    ])
    assert report["midi"] == {
        "marker_selected_count": 3,
        "nonzero_byte_0x01_count": 1,
        "nonzero_word_0x02_count": 1,
        "nonzero_word_0x1a_count": 1,
        "zero_prefix_filter_exclusion_count": 2,
    }
    assert all(value == 0 for value in report["audio"].values())


def test_word_audit_distinguishes_audio_marker_family():
    report = profile_records([row(0x24, (0x89, 0xBC, 0x8A, 0x89), low_word=1)])
    assert report["audio"]["marker_selected_count"] == 1
    assert report["audio"]["zero_prefix_filter_exclusion_count"] == 1
    assert report["midi"]["marker_selected_count"] == 0
