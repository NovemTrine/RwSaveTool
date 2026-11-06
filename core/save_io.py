"""存档文件访问：定位、槽位、读取。

只读。不写存档，不改时间戳。
"""

from __future__ import annotations

import os

from . import paths

MAX_SAVE_BYTES = 128 * 1024 * 1024  # 128 MiB 上限，见设计文档 8


def read_save_file(path: str) -> dict:
    """读取存档原文（UTF-8，去 BOM）。返回给前端直接解析。"""
    if not path:
        return {"ok": False, "error": "路径为空"}
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return {"ok": False, "error": f"文件不存在：{path}"}
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return {"ok": False, "error": f"无法读取文件：{exc}"}
    if size == 0:
        return {"ok": False, "error": "文件为空"}
    if size > MAX_SAVE_BYTES:
        return {
            "ok": False,
            "error": f"文件过大（{size / 1024 / 1024:.1f} MiB），超过 128 MiB 上限",
        }
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {"ok": False, "error": f"读取失败：{exc}"}
    return {
        "ok": True,
        "path": path,
        "name": os.path.basename(path),
        "size": size,
        "text": text,
        "bytesRead": len(text),
    }


def slots() -> list[dict]:
    return paths.list_slots()


def default_dir() -> str | None:
    dirs = paths.rain_world_dirs()
    return dirs[0] if dirs else None
