#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TIMELINE_PATH = ROOT / "timeline.json"
OUTPUT_ROOT = ROOT / "output" / "gemini_timeline_by_track"
XHS_WIDTH = 1242
XHS_HEIGHT = 1660
IDEAL_EVENTS_PER_PAGE = 10
MAX_EVENTS_PER_PAGE = 10


def load_timeline() -> dict[str, Any]:
    with TIMELINE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_asset_path(path_str: str | None) -> str | None:
    if not path_str:
        return None
    cleaned = path_str.strip()
    if not cleaned:
        return None
    if cleaned.startswith("./"):
        return str((ROOT / cleaned[2:]).resolve())
    return str((ROOT / cleaned).resolve())


def build_track_payload(
    track_key: str,
    track_meta: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_events = sorted(events, key=lambda item: (item.get("start", ""), item.get("id", 0)))
    payload_events: list[dict[str, Any]] = []
    for index, event in enumerate(sorted_events, start=1):
        payload_events.append(
            {
                "sequence": index,
                "id": event.get("id"),
                "start": event.get("start"),
                "end": event.get("end"),
                "title": event.get("title"),
                "category": event.get("category"),
                "description": event.get("description"),
                "keywords": event.get("keywords") or [],
                "track": event.get("track"),
                "primaryTrack": event.get("primaryTrack") or event.get("track"),
                "pest": event.get("pest") or [],
                "logo": resolve_asset_path(event.get("logo")),
                "icon": resolve_asset_path(event.get("icon")),
                "favorite": bool(event.get("favorite")),
            }
        )

    return {
        "track": {
            "key": track_key,
            "label": track_meta.get("label", track_key),
            "parent": track_meta.get("parent"),
            "order": track_meta.get("order", 999),
            "color": track_meta.get("color", "#334155"),
            "dot": track_meta.get("dot", "#cbd5e1"),
        },
        "canvas": {
            "platform": "Xiaohongshu",
            "width": XHS_WIDTH,
            "height": XHS_HEIGHT,
            "aspectRatio": "3:4",
        },
        "layout_requirements": {
            "timeline_style": "single_s_curve",
            "node_anchor": "all_nodes_must_sit_on_the_curve",
            "image_usage": "use_event_logo_or_icon_as_visual_material_when_available",
            "reading_direction": "top_to_bottom",
        },
        "events": payload_events,
    }


def build_prompt(track_payload: dict[str, Any]) -> str:
    track = track_payload["track"]
    canvas = track_payload["canvas"]
    events = track_payload["events"]
    page = track_payload.get("page")
    event_lines = []
    for event in events:
        image_path = event["logo"] or event["icon"] or "无"
        keywords = "、".join(event["keywords"]) if event["keywords"] else "无"
        event_lines.append(
            "\n".join(
                [
                    f"- 序号：{event['sequence']}",
                    f"  日期：{event['start']}" + (f" 至 {event['end']}" if event.get("end") else ""),
                    f"  标题：{event['title']}",
                    f"  描述：{event['description'] or '无'}",
                    f"  关键词：{keywords}",
                    f"  图片素材：{image_path}",
                ]
            )
        )

    event_block = "\n".join(event_lines)
    page_title = ""
    page_instruction = ""
    if page:
        page_title = f"\n分页信息：第 {page['number']} 张，共 {page['total']} 张"
        page_instruction = (
            f"\n11. 这是一个分页系列中的第 {page['number']} 张，请只呈现当前页事件，"
            "不要混入其他分页内容；但视觉风格需要与同赛道其他分页保持一致。"
        )

    return f"""你是一名信息设计师，请基于下面的数据，为“小红书竖版封面图/信息图”生成一张时间轴海报。

目标赛道：{track['label']}（track key: {track['key']}）
画布尺寸：{canvas['width']} x {canvas['height']}，比例 {canvas['aspectRatio']}
主色：{track['color']}
辅助点色：{track['dot']}{page_title}

必须满足的版式要求：
1. 使用一条从上到下延展的 S 曲线时间轴，曲线要自然、优雅、连续。
2. 所有时间节点都必须落在这条 S 曲线上，不要漂浮在线外。
3. 每个节点包含：年份/日期、事件标题、极短说明、对应图片。
4. 优先使用“图片素材”字段中的本地图片作为节点视觉；如果图片较小，可做裁切、描边、圆角卡片或徽章处理。
5. 信息密度要适合小红书浏览，层次清楚，避免过多正文；标题醒目，说明尽量 1 行到 2 行。
6. 整体风格偏高信息密度的信息图，不要做成 PPT，也不要做成普通折线图。
7. 赛道名“{track['label']}”作为主标题，标题区可加入一句副标题：关键节点时间轴。
8. 时间顺序必须严格按从早到晚排列。
9. 节点文案请直接使用中文，不要改写得过长。
10. 画面中要明显看到“点在线上”的关系：节点圆点、图片卡片、说明卡片都围绕 S 曲线组织。
{page_instruction}

建议视觉表现：
- 让 S 曲线成为视觉骨架，可带轻微发光、渐变或虚实变化。
- 节点图片大小可有节奏变化，但不要喧宾夺主。
- 可在起点、拐点、终点设置更强的视觉锚点。
- 背景尽量干净，可带轻微纹理、网格或淡渐变。

请基于以下事件数据完成设计：
{event_block}
"""


def paginate_events(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    total = len(events)
    if total <= MAX_EVENTS_PER_PAGE:
        return [events]

    page_count = max(2, (total + IDEAL_EVENTS_PER_PAGE - 1) // IDEAL_EVENTS_PER_PAGE)
    base_size = total // page_count
    remainder = total % page_count

    pages: list[list[dict[str, Any]]] = []
    start = 0
    for page_index in range(page_count):
        size = base_size + (1 if page_index < remainder else 0)
        if size > MAX_EVENTS_PER_PAGE:
            size = MAX_EVENTS_PER_PAGE
        pages.append(events[start : start + size])
        start += size

    if start < total:
        pages[-1].extend(events[start:])

    return [page for page in pages if page]


def main() -> None:
    timeline = load_timeline()
    meta_tracks = timeline.get("meta", {}).get("tracks", {})
    events = timeline.get("events", [])

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        track_key = event.get("primaryTrack") or event.get("track") or "general"
        grouped[track_key].append(event)

    ensure_dir(OUTPUT_ROOT)
    manifest: list[dict[str, Any]] = []

    for track_key, track_events in sorted(
        grouped.items(),
        key=lambda item: (meta_tracks.get(item[0], {}).get("order", 999), item[0]),
    ):
        track_meta = meta_tracks.get(track_key, {"label": track_key})
        track_dir = OUTPUT_ROOT / track_key
        ensure_dir(track_dir)

        payload = build_track_payload(track_key, track_meta, track_events)
        prompt = build_prompt(payload)

        data_path = track_dir / "events.json"
        prompt_path = track_dir / "gemini_prompt.md"

        data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt_path.write_text(prompt, encoding="utf-8")

        pages = paginate_events(payload["events"])
        page_manifest: list[dict[str, Any]] = []
        pages_dir = track_dir / "pages"
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
        ensure_dir(pages_dir)

        for page_index, page_events in enumerate(pages, start=1):
            page_payload = {
                **payload,
                "page": {
                    "number": page_index,
                    "total": len(pages),
                    "eventCount": len(page_events),
                },
                "events": page_events,
            }
            page_prompt = build_prompt(page_payload)

            page_dir = pages_dir / f"page-{page_index:02d}"
            ensure_dir(page_dir)

            page_data_path = page_dir / "events.json"
            page_prompt_path = page_dir / "gemini_prompt.md"
            page_data_path.write_text(
                json.dumps(page_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            page_prompt_path.write_text(page_prompt, encoding="utf-8")

            page_manifest.append(
                {
                    "page": page_index,
                    "eventCount": len(page_events),
                    "start": page_events[0]["start"],
                    "end": page_events[-1]["start"],
                    "titles": [event["title"] for event in page_events],
                    "dataFile": str(page_data_path.relative_to(ROOT)),
                    "promptFile": str(page_prompt_path.relative_to(ROOT)),
                }
            )

        manifest.append(
            {
                "track": track_key,
                "label": payload["track"]["label"],
                "eventCount": len(payload["events"]),
                "recommendedImageCount": len(pages),
                "dataFile": str(data_path.relative_to(ROOT)),
                "promptFile": str(prompt_path.relative_to(ROOT)),
                "pages": page_manifest,
            }
        )

    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(manifest)} tracks to {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
