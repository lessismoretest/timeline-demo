#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
from typing import Any

import cairosvg
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont


WIDTH = 1242
HEIGHT = 1660
SCALE = 2
W2 = WIDTH * SCALE
H2 = HEIGHT * SCALE
MARGIN_X = 78 * SCALE
TITLE_TOP = 110 * SCALE
CURVE_TOP = 238 * SCALE
CURVE_BOTTOM = 1515 * SCALE
CURVE_CENTER_X = W2 / 2
CURVE_AMPLITUDE = 120 * SCALE
CURVE_CYCLES = 2.2
CARD_WIDTH = 350 * SCALE
CARD_HEIGHT = 92 * SCALE
IMAGE_SIZE = 46 * SCALE

FONT_SF = "/System/Library/Fonts/SFNS.ttf"
FONT_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Apple-style timeline poster to PNG.")
    parser.add_argument("--input", required=True, help="Path to page-level events.json")
    parser.add_argument("--output", required=True, help="Path to output PNG")
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def load_font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)


def blend(c1: str, c2: str, amount: float) -> tuple[int, int, int]:
    a = hex_to_rgb(c1)
    b = hex_to_rgb(c2)
    return tuple(round(x * (1 - amount) + y * amount) for x, y in zip(a, b))


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


def curve_samples(total: int = 140) -> list[tuple[float, float]]:
    points = []
    for idx in range(total):
        t = idx / (total - 1)
        y = CURVE_TOP + (CURVE_BOTTOM - CURVE_TOP) * t
        x = CURVE_CENTER_X + CURVE_AMPLITUDE * math.sin(t * math.pi * CURVE_CYCLES)
        points.append((x, y))
    return points


def date_label(start: str, end: str | None) -> str:
    if not start:
        return ""
    short = start[:7].replace("-", ".")
    if end and end != start:
        return f"{short} - {end[:7].replace('-', '.')}"
    return short


def fit_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str]:
    normalized = " ".join((text or "").replace("\n", " ").split())
    if not normalized:
        return []

    lines: list[str] = []
    current = ""
    for ch in normalized:
        candidate = f"{current}{ch}"
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)

    if len(lines) <= max_lines:
        return lines

    trimmed = lines[:max_lines]
    while trimmed and draw.textlength(trimmed[-1] + "…", font=font) > max_width:
        trimmed[-1] = trimmed[-1][:-1]
    trimmed[-1] += "…"
    return trimmed


def rounded_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int], outline: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)


def paste_image(canvas: Image.Image, image_path: str | None, x: int, y: int, size: int) -> None:
    if not image_path or not Path(image_path).exists():
        return
    path = Path(image_path)
    if path.suffix.lower() == ".svg":
        png_bytes = cairosvg.svg2png(url=str(path), output_width=size, output_height=size)
        image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    else:
        image = Image.open(path).convert("RGBA")
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    plate = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    plate.alpha_composite(image, dest=offset)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=44, fill=255)
    canvas.paste(plate, (x, y), mask)


def render(payload: dict[str, Any], output_path: Path) -> None:
    track = payload["track"]
    events = payload["events"]
    page = payload.get("page", {"number": 1, "total": 1})

    accent = blend(track.get("color", "#64748b"), "#ffffff", 0.18)
    accent_soft = blend(track.get("color", "#64748b"), "#ffffff", 0.8)
    line_color = blend(track.get("color", "#64748b"), "#ffffff", 0.28)
    line_halo = blend(track.get("color", "#64748b"), "#ffffff", 0.72)
    bg_top = (249, 250, 252)
    bg_bottom = blend(track.get("color", "#64748b"), "#ffffff", 0.93)
    text_main = (19, 27, 41)
    text_sub = (102, 112, 133)
    border = (216, 224, 234)
    white = (255, 255, 255)

    canvas = Image.new("RGBA", (W2, H2), bg_top + (255,))
    draw = ImageDraw.Draw(canvas)

    for y in range(H2):
        t = y / max(H2 - 1, 1)
        color = tuple(round(bg_top[i] * (1 - t) + bg_bottom[i] * t) for i in range(3))
        draw.line((0, y, W2, y), fill=color, width=1)

    title_text = track.get("label", "时间轴")
    title_font = load_font(FONT_CN if has_cjk(title_text) else FONT_SF, 74 * SCALE // 2, index=0)
    subtitle_font = load_font(FONT_CN, 30 * SCALE // 2, index=0)
    page_font = load_font(FONT_SF, 24 * SCALE // 2)
    date_font = load_font(FONT_SF, 23 * SCALE // 2)
    title_card_font = load_font(FONT_CN, 29 * SCALE // 2, index=0)
    desc_font = load_font(FONT_CN, 21 * SCALE // 2, index=0)

    draw.text((MARGIN_X, TITLE_TOP), title_text, font=title_font, fill=text_main)
    draw.text((MARGIN_X, TITLE_TOP + 106), "关键节点时间轴", font=subtitle_font, fill=(125, 132, 146))
    draw.line((MARGIN_X, 208 * SCALE, W2 - MARGIN_X, 208 * SCALE), fill=(232, 237, 242), width=3)
    draw.line((MARGIN_X + 30, 230 * SCALE, W2 - MARGIN_X - 30, 230 * SCALE), fill=(232, 237, 242), width=2)

    page_box = (W2 - MARGIN_X - 112 * SCALE, TITLE_TOP + 6, W2 - MARGIN_X, TITLE_TOP + 52 * SCALE)
    draw.rounded_rectangle(page_box, radius=23 * SCALE, fill=white, outline=border, width=3)
    page_text = f"{page.get('number', 1)} / {page.get('total', 1)}"
    tw = draw.textlength(page_text, font=page_font)
    draw.text((page_box[0] + (page_box[2] - page_box[0] - tw) / 2, page_box[1] + 12 * SCALE), page_text, font=page_font, fill=(71, 84, 103))

    samples = curve_samples()
    glow = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.line(samples, fill=line_halo + (130,), width=46 * SCALE // 2, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=18))
    canvas.alpha_composite(glow)

    draw = ImageDraw.Draw(canvas)
    draw.line(samples, fill=line_color, width=15 * SCALE, joint="curve")
    draw.line(samples, fill=white, width=7 * SCALE, joint="curve")

    points = curve_points(len(events))
    for index, event in enumerate(events):
        x, y = points[index]
        side = -1 if index % 2 == 0 else 1
        card_x = int(x - CARD_WIDTH - 62 * SCALE if side < 0 else x + 62 * SCALE)
        card_x = max(MARGIN_X, min(card_x, W2 - MARGIN_X - CARD_WIDTH))
        card_y = int(y - CARD_HEIGHT / 2)
        card_y = max(172 * SCALE, min(card_y, H2 - 102 * SCALE - CARD_HEIGHT))

        connector_end_x = card_x + CARD_WIDTH if side < 0 else card_x
        draw.line((x, y, connector_end_x, y), fill=(210, 218, 228), width=3)

        rounded_card(draw, (card_x, card_y, card_x + CARD_WIDTH, card_y + CARD_HEIGHT), 22 * SCALE, white, border)
        image_x = card_x + 16 * SCALE
        image_y = card_y + 16 * SCALE
        draw.rounded_rectangle((image_x, image_y, image_x + IMAGE_SIZE, image_y + IMAGE_SIZE), radius=14 * SCALE, fill=(246, 248, 251), outline=(229, 235, 242), width=2)
        paste_image(canvas, event.get("logo") or event.get("icon"), image_x, image_y, IMAGE_SIZE)

        dot_r = 12 * SCALE
        draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=accent, outline=white, width=5 * SCALE)

        text_x = image_x + IMAGE_SIZE + 12 * SCALE
        draw.text((text_x, card_y + 10 * SCALE), date_label(event.get("start", ""), event.get("end")), font=date_font, fill=accent)

        title_lines = fit_lines(draw, event.get("title", ""), title_card_font, max_width=220 * SCALE, max_lines=2)
        for line_idx, line in enumerate(title_lines):
            draw.text((text_x, card_y + (28 + line_idx * 20) * SCALE), line, font=title_card_font, fill=text_main)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final = canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).convert("RGB")
    final.save(output_path, quality=100)


def main() -> None:
    args = parse_args()
    payload = load_payload(Path(args.input))
    render(payload, Path(args.output))
    print(args.output)


if __name__ == "__main__":
    main()
