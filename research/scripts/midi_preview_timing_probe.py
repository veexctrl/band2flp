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


def fit_vertical_fields(observed_boxes, candidate_points, tolerance):
    """Fit candidate note fields to preview y after one-to-one x association.

    candidate_points contains (predicted_x, {field: integer_value}). The fit
    is diagnostic only: each track can use an independent vertical zoom.
    """
    if tolerance < 0 or len(observed_boxes) * len(candidate_points) > 2_000_000:
        raise ValueError("invalid vertical comparison or resource limit")
    observed = sorted(observed_boxes, key=lambda box: box[0])
    candidates = sorted(candidate_points, key=lambda point: point[0])
    i = j = 0
    pairs = []
    while i < len(observed) and j < len(candidates):
        delta = observed[i][0] - candidates[j][0]
        if abs(delta) <= tolerance:
            y = (observed[i][1] + observed[i][3]) / 2
            pairs.append((candidates[j][1], y))
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    fields = sorted({name for values, _ in pairs for name in values})
    result = {}
    for field in fields:
        samples = [(values[field], y) for values, y in pairs
                   if isinstance(values.get(field), int)]
        xs = [float(x) for x, _ in samples]
        ys = [float(y) for _, y in samples]
        distinct = len(set(xs))
        if len(samples) < 3 or distinct < 2:
            result[field] = {"sample_count": len(samples),
                             "distinct_candidate_values": distinct,
                             "linear_fit": "unavailable"}
            continue
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        variance = sum((x-x_mean)**2 for x in xs)
        slope = sum((x-x_mean)*(y-y_mean) for x, y in zip(xs, ys)) / variance
        intercept = y_mean - slope*x_mean
        residuals = [y-(intercept+slope*x) for x, y in zip(xs, ys)]
        total = sum((y-y_mean)**2 for y in ys)
        held_out_errors = []
        for held_out in set(xs):
            train = [(x, y) for x, y in zip(xs, ys) if x != held_out]
            if len({x for x, _ in train}) < 2:
                continue
            train_x = sum(x for x, _ in train)/len(train)
            train_y = sum(y for _, y in train)/len(train)
            train_var = sum((x-train_x)**2 for x, _ in train)
            train_slope = sum((x-train_x)*(y-train_y) for x, y in train)/train_var
            train_intercept = train_y-train_slope*train_x
            held_out_errors.extend(abs(y-(train_intercept+train_slope*x))
                                   for x, y in zip(xs, ys) if x == held_out)
        result[field] = {
            "sample_count": len(samples),
            "distinct_candidate_values": distinct,
            "slope_pixels_per_value": round(slope, 4),
            "mean_absolute_residual_pixels": round(
                sum(abs(x) for x in residuals)/len(residuals), 4),
            "r_squared": round(1-sum(x*x for x in residuals)/total, 5) if total else None,
            "leave_one_value_out_mean_absolute_error_pixels": round(
                sum(held_out_errors)/len(held_out_errors), 4) if held_out_errors else None,
        }
    return {"matched_start_count": len(pairs), "field_fits": result}


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
    candidate_notes = [n for n in project.project_data["midi_note_event_candidates"]
                       if n["candidate_mseq_chunk_indices_for_group"] == [args.mseq_index]]
    if not candidate_notes:
        parser.error("no uniquely linked note candidates for this MSeq index")
    notes = [(n["position_ticks_from_38400_candidate"], n["duration_ticks_candidate"])
             for n in candidate_notes]
    anchors = [(int(x), Fraction(beat)) for x, beat in args.anchor]
    with Image.open(args.preview) as image:
        boxes = green_components(image.convert("RGB"), args.roi)
    (anchor_x, anchor_beat), (anchor_x2, anchor_beat2) = anchors
    pixels_per_beat = Fraction(anchor_x2-anchor_x, 1)/(anchor_beat2-anchor_beat)
    vertical_points = []
    for note in candidate_notes:
        x = anchor_x + (Fraction(note["position_ticks_from_38400_candidate"], 960)
                        - anchor_beat)*pixels_per_beat
        vertical_points.append((x, {
            "pitch_candidate": note["pitch_candidate"],
            "velocity_candidate": note["velocity_candidate"],
            "fine_velocity_byte_candidate": note["fine_velocity_byte_candidate"],
        }))
    vertical_fit = fit_vertical_fields(boxes, vertical_points, args.tolerance)
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
                      "tolerance_pixels": args.tolerance,
                      "vertical_candidate_field_associations": vertical_fit,
                      "hypotheses": report}, indent=2))


if __name__ == "__main__":
    main()
