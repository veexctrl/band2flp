# band2flp

Research tools for recovering GarageBand project structure and converting supported data into a neutral project model and FL Studio projects.

The current parser inventories `.band` ZIP packages and reads summary tempo, meter, duration, and track-count values from `Output/metadata.plist`. It preserves uninterpreted `projectData` NSData payloads in JSON. It does not yet decode tracks, regions, MIDI, audio placement, or produce FLP files; the output calls those structures unknown rather than guessing.

## Use

```powershell
python -m band2flp.cli inspect path\to\project.band
python -m band2flp.cli inspect path\to\project.band --json
```

Run the regression suite with:

```powershell
python -m unittest discover -s tests -v
```

See [architecture](docs/architecture.md), [format observations](docs/band-format.md), and [research findings](docs/reverse-engineering/findings.md).
