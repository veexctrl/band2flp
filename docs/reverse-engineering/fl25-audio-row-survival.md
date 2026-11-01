# FLP-NATIVE-001: audio row survival and explicit boundaries

## Reproduction

A fresh export contains two silent synthetic WAV clips sharing one source,
plus a four-note synthetic MIDI pattern. At 96 PPQ and 120 BPM, the audio
start/length pairs are `(0, 192)` and `(384, 288)` ticks. The generated playlist
has three 32-byte rows. PyFLP save/parse validation reports all three items.

FL Studio 2025 opens this file without an invalid-playlist or missing-sample
dialog, but displays only the MIDI clip. Native resaving produces one 80-byte
playlist row. Thus a warning-free load and a PyFLP round trip do not prove
that FL retained the audio arrangement.

Dragging the already loaded synthetic audio source from FL's clip picker into
the playlist creates a visible audio clip. This separates source loading from
playlist-row retention. A native save containing that audio clip and MIDI
provides two 80-byte reference rows.

## Controlled layout and flag probes

The native audio row has flags `0x8040`, versus generated `0x0040`. Setting only
bit 15 on the two generated audio rows changes two bytes but does not restore
the clips. A flag-only fix is unsupported.

Preserving every original 32-byte row prefix and appending the corresponding
48-byte native tail by item type creates three 80-byte rows. FL then displays
both audio clips and MIDI without warnings. This validates that particular
layout/tail combination; it does not assign meanings to all tail fields.

Native resaving initially expands both audio clip lengths to the full source
length of 384 ticks. The MIDI length also rounds from 336 to 384 ticks.
Layout correction alone therefore does not preserve arrangement boundaries.

## Controlled native audio trims

Shortening the first native audio clip to two beats changes its length to 192
ticks and its float32 fields at row `+0x18/+0x1c` from `-1/-1` to `0/1000`.
The other two rows remain byte-identical. Independently shortening the second
clip to three beats saves length 288 and offset fields `0/1500`.

The values are consistent with milliseconds at 120 BPM. A follow-up generated
probe uses these explicit audio offsets in the previously successful 80-byte
layout. Both clips display at the intended lengths, and native resaving keeps
both start/length pairs and both offset pairs exactly unchanged.

Headless IDA reads match the generated and native playlist payloads byte for
byte. The complete 240-byte controlled-trim playlist is independently checked.
All media is generated silence; no song recordings were opened or played.
Screenshots are kept out of the public repository because app/account UI is
visible around the synthetic project.

## Confidence and implementation requirements

CONFIRMED for these synthetic probes: the original audio-row loss, editable
MIDI notes (a note move was undone), successful audio visibility with the
observed 80-byte layout/tails, and native survival of explicit audio boundaries.
HIGH CONFIDENCE within this configuration: audio float32 offset units are
milliseconds. UNKNOWN: complete tail semantics, MIDI offset encoding and
pattern-boundary handling, older FL versions, source-head trims, stretching,
looping, other tempos and arbitrary sample formats.

The production serializer still needs integration and regression coverage.
Do not claim that the current 32-byte exporter reliably preserves audio in
FL Studio 2025. Validate corrected output through actual native load/save,
including source association, start, length and note editability. Keep the
GarageBand-side duration uncertainty separate from this FLP encoding issue.
