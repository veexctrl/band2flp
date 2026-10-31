# ARR-046: nonzero audio placement low word

The former audio placement selector required `24 00 00 00` at the start of
each record. This constrained an unresolved little-endian 16-bit word at
event offset `+0x02` to zero, silently excluding a structurally matching
candidate in the local audio-bearing fixture.

Select the candidate family using type `0x24`, byte `+0x01 == 0`, a minimum
80-byte length, and markers `89 BC 8A 89` at `+0x17`, `+0x27`, `+0x37`, and
`+0x47`. Preserve `+0x02` as `u16_at_0x02_candidate`; its meaning is UNKNOWN.

Independent marker selection yields eleven candidates in the audio-bearing
fixture, one with a nonzero low word. The other fixture has nine candidates,
all with zero low words. The extra candidate's source-group relation and
in-range track-number candidate support the family classification. Full
record reads in headless IDA match the current Python extraction byte for
byte, including the previously excluded record. Package and extracted
component are paired by exact metadata bytes, not counted as separate fixtures.

CONFIRMED: the former filter's exclusion, the raw byte comparisons and the
observed counts. HIGH CONFIDENCE: membership of the additional record in the
placement family. UNKNOWN: low-word semantics, possible timing contribution,
and generalization across other GarageBand projects.

The parser retains the existing integer start calculation without applying
this word. This recovers the candidate's source/track/start association; it
does not prove exact sub-tick timing, duration or trim. A controlled region
move fixture is needed before assigning any fractional interpretation.

Synthetic tests cover zero, nonzero and maximum unsigned low words through
placement parsing and neutral track/region construction. Wrong markers and
nonzero byte `+0x01` remain excluded. Actual FL Studio behavior of a project
containing the extra candidate awaits a GUI check.
