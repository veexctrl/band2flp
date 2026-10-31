# MIX-001: explicit mixer-field search

Question: do the two available projectData keyed archives expose explicit
volume, pan, mute or solo fields that can seed neutral track-state recovery?

The search inspected every direct dictionary field and resolved `NS.keys`
string in the outer keyed archives. Neither has a volume, mute or solo field
under those literal keywords. The only pan-substring key is
`CbTrackPanelVisible`, which names track-panel visibility and is not evidence
of a pan control.

For the audio-bearing archive, its current package member, cached component
and IDA input digest match. Headless IDA raw-byte searches for lower/title-case
ASCII spellings of volume, mute, solo and pan agree with the structured search:
only the title-case `Pan` substring occurs. An independent byte read around
that occurrence confirms the `CbTrackPanelVisible` key. An empty IDA string
index was not used as evidence of absence; raw byte searches were required.

CONFIRMED: the bounded search results and input correspondence for these
fixtures. UNKNOWN: whether mixer settings are encoded in opaque binary data,
other components, differently named fields, or an encoding not tested here.
This is not proof that the project lacks mixer state. No state values or
defaults are inferred or exported.

Next investigate binary `AuCO`/`Trak` relationships or use controlled saves
changing exactly one mixer control. Distinguish channel-strip identity from
arrange-track identity before attaching any recovered setting to a track.
