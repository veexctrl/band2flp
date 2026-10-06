"""Render the repository's reverse-engineering progress JSON as an SVG card."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "docs" / "progress.json"
DEFAULT_OUTPUT = ROOT / "docs" / "progress.svg"


def render(data: dict) -> str:
    categories = data["categories"]
    milestones = data["milestones"]
    if sum(item["weight"] for item in categories) != 100:
        raise ValueError("progress category weights must total 100")
    for item in categories:
        if not 0 <= item["recovered"] <= 100:
            raise ValueError(f"invalid recovered percentage for {item['name']}")
    estimate = sum(item["weight"] * item["recovered"] for item in categories) / 100
    headline = round(estimate / 10) * 10

    rows: list[str] = []
    y = 218
    for item in categories:
        name = escape(item["name"])
        basis = escape(item["basis"])
        pct = item["recovered"]
        rows.append(f'<text x="76" y="{y}" class="row-title">{name}</text>')
        rows.append(f'<text x="1090" y="{y}" class="row-pct" text-anchor="end">~{pct}%</text>')
        rows.append(f'<rect x="76" y="{y + 13}" width="1014" height="8" rx="4" class="bar-bg"/>')
        rows.append(f'<rect x="76" y="{y + 13}" width="{1014 * pct / 100:.1f}" height="8" rx="4" class="bar-fill"/>')
        rows.append(f'<text x="76" y="{y + 43}" class="row-note">{basis}</text>')
        y += 66

    state_style = {
        "complete": ("#52d6a0", "DONE"),
        "partial": ("#58c9f5", "PARTIAL"),
        "early": ("#a994ff", "EARLY"),
        "open": ("#6f8199", "OPEN"),
        "experimental": ("#ffbc66", "EXPERIMENTAL"),
    }
    milestone_nodes: list[str] = []
    left, right = 76, 1090
    step = (right - left) / max(1, len(milestones) - 1)
    for index, item in enumerate(milestones):
        x = left + step * index
        state = item["state"].split(":", 1)[0]
        color, default_label = state_style[state]
        label = escape(item.get("display_label", default_label))
        name = escape(item["name"])
        milestone_nodes.append(f'<circle cx="{x:.1f}" cy="786" r="8" fill="{color}"/>')
        milestone_nodes.append(f'<text x="{x:.1f}" y="816" class="milestone-name" text-anchor="middle">{name}</text>')
        milestone_nodes.append(f'<text x="{x:.1f}" y="838" class="milestone-state" text-anchor="middle" fill="{color}">{label}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1166 880" role="img" aria-labelledby="title desc">
<title id="title">{escape(data['title'])}: about {headline}%</title>
<desc id="desc">{escape(data['scope_note'])}</desc>
<defs><linearGradient id="accent" x1="0" x2="1"><stop offset="0" stop-color="#4de0bd"/><stop offset="1" stop-color="#61b9ff"/></linearGradient></defs>
<rect width="1166" height="880" rx="26" fill="#101826"/>
<text x="76" y="74" class="eyebrow">BAND2FLP · RESEARCH SNAPSHOT · {escape(data['as_of'])}</text>
<text x="76" y="132" class="headline">GarageBand reverse engineering</text>
<text x="76" y="190" class="subhead">Evidence recovered across the targeted project format</text>
<rect x="922" y="54" width="168" height="116" rx="18" fill="#1b2c3e" stroke="#31506a"/>
<text x="1006" y="111" class="big-pct" text-anchor="middle">~{headline}%</text>
<text x="1006" y="143" class="small" text-anchor="middle">estimated coverage</text>
{''.join(rows)}
<line x1="76" y1="706" x2="1090" y2="706" stroke="#2b3a4b"/>
<text x="76" y="748" class="section">MILESTONES</text>
<line x1="76" y1="786" x2="1090" y2="786" stroke="#35465b" stroke-width="2"/>
{''.join(milestone_nodes)}
<text x="76" y="868" class="footer">Heuristic estimate · See docs/progress.json and reverse-engineering notes for evidence and unknowns.</text>
<style>
text {{ font-family: Inter, Segoe UI, Arial, sans-serif; }}
.eyebrow {{ fill:#81a0bb; font-size:14px; font-weight:700; letter-spacing:2px; }}
.headline {{ fill:#edf5fb; font-size:34px; font-weight:700; }}
.subhead {{ fill:#9eb2c4; font-size:17px; }}
.big-pct {{ fill:url(#accent); font-size:43px; font-weight:800; }}
.small {{ fill:#9eb2c4; font-size:13px; }}
.row-title {{ fill:#e1eaf1; font-size:16px; font-weight:650; }}
.row-pct {{ fill:#c0d4e3; font-size:14px; font-weight:700; }}
.bar-bg {{ fill:#243448; }} .bar-fill {{ fill:url(#accent); }}
.row-note {{ fill:#8da2b4; font-size:12px; }}
.section {{ fill:#81a0bb; font-size:13px; font-weight:700; letter-spacing:2px; }}
.milestone-name {{ fill:#cbd8e2; font-size:11px; font-weight:650; }}
.milestone-state {{ font-size:10px; font-weight:800; letter-spacing:1px; }}
.footer {{ fill:#71869a; font-size:11px; }}
</style></svg>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    svg = render(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    estimate = sum(item["weight"] * item["recovered"] for item in data["categories"]) / 100
    print(f"Estimated coverage: {estimate:.1f}% (headline rounded to {round(estimate / 10) * 10}%)")
    print(f"Updated image: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
