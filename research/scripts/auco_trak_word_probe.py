"""Test bounded AuCO prefix word equality against Trak reference candidates.

Matches can overlap header fields or represent ordinal coincidences. No
channel identity or mixer-state interpretation is assigned. Output omits
source labels, raw bytes and matching word values.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from band2flp.parser import _parse_chunk_stream


def profile_payload(data: bytes) -> dict:
    chunks = _parse_chunk_stream(data)["chunks"]
    tracks = [c for c in chunks if c["type"] == "Trak" and c["payload_size"] == 58]
    strips = [c for c in chunks if c["type"] == "AuCO"
              and data[c["offset"] + 4:c["offset"] + 8] == bytes.fromhex("07000e00")]
    families = []
    for group in (0x40000, 0x80000):
        words = Counter(struct.unpack_from("<I", data, c["payload_offset"] + 8)[0]
                        for c in tracks if c["group_id_candidate"] == group)
        words.pop(0, None)
        positions = []
        for relative in range(-36, 125):
            values = [struct.unpack_from("<I", data, c["payload_offset"] + relative)[0]
                      for c in strips if c["payload_size"] >= relative + 4]
            hits = Counter(value for value in values if value in words)
            if hits:
                positions.append({
                    "payload_relative_offset": relative,
                    "rows_with_word_match": sum(hits.values()),
                    "distinct_matching_words": len(hits),
                    "unique_in_both_families": sum(count == 1 and words[word] == 1
                                                   for word, count in hits.items()),
                })
        families.append({"trak_group_candidate": group,
                         "distinct_nonzero_trak_words": len(words),
                         "positions_with_matches": positions})
    return {"auco_variant_record_count": len(strips), "families": families}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("components", nargs="+", type=Path)
    args = parser.parse_args()
    for index, path in enumerate(args.components, 1):
        print(json.dumps({"fixture_index": index, **profile_payload(path.read_bytes())}))


if __name__ == "__main__":
    main()
