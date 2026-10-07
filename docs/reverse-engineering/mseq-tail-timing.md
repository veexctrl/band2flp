# MIDI-022 — MSeq tail timing comparisons

## Question and method

Do the end-relative fields in the independent [Logic Pro MIDI implementation](https://github.com/loov/logicx/blob/main/midi.go) have useful relationships to GarageBand placement and note candidates?

MIDI-013 previously inventoried the words without comparing their relationships. MIDI-015 tested different, fixed record-relative offsets. This experiment tests two **payload-end-relative** locations:

| Location | Read | Candidate tested |
| --- | --- | --- |
| payload end minus 219 bytes | 4 bytes, unsigned little endian | Sequence length |
| payload end minus 55 bytes | 4 bytes, signed little endian | Position or offset |

Use `python -m research.scripts.mseq_timing_relations_probe example.band`. The script validates chunk bounds and reports aggregate counts only. It joins notes and placements through existing unique MSeq links. It compares the second word with `0x20 +0x04 minus 34,560`; it compares the first word with the maximum candidate integer note end and with nonsentinel `0x20 +0x1c` words. Origins, units and field meanings remain hypotheses transferred from Logic.

## Observations

The two supplied, uncontrolled fixtures contain 35 and 33 MSeq payloads. Both have payload sizes sufficient for the reads. Neither fixture has a zero word at end minus 219. The word at end minus 55 is zero in 30 and 29 payloads respectively.

All 19 and 12 uniquely linked MIDI placements have an end-minus-55 word equal to the candidate placement integer position. These comprise **29 zero matches and two nonzero matches**. Both nonzero matches occur in the note-bearing fixture. Thus the equality is stronger than the zero-only result of the earlier fixed-offset probe, although the fixtures do not establish its behavior under a controlled region move.

The five uniquely linked note-bearing MSeq groups contain all 133 note-shaped candidates. Their end-minus-219 words contain all candidate integer note ends, but none equals the maximum note end. The original shifted comparison counted three of five groups against an origin-zero end; MIDI-024 identifies that comparison as mixing coordinate systems. Comparing both bounds in the placed frame contains all five groups. The two nonsentinel placement words do not equal the linked end-minus-219 words.

117 of the 133 note candidates have a nonzero 16-bit word at note-record `+0x02`; three distinct values occur. The parser retains these raw words. Its current candidate onset in beats uses only the integer position, while its scope comparison also tests a hypothetical fractional-tick interpretation. This inconsistency needs investigation; the denominator and musical meaning are not established by these counts.

## Independent validation

The two raw logic-song files opened in headless IDA were first compared byte for byte with their current archive payloads. The inputs matched. IDA then read all 35 and 33 end-minus-55 words at the parser-derived offsets; all 68 reads matched Python. These are data payloads, with no executable functions. No audio was opened or exported. Synthetic tests cover nonzero and zero equalities, a negative signed offset, containment failures, the placement sentinel, short payloads and invalid bounds.

## Interpretation and alternatives

**CONFIRMED for these fixtures:** the 31 linked word equalities, including two nonzero equalities, and all 68 IDA/Python byte matches.

**HIGH CONFIDENCE:** end minus 55 stores a value related to the linked placement position in these fixtures. This could be duplicated placement metadata, a cache or another related state value. Equality does not prove which copy is authoritative.

**HYPOTHESIS:** the signed word represents a GarageBand region position under the existing origin and unit assumptions. No parser timing field is promoted on this evidence.

**UNKNOWN:** end-minus-219 semantics and fractional-word scaling. A length could exceed its last note because of silence or padding; simple containment also fits unrelated sufficiently large values. Trimmed regions could differ from their source extent. Withdraw the earlier inference that the shifted comparison warned against Logic-style materialization: it compared shifted positions with an unshifted end. MIDI-024 corrects the arithmetic and leaves the GarageBand interpretation unconfirmed.

## Next evidence

Compare a controlled nonzero region move to test which words follow placement; compare a region trim without editing its notes to distinguish source length from visible region length. A controlled fractional note move is needed before incorporating `+0x02` into the candidate onset formula. These inputs are currently unavailable; retain raw data and continue other arrangement research.
