# MIDI-024 — source extents and coordinate-system correction

## Question

Do the note-bearing MSeq tail words explain region extents better than the final note end? Does MIDI-022's failed shifted containment comparison actually contradict a Logic-style placement shift?

## Coordinate systems

The independent [Logic MIDI implementation](https://github.com/loov/logicx/blob/main/midi.go) uses an MSeq source duration, signed position shift and separate region-link extent. Its shifted positions are checked against placed-region bounds. These are cross-format hypotheses for GarageBand, not confirmed source meanings.

The old probe added the signed shift to candidate note positions but compared them with a region end measured from zero. Its three-of-five result is descriptive only and cannot falsify the placed-shift interpretation for nonzero region starts. The revised integer-word comparison is:

```text
note relative candidate = note +0x04 u32 - 38,400
placed start candidate  = placement +0x04 u32 - 34,560
shift candidate         = MSeq end-minus-55 i32
source extent candidate = MSeq end-minus-219 u32

placed start <= note relative + shift
             <= note relative + duration word + shift
             <= placed start + source extent
```

This comparison uses the same frame for both bounds. It intentionally excludes the unverified 16-bit fractional-word scaling. Integer arithmetic consistency does not prove the origins or units.

## Observations

The note-bearing fixture has five uniquely linked MSeq groups containing all 133 note-shaped candidates:

- All five source-extent words are nonzero multiples of the candidate 960 PPQ. This is a descriptive alignment, not a requirement for tick durations.
- All five exceed the maximum candidate integer note end and contain the integer note bounds in the placed frame.
- In two groups, the source word is smaller than the candidate placement start. Under the existing coordinate/unit assumptions, it cannot itself be a global timeline end.
- Three placement extent words have the `0x3fffffff` value. The other two exceed their linked source-extent words; both are exactly three halves of the source word.
- Both finite cases start at candidate position zero. They cannot distinguish duration from an absolute end-position interpretation.
- One same-reference consecutive-region pair has a start gap equal to the preceding source word, exceeding that region's last integer note end. The reference association is supported by TRK-016/TRK-017, but its track identity remains provisional.

The other supplied fixture has no recognized note-shaped candidates and supplies no corresponding note-bound comparison.

## Validation

Run `python -m research.scripts.mseq_timing_relations_probe example.band`. The added results are aggregate counts; legacy shifted counts remain available with an explicit coordinate-system warning. Synthetic tests cover a negative shift whose placed bounds are valid despite failure against an origin-zero end, a finite three-halves ratio without assuming repeats, and adjacent regions whose source extent exceeds their final note end.

The current archive payload matches its headless IDA input byte for byte. IDA read five MSeq source words, five shifts, ten placement position/extent words, and 266 note position/duration words. All **286** reads match Python. The saved cached arrangement image was independently matched byte for byte to an archive member. Its cropped timeline does not show the full extents, so it cannot validate the longer regions or repeat behavior. Neither the image nor source-derived music is published.

## Interpretation and alternatives

**CONFIRMED for this fixture:** the byte reads, integer containment in the consistent frame, two numeric ratios and one adjacent-pair equality. MIDI-022's prior materialization warning is withdrawn because it used mismatched bounds.

**HYPOTHESIS:** end minus 219 is a source-sequence extent, and finite placement words describe a longer placed extent. The aligned source words, positive trailing gaps and adjacent-pair equality support this lead, but there are no controlled duration edits.

**UNKNOWN:** whether the longer extent means repeats, stretch, section bounds or another cached limit. Repetition is plausible under the Logic interpretation; stretching is an alternative. The sentinel's GarageBand meaning, trim semantics, fractional positions and nonzero-start finite extents remain unresolved. The same-reference pair is one uncontrolled observation, not independent proof of a duration field.

## Implementation consequences

The FLP preview still uses last-note bounds and does not materialize repeat or stretch behavior. That policy can omit trailing silence and does not reproduce a longer placed extent. Preserve both source and placement candidates at the neutral boundary before experimenting with any separately labeled extent policy. Require explicit diagnostics and retain original note data; do not silently introduce repeats or promote source words into confirmed duration.
