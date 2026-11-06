"""自定义译名（覆盖内置中文名）。

内置译名写在 `ui/rw_gui.html` 里（角色 / 生物 / 区域 / 通行证 / 阵营五张表），
用户觉得不合适时可以在界面里逐条改，改过的条目存到 `region_data/_translations.json`，
读取时覆盖内置表 —— 不修改内置数据，随时可「恢复默认」。

文件格式：

```jsonc
{
  "version": 1,
  "updated": "2026-11-01T13:40:00",
  "slugcats":    {"White": "白猫"},
  "creatures":   {"BlueLizard": "蓝蜥蜴"},
  "regions":     {"SU": "外缘"},
  "passages":    {"Traveller": "旅行者"},
  "communities": {"Lizards": "蜥蜴"}
}
```

只有「中文名」会被覆盖；英文名与代码始终来自内置表。
"""

from __future__ import annotations

import json
import os
import time

from . import paths

KINDS = ("slugcats", "creatures", "regions", "passages", "communities")
FILE_NAME = "_translations.json"
VERSION = 1
MAX_LEN = 32


def _path() -> str:
    return os.path.join(paths.data_dir(), FILE_NAME)


def _clean_map(value) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(value, dict):
        return out
    for key, text in value.items():
        if not isinstance(key, str) or not isinstance(text, str):
            continue
        k = key.strip()
        v = text.strip()[:MAX_LEN]
        if k and v:
            out[k] = v
    return out


def load() -> dict:
    """读覆盖表；文件不存在或损坏时返回空表（不抛错，界面照常用内置名）。"""
    data = {"version": VERSION, "updated": ""}
    for kind in KINDS:
        data[kind] = {}
    path = _path()
    if not os.path.isfile(path):
        return data
    try:
        with open(path, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, ValueError):
        return data
    if not isinstance(stored, dict):
        return data
    for kind in KINDS:
        data[kind] = _clean_map(stored.get(kind))
    data["updated"] = str(stored.get("updated") or "")
    return data


def _write(data: dict) -> bool:
    data["version"] = VERSION
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def save(payload: dict) -> dict:
    """整表覆盖：调用方传来哪几类就替换哪几类，没传的保持原样。"""
    current = load()
    if isinstance(payload, dict):
        for kind in KINDS:
            if kind in payload:
                current[kind] = _clean_map(payload.get(kind))
    ok = _write(current)
    current["ok"] = ok
    return current


def set_one(kind: str, key: str, value: str) -> dict:
    if kind not in KINDS:
        return {"ok": False, "error": f"未知分类：{kind}"}
    current = load()
    bucket = current.get(kind) or {}
    key = (key or "").strip()
    value = (value or "").strip()[:MAX_LEN]
    if not key:
        return {"ok": False, "error": "缺少条目代码"}
    if value:
        bucket[key] = value
    else:
        bucket.pop(key, None)  # 清空 = 恢复内置名
    current[kind] = bucket
    ok = _write(current)
    current["ok"] = ok
    return current


def reset(kind: str = "") -> dict:
    """清空某类（或全部）覆盖，回到内置译名。"""
    current = load()
    targets = [kind] if kind in KINDS else ([] if kind else list(KINDS))
    if not targets:
        return {"ok": False, "error": f"未知分类：{kind}"}
    for k in targets:
        current[k] = {}
    ok = _write(current)
    current["ok"] = ok
    return current


def summary() -> dict:
    data = load()
    return {kind: len(data.get(kind) or {}) for kind in KINDS}
