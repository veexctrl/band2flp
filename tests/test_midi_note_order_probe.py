from research.scripts.midi_note_order_probe import inventory_note_order


def _note(group, chunk, event, whole, fraction=0, pitch=60, duration=480):
    return {
        "source_group_id_candidate": group,
        "source_chunk_index": chunk,
        "source_event_index": event,
        "position_raw": whole,
        "position_fraction_raw": fraction,
        "pitch_candidate": pitch,
        "duration_ticks_candidate": duration,
    }


def test_inventory_counts_onset_order_per_group_and_sorts_serialized_order():
    notes = [
        _note(1, 2, 1, 4),
        _note(1, 1, 1, 2, pitch=60),
        _note(1, 1, 2, 2, pitch=64),
        _note(1, 2, 2, 1),
        _note(2, 8, 3, 10),
        _note(2, 8, 4, 10, pitch=62, duration=240),
    ]
    assert inventory_note_order(notes) == {
        "groups": 2,
        "adjacent_pairs": 4,
        "nondecreasing": 3,
        "strictly_increasing": 1,
        "ties": 2,
        "decreases": 1,
        "shared_onset_groups": 2,
        "extra_events_at_shared_onsets": 2,
        "distinct_pitch_shared_onsets": 2,
        "repeated_pitch_shared_onsets": 0,
        "same_duration_shared_onsets": 1,
        "mixed_duration_shared_onsets": 1,
    }


def test_inventory_ignores_incomplete_candidates():
    assert inventory_note_order([{"source_group_id_candidate": 1}]) == {
        "groups": 0,
        "adjacent_pairs": 0,
        "nondecreasing": 0,
        "strictly_increasing": 0,
        "ties": 0,
        "decreases": 0,
        "shared_onset_groups": 0,
        "extra_events_at_shared_onsets": 0,
        "distinct_pitch_shared_onsets": 0,
        "repeated_pitch_shared_onsets": 0,
        "same_duration_shared_onsets": 0,
        "mixed_duration_shared_onsets": 0,
    }
