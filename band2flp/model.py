"""Neutral model types; unknown GarageBand structures remain explicitly unknown."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Region:
    name: str | None = None
    start_beats: str | None = None
    duration_beats: str | None = None
    source_offset_beats: str | None = None
    kind: str = "unknown"
    source: str | None = None
    muted: bool | None = None
    unknown: dict[str, Any] = field(default_factory=dict)


@dataclass
class Track:
    index: int
    name: str | None = None
    kind: str = "unknown"
    regions: list[Region] = field(default_factory=list)
    unknown: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaReference:
    index: int
    category: str
    reference: str
    package_member: str | None = None
    source_chunk_index: int | None = None
    group_id_candidate: int | None = None
    related_region_chunk_indices: list[int] = field(default_factory=list)
    name_matched_region_chunk_indices: list[int] = field(default_factory=list)
    region_chunk_metadata_candidates: list[dict[str, Any]] = field(default_factory=list)
    unknown: dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    source_format: str = "GarageBand .band ZIP package"
    tempo_bpm: float | None = None
    time_signature: tuple[int, int] | None = None
    tempo_map: list[dict[str, Any]] = field(default_factory=list)
    time_signatures: list[dict[str, Any]] = field(default_factory=list)
    duration_value: float | None = None
    declared_track_count: int | None = None
    tracks: list[Track] = field(default_factory=list)
    media_references: list[MediaReference] = field(default_factory=list)
    package_members: list[dict[str, Any]] = field(default_factory=list)
    project_data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.time_signature is not None:
            result["time_signature"] = {
                "numerator": self.time_signature[0],
                "denominator": self.time_signature[1],
            }
        return result
