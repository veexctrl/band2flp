# band2flp

Research tools for recovering GarageBand project structure and converting supported data into a neutral project model and FL Studio projects.

The current parser inventories `.band` ZIP packages and reads summary tempo, meter, duration, and track-count values from `Output/metadata.plist`. It validates the outer logic-song chunk stream, preserves the source bytes and unknown event records, and reports tempo/meter candidates that agree with project metadata. It also retains media references and candidate links to audio-file and region chunks. It does not yet decode track identities, region timing/placement, MIDI notes, or produce FLP files; the output marks those structures unknown rather than guessing.

## Use

```powershell
python -m band2flp.cli inspect path\to\project.band
python -m band2flp.cli inspect path\to\project.band --json
python -m band2flp.cli inspect path\to\project.band --groups
```

`--groups` lists chunk types and indices by the opaque candidate group field; it does not interpret that field.

Run the regression suite with:

```powershell
python -m unittest discover -s tests -v
```

See [architecture](docs/architecture.md), [format observations](docs/band-format.md), and [research findings](docs/reverse-engineering/findings.md).

Compare a raw component or matching members from two ZIP packages with:

```powershell
python research/scripts/binary_diff.py old.band new.band --member-suffix /projectData
python -m research.scripts.projectdata_diff old.band new.band
python -m research.scripts.auco_probe project.band
```

The byte diff flags absolute-offset alignment limits and labels integer/float readings as candidates. The ProjectData diff pairs chunks by type, candidate group value, and ordinal within that pair; it reports header and payload changes, and warns that ordinal matches can shift when a same-type chunk is inserted or deleted. The AuCO probe checks a Logic-like channel-strip record candidate and reports structural counts without outputting track names or assigning GarageBand semantics.
