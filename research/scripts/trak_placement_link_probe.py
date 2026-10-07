"""Test Trak/placement word joins without emitting identifiers or music."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
from typing import Any

from band2flp.parser import (
    BandFormatError, _parse_chunk_stream, _parse_event_sequences,
    _parse_audio_placements, _parse_midi_region_placement_candidates,
    _parse_midi_note_candidates,
)
from research.scripts.midi_region_timing_probe import _payload_from_archive


def profile_links(raw: bytes, stream: dict[str, Any]) -> dict[str, Any]:
    """Compare payload +8 in 58-byte Trak records with placement +16.

    Group values scope separate candidate families. They are not track kinds.
    Zero fields never establish links. Multiplicity is checked per family.
    """
    by_group: dict[int, Counter[int]] = defaultdict(Counter)
    ordered_words: dict[int, list[int]] = defaultdict(list)
    for chunk in stream.get("chunks", []):
        start, size = chunk.get("payload_offset"), chunk.get("payload_size")
        if (not isinstance(start, int) or not isinstance(size, int)
                or size < 0 or not 0 <= start <= len(raw) - size):
            raise BandFormatError("chunk payload bounds are invalid")
        if chunk.get("type") == "Trak" and size == 58:
            word = struct.unpack_from("<I", raw, start + 8)[0]
            group = chunk["group_id_candidate"]
            by_group[group][word] += 1
            ordered_words[group].append(word)
    events = _parse_event_sequences(raw, stream)
    audio = _parse_audio_placements(events)
    midi = _parse_midi_region_placement_candidates(events, stream)
    notes = _parse_midi_note_candidates(events, stream)
    note_mseq_indices = {
        index for note in notes for index in note["candidate_mseq_chunk_indices_for_group"]
    }
    with_notes, without_notes, ambiguous = [], [], []
    for placement in midi:
        links = placement["candidate_mseq_chunk_indices"]
        if len(links) != 1:
            ambiguous.append(placement)
        elif links[0] in note_mseq_indices:
            with_notes.append(placement)
        else:
            without_notes.append(placement)
    categories = (("audio", audio), ("midi", midi),
                  ("midi_with_note_candidates", with_notes),
                  ("midi_without_note_candidates", without_notes),
                  ("midi_with_ambiguous_mseq_link", ambiguous))
    families = {}
    for group, counts in sorted(by_group.items()):
        kinds = {}
        ordinals = {word: index + 1 for index, word in enumerate(ordered_words[group])}
        for label, placements in categories:
            words = [p["event_id_candidate"] for p in placements]
            kinds[label] = {
                "placement_count": len(words),
                "unique_nonzero_word_match_count": sum(w != 0 and counts[w] == 1 for w in words),
                "ambiguous_nonzero_word_match_count": sum(w != 0 and counts[w] > 1 for w in words),
                "unmatched_or_zero_word_count": sum(w == 0 or counts[w] == 0 for w in words),
                "unique_word_file_order_1_based_equals_track_byte_count": sum(
                    word != 0 and counts[word] == 1 and ordinals[word] == (
                        p["track_number_1_based_candidate"] if label == "audio"
                        else p["track_value_candidate"]
                    ) for p, word in zip(placements, words)
                ),
            }
        families[f"0x{group:08X}"] = {
            "record_count": sum(counts.values()),
            "distinct_nonzero_word_count": sum(w != 0 for w in counts),
            "zero_word_record_count": counts[0],
            "placement_comparisons": kinds,
        }
    first, second = by_group.get(0x00040000, Counter()), by_group.get(0x00080000, Counter())
    shared = (first.keys() & second.keys()) - {0}
    track_bytes: dict[int, set[int]] = defaultdict(set)
    for p in audio:
        track_bytes[p["event_id_candidate"]].add(p["track_number_1_based_candidate"])
    for p in midi:
        track_bytes[p["event_id_candidate"]].add(p["track_value_candidate"])
    note_and_audio_bytes: dict[int, set[int]] = defaultdict(set)
    for p in audio:
        note_and_audio_bytes[p["event_id_candidate"]].add(p["track_number_1_based_candidate"])
    for p in with_notes:
        note_and_audio_bytes[p["event_id_candidate"]].add(p["track_value_candidate"])
    return {
        "trak_families": families,
        "group4_group8_shared_nonzero_word_count": len(shared),
        "group4_group8_unique_pair_count": sum(first[w] == second[w] == 1 for w in shared),
        "combined_placement_word_group_count": len(track_bytes),
        "combined_placement_word_groups_with_one_track_byte": sum(len(v) == 1 for v in track_bytes.values()),
        "combined_placement_word_groups_with_conflicting_track_bytes": sum(len(v) > 1 for v in track_bytes.values()),
        "audio_and_note_bearing_midi_word_group_count": len(note_and_audio_bytes),
        "note_bearing_midi_nonzero_word_group_count": len({
            p["event_id_candidate"] for p in with_notes if p["event_id_candidate"] != 0
        }),
        "audio_and_note_bearing_midi_word_groups_with_conflicting_track_bytes": sum(
            len(v) > 1 for v in note_and_audio_bytes.values()
        ),
        "confidence": "UNKNOWN: word equalities are candidate links, not confirmed arrangement track identity",
        "privacy_note": "Counts and structural family values only; identifiers, labels, music and paths omitted.",
    }


def probe(path: Path) -> dict[str, Any]:
    raw = _payload_from_archive(path)
    return profile_links(raw, _parse_chunk_stream(raw))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        report = probe(args.project)
    except (BandFormatError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
