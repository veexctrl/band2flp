import struct

import pytest

from band2flp.parser import BandFormatError
from research.scripts.auco_trak_word_probe import profile_payload


def chunk(tag, payload, group=0, variant=bytes(4)):
    header = bytearray(36)
    header[:4] = tag[::-1].encode()
    header[4:8] = variant
    struct.pack_into("<I", header, 8, group)
    struct.pack_into("<Q", header, 28, len(payload))
    return header + payload


def fixture(duplicate=False):
    data = bytes.fromhex("2347c0ab") + bytes(20)
    for word in (0, 0x11223344, 0x11223344 if duplicate else 0x55667788):
        payload = bytearray(58)
        struct.pack_into("<I", payload, 8, word)
        data += chunk("Trak", payload, group=0x40000)
    for word in (0x11223344, 0x55667788):
        payload = bytearray(16)
        struct.pack_into("<I", payload, 8, word)
        data += chunk("AuCO", payload, variant=bytes.fromhex("07000e00"))
    return data


def test_unique_word_links_are_counted_without_emitting_values():
    result = profile_payload(fixture())
    family = result["families"][0]
    position = next(p for p in family["positions_with_matches"] if p["payload_relative_offset"] == 8)
    assert family["distinct_nonzero_trak_words"] == 2
    assert position["rows_with_word_match"] == 2
    assert position["unique_in_both_families"] == 2
    assert result["families"][1]["positions_with_matches"] == []
    assert str(0x11223344) not in str(result)


def test_duplicate_trak_words_do_not_become_unique_links():
    result = profile_payload(fixture(duplicate=True))
    positions = result["families"][0]["positions_with_matches"]
    position = next(p for p in positions if p["payload_relative_offset"] == 8)
    assert position["unique_in_both_families"] == 0


def test_truncated_components_are_rejected():
    with pytest.raises(BandFormatError):
        profile_payload(fixture()[:-1])
