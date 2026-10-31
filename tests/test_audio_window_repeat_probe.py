from band2flp.model import Project, Region, Track
from research.scripts.audio_window_repeat_probe import profile_project


def region(source="synthetic.caf", start="0", extent=960, links=None):
    return Region(kind="audio", source=source, start_beats=start, unknown={
        "placement": {"u32_at_0x1c_candidate": extent},
        "region_chunk_indices_matching_0x8a_to_0x28_candidate": [1] if links is None else links,
        "candidate_region_chunk_metadata_for_source": [{
            "chunk_index": 1, "filename_stem_matches": True,
            "payload_u32_at_0x06_candidate": 0,
            "payload_u32_at_0x16_candidate": 100,
        }],
    })


def profile(*regions):
    return profile_project(Project(tracks=[Track(index=0, regions=list(regions))]))


def test_same_window_can_have_finite_and_sentinel_extent_without_duration_claim():
    result = profile(region(), region(start="4", extent=0x3FFFFFFF))
    assert result["linked_records"] == 2
    assert result["repeated_buckets"] == 1
    assert result["repeated_buckets_with_different_starts"] == 1
    assert result["repeated_buckets_with_different_extent_words"] == 1
    assert result["repeated_buckets_with_finite_and_sentinel_extents"] == 1
    assert all(type(value) is int for value in result.values())


def test_distinct_sources_and_ambiguous_links_are_not_merged():
    result = profile(region(), region(source="other.caf"), region(links=[1, 2]), region(source=None))
    assert result["distinct_source_window_buckets"] == 2
    assert result["repeated_buckets"] == 0
    assert result["skipped_audio_regions"] == 2


def test_missing_words_and_duplicate_metadata_are_not_links():
    missing = region()
    del missing.unknown["candidate_region_chunk_metadata_for_source"][0]["payload_u32_at_0x06_candidate"]
    duplicate = region()
    duplicate.unknown["candidate_region_chunk_metadata_for_source"] *= 2
    result = profile(missing, duplicate)
    assert result["linked_records"] == 0
    assert result["skipped_audio_regions"] == 2


def test_equal_rational_starts_and_zero_extents_are_not_false_variation():
    result = profile(region(start="1/2", extent=0), region(start="0.5", extent=0x3FFFFFFF))
    assert result["repeated_buckets_with_different_starts"] == 0
    assert result["repeated_buckets_with_finite_and_sentinel_extents"] == 0
