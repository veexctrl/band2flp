# Audio placement extent candidates

Audio `Region` objects expose `placement_extent_beats_candidate` separately
from `duration_beats`. This preserves the finite placement `+0x1c` word as
an exact rational number divided by the candidate PPQ. The normalization is
arithmetic, not confirmation of units or duration semantics.

Zero and `0x3fffffff` yield no normalized candidate. Their raw values remain
in `unknown.placement`. Invalid or out-of-range values also yield no candidate.

The FLP JSON sidecar carries the candidate on each exported audio item.
`length_ticks` and `length_basis` describe what was actually written to the
FLP; the candidate does not override them. A known duration continues to set
clip length, and unknown durations still require an explicit placeholder
policy. This permits later boundary comparisons without losing source evidence.

Source-frame windows, placement extents and confirmed durations remain
distinct. See [ARR-047](reverse-engineering/audio-source-window-limits.md)
for the repeated-window counterexample and its interpretation limits.

Synthetic tests cover exact fractional normalization, sentinel handling,
neutral JSON preservation, and reporting a candidate that differs from a
known clip duration through an FLP save/parse round trip.
