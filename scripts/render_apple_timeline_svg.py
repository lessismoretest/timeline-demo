#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import math
import textwrap
from pathlib import Path
from typing import Any


WIDTH = 1242
HEIGHT = 1660
MARGIN_X = 78
TITLE_TOP = 106
CURVE_TOP = 258
CURVE_BOTTOM = 1490
CURVE_CENTER_X = WIDTH / 2
CURVE_AMPLITUDE = 120
CURVE_CYCLES = 2.2
CARD_WIDTH = 390
CARD_HEIGHT = 162
IMAGE_SIZE = 82


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Apple-style XHS timeline poster to SVG.")
    parser.add_argument("--input", required=True, help="Path to page-level events.json")
    parser.add_argument("--output", required=True, help="Path to output SVG")
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))


def blend(hex_color: str, other: str, amount: float) -> str:
    r1, g1, b1 = hex_to_rgb(hex_color)
    r2, g2, b2 = hex_to_rgb(other)
    mix = lambda a, b: round(a * (1 - amount) + b * amount)
    return f"#{mix(r1, r2):02x}{mix(g1, g2):02x}{mix(b1, b2):02x}"


def date_label(start: str, end: str | None) -> str:
    if not start:
        return ""
    short = start[:7].replace("-", ".")
    if end and end != start:
        return f"{short} - {end[:7].replace('-', '.')}"
    return short


def wrap_text(text: str, width: int, lines: int) -> list[str]:
    normalized = " ".join((text or "").replace("\n", " ").split())
    if not normalized:
        return []
    wrapped = textwrap.wrap(normalized, width=width, break_long_words=True, break_on_hyphens=False)
    if len(wrapped) <= lines:
        return wrapped
    kept = wrapped[:lines]
    kept[-1] = kept[-1].rstrip("，。；：,. ") + "…"
    return kept


def image_data_uri(path_str: str | None) -> str | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.exists():
        return None
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower())
    if not mime:
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def curve_points(count: int) -> list[tuple[float, float]]:
    if count == 1:
        return [(CURVE_CENTER_X, (CURVE_TOP + CURVE_BOTTOM) / 2)]
    points = []
    for index in range(count):
        t = index / (count - 1)
        y = CURVE_TOP + (CURVE_BOTTOM - CURVE_TOP) * t
        x = CURVE_CENTER_X + CURVE_AMPLITUDE * math.sin(t * math.pi * CURVE_CYCLES)
        points.append((x, y))
    return points


def build_curve_path() -> str:
    samples: list[tuple[float, float]] = []
    total = 84
    for idx in range(total):
        t = idx / (total - 1)
        y = CURVE_TOP + (CURVE_BOTTOM - CURVE_TOP) * t
        x = CURVE_CENTER_X + CURVE_AMPLITUDE * math.sin(t * math.pi * CURVE_CYCLES)
        samples.append((x, y))

    commands = [f"M {samples[0][0]:.1f} {samples[0][1]:.1f}"]
    for i in range(1, len(samples) - 2, 3):
        p1 = samples[i]
        p2 = samples[i + 1]
        p3 = samples[i + 2]
        commands.append(f"C {p1[0]:.1f} {p1[1]:.1f}, {p2[0]:.1f} {p2[1]:.1f}, {p3[0]:.1f} {p3[1]:.1f}")
    return " ".join(commands)


def render_svg(payload: dict[str, Any]) -> str:
    track = payload["track"]
    events = payload["events"]
    page = payload.get("page", {"number": 1, "total": 1})
    accent = blend(track.get("color", "#64748b"), "#ffffff", 0.2)
    accent_soft = blend(track.get("color", "#64748b"), "#ffffff", 0.78)
    line_outer = blend(track.get("color", "#64748b"), "#e2e8f0", 0.55)
    line_inner = blend(track.get("color", "#64748b"), "#ffffff", 0.3)
    text_main = "#111827"
    text_sub = "#6b7280"
    card_border = "#d7dee8"
    bg_tint = blend(track.get("color", "#64748b"), "#ffffff", 0.93)

    nodes = curve_points(len(events))
    curve_path = build_curve_path()
    card_elements: list[str] = []

    for index, event in enumerate(events):
        x, y = nodes[index]
        side = -1 if index % 2 == 0 else 1
        card_x = x - CARD_WIDTH - 88 if side < 0 else x + 88
        card_x = max(MARGIN_X, min(card_x, WIDTH - MARGIN_X - CARD_WIDTH))
        card_y = y - CARD_HEIGHT / 2
        card_y = max(190, min(card_y, HEIGHT - 120 - CARD_HEIGHT))

        date = date_label(event.get("start", ""), event.get("end"))
        title_lines = wrap_text(event.get("title", ""), width=13, lines=2)
        desc_lines = wrap_text(event.get("description", ""), width=18, lines=2)
        image_uri = image_data_uri(event.get("logo") or event.get("icon"))
        card_id = f"card-{index}"
        image_x = card_x + 18
        image_y = card_y + 18
        text_x = image_x + IMAGE_SIZE + 18

        connector_end_x = card_x + CARD_WIDTH if side < 0 else card_x
        connector_mid_x = x + (connector_end_x - x) * 0.46

        title_svg = "".join(
            f'<text x="{text_x}" y="{card_y + 76 + line_idx * 30}" class="title">{line}</text>'
            for line_idx, line in enumerate(title_lines)
        )
        desc_svg = "".join(
            f'<text x="{text_x}" y="{card_y + 118 + line_idx * 24}" class="desc">{line}</text>'
            for line_idx, line in enumerate(desc_lines)
        )

        image_svg = (
            f'<image href="{image_uri}" x="{image_x}" y="{image_y}" width="{IMAGE_SIZE}" height="{IMAGE_SIZE}" preserveAspectRatio="xMidYMid meet" clip-path="url(#{card_id}-clip)" />'
            if image_uri
            else f'<rect x="{image_x}" y="{image_y}" width="{IMAGE_SIZE}" height="{IMAGE_SIZE}" rx="22" fill="{accent_soft}" />'
        )

        card_elements.append(
            f"""
            <g>
              <path d="M {x:.1f} {y:.1f} C {connector_mid_x:.1f} {y:.1f}, {connector_mid_x:.1f} {y:.1f}, {connector_end_x:.1f} {y:.1f}"
                    stroke="#cfd8e3" stroke-width="3" fill="none" stroke-linecap="round"/>
              <circle cx="{x:.1f}" cy="{y:.1f}" r="14" fill="{accent}" stroke="white" stroke-width="6"/>
              <rect x="{card_x}" y="{card_y}" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="30" fill="white" stroke="{card_border}" stroke-width="2"/>
              <rect x="{image_x}" y="{image_y}" width="{IMAGE_SIZE}" height="{IMAGE_SIZE}" rx="22" fill="#f6f8fb" stroke="#e5ebf2" stroke-width="1.5"/>
              <clipPath id="{card_id}-clip">
                <rect x="{image_x}" y="{image_y}" width="{IMAGE_SIZE}" height="{IMAGE_SIZE}" rx="22"/>
              </clipPath>
              {image_svg}
              <text x="{text_x}" y="{card_y + 42}" class="date">{date}</text>
              {title_svg}
              {desc_svg}
            </g>
            """
        )

    page_badge = f"{page.get('number', 1)} / {page.get('total', 1)}"
    subtitle = "关键节点时间轴"
    header_title = track.get("label", "时间轴")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fbfcfe"/>
      <stop offset="100%" stop-color="{bg_tint}"/>
    </linearGradient>
    <linearGradient id="line" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{line_outer}"/>
      <stop offset="50%" stop-color="{line_inner}"/>
      <stop offset="100%" stop-color="{line_outer}"/>
    </linearGradient>
    <filter id="lineGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="12" result="blur"/>
      <feColorMatrix in="blur" type="matrix"
        values="1 0 0 0 0
                0 1 0 0 0
                0 0 1 0 0
                0 0 0 .18 0" result="soft"/>
      <feMerge>
        <feMergeNode in="soft"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <style>
      .display {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 74px;
        font-weight: 700;
        fill: {text_main};
        letter-spacing: -1.5px;
      }}
      .subtitle {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 28px;
        font-weight: 600;
        fill: {text_sub};
        letter-spacing: .5px;
      }}
      .page {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 24px;
        font-weight: 600;
        fill: #475467;
      }}
      .date {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 23px;
        font-weight: 700;
        fill: {accent};
        letter-spacing: .2px;
      }}
      .title {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 29px;
        font-weight: 700;
        fill: {text_main};
      }}
      .desc {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
        font-size: 21px;
        font-weight: 500;
        fill: {text_sub};
      }}
    </style>
  </defs>

  <rect width="100%" height="100%" fill="url(#bg)"/>
  <g opacity=".35">
    <path d="M 106 164 H 1136" stroke="#edf1f5" stroke-width="2"/>
    <path d="M 106 208 H 1136" stroke="#edf1f5" stroke-width="2"/>
  </g>

  <text x="{MARGIN_X}" y="{TITLE_TOP}" class="display">{header_title}</text>
  <text x="{MARGIN_X}" y="{TITLE_TOP + 48}" class="subtitle">{subtitle}</text>
  <g transform="translate({WIDTH - MARGIN_X - 110}, {TITLE_TOP - 38})">
    <rect width="110" height="46" rx="23" fill="white" stroke="#d8e0ea" stroke-width="2"/>
    <text x="55" y="31" text-anchor="middle" class="page">{page_badge}</text>
  </g>

  <g filter="url(#lineGlow)">
    <path d="{curve_path}" stroke="url(#line)" stroke-width="28" fill="none" stroke-linecap="round"/>
    <path d="{curve_path}" stroke="#ffffff" stroke-width="10" fill="none" stroke-linecap="round" opacity=".92"/>
  </g>

  {''.join(card_elements)}
</svg>
"""


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    payload = load_payload(input_path)
    svg = render_svg(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
