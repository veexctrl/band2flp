"""Compare raw files or identically named ZIP members without assuming a format."""

from __future__ import annotations

import argparse
import json
import math
import struct
import zipfile
from pathlib import Path
from typing import Any

MAX_COMPONENT_SIZE = 512_000_000


def load_component(path: Path, suffix: str | None) -> tuple[bytes, str]:
    if not zipfile.is_zipfile(path):
        if suffix:
            raise ValueError("--member-suffix requires ZIP package inputs")
        data = path.read_bytes()
        if len(data) > MAX_COMPONENT_SIZE:
            raise ValueError("input exceeds the component size limit")
        return data, "<raw file>"

    with zipfile.ZipFile(path) as archive:
        if suffix is None:
            raise ValueError("ZIP inputs require --member-suffix")
        matches = [item for item in archive.infolist() if item.filename.endswith(suffix)]
        if len(matches) != 1:
            raise ValueError(f"member suffix {suffix!r} matched {len(matches)} entries in {path.name}")
        item = matches[0]
        if item.file_size > MAX_COMPONENT_SIZE:
            raise ValueError("ZIP member exceeds the component size limit")
        return archive.read(item), item.filename


def changed_ranges(left: bytes, right: bytes) -> list[dict[str, Any]]:
    """Return positional changed runs; offsets after insertions are not realigned."""
    ranges: list[dict[str, Any]] = []
    limit = max(len(left), len(right))
    start: int | None = None
    for offset in range(limit):
        differs = offset >= len(left) or offset >= len(right) or left[offset] != right[offset]
        if differs and start is None:
            start = offset
        elif not differs and start is not None:
            ranges.append(_range(left, right, start, offset))
            start = None
    if start is not None:
        ranges.append(_range(left, right, start, limit))
    return ranges


def _range(left: bytes, right: bytes, start: int, end: int) -> dict[str, Any]:
    return {
        "offset_start": start,
        "offset_end_exclusive": end,
        "left_hex": left[start:min(end, len(left))].hex(),
        "right_hex": right[start:min(end, len(right))].hex(),
    }


def scalar_candidates(left: bytes, right: bytes, offset: int) -> dict[str, Any]:
    """Show common numeric interpretations at an offset as hypotheses only."""
    result: dict[str, Any] = {}
    for width in (2, 4, 8):
        if offset + width > len(left) or offset + width > len(right):
            continue
        before = left[offset:offset + width]
        after = right[offset:offset + width]
        result[f"u{width * 8}_little"] = [int.from_bytes(before, "little"), int.from_bytes(after, "little")]
        result[f"u{width * 8}_big"] = [int.from_bytes(before, "big"), int.from_bytes(after, "big")]
        if width in (4, 8):
            code = "f" if width == 4 else "d"
            a, b = struct.unpack("<" + code, before)[0], struct.unpack("<" + code, after)[0]
            result[f"float{width * 8}_little"] = [a if math.isfinite(a) else repr(a), b if math.isfinite(b) else repr(b)]
    return result


def compare(left: bytes, right: bytes) -> dict[str, Any]:
    ranges = changed_ranges(left, right)
    for item in ranges[:100]:
        item["numeric_candidates_at_start"] = scalar_candidates(left, right, item["offset_start"])
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(left) - prefix, len(right) - prefix) and left[-1 - suffix] == right[-1 - suffix]:
        suffix += 1
    return {
        "left_size": len(left),
        "right_size": len(right),
        "common_prefix_size": prefix,
        "common_suffix_size": suffix,
        "changed_range_count": len(ranges),
        "changed_ranges": ranges[:100],
        "ranges_truncated": len(ranges) > 100,
        "alignment_warning": "Ranges compare absolute offsets; insertions can shift later data. Numeric interpretations are candidates, not field identifications.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--member-suffix", help="unique ZIP member suffix, such as /projectData")
    args = parser.parse_args()
    try:
        left, left_name = load_component(args.left, args.member_suffix)
        right, right_name = load_component(args.right, args.member_suffix)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.error(str(exc))
    result = compare(left, right)
    result["left_component"] = left_name
    result["right_component"] = right_name
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
