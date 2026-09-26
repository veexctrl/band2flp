# FL Studio mapping and exporter research

## Boundary

GarageBand parsing populates the neutral `Project`, `Track`, and `Region` model. The FLP writer consumes that model and must report fields that are missing or uncertain. It must not fill unknown region lengths or MIDI values with guesses.

## Current conversion coverage

| GarageBand information | Current neutral representation | Export status |
| --- | --- | --- |
| Summary tempo | `Project.tempo_bpm` | Exported when present |
| Summary time signature | `Project.time_signature` | Exported when present |
| Audio placement start | `Region.start_beats` | Exported as playlist position in template PPQ ticks |
| Audio track number | `Track.index` plus raw candidate in `Region.unknown` | High confidence for audio preview fixture; cross-fixture mapping needs validation |
| Audio source | `Region.source` and `MediaReference` | Extracted into a user-selected media directory and referenced by a sampler channel |
| Audio duration/source offset/trim/loop | Duration unknown; nonzero offset unsupported | Default export rejects unknown duration; explicit `source-full` uses complete source length as a placeholder. Trims, loops, and stretching are not reconstructed. Nonzero offsets are rejected. |
| MIDI placement to `MSeq` | Candidate records in `Project.project_data` | Not transferred to neutral tracks yet; track and timing semantics remain unconfirmed |
| MIDI note to placed `MSeq` | Candidate event indices in `Project.project_data` | Fixture-specific shared-chunk relation; note fields remain hypotheses |
| Automation, sections, track mixer state | Unknown or unparsed | Not exported |

## PyFLP capability probe

A local PyFLP 2.2.1 copy was tested without adding it to project dependencies. Under Python 3.10 it parsed the installed FL Studio 2025 blank project template and saved a byte-identical round trip. The parsed project reports one arrangement, 96 PPQ, and an empty playlist. Its arrangement model exposes 500 virtual rows. Appending one candidate playlist record through PyFLP's `PlaylistEvent` and saving/reparsing preserved the fields, but this did not verify a playable audio clip or an FL Studio GUI load.

The same PyFLP copy fails to parse that template under Python 3.14 with `TypeError: <enum 'EventEnum'> has no members`. The same error is reported against PyFLP 2.2.1 on Python 3.12 in upstream [issue #183](https://github.com/demberto/PyFLP/issues/183); a proposed fix remains an [open pull request #196](https://github.com/demberto/PyFLP/pull/196) as of this research. The repository currently requires Python 3.11 or newer, so compatibility with its supported runtimes is not established. PyFLP 2.2.1 declares GPL-3.0; the repository currently has no selected license. Do not add it as a mandatory runtime dependency until runtime compatibility and the project's licensing choice are resolved.

For a local-only compatibility probe, adding a sentinel member to PyFLP's base `EventEnum` internal maps allowed the installed copy to parse, save, and reparse the blank template under Python 3.14. This relies on unsupported enum internals and is not used by project code.

### FL Studio 25 template check

The installed FL Studio executable reports version 25.1.5.4976. The three available empty templates under that installation all report FLP project version 24.2.99.4720 when read through PyFLP. FL Studio 9 is also present on the machine but is not used for exporter research. The FL Studio 25 executable is the target runtime. Its older-version empty project is a reasonable seed because newer FL Studio releases can open older projects; actual load/save validation in the FL Studio 25 application is still required before claiming it.

The template and generated probes remain local and ignored. No FL Studio template, demo project, proprietary plugin state, GarageBand media, or private song content is committed.

## Experimental audio export

The CLI now offers `band2flp export-flp PROJECT OUTPUT --template EMPTY.flp --media-dir NEW_MEDIA_DIR`. It uses a user-supplied empty FL Studio template, extracts uniquely embedded audio, creates sampler channels and playlist clips, and writes a `.band2flp.json` report beside the FLP. Exact fractional beat strings are converted to PPQ ticks with rational arithmetic. PyFLP 2.2.1 is loaded optionally and is not declared as a project dependency because its GPL-3.0 licensing and runtime support remain unresolved.

The default `--length-policy reject-unknown` refuses to export if any audio region duration is unknown. `--length-policy source-full` opts into using each complete source file's frame count to estimate the clip duration at project tempo. The resulting clip length is only a placeholder: GarageBand trim, loop, and playback-stretch behavior is not recovered. The command refuses nonzero source offsets and requires each source to resolve to uniquely embedded audio. The Python 3.12+ workaround modifies PyFLP 2.2.1 enum internals; it is isolated to the exporter and must be replaced if upstream fixes the issue.

Parser tests cover WAVE and CAF timing metadata and rejection of unknown lengths. A private local integration probe produced an FLP with six audio channels and ten playlist items from one user-supplied project; PyFLP reparsing preserved positions and lengths. The private project and its audio remain local. No FL Studio 25 GUI load or playback validation has been completed, so the exporter remains experimental.

## Remaining exporter work

1. Establish a supported PyFLP/runtime combination, including the project's Python 3.11+ range, or choose a different maintained writer.
2. Validate the audio paths in FL Studio 25 and confirm playback and track placement.
3. Recover region duration, trimming, looping, stretching, and source offsets before claiming arrangement-faithful audio export.
4. Reject or clearly diagnose regions with unresolved timing or missing media. Never silently invent their values.
5. Add MIDI patterns and notes only after GarageBand note and placement semantics are validated.
6. Reopen generated output with PyFLP and FL Studio, then compare exported track and clip positions with the neutral project.

## Experiments

- **FLP-001:** Blank-template parse/save/reparse. The template round-tripped byte-for-byte through PyFLP 2.2.1 under Python 3.10. Python 3.14 parsing failed as described above.
- **FLP-002:** Playlist-event serialization probe. One synthetic playlist event survived PyFLP save/reparse. It was not linked to a resolved audio sampler and was not loaded in the FL Studio GUI; this confirms serializer mechanics only.
- **FLP-003:** FL Studio 25 installation/template check. The installed executable reports 25.1.5.4976, while all three bundled empty templates tested report project version 24.2.99.4720. The older FL Studio 9 installation was excluded. No claim of FL Studio 25 GUI load/save validation is made from this check.
- **FLP-004:** Python 3.14 compatibility shim probe. A local sentinel member in PyFLP's `EventEnum` internals enabled blank-template parse/save/reparse. This is experimental only; upstream's same error report is tracked in #183, and the proposed fix in #196 remains open.
- **FLP-005:** Local arrangement/audio serialization probe. Starting from the installed empty template, PyFLP created six sampler channels, five named playlist tracks, and ten audio playlist items from the private fixture's recovered starts. All six local media paths and the playlist position/length fields survived PyFLP save/reparse. Clip lengths deliberately use each complete source duration as a placeholder because GarageBand region trims and loops remain unknown. The `.flp`, sidecar, and extracted media are ignored local files; FL Studio 25 GUI loading and media playback have not yet been checked.
- **FLP-006:** Implemented the experimental `export-flp` command with an optional PyFLP backend, duration-policy guard, WAVE/CAF frame probing, FLP save/reparse verification, and a JSON report. The private local integration emitted six audio channels and ten clips, with all playlist positions and lengths preserved through PyFLP round-trip. This is a serializer check only; FL Studio 25 GUI load and playback remain unverified. Automated suite: 27 tests passed.
