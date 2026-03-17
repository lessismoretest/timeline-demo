#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
TIMELINE_PATH = ROOT / "timeline.json"
ASSETS_DATA_PATH = ROOT / "assets" / "image_data.json"
ASSETS_IMAGE_DIR = ROOT / "assets" / "image"
GRAPH_SCHEMA_PATH = ROOT / "schemas" / "graph-refine.v1.schema.json"
MODEL_SCHEMA_VERSION = "graph-refine.v1"
GRAPH_SCHEMA = json.loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
SERVER_BUILD = "2026-03-21-focus-fix-3"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
MAX_MODEL_OPERATIONS = int(os.getenv("MAX_MODEL_OPERATIONS", "6"))
THINK_DIFFERENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "tone": {"type": "string"},
        "items": {
            "type": "array",
            "minItems": 4,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "perspective": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tone": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 4,
                    },
                },
                "required": ["perspective", "title", "body", "tone", "tags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["topic", "tone", "items"],
    "additionalProperties": False,
}
GEMINI_MODEL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "request_id": {"type": "string"},
        "summary": {
            "type": "object",
            "properties": {
                "reasoning_mode": {"type": "string"},
                "operation_count": {"type": "integer"},
            },
            "required": ["reasoning_mode", "operation_count"],
            "additionalProperties": False,
        },
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": [
                            "merge_node",
                            "set_node_type",
                            "add_pending_node",
                            "rename_node",
                            "update_node_description",
                            "add_edge",
                            "remove_edge",
                            "mark_revisited",
                            "set_focus",
                        ],
                    },
                    "from": {"type": "object"},
                    "to": {"type": "object"},
                    "target": {"type": "object"},
                    "source": {"type": "object"},
                    "node": {"type": "object"},
                    "connect_to": {"type": "object"},
                    "node_type": {"type": "string"},
                    "new_label": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["op"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["schema_version", "request_id", "summary", "operations"],
    "additionalProperties": False,
}


class TimelineHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path == "/assets/image_data.json":
            self.handle_get_assets_data()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/save":
            self.handle_save_timeline()
        elif self.path == "/save-assets":
            self.handle_save_assets()
        elif self.path == "/rename-asset":
            self.handle_rename_asset()
        elif self.path == "/delete-asset":
            self.handle_delete_asset()
        elif self.path == "/api/graph-refine":
            self.handle_graph_refine()
        elif self.path == "/api/think-different":
            self.handle_think_different()
        elif self.path == "/api/camera-view":
            self.handle_camera_view()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def handle_save_timeline(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
            if isinstance(payload, list):
                payload = {"meta": {"tracks": {}}, "events": payload}

            TIMELINE_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "saved": str(TIMELINE_PATH)})
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_save_assets(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            decoded_body = raw_body.decode("utf-8")
            payload = json.loads(decoded_body)

            if not isinstance(payload, dict) or "images" not in payload:
                raise ValueError(f"Invalid assets data format: {type(payload)}")

            # Ensure all entries are clean
            images = payload["images"]

            ASSETS_DATA_PATH.write_text(
                json.dumps({"images": images}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Successfully saved {len(images)} images to {ASSETS_DATA_PATH}")
            self._send_json(HTTPStatus.OK, {"ok": True, "saved": str(ASSETS_DATA_PATH)})
        except Exception as exc:
            print(f"Error saving assets: {exc}")
            import traceback

            traceback.print_exc()
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_get_assets_data(self) -> None:
        try:
            payload = self._sync_assets_data()
            self._send_json(HTTPStatus.OK, payload)
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_rename_asset(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))

            old_filename = self._clean_filename(payload.get("oldFilename", ""))
            new_filename = self._clean_filename(payload.get("newFilename", ""))

            if not old_filename or not new_filename:
                raise ValueError("oldFilename 和 newFilename 不能为空")

            old_path = ASSETS_IMAGE_DIR / old_filename
            new_path = ASSETS_IMAGE_DIR / new_filename

            if not old_path.exists():
                raise FileNotFoundError(f"原文件不存在: {old_filename}")

            if new_path.exists():
                raise FileExistsError(f"目标文件已存在: {new_filename}")

            assets_payload = json.loads(ASSETS_DATA_PATH.read_text(encoding="utf-8"))
            images = assets_payload.get("images", [])

            match = next(
                (image for image in images if image.get("filename") == old_filename),
                None,
            )
            if match is None:
                raise ValueError(f"未在 image_data.json 中找到文件: {old_filename}")

            old_path.rename(new_path)
            match["filename"] = new_filename

            ASSETS_DATA_PATH.write_text(
                json.dumps({"images": images}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "oldFilename": old_filename,
                    "newFilename": new_filename,
                    "saved": str(ASSETS_DATA_PATH),
                },
            )
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_delete_asset(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))

            filename = self._clean_filename(payload.get("filename", ""))
            if not filename:
                raise ValueError("filename 不能为空")

            assets_payload = json.loads(ASSETS_DATA_PATH.read_text(encoding="utf-8"))
            images = assets_payload.get("images", [])
            next_images = [
                image for image in images if image.get("filename") != filename
            ]

            if len(next_images) == len(images):
                raise ValueError(f"未在 image_data.json 中找到文件: {filename}")

            asset_path = ASSETS_IMAGE_DIR / filename
            file_deleted = False
            if asset_path.exists():
                asset_path.unlink()
                file_deleted = True

            ASSETS_DATA_PATH.write_text(
                json.dumps({"images": next_images}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )

            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "deletedFilename": filename,
                    "fileDeleted": file_deleted,
                    "saved": str(ASSETS_DATA_PATH),
                },
            )
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_graph_refine(self) -> None:
        try:
            payload = self._read_json_body()
            self._validate_graph_refine_request(payload)
            try:
                response = self._gemini_graph_refine_response(payload)
            except Exception as gemini_exc:
                print(f"Gemini refine failed, fallback to server mock: {gemini_exc}")
                response = self._mock_graph_refine_response(
                    payload,
                    reasoning_mode="server-mock-fallback",
                )
            self._validate_graph_refine_response(response)
            self._send_json(HTTPStatus.OK, response)
        except Exception as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": str(exc),
                    "schemaVersion": MODEL_SCHEMA_VERSION,
                },
            )

    def handle_think_different(self) -> None:
        try:
            payload = self._read_json_body()
            topic = str(payload.get("topic", "")).strip()
            tone = str(payload.get("tone", "mixed")).strip() or "mixed"
            if not topic:
                raise ValueError("topic 不能为空")
            if tone not in {"mixed", "poetic", "sharp", "vision"}:
                raise ValueError("tone 不合法")
            response = self._gemini_think_different_response(topic=topic, tone=tone)
            self._send_json(HTTPStatus.OK, response)
        except Exception as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": str(exc),
                    "source": "server",
                },
            )

    def handle_camera_view(self) -> None:
        try:
            payload = self._read_json_body()
            b64_image = payload.get("image", "")
            user_prompt = payload.get("prompt", "")

            if not b64_image or not user_prompt:
                raise ValueError("image 和 prompt 不能为空")

            os.makedirs(ASSETS_IMAGE_DIR, exist_ok=True)

            if "," in b64_image:
                header, b64_image = b64_image.split(",", 1)

            input_filename = f"camera_input_{int(time.time())}.png"
            input_path = ASSETS_IMAGE_DIR / input_filename
            input_path.write_bytes(base64.b64decode(b64_image))

            output_filename = f"camera_output_{int(time.time())}.png"
            output_path = ASSETS_IMAGE_DIR / output_filename

            aspect_ratio_arg = []
            if "16:9 cinematic aspect ratio" in user_prompt:
                aspect_ratio_arg = ["--aspect-ratio", "16:9"]
            elif "9:16 vertical mobile aspect ratio" in user_prompt:
                aspect_ratio_arg = ["--aspect-ratio", "9:16"]
            elif "1:1 square aspect ratio" in user_prompt:
                aspect_ratio_arg = ["--aspect-ratio", "1:1"]

            clean_prompt = (
                user_prompt.replace(" | 16:9 cinematic aspect ratio", "")
                .replace(" | 9:16 vertical mobile aspect ratio", "")
                .replace(" | 1:1 square aspect ratio", "")
                .replace(
                    " | (THREE-VIEW-MODE) generate three separate consistent character reference images: front, side, and back views. ensure each view is clear and isolated.",
                    "",
                )
            )

            full_prompt = (
                f"Repaint image from a new camera angle: {clean_prompt}. "
                "Keep subject, lighting, and colors identical. "
                "The target is to see the exact same object from the specified perspective."
            )

            skill_script = os.path.expanduser(
                "~/.codex/skills/nano-banana-pro/scripts/generate_image.py"
            )
            cmd = [
                "uv",
                "run",
                skill_script,
                "--prompt",
                full_prompt,
                "--input-image",
                str(input_path),
                "--filename",
                str(output_path),
                "--resolution",
                "1K",
            ] + aspect_ratio_arg

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                err_msg = (
                    result.stderr.strip() or result.stdout.strip() or "未知生成脚本错误"
                )
                print(f"Skill error: {err_msg}")
                raise RuntimeError(f"图像生成失败: {err_msg}")

            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "url": f"/assets/image/{output_filename}",
                    "prompt": full_prompt,
                },
            )

        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _sync_assets_data(self) -> dict:
        if ASSETS_DATA_PATH.exists():
            assets_payload = json.loads(ASSETS_DATA_PATH.read_text(encoding="utf-8"))
            images = assets_payload.get("images", [])
        else:
            images = []

        existing_by_filename = {
            str(image.get("filename", "")).strip(): image
            for image in images
            if str(image.get("filename", "")).strip()
        }

        discovered_files = sorted(
            [
                path.name
                for path in ASSETS_IMAGE_DIR.iterdir()
                if path.is_file() and path.name != ".DS_Store"
            ],
            key=str.lower,
        )

        next_images = []
        next_id = self._next_image_id(images)

        for filename in discovered_files:
            if filename in existing_by_filename:
                next_images.append(existing_by_filename[filename])
                continue

            stem = Path(filename).stem
            next_images.append(
                {
                    "id": str(next_id),
                    "filename": filename,
                    "title": stem,
                    "tags": [],
                    "remarks": "",
                }
            )
            next_id += 1

        payload = {"images": next_images}
        ASSETS_DATA_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    def _next_image_id(self, images: list[dict]) -> int:
        numeric_ids = []
        for image in images:
            try:
                numeric_ids.append(int(str(image.get("id", "")).strip()))
            except ValueError:
                continue
        return (max(numeric_ids) if numeric_ids else 0) + 1

    def _clean_filename(self, value: str) -> str:
        filename = Path(str(value or "").strip()).name
        if not filename or filename in {".", ".."}:
            raise ValueError("文件名不合法")
        return filename

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body 必须是 object")
        return payload

    def _assert_has_keys(
        self, obj: dict[str, Any], keys: list[str], label: str
    ) -> None:
        missing = [key for key in keys if key not in obj]
        if missing:
            raise ValueError(f"{label} 缺少字段: {', '.join(missing)}")

    def _validate_graph_refine_request(self, payload: dict[str, Any]) -> None:
        self._assert_has_keys(
            payload,
            [
                "protocol",
                "schema_version",
                "session",
                "window",
                "graph_snapshot",
                "candidate_nodes",
                "instructions",
            ],
            "request",
        )
        protocol = payload["protocol"]
        if not isinstance(protocol, dict):
            raise ValueError("protocol 必须是 object")
        self._assert_has_keys(protocol, ["schema_version", "schema_path"], "protocol")
        if (
            protocol["schema_version"] != MODEL_SCHEMA_VERSION
            or payload["schema_version"] != MODEL_SCHEMA_VERSION
        ):
            raise ValueError(f"schema_version 必须是 {MODEL_SCHEMA_VERSION}")
        session = payload["session"]
        window = payload["window"]
        graph_snapshot = payload["graph_snapshot"]
        instructions = payload["instructions"]
        self._assert_has_keys(session, ["session_id", "request_id"], "session")
        self._assert_has_keys(window, ["raw_text", "segments"], "window")
        self._assert_has_keys(
            graph_snapshot,
            ["node_count", "edge_count", "nodes", "edges"],
            "graph_snapshot",
        )
        self._assert_has_keys(
            instructions, ["goal", "allowed_operations"], "instructions"
        )
        if not isinstance(payload["candidate_nodes"], list):
            raise ValueError("candidate_nodes 必须是数组")
        if not isinstance(window["segments"], list):
            raise ValueError("window.segments 必须是数组")
        if not isinstance(graph_snapshot["nodes"], list) or not isinstance(
            graph_snapshot["edges"], list
        ):
            raise ValueError("graph_snapshot.nodes / edges 必须是数组")

    def _validate_graph_refine_response(self, response: dict[str, Any]) -> None:
        self._assert_has_keys(
            response,
            ["schema_version", "request_id", "summary", "operations"],
            "response",
        )
        if response["schema_version"] != MODEL_SCHEMA_VERSION:
            raise ValueError(f"response.schema_version 必须是 {MODEL_SCHEMA_VERSION}")
        summary = response["summary"]
        self._assert_has_keys(
            summary, ["reasoning_mode", "operation_count"], "response.summary"
        )
        if not isinstance(response["operations"], list):
            raise ValueError("response.operations 必须是数组")

    def _normalize_model_response(
        self,
        payload: dict[str, Any],
        raw_response: dict[str, Any],
        *,
        reasoning_mode: str,
        debug_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        operations = raw_response.get("operations", [])
        if not isinstance(operations, list):
            operations = []

        normalized_ops: list[dict[str, Any]] = []
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            normalized_op = self._coerce_operation_shape(operation)
            op_type = normalized_op.get("op")
            if op_type not in {
                "merge_node",
                "set_node_type",
                "add_pending_node",
                "rename_node",
                "add_edge",
                "remove_edge",
                "mark_revisited",
                "set_focus",
            }:
                continue
            normalized_ops.append(normalized_op)

        normalized_ops = self._prune_operations(payload, normalized_ops)

        return {
            "schema_version": MODEL_SCHEMA_VERSION,
            "request_id": payload["session"]["request_id"],
            "summary": {
                "reasoning_mode": reasoning_mode,
                "operation_count": len(normalized_ops),
                "server_build": SERVER_BUILD,
                "debug": debug_meta or {},
            },
            "operations": normalized_ops,
        }

    def _prune_operations(
        self,
        payload: dict[str, Any],
        operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen_keys: set[str] = set()
        pruned: list[dict[str, Any]] = []
        focus_ops: list[dict[str, Any]] = []
        existing_labels = {
            str(node.get("label", "")).strip()
            for node in payload.get("graph_snapshot", {}).get("nodes", [])
            if str(node.get("label", "")).strip()
        }
        raw_text = payload.get("window", {}).get("raw_text", "")

        for op in operations:
            if op["op"] == "set_focus":
                focus_ops = [op]
                continue

            key = json.dumps(op, ensure_ascii=False, sort_keys=True)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            if op["op"] == "rename_node":
                new_label = op.get("new_label", "").strip()
                target = op.get("target", {})
                old_label = (
                    target.get("value", "").strip()
                    if target.get("by") == "label"
                    else ""
                )
                if not new_label or len(new_label) < 2:
                    continue
                if old_label and old_label == new_label:
                    continue
                if new_label in existing_labels:
                    continue

            if op["op"] == "update_node_description":
                description = str(op.get("description", "")).strip()
                if len(description) < 4:
                    continue

            if op["op"] == "add_pending_node":
                node = op.get("node", {})
                label = str(node.get("label", "")).strip()
                if not label or label in existing_labels or len(label) > 18:
                    continue

            if op["op"] == "mark_revisited":
                target = op.get("target", {})
                target_value = str(target.get("value", "")).strip()
                if (
                    target.get("by") == "label"
                    and target_value
                    and target_value not in raw_text
                ):
                    continue

            pruned.append(op)

        if focus_ops:
            pruned.extend(focus_ops[-1:])

        preferred_focus_labels = ["信源选择", "信息可信度", "信息频率", "信息载体"]
        weak_focus_labels = {"处理能力有限", "FOMO"}
        existing_labels = {
            str(node.get("label", "")).strip(): str(node.get("id", "")).strip()
            for node in payload.get("graph_snapshot", {}).get("nodes", [])
        }
        id_to_label = {
            node_id: label for label, node_id in existing_labels.items() if node_id
        }
        focus_index = next(
            (index for index, op in enumerate(pruned) if op["op"] == "set_focus"), None
        )
        if focus_index is not None:
            focus_op = pruned[focus_index]
            target = focus_op.get("target", {})
            focus_label = ""
            if target.get("by") == "label":
                focus_label = str(target.get("value", "")).strip()
            elif target.get("by") == "id":
                focus_label = id_to_label.get(str(target.get("value", "")).strip(), "")
            if focus_label in weak_focus_labels:
                replacement_label = next(
                    (
                        label
                        for label in preferred_focus_labels
                        if label in existing_labels
                    ),
                    None,
                )
                if replacement_label:
                    pruned[focus_index] = {
                        "op": "set_focus",
                        "target": {
                            "by": "label",
                            "value": replacement_label,
                        },
                    }

        if len(pruned) > MAX_MODEL_OPERATIONS:
            non_focus = [op for op in pruned if op["op"] != "set_focus"]
            focus = [op for op in pruned if op["op"] == "set_focus"]
            pruned = non_focus[: max(0, MAX_MODEL_OPERATIONS - len(focus))] + focus[:1]

        return pruned

    def _coerce_node_ref(self, value: Any) -> dict[str, str] | None:
        if isinstance(value, dict):
            if value.get("by") in {"id", "label"} and isinstance(
                value.get("value"), str
            ):
                return {"by": value["by"], "value": value["value"]}
            if isinstance(value.get("id"), str):
                return {"by": "id", "value": value["id"]}
            if isinstance(value.get("label"), str):
                return {"by": "label", "value": value["label"]}
            if isinstance(value.get("name"), str):
                return {"by": "label", "value": value["name"]}
        if isinstance(value, str) and value:
            return {"by": "label", "value": value}
        return None

    def _coerce_operation_shape(self, operation: dict[str, Any]) -> dict[str, Any]:
        op_type = operation.get("op")
        if not isinstance(op_type, str):
            return {}

        if op_type == "merge_node":
            from_ref = self._coerce_node_ref(
                operation.get("from") or operation.get("source")
            )
            to_ref = self._coerce_node_ref(
                operation.get("to") or operation.get("target")
            )
            if from_ref and to_ref:
                return {"op": op_type, "from": from_ref, "to": to_ref}
            return {}

        if op_type == "set_node_type":
            target = self._coerce_node_ref(
                operation.get("target") or operation.get("node")
            )
            node_type = operation.get("node_type") or operation.get("type")
            if target and isinstance(node_type, str):
                return {"op": op_type, "target": target, "node_type": node_type}
            return {}

        if op_type == "add_pending_node":
            node = operation.get("node")
            connect_to = self._coerce_node_ref(
                operation.get("connect_to")
                or operation.get("target")
                or operation.get("parent")
            )
            if (
                isinstance(node, dict)
                and isinstance(node.get("label"), str)
                and isinstance(node.get("description"), str)
            ):
                return {
                    "op": op_type,
                    "node": {
                        "label": node["label"],
                        "description": node["description"],
                    },
                    "connect_to": connect_to or {"by": "id", "value": "system"},
                }
            return {}

        if op_type == "rename_node":
            target = self._coerce_node_ref(
                operation.get("target") or operation.get("node")
            )
            new_label = operation.get("new_label") or operation.get("label")
            if target and isinstance(new_label, str):
                return {"op": op_type, "target": target, "new_label": new_label}
            return {}

        if op_type == "update_node_description":
            target = self._coerce_node_ref(
                operation.get("target") or operation.get("node")
            )
            description = operation.get("description") or operation.get(
                "new_description"
            )
            if target and isinstance(description, str):
                return {"op": op_type, "target": target, "description": description}
            return {}

        if op_type in {"add_edge", "remove_edge"}:
            source = self._coerce_node_ref(
                operation.get("source") or operation.get("from")
            )
            target = self._coerce_node_ref(
                operation.get("target")
                or operation.get("to")
                or operation.get("connect_to")
            )
            if source and target:
                return {"op": op_type, "source": source, "target": target}
            return {}

        if op_type in {"mark_revisited", "set_focus"}:
            target = self._coerce_node_ref(
                operation.get("target")
                or operation.get("node")
                or operation.get("focus")
            )
            if target:
                return {"op": op_type, "target": target}
            return {}

        return {}

    def _gemini_graph_refine_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY 未配置")

        prompt = (
            "You refine a thought graph for a realtime conversation UI.\n"
            "Return ONLY JSON matching the schema.\n"
            "Do not explain, do not include markdown.\n"
            "Optimize for stability over cleverness.\n"
            "Prefer 2-5 operations total. Fewer is better.\n"
            "Never rename a node unless the current label is clearly misleading.\n"
            "Never add a pending node if an existing node already covers the idea.\n"
            "Prefer merge_node over add_pending_node when a question obviously belongs under an existing stable concept.\n"
            "Use add_edge/remove_edge sparingly; only when the current relation is clearly wrong or clearly missing.\n"
            "Use mark_revisited only when the node is explicitly revisited in the recent text.\n"
            "Use set_focus exactly once and make it the final operation.\n"
            "Use existing ids/labels from the graph_snapshot whenever possible.\n"
            "Avoid cosmetic churn. Do not invent broad generic labels.\n\n"
            "Decision rubric:\n"
            "1. Collapse duplicate or question-like labels into stable concepts.\n"
            "2. Keep unresolved questions visible only if they are actionable and not already represented.\n"
            "3. Preserve the user's wording when it carries meaning, but prefer existing graph labels for consistency.\n"
            "4. If uncertain, do less.\n\n"
            "Interpretation rules for long spoken input:\n"
            "- Prefer stable meta-topics over examples, brands, people, or publications.\n"
            "- Treat named examples (e.g. media brands, investors, bloggers) as evidence for a broader topic, not as the topic itself.\n"
            "- Use window.window_summary as a strong hint for the stable themes already detected locally.\n"
            "- For very long text, optimize for the recurring core tensions, not exhaustiveness.\n\n"
            "If the conversation is clearly not about information acquisition, do not force it into information themes.\n"
            "You may introduce new pending nodes and update descriptions when the local draft graph is off-domain.\n\n"
            f"Request payload:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        request_body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": GEMINI_MODEL_RESPONSE_SCHEMA,
            },
        }
        response = requests.post(
            GEMINI_API_URL,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload_json = response.json()
        text = (
            payload_json.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            raise ValueError("Gemini 返回为空")
        raw_model_response = json.loads(text)
        return self._normalize_model_response(
            payload,
            raw_model_response,
            reasoning_mode=GEMINI_MODEL,
            debug_meta={
                "source": "gemini",
                "raw_model_response": raw_model_response,
            },
        )

    def _gemini_think_different_response(
        self, *, topic: str, tone: str
    ) -> dict[str, Any]:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY 未配置")

        tone_guide = {
            "mixed": "Mix poetic, sharp, and visionary tones across the feed.",
            "poetic": "Use restrained, vivid, keynote-like language with metaphor and elegance.",
            "sharp": "Use crisp, strategic, high-signal language with bold judgments.",
            "vision": "Use future-facing product language and paradigm-shift framing.",
        }[tone]

        prompt = (
            "You are generating a 'Think different' inspiration feed for a product ideation UI.\n"
            "Return ONLY JSON matching the schema. No markdown. No explanation.\n"
            "Write in Simplified Chinese.\n"
            "The feed should feel like Apple-style speculative thinking, not generic brainstorming.\n"
            "Each card must feel distinct, memorable, and slightly surprising.\n"
            "Avoid bland advice, empty slogans, and repeated wording.\n"
            "Focus on unconventional product insight, reframing, metaphor, first-principles, future framing, and brand-worthy language.\n"
            "Each item body should be 90-180 Chinese characters.\n"
            "Generate exactly 6 items.\n"
            "Use varied perspectives such as: first principles, inversion, future hindsight, wrong-category analogy, anti-consensus bet, identity shift, invisible interface.\n"
            "Ensure title lines are concise and strong.\n"
            f"Tone instruction: {tone_guide}\n"
            f"Topic: {topic}\n"
        )
        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": THINK_DIFFERENT_RESPONSE_SCHEMA,
            },
        }
        response = requests.post(
            GEMINI_API_URL,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload_json = response.json()
        text = (
            payload_json.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            raise ValueError("Gemini 返回为空")

        raw_model_response = json.loads(text)
        items = raw_model_response.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("Gemini 未返回有效 items")

        normalized_items: list[dict[str, Any]] = []
        for item in items[:6]:
            if not isinstance(item, dict):
                continue
            normalized_items.append(
                {
                    "perspective": str(item.get("perspective", "")).strip()
                    or "不同视角",
                    "title": str(item.get("title", "")).strip(),
                    "body": str(item.get("body", "")).strip(),
                    "tone": str(item.get("tone", "")).strip() or tone,
                    "tags": [
                        str(tag).strip()
                        for tag in item.get("tags", [])
                        if str(tag).strip()
                    ][:4],
                }
            )

        normalized_items = [
            item for item in normalized_items if item["title"] and item["body"]
        ]
        if not normalized_items:
            raise ValueError("Gemini 返回内容为空")

        return {
            "ok": True,
            "source": "gemini",
            "model": GEMINI_MODEL,
            "topic": str(raw_model_response.get("topic", "")).strip() or topic,
            "tone": str(raw_model_response.get("tone", "")).strip() or tone,
            "items": normalized_items,
        }

    def _mock_graph_refine_response(
        self,
        payload: dict[str, Any],
        *,
        reasoning_mode: str = "server-mock",
    ) -> dict[str, Any]:
        candidate_labels = [
            node.get("label", "") for node in payload["candidate_nodes"]
        ]
        raw_text = payload["window"]["raw_text"]
        operations: list[dict[str, Any]] = []
        focus_label = candidate_labels[0] if candidate_labels else "思维主问题"

        if "我该信谁" in candidate_labels and "信息可信度" in candidate_labels:
            operations.append(
                {
                    "op": "merge_node",
                    "from": {"by": "label", "value": "我该信谁"},
                    "to": {"by": "label", "value": "信息可信度"},
                }
            )
            focus_label = "信息可信度"

        if "要不要追求一手源" in candidate_labels and "信源选择" in candidate_labels:
            operations.append(
                {
                    "op": "merge_node",
                    "from": {"by": "label", "value": "要不要追求一手源"},
                    "to": {"by": "label", "value": "信源选择"},
                }
            )

        if all(token in raw_text for token in ["每天", "每周", "每月"]):
            operations.append(
                {
                    "op": "add_pending_node",
                    "node": {
                        "label": "信息节律规则",
                        "description": "把“每天 / 每周 / 每月看什么”沉淀成明确节律规则。",
                    },
                    "connect_to": {"by": "id", "value": "system"},
                }
            )
            focus_label = "信息频率"

        if "原文" in raw_text and "总结" in raw_text:
            operations.append(
                {
                    "op": "set_node_type",
                    "target": {"by": "label", "value": "原文 vs AI总结"},
                    "node_type": "loop",
                }
            )
            operations.append(
                {
                    "op": "mark_revisited",
                    "target": {"by": "label", "value": "原文 vs AI总结"},
                }
            )

        if "评论区" in raw_text and "陪伴感" in raw_text:
            operations.extend(
                [
                    {
                        "op": "add_pending_node",
                        "node": {
                            "label": "评论区的真实增量",
                            "description": "评论区带来的到底是信息增量，还是陪伴感和在场感。",
                        },
                        "connect_to": {"by": "id", "value": "commentary"},
                    },
                    {
                        "op": "rename_node",
                        "target": {"by": "id", "value": "commentary"},
                        "new_label": "评论区意义",
                    },
                    {
                        "op": "remove_edge",
                        "source": {"by": "id", "value": "system"},
                        "target": {"by": "id", "value": "commentary"},
                    },
                    {
                        "op": "add_edge",
                        "source": {"by": "label", "value": "信息载体"},
                        "target": {"by": "id", "value": "commentary"},
                    },
                ]
            )

        if "一手" in raw_text and "二手" in raw_text:
            operations.append(
                {
                    "op": "add_edge",
                    "source": {"by": "label", "value": "信源选择"},
                    "target": {"by": "label", "value": "信息可信度"},
                }
            )

        if "FOMO" in raw_text or "漏掉" in raw_text:
            operations.append(
                {
                    "op": "mark_revisited",
                    "target": {"by": "label", "value": "FOMO"},
                }
            )

        operations.append(
            {
                "op": "set_focus",
                "target": {"by": "label", "value": focus_label},
            }
        )

        return self._normalize_model_response(
            payload,
            {"operations": operations},
            reasoning_mode=reasoning_mode,
            debug_meta={
                "source": "server-mock",
                "raw_model_response": {"operations": operations},
            },
        )

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 4180), TimelineHandler)
    print("Serving timeline demo on http://localhost:4180")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
