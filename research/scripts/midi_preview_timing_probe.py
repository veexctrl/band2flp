"""Compare private cached note glyphs with timing hypotheses; aggregate output.

Ruler anchors must be established independently of the notes being tested.
Pillow is optional research tooling only. No images or music are written.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path

from band2flp.parser import parse_band


def green_components(image, roi):
    """Return bounding boxes for four-connected bright green preview glyphs."""
    left, top, right, bottom = roi
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError("ROI is outside the image")
    if (right - left) * (bottom - top) > 250_000:
        raise ValueError("ROI exceeds research pixel limit")
    pixels = image.load()
    remaining = set()
    for y in range(top, bottom):
        for x in range(left, right):
            r, g, b = pixels[x, y][:3]
            if g > 160 and r < 100 and b < 100:
                remaining.add((x, y))
    boxes = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        xs, ys = [seed[0]], [seed[1]]
        while stack:
            x, y = stack.pop()
            for point in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if point in remaining:
                    remaining.remove(point)
                    stack.append(point)
                    xs.append(point[0])
                    ys.append(point[1])
        boxes.append((min(xs), min(ys), max(xs)+1, max(ys)+1))
    return sorted(boxes)


def predicted_boxes(notes, *, ppq, mode, source_ticks, placement_ticks, anchors, viewport,
                    minimum_width=6):
    """Project integer tick hypotheses into an independently calibrated crop.

    notes contains (relative integer onset, integer duration) pairs. Fraction
    words are deliberately excluded because their scale is unresolved.
    """
    if ppq <= 0 or mode not in ("single", "stretch", "repeat"):
        raise ValueError("invalid timing hypothesis")
    if source_ticks <= 0 or placement_ticks <= 0 or len(notes) > 10_000:
        raise ValueError("invalid source extent or note count")
    (x1, beat1), (x2, beat2) = anchors
    left, right = viewport
    if x2 <= x1 or beat2 <= beat1 or right <= left or minimum_width <= 0:
        raise ValueError("invalid calibration or viewport")
    scale = Fraction(x2-x1, 1) / (beat2-beat1)
    source_beats = Fraction(source_ticks, ppq)
    placement_beats = Fraction(placement_ticks, ppq)
    placement_x = x1 + (placement_beats-beat1) * scale
    repeats = ((placement_ticks + source_ticks - 1) // source_ticks
               if mode == "repeat" else 1)
    if repeats * len(notes) > 100_000:
        raise ValueError("repeat projection exceeds research limit")
    result = []
    for onset, duration in notes:
        if onset < 0 or duration < 0:
            raise ValueError("negative note timing")
        for repeat in range(repeats):
            start = Fraction(onset, ppq) + repeat * source_beats
            length = Fraction(duration, ppq)
            if mode == "stretch":
                start *= Fraction(3, 2)
                length *= Fraction(3, 2)
            if start >= placement_beats:
                continue
            x = x1 + (start-beat1) * scale
            length = min(length, placement_beats-start)
            end = min(placement_x, x + max(minimum_width, length*scale))
            if x < right and end > left:
                result.append((max(left, x), min(right, end)))
    return sorted(result)


def compare_starts(observed, predicted, tolerance):
    """Maximum one-to-one matching for sorted positions, plus residuals.

    Greedy matching of sorted points is maximal for a uniform distance bound.
    Both directions are reported so extra projected notes remain visible.
    """
    if tolerance < 0:
        raise ValueError("negative tolerance")
    observed, predicted = sorted(observed), sorted(predicted)
    if len(observed) * len(predicted) > 2_000_000:
        raise ValueError("comparison exceeds research limit")
    i = j = matched = 0
    while i < len(observed) and j < len(predicted):
        delta = observed[i] - predicted[j]
        if abs(delta) <= tolerance:
            matched += 1
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    def residuals(a, b):
        if not a or not b:
            return None
        errors = [min(abs(x-y) for y in b) for x in a]
        return {"mean_pixels": round(float(sum(errors)/len(errors)), 3),
                "maximum_pixels": round(float(max(errors)), 3)}
    return {"observed_count": len(observed), "predicted_count": len(predicted),
            "one_to_one_matches": matched,
            "unmatched_observed": len(observed)-matched,
            "unmatched_predicted": len(predicted)-matched,
            "observed_residual": residuals(observed, predicted),
            "predicted_residual": residuals(predicted, observed)}


def compare_widths(observed_boxes, predicted_boxes, tolerance, viewport,
                   minimum_width=6):
    """Compare widths only for matched, interior bars above display minimum."""
    left, right = viewport
    observed = sorted(observed_boxes, key=lambda box: box[0])
    predicted = sorted(predicted_boxes, key=lambda box: box[0])
    if tolerance < 0 or right <= left or minimum_width <= 0:
        raise ValueError("invalid width comparison bounds")
    if len(observed) * len(predicted) > 2_000_000:
        raise ValueError("comparison exceeds research limit")
    i = j = 0
    errors = []
    while i < len(observed) and j < len(predicted):
        delta = observed[i][0] - predicted[j][0]
        if abs(delta) <= tolerance:
            ow = observed[i][2] - observed[i][0]
            pw = predicted[j][1] - predicted[j][0]
            interior = (observed[i][0] > left and observed[i][2] < right
                        and predicted[j][0] > left and predicted[j][1] < right)
            if interior and ow > minimum_width and pw > minimum_width:
                errors.append(abs(ow-pw))
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    return {"informative_width_count": len(errors),
            "mean_absolute_width_error_pixels": (
                round(float(sum(errors)/len(errors)), 3) if errors else None),
            "maximum_absolute_width_error_pixels": (
                round(float(max(errors)), 3) if errors else None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("preview", type=Path)
    parser.add_argument("--mseq-index", type=int, required=True)
    parser.add_argument("--roi", nargs=4, type=int, required=True,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--anchor", nargs=2, action="append", required=True,
                        metavar=("PIXEL_X", "BEAT"))
    parser.add_argument("--source-ticks", type=int, required=True)
    parser.add_argument("--placement-ticks", type=int, required=True)
    parser.add_argument("--ppq", nargs="+", type=int, default=[480, 960, 1920])
    parser.add_argument("--tolerance", type=int, default=6)
    args = parser.parse_args()
    if len(args.anchor) != 2:
        parser.error("exactly two independent ruler anchors are required")
    try:
        from PIL import Image
    except ImportError:
        parser.error("Pillow is required only for this research command")
    project = parse_band(args.project)
    notes = [(n["position_ticks_from_38400_candidate"], n["duration_ticks_candidate"])
             for n in project.project_data["midi_note_event_candidates"]
             if n["candidate_mseq_chunk_indices_for_group"] == [args.mseq_index]]
    if not notes:
        parser.error("no uniquely linked note candidates for this MSeq index")
    anchors = [(int(x), Fraction(beat)) for x, beat in args.anchor]
    with Image.open(args.preview) as image:
        boxes = green_components(image.convert("RGB"), args.roi)
    report = []
    for ppq in args.ppq:
        for mode in ("single", "stretch", "repeat"):
            predicted = predicted_boxes(notes, ppq=ppq, mode=mode,
                                        source_ticks=args.source_ticks,
                                        placement_ticks=args.placement_ticks,
                                        anchors=anchors,
                                        viewport=(args.roi[0], args.roi[2]))
            report.append({"ppq_hypothesis": ppq, "mode_hypothesis": mode,
                           **compare_starts([b[0] for b in boxes],
                                            [b[0] for b in predicted], args.tolerance),
                           **compare_widths(boxes, predicted, args.tolerance,
                                            (args.roi[0], args.roi[2]))})
    print(json.dumps({"confidence": "HYPOTHESIS; cached image may be stale",
                      "fraction_word_scaling": "UNKNOWN; integer onsets only",
                      "tolerance_pixels": args.tolerance, "hypotheses": report}, indent=2))


if __name__ == "__main__":
    main()
