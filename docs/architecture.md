# Architecture

The intended pipeline keeps GarageBand parsing separate from FL Studio writing:

```text
.band package -> package/parser -> neutral Project -> JSON/debug output
                                             `-> FLP arrangement exporter
                                                     + linked audio sources
```

`band2flp.parser` performs bounded, read-only ZIP, plist, chunk-boundary, and event-record parsing. `band2flp.model` defines the format-neutral project, track, region, and media-reference types. Summary tempo/meter values are read from metadata; matching group-zero tempo/meter events are exposed as high-confidence candidates with raw positions and unknown units. Audio placement records populate neutral tracks and regions with start positions, external media references, and raw event data. Same-group `AuRg` chunks whose NUL-delimited filename stem matches an audio resource are reported separately as stronger source-to-region-chunk links. Region durations, placement-event-to-region-object ordinals, track names, and other track settings remain unknown. The `project_data` field carries chunk/event records, archive-level observations, and complete retained payload bytes.

Timing fields on future notes and regions are represented as exact beat strings. Their units and mapping will be set only after differential evidence identifies the source encoding. The parser exposes the raw numeric duration summary with an unknown unit; it does not convert that value into beats or seconds.

The FLP exporter is not implemented. It will consume `Project`, independent of `.band` parsing. Arrangement recovery is the first export target: create FL Studio tracks and place audio clips at recovered positions, with source paths that can point to recovered media or separately rendered stems. Separate rendering can supply usable audio without reproducing GarageBand instruments, but it cannot repair incorrect region boundaries: region duration, source offset, trimming, and looping must still be recovered or explicitly supplied before clips can faithfully reproduce the source arrangement. The exporter must surface missing media and unresolved clip lengths instead of silently choosing values.
