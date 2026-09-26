# band2flp

Research tools for recovering GarageBand project structure and converting supported data into a neutral project model and FL Studio projects.

The parser inventories `.band` ZIP packages and reads summary tempo, meter, duration, and track-count values from `Output/metadata.plist`. It validates the logic-song chunk stream, preserves raw project bytes and unknown event records, and reports tempo/meter candidates that agree with project metadata.

For inspected fixtures it also decodes audio placement starts, track-number candidates, and source links into neutral audio regions. The start positions agree with one project's arrangement preview. Region duration, source offset, trimming, looping, and full track identity remain unresolved. MIDI placement candidates are linked to `MSeq` chunks; note-shaped events that share a linked chunk are exposed in JSON, but note pitch, velocity, onset, duration, MIDI track mapping, and placement timing have not been confirmed in controlled GarageBand fixtures. An experimental audio-only FLP exporter is available; it requires a blank FL Studio template and optional PyFLP, and documents unknown clip lengths rather than claiming a faithful conversion.

Special thanks to [@zazasys](https://github.com/zazasys) (Instagram: `_zaaaaan_`) for sharing a few fun GarageBand projects for reverse-engineering and helping make band2flp possible.

## Use

```powershell
python -m band2flp.cli inspect path\to\project.band
python -m band2flp.cli inspect path\to\project.band --json
python -m band2flp.cli inspect path\to\project.band --groups
python -m band2flp.cli extract-audio path\to\project.band path\to\new-audio-folder
python -m band2flp.cli export-flp path\to\project.band output.flp --template path\to\empty.flp --media-dir path\to\new-media-folder --length-policy source-full
```

Install the Python package locally with `python -m pip install .`; this also provides the `band2flp` command. FLP export additionally needs PyFLP 2.2.1 installed separately and a user-supplied blank FL Studio project. See [FL Studio mapping research](docs/flp-mapping.md) for its experimental status and duration policy.

`--groups` lists chunk types and indices by the opaque candidate group field; it does not interpret that field.

`extract-audio` copies only audio files uniquely referenced by the project into a new output directory, with generated filenames and a JSON mapping. It does not extract previews, caches, or unreferenced media. The output folder must not already exist. This command is opt-in; inspection does not copy audio.

Run the regression suite with:

```powershell
python -m unittest discover -s tests -v
```

See [architecture](docs/architecture.md), [format observations](docs/band-format.md), [FL Studio mapping research](docs/flp-mapping.md), and [reverse-engineering findings](docs/reverse-engineering/findings.md).

Compare a raw component or matching members from two ZIP packages with:

```powershell
python research/scripts/binary_diff.py old.band new.band --member-suffix /projectData
python -m research.scripts.projectdata_diff old.band new.band
python -m research.scripts.auco_probe project.band
python -m research.scripts.audio_frame_probe project.band
```

The byte diff flags absolute-offset alignment limits and labels integer/float readings as candidates. The ProjectData diff pairs chunks by type, candidate group value, and ordinal within that pair; it reports header and payload changes, and warns that ordinal matches can shift when a same-type chunk is inserted or deleted. The AuCO probe checks a Logic-like channel-strip record candidate and reports structural counts without outputting track names or assigning GarageBand semantics.

The audio frame probe compares `AuRg` length candidates against embedded WAVE, AIFF/AIFC, or CAF source frame counts. It reads archive members in memory and emits aggregate counts without writing or naming audio files. A match is diagnostic only; it does not establish trim or arrangement-duration semantics.
