# MIDI-026 — compare cached note starts with candidate timing

## Question

Does the cached GarageBand arrangement preview constrain the candidate ticks-per-beat value independently of FLP output?

## Method

The analysis uses the preview image stored inside the private fixture only at runtime. The image and per-note positions are not part of the public repository. It detects four-connected bright-green glyphs separately in two track-row crops. Component starts are compared with integer candidate MIDI onsets; glyph widths and MIDI pitch are not used as timing evidence.

The horizontal scale is calibrated from two ruler ticks, independently of note positions: x=2119 at beat 32 and x=2323 at beat 40. This gives 25.5 pixels per beat. The tested viewport spans x=2007 through x=2532. A six-pixel matching tolerance allows for rasterized glyph starts and ruler quantization. Candidate projections use the existing integer onset origin of 38,400 and compare 480, 960 and 1,920 ticks per beat. The integer fractional word is excluded because its scaling remains unknown.

Three timing interpretations are projected: a single source pass, a 3:2 stretch, and source repetition up to the candidate placement extent. Every projection is clipped to the placement extent and the visible crop. One-to-one matching prevents one predicted note from explaining multiple observed glyphs. Duration comparisons use only matched bars whose observed and predicted widths both exceed the six-pixel display minimum and are not crop-clipped. The script reports counts and aggregate pixel residuals only.

## Observations

For the two visible rows, the 960-tick single-pass projection matches all 19 and all seven detected starts, respectively. Mean nearest-start residuals are 1.912 and 2.693 pixels; maximum residuals are 3.961 and 4.820 pixels. At 480 ticks, the single-pass projections match four and two starts. At 1,920 ticks, they match two starts in each row. The 1,920-tick repeated projection matches 11 and four starts, leaving additional predicted starts and observed glyphs unexplained. A 3:2 stretch at 960 ticks matches only three starts in the first row and one in the second.

Five interior, non-minimum-width bars in the second row also match the 960-tick duration projection with a mean absolute width error of 2.579 pixels and a maximum of 4.434 pixels. No bar in the first row qualifies after minimum-width and crop filters. This is limited duration evidence; at 1,920 ticks, alternative projections can match individual widths while accounting for far fewer starts.

At 960 ticks, the single-pass and repeat projections are identical in this crop: the candidate source length is 64 beats, while the visible ruler spans approximately beats 27.6–48.2. The crop ends before the candidate source boundary, so this preview does not discriminate repeat behavior. It also does not show the full region ends.

The parser's event indices are logical record ordinals, not fixed-size slots. An initial 64-byte-slot IDA read failed and was discarded. After tracing each variable-length event's actual parsed offset, IDA byte reads matched all 75 candidate note records in the two visible rows exactly. The IDA database is a raw data segment with no functions; disassembly was not applicable. The Python tool and private image comparison remain reproducible from the local fixture.

## Confidence and limitations

**HIGH CONFIDENCE, fixture-specific:** the 960 tick scale and the existing integer-onset origin together explain the visible note starts much better than the tested alternatives. Five measurable note-bar widths also support the candidate durations at that scale. The IDA cross-check confirms that the parser's note records at the measured offsets match the raw logic-song component.

This does not prove a universal PPQ value or origin. The fixture is uncontrolled, the preview may be stale, the two ruler anchors are manually read, and the window is cropped. The source and placement extent meanings, fractional-word scale, actual note lengths, and repeat/stretch semantics remain unresolved. The screen image is cached presentation evidence, not a substitute for a controlled GarageBand edit pair.

## Reproduction

Run `python -m research.scripts.midi_preview_timing_probe project.band preview.png --mseq-index INDEX --roi LEFT TOP RIGHT BOTTOM --anchor X1 BEAT1 --anchor X2 BEAT2 --source-ticks TICKS --placement-ticks TICKS`. Pillow is optional and used only by this research script. The script emits no image pixels, note values, names, or source audio.

## Next

When a controlled GarageBand fixture becomes available, compare one note moved by a known beat while holding all other project properties fixed. A wider, un-cropped preview could independently test the source boundary and whether the longer candidate extent represents repetition, stretching, or another limit.
