"""生成发布用的干净区域数据（一次性脚本，打完包即可删除）。

做三件事：
1. 只保留 kind=official 的层，剔除全部模组层；
2. 抹掉 source 里的本机路径 / 导入时间 / 文件清单；
3. 删除 imagePath 等指向本机磁盘的字段，最后全量复查绝对路径。
"""

from __future__ import annotations

import io
import json
import os
import re

SRC = "region_data"
OUT = os.path.join("build", "_clean_region_data")
KEEP_SRC = ("kind", "packId", "packLabel")
PACK_ORDER = {"official:base": 0, "official:moreslugcats": 10, "official:watcher": 20}
ABS = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")
SENSITIVE_KEYS = {"imagePath", "gameRoot", "modRoot", "importedAt", "files", "path"}


def scrub(value, dropped):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in SENSITIVE_KEYS:
                dropped.append(key)
                continue
            out[key] = scrub(item, dropped)
        return out
    if isinstance(value, list):
        return [scrub(item, dropped) for item in value]
    if isinstance(value, str) and ABS.match(value):
        dropped.append("abs")
        return ""
    return value


def scan(value, path, bad):
    if isinstance(value, dict):
        for key, item in value.items():
            scan(item, path + "." + key, bad)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan(item, "%s[%d]" % (path, index), bad)
    elif isinstance(value, str) and ("\\" in value or ABS.match(value)):
        bad.append((path, value[:60]))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(OUT):
        os.remove(os.path.join(OUT, name))

    kept = []
    dropped_stat = {}
    for name in sorted(os.listdir(SRC)):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        with io.open(os.path.join(SRC, name), encoding="utf-8") as fh:
            data = json.load(fh)
        layers = [L for L in (data.get("layers") or []) if L.get("kind") == "official"]
        if not layers:
            continue
        clean_layers = []
        for layer in layers:
            src = layer.get("source") or {}
            item = dict(layer)
            item["source"] = {k: src[k] for k in KEEP_SRC if k in src}
            clean_layers.append(item)
        out = dict(data)
        out["layers"] = sorted(clean_layers, key=lambda L: PACK_ORDER.get(L.get("id"), 99))
        dropped = []
        out = scrub(out, dropped)
        for key in dropped:
            dropped_stat[key] = dropped_stat.get(key, 0) + 1
        with io.open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
        kept.append(name[:-5])

    sources = {
        "schema": 1,
        "sources": [
            {"id": "official:base", "name": "Original", "kind": "original", "enabled": True, "order": 0},
            {"id": "official:moreslugcats", "name": "Downpour", "kind": "downpour", "enabled": True, "order": 10},
            {"id": "official:watcher", "name": "Watcher", "kind": "watcher", "enabled": True, "order": 20},
        ],
    }
    with io.open(os.path.join(OUT, "_sources.json"), "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(sources, ensure_ascii=False, separators=(",", ":")))

    bad = []
    for name in os.listdir(OUT):
        with io.open(os.path.join(OUT, name), encoding="utf-8") as fh:
            scan(json.load(fh), name, bad)

    print("保留区域:", len(kept))
    print("剔除字段统计:", dropped_stat)
    print("残留路径:", bad[:5] if bad else "无")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
