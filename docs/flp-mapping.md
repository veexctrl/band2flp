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
| Audio source | `Region.source` and `MediaReference` | Resource reference only; uniquely matched embedded audio can be copied locally with the opt-in `extract-audio` command |
| Audio duration/source offset/trim/loop | Unknown | Must not be guessed for an arrangement-faithful export |
| MIDI placement to `MSeq` | Candidate records in `Project.project_data` | Not transferred to neutral tracks yet; track and timing semantics remain unconfirmed |
| MIDI note to placed `MSeq` | Candidate event indices in `Project.project_data` | Fixture-specific shared-chunk relation; note fields remain hypotheses |
| Automation, sections, track mixer state | Unknown or unparsed | Not exported |

## PyFLP capability probe

A local PyFLP 2.2.1 copy was tested without adding it to project dependencies. Under Python 3.10 it parsed the installed FL Studio 2025 blank project template and saved a byte-identical round trip. The parsed project reports one arrangement, 96 PPQ, and an empty playlist. Its arrangement model exposes 500 virtual rows. Appending one candidate playlist record through PyFLP's `PlaylistEvent` and saving/reparsing preserved the fields, but this did not verify a playable audio clip or an FL Studio GUI load.

The same PyFLP copy fails to parse that template under Python 3.14 with `TypeError: <enum 'EventEnum'> has no members`. The same error is reported against PyFLP 2.2.1 on Python 3.12 in upstream [issue #183](https://github.com/demberto/PyFLP/issues/183); a proposed fix remains an [open pull request #196](https://github.com/demberto/PyFLP/pull/196) as of this research. The repository currently requires Python 3.11 or newer, so compatibility with its supported runtimes is not established. PyFLP 2.2.1 declares GPL-3.0; the repository currently has no selected license. Do not add it as a mandatory runtime dependency until runtime compatibility and the project's licensing choice are resolved.

For a local-only compatibility probe, adding a sentinel member to PyFLP's base `EventEnum` internal maps allowed the installed copy to parse, save, and reparse the blank template under Python 3.14. This relies on unsupported enum internals and is not used by project code.

### FL Studio 25 template check

The installed FL Studio executable reports version 25.1.5.4976. The three available empty templates under that installation all report FLP project version 24.2.99.4720 when read through PyFLP. FL Studio 9 is also present on the machine but is not used for exporter research. The FL Studio 25 executable is the target runtime. Its older-version empty project is a reasonable seed because newer FL Studio releases can open older projects; actual load/save validation in the FL Studio 25 application is still required before claiming it.

The template and generated probes remain local and ignored. The audio extractor is covered by synthetic fixtures; it has not been run against the supplied private audio project. No FL Studio template, demo project, proprietary plugin state, GarageBand media, or private song content is committed.

## Required exporter work

1. Decide on a template strategy that does not require committing Image-Line project assets. Allow a user-supplied blank FLP template or locate a supported template explicitly.
2. Establish a supported PyFLP/runtime combination, including the project's Python 3.11+ range, or choose a different maintained writer.
3. Use the opt-in referenced-media extractor and create/validate named audio tracks and sampler channels with resolved source paths.
4. Add playlist clips at neutral beat positions and preserve the project's tempo and meter where supported.
5. Reject or clearly diagnose regions with unresolved duration, source offsets, or missing media. Never silently invent their values.
6. Add MIDI patterns and notes only after GarageBand note and placement semantics are validated.
7. Reopen generated output with PyFLP and FL Studio, then compare exported track and clip positions with the neutral project.

## Experiments

- **FLP-001:** Blank-template parse/save/reparse. The template round-tripped byte-for-byte through PyFLP 2.2.1 under Python 3.10. Python 3.14 parsing failed as described above.
- **FLP-002:** Playlist-event serialization probe. One synthetic playlist event survived PyFLP save/reparse. It was not linked to a resolved audio sampler and was not loaded in the FL Studio GUI; this confirms serializer mechanics only.
- **FLP-003:** FL Studio 25 installation/template check. The installed executable reports 25.1.5.4976, while all three bundled empty templates tested report project version 24.2.99.4720. The older FL Studio 9 installation was excluded. No claim of FL Studio 25 GUI load/save validation is made from this check.
- **FLP-004:** Python 3.14 compatibility shim probe. A local sentinel member in PyFLP's `EventEnum` internals enabled blank-template parse/save/reparse. This is experimental only; upstream's same error report is tracked in #183, and the proposed fix in #196 remains open.
- **FLP-005:** Local arrangement/audio serialization probe. Starting from the installed empty template, PyFLP created six sampler channels, five named playlist tracks, and ten audio playlist items from the private fixture's recovered starts. All six local media paths and the playlist position/length fields survived PyFLP save/reparse. Clip lengths deliberately use each complete source duration as a placeholder because GarageBand region trims and loops remain unknown. The `.flp`, sidecar, and extracted media are ignored local files; FL Studio 25 GUI loading and media playback have not yet been checked.
