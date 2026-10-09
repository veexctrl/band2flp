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

The fractional-word scale remains unresolved. Every start-matched note in each visible row has the same `position_fraction_raw` value, so the image supplies no within-row variation with which to fit a fractional multiplier independently of a row offset. Applying a Q16 tick fraction changes mean absolute residuals by less than raster precision (1.912 to 1.912 pixels in one row; 2.693 to 2.690 in the other). A larger tested fraction scale worsens the fit. These results do not establish that the word is a sub-tick fraction.

## Candidate pitch byte and vertical note position (MIDI-027)

For each start-matched glyph, compare its vertical center with the note candidate's byte at event offset `+0x0c`. Fit an independent straight line per track row because each row may use its own vertical zoom. In the first row, 19 glyphs spanning four candidate values produce an in-sample R² of 0.99991 and leave-one-value-out mean absolute error of 0.8004 pixels. The second row has seven glyphs and five candidate values, R² 0.99986, and leave-one-value-out error 0.3432 pixels. Candidate velocity and fine-velocity fields have R² below 0.008 in both rows. The fitted slopes differ between rows, so the image does not provide a common pixel-to-pitch scale.

This is **HIGH CONFIDENCE** that `+0x0c` orders visible notes by vertical pitch in these two rows of this fixture. It does not establish the absolute MIDI key convention, semitone spacing, or the field's meaning in every event family. No pitch values or screenshot pixels are emitted or published. IDA's raw record reads match the parser for all 75 note records in the two rows.

At 960 ticks, the single-pass and repeat projections are identical in this crop: the candidate source length is 64 beats, while the visible ruler spans approximately beats 27.6–48.2. The crop ends before the candidate source boundary, so this preview does not discriminate repeat behavior. It also does not show the full region ends.

The parser's event indices are logical record ordinals, not fixed-size slots. An initial 64-byte-slot IDA read failed and was discarded. After tracing each variable-length event's actual parsed offset, IDA byte reads matched all 75 candidate note records in the two visible rows exactly. The IDA database is a raw data segment with no functions; disassembly was not applicable. The Python tool and private image comparison remain reproducible from the local fixture.

## Confidence and limitations

**HIGH CONFIDENCE, fixture-specific:** the 960 tick scale and the existing integer-onset origin together explain the visible note starts much better than the tested alternatives. Five measurable note-bar widths also support the candidate durations at that scale. The IDA cross-check confirms that the parser's note records at the measured offsets match the raw logic-song component.

This does not prove a universal PPQ value or origin. The fixture is uncontrolled, the preview may be stale, the two ruler anchors are manually read, and the window is cropped. The source and placement extent meanings, fractional-word scale, absolute pitch convention, and repeat/stretch semantics remain unresolved; the width comparison gives limited support for the visible note lengths. The screen image is cached presentation evidence, not a substitute for controlled GarageBand note-pitch and timing edits.

## Reproduction

Run `python -m research.scripts.midi_preview_timing_probe project.band preview.png --mseq-index INDEX --roi LEFT TOP RIGHT BOTTOM --anchor X1 BEAT1 --anchor X2 BEAT2 --source-ticks TICKS --placement-ticks TICKS`. Pillow is optional and used only by this research script. The script emits no image pixels, note values, names, or source audio.

## Next

When a controlled GarageBand fixture becomes available, compare one note moved by a known beat while holding all other project properties fixed. A wider, un-cropped preview could independently test the source boundary and whether the longer candidate extent represents repetition, stretching, or another limit.
