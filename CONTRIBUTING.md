# Contributing to band2flp

Thanks for helping investigate GarageBand projects and improve their FL Studio conversion. The project is experimental: much of the serialized song data is still unknown, so evidence and clear uncertainty are as useful as implementation changes.

## Development setup

Use Python 3.11 or newer, as declared in `pyproject.toml`. From the repository root, run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

FLP export uses optional PyFLP support and a blank FL Studio template. It is separate from GarageBand parsing; do not make IDA or FL Studio a runtime dependency of the parser or inspection commands.

## Research and implementation

- Prefer controlled comparisons that change one project property at a time. Verify that fixtures differ only as intended before interpreting changed data.
- Record important observations in `docs/reverse-engineering/experiments.md` with the fixture class, method, result, alternatives, confidence, and next experiment. Use CONFIRMED, HIGH CONFIDENCE, HYPOTHESIS, or UNKNOWN where appropriate.
- Preserve unrecognized fields and event bytes. Keep GarageBand parsing, the neutral project model, and FLP export as separate layers.
- Treat Logic Pro format descriptions as cross-format leads. Validate any transferred interpretation against GarageBand evidence before promoting it to a decoded field.
- Add regression tests when a behavior or parser rule is supported by evidence. Include malformed-input tests when changing package or binary parsing.
- When checking FL Studio compatibility, record the FL Studio version and template version. Report invalid playlist warnings without accepting deletion of clips from the only copy of a project.

## Fixture and privacy rules

The repository is public. Do not commit GarageBand projects, FL Studio projects, audio, MIDI, screenshots, application binaries, IDA databases, or logs from private projects. Keep fixtures local and ignored, or create small synthetic fixtures that contain no personal or copyrighted project content. Publish only anonymized structural observations that do not reveal project titles, track names, media names, local paths, or recorded audio.

Before staging a change, inspect the complete diff and staged file list for media, credentials, personal information, machine-specific paths, and generated files. Never include secrets in source, tests, documentation, or commit messages.

## Git changes

Use small commits with descriptive messages, such as `research: compare audio region candidates` or `test: cover truncated chunk headers`. Do not rewrite published history. Keep documentation and tests aligned with the evidence behind each behavior.
