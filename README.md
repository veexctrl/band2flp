# band2flp

Research tools for recovering GarageBand project structure into a neutral model and exporting supported data to FL Studio.

Licensed under the [MIT License](LICENSE).

<p align="center"><img src="docs/progress.svg" alt="Estimated GarageBand reverse-engineering progress, with work areas and milestones"></p>

The graphic is a rough estimate of format knowledge recovered, not a measure of converter completeness. See docs/progress.json for its evidence-based workstream estimates.

## What it can do now

- Inspect a GarageBand .band package and summarize its members, tempo, time signature, reported duration, and declared arrange-track count.
- Validate the observed logic-song chunk boundaries and event-record boundaries while preserving opaque payloads and unrecognized records.
- Emit a neutral JSON representation with raw candidate data, provenance, and warnings.
- In inspected project variants, recover candidate audio placement starts and link audio sources to placement records. One fixture's starts match its GarageBand arrangement preview.
- Report MIDI region-placement and note-shaped event candidates, including observed links to MSeq chunks. These are research candidates, not a confirmed MIDI conversion.
- Extract audio files that are explicitly referenced by the project, using generated filenames and a mapping report.
- Experimentally export recovered audio starts to an FL Studio project using PyFLP and a blank FL Studio template. The exporter checks that each sample path survives its PyFLP round-trip unchanged. The latest candidate still triggers FL Studio's invalid-playlist warning. The user also reports that clips are not visible on the named rows and that FL Studio reports a missing audio file. Arrangement visibility and media playback are not verified.

## What is still being researched

GarageBand audio-region duration, trimming, looping, stretching, source offsets, complete track identity, and mixer state are not recovered. MIDI pitch, velocity, onset, duration, and track assignment still need controlled GarageBand fixtures. Automation, sections, and tempo/meter changes are not reconstructed.

The audio-only FLP exporter is experimental. When a region length is unknown, the default export stops with an error. The optional source-full policy uses the complete audio source length as an explicit placeholder; it does not reproduce GarageBand trims or loops. FL Studio 25 continues to report invalid playlist clips; the exporter’s FL Studio row mapping and media resolution remain under investigation.

## Install

Use Python 3.11 or newer:

    python -m pip install .

This installs the band2flp command. From a source checkout, the equivalent commands below can use python -m band2flp.cli.

FLP export additionally requires PyFLP 2.2.1 and a blank FL Studio project template. PyFLP is optional and is not installed as a project dependency; see docs/flp-mapping.md for compatibility and licensing notes.

## Inspect a project

    band2flp inspect path/to/project.band
    band2flp inspect path/to/project.band --json
    band2flp inspect path/to/project.band --groups

Text inspection gives a concise summary. JSON output preserves raw project payloads and media references, which may contain private project information; review it before storing or sharing it. The groups option displays opaque candidate group values and does not assign them meaning.

## Extract referenced audio

    band2flp extract-audio path/to/project.band path/to/new-audio-folder

Extraction is explicit. It copies only uniquely matched AudioFiles references, gives the files generated names such as audio-001.caf, and writes a JSON mapping. The destination folder must not already exist. Extracted recordings remain private project material unless you intentionally choose to share them.

## Export an experimental FLP

    band2flp export-flp path/to/project.band path/to/new-project.flp --template path/to/blank.flp --media-dir path/to/new-media-folder --length-policy source-full

The command extracts uniquely matched audio into the new media folder, writes the FLP, and saves a JSON report beside it. Both output paths must be new. Without source-full, export rejects audio regions whose duration is unknown. Source-full estimates a placeholder length from the full source file.

Keep the FLP and its referenced media together, or make sure the paths stored in the FLP still resolve on the target computer. The latest GUI check still reported audio-006.caf missing, so check the media directory before expecting playback.

## Research and tests

Compare projectData structures without assuming fixed offsets:

    python -m research.scripts.projectdata_diff old.band new.band

Inventory unclassified event record shapes without printing their contents:

    python -m research.scripts.event_inventory path/to/project.band

Compare generated sample-channel event layouts with FLP references (requires optional PyFLP):

    python -m research.scripts.flp_channel_inventory candidate.flp path/to/flp-projects --limit 100

This probe prints aggregate event-shape counts only; it omits project names, paths, media paths, and field values.

Compare generated playlist audio-row structures with FLP references (requires optional PyFLP):

    python -m research.scripts.flp_playlist_inventory candidate.flp path/to/flp-projects --limit 100

This probe also reports aggregate counts only, omitting project names, paths, clip timing, media paths, and field values.

Check whether the saved previous-track UUID appears in logic-song chunks:

    python -m research.scripts.track_uuid_probe path/to/project.band

The probe reports aggregate chunk and UUID-field shapes only; it never prints the UUID or project paths.

Run the regression suite from the repository root:

    python -m unittest discover -s tests -v

## Acknowledgments and format references

Special thanks to [@zazasys](https://github.com/zazasys) (Instagram: `_zaaaaan_`) for sharing fun GarageBand projects that helped us reverse-engineer the project format and develop band2flp.

Cross-format research references include [loov/logicx](https://github.com/loov/logicx) and [Jon Kubis's LogicProFormatWriter format notes](https://github.com/jonkubis/LogicProFormatWriter/blob/main/PROJECTDATA_FORMAT.md). They document Logic Pro, so we use them as research leads and validate candidate meanings against GarageBand evidence. The band2flp implementation was written independently; no code was copied from these projects.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the research workflow and fixture privacy guidance, [docs/roadmap.md](docs/roadmap.md) for milestones, [docs/architecture.md](docs/architecture.md) for the parser/model/exporter boundary, [docs/band-format.md](docs/band-format.md) for observed format details, and [docs/flp-mapping.md](docs/flp-mapping.md) for FL Studio status.
