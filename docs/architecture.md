# Architecture

The intended pipeline keeps GarageBand parsing separate from FL Studio writing:

```text
.band package -> package/parser -> neutral Project -> JSON/debug output
                                             `-> future FLP exporter
```

`band2flp.parser` performs bounded, read-only ZIP, plist, chunk-boundary, and event-record parsing. `band2flp.model` defines the format-neutral project, track, and region types. Summary tempo/meter values are read from metadata; matching group-zero tempo/meter events are exposed as high-confidence candidates with raw positions and unknown units. The parser leaves the track list empty until track and region placements are decoded. The `project_data` field carries chunk/event records, archive-level observations, and complete retained payload bytes; other chunk and event meanings remain unknown.

Timing fields on future notes and regions are represented as exact beat strings. Their units and mapping will be set only after differential evidence identifies the source encoding. The parser exposes the raw numeric duration summary with an unknown unit; it does not convert that value into beats or seconds.

The FLP exporter is not implemented. It will consume `Project`, independent of `.band` parsing, after arrangement semantics are understood.
