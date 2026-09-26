# FL Studio mapping and exporter research

## Boundary

GarageBand parsing populates the neutral `Project`, `Track`, and `Region` model. The FLP writer consumes that model and must report fields that are missing or uncertain. It must not fill unknown region lengths or MIDI values with guesses.

## Current conversion coverage

| GarageBand information | Current neutral representation | Export status |
| --- | --- | --- |
| Summary tempo | `Project.tempo_bpm` | Candidate mapping to FL tempo; not exported |
| Summary time signature | `Project.time_signature` | Candidate mapping to FL arrangement meter; not exported |
| Audio placement start | `Region.start_beats` | Recovered in inspected fixtures; start may be mapped when its confidence is retained |
| Audio track number | `Track.index` plus raw candidate in `Region.unknown` | High confidence for audio preview fixture; cross-fixture mapping needs validation |
| Audio source | `Region.source` and `MediaReference` | Resource reference only; may not resolve to a local file |
| Audio duration/source offset/trim/loop | Unknown | Must not be guessed for an arrangement-faithful export |
| MIDI placement to `MSeq` | Candidate records in `Project.project_data` | Not transferred to neutral tracks yet; track and timing semantics remain unconfirmed |
| MIDI note to placed `MSeq` | Candidate event indices in `Project.project_data` | Fixture-specific shared-chunk relation; note fields remain hypotheses |
| Automation, sections, track mixer state | Unknown or unparsed | Not exported |

## PyFLP capability probe

A local PyFLP 2.2.1 copy was tested without adding it to project dependencies. Under Python 3.10 it parsed the installed FL Studio 2025 blank project template and saved a byte-identical round trip. The parsed project reports one arrangement, 96 PPQ, and an empty playlist. Its arrangement model exposes 500 virtual rows. Appending one candidate playlist record through PyFLP's `PlaylistEvent` and saving/reparsing preserved the fields, but this did not verify a playable audio clip or an FL Studio GUI load.

The same PyFLP copy fails to parse that template under Python 3.14 with `TypeError: <enum 'EventEnum'> has no members`. The repository currently requires Python 3.11 or newer, so compatibility with its supported runtimes is not established. PyFLP 2.2.1 declares GPL-3.0; the repository currently has no selected license. Do not add it as a mandatory runtime dependency until runtime compatibility and the project's licensing choice are resolved.

The template and generated probes remain local and ignored. No FL Studio template, demo project, proprietary plugin state, GarageBand media, or private song content is committed.

## Required exporter work

1. Decide on a template strategy that does not require committing Image-Line project assets. Allow a user-supplied blank FLP template or locate a supported template explicitly.
2. Establish a supported PyFLP/runtime combination, including the project's Python 3.11+ range, or choose a different maintained writer.
3. Create and validate named audio tracks and sampler channels with resolved source paths.
4. Add playlist clips at neutral beat positions and preserve the project's tempo and meter where supported.
5. Reject or clearly diagnose regions with unresolved duration, source offsets, or missing media. Never silently invent their values.
6. Add MIDI patterns and notes only after GarageBand note and placement semantics are validated.
7. Reopen generated output with PyFLP and FL Studio, then compare exported track and clip positions with the neutral project.

## Experiments

- **FLP-001:** Blank-template parse/save/reparse. The template round-tripped byte-for-byte through PyFLP 2.2.1 under Python 3.10. Python 3.14 parsing failed as described above.
- **FLP-002:** Playlist-event serialization probe. One synthetic playlist event survived PyFLP save/reparse. It was not linked to a resolved audio sampler and was not loaded in the FL Studio GUI; this confirms serializer mechanics only.
