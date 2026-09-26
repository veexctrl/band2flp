# Architecture

The intended pipeline keeps GarageBand parsing separate from FL Studio writing:

```text
.band package -> package/parser -> neutral Project -> JSON/debug output
                                             `-> future FLP exporter
```

`band2flp.parser` performs bounded, read-only ZIP, plist, and observed chunk-boundary parsing. `band2flp.model` defines the format-neutral project, track, and region types. The parser currently fills only summary fields whose source keys are explicit in GarageBand's output metadata plist. It leaves the track list empty until track records can be identified in project data. The `project_data` field carries chunk headers, archive-level observations, and the complete retained payload bytes; chunk tags and boundaries do not yet imply decoded track or region semantics.

Timing fields on future notes and regions are represented as exact beat strings. Their units and mapping will be set only after differential evidence identifies the source encoding. The parser exposes the raw numeric duration summary with an unknown unit; it does not convert that value into beats or seconds.

The FLP exporter is not implemented. It will consume `Project`, independent of `.band` parsing, after arrangement semantics are understood.
