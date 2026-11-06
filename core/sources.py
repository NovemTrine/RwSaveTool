"""来源（Source）注册表。

一个「来源」= 一份地图/房间数据的出处。同一个区域可能同时有三份：
    原版（Original） / Downpour / Watcher / 各个模组
把来源做成独立实体，是为了让用户可以：
    1. 给来源起名字（默认 Original / Downpour / Watcher / Mod）
    2. 单独点亮或熄灭某个来源，只让点亮的来源参与完成度计算

存储：paths.data_dir()/_sources.json
    {"schema":1,"sources":[{"id","name","kind","enabled","order"}]}

id 与区域数据层的 id 一致（official:base / official:moreslugcats / mod:xxxx），
这样「层」和「来源」一一对应，不需要第二套 id。
"""

from __future__ import annotations

import json
import os

from . import paths

REGISTRY_FILE = "_sources.json"
SCHEMA = 1

# 前三个是官方内置来源，始终存在；模组来源在导入时按需创建
DEFAULT_SOURCES = [
    {"id": "official:base", "name": "Original", "kind": "original", "order": 0},
    {"id": "official:moreslugcats", "name": "Downpour", "kind": "downpour", "order": 10},
    {"id": "official:watcher", "name": "Watcher", "kind": "watcher", "order": 20},
]

# 导入对话框里的快捷标签
PRESETS = ["Original", "Downpour", "Watcher", "Mod"]

# 这些名字是「没起名」的占位，一旦能查到模组原名就换成原名
GENERIC_NAMES = {"", "mod", "mods", "mod 数据", "已导入数据", "已导入", "unnamed", "未命名"}


def is_generic(name: str | None) -> bool:
    return str(name or "").strip().lower() in GENERIC_NAMES

_KIND_ORDER = {"original": 0, "downpour": 10, "watcher": 20, "official": 30, "mod": 100}

# 官方数据包 id → 来源类型
_PACK_KIND = {
    "official:base": "original",
    "official:moreslugcats": "downpour",
    "official:watcher": "watcher",
    "official:expedition": "official",
}


def _path() -> str:
    return os.path.join(paths.data_dir(), REGISTRY_FILE)


def _read() -> dict:
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("sources"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "sources": []}


def _write(data: dict) -> bool:
    tmp = _path() + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, _path())
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def kind_of(layer_id: str, layer_kind: str | None = None) -> str:
    """推断来源类型：原版 / Downpour / Watcher / 官方其它 / 模组。"""
    if layer_id in _PACK_KIND:
        return _PACK_KIND[layer_id]
    if layer_kind == "official" or str(layer_id).startswith("official:"):
        return "official"
    return "mod"


def default_name(layer_id: str, layer_kind: str | None = None, hint: str | None = None) -> str:
    if layer_id in _PACK_KIND:
        for item in DEFAULT_SOURCES:
            if item["id"] == layer_id:
                return item["name"]
        return "Original"
    if hint:
        return hint
    if layer_kind == "official":
        return str(layer_id).split(":", 1)[-1].capitalize()
    return "Mod"


def _entries() -> dict[str, dict]:
    """注册表内容 + 三个默认来源（内存合并，不落盘）。"""
    data = _read()
    out: dict[str, dict] = {}
    for item in DEFAULT_SOURCES:
        out[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "kind": item["kind"],
            "enabled": True,
            "order": item["order"],
        }
    for item in data.get("sources") or []:
        lid = str(item.get("id") or "")
        if not lid:
            continue
        base = out.get(lid) or {}
        out[lid] = {
            "id": lid,
            "name": item.get("name") or base.get("name") or lid,
            "kind": item.get("kind") or base.get("kind") or kind_of(lid),
            "enabled": bool(item.get("enabled", base.get("enabled", True))),
            "order": int(item.get("order", base.get("order", _KIND_ORDER.get(kind_of(lid), 100)))),
        }
    return out


def save_entries(entries: dict[str, dict]) -> bool:
    payload = {
        "schema": SCHEMA,
        "sources": sorted(entries.values(), key=lambda e: (int(e.get("order") or 0), str(e.get("id")))),
    }
    return _write(payload)


def ensure(layer_id: str, layer_kind: str | None = None, name: str | None = None) -> dict:
    """确保某个层 id 在注册表里有一席之地，返回该来源。"""
    entries = _entries()
    current = entries.get(layer_id)
    if layer_id in _PACK_KIND:
        # 官方来源用固定默认名（Original / Downpour / Watcher），除非用户改过
        want_name = (current or {}).get("name") or default_name(layer_id, layer_kind)
    else:
        want_name = name or (current or {}).get("name") or default_name(layer_id, layer_kind)
    entry = {
        "id": layer_id,
        "name": want_name,
        "kind": kind_of(layer_id, layer_kind),
        "enabled": bool((current or {}).get("enabled", True)),
        "order": int((current or {}).get("order", _KIND_ORDER.get(kind_of(layer_id, layer_kind), 100))),
    }
    if current != entry:
        entries[layer_id] = entry
        save_entries(entries)
    return entry


def rename(layer_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "来源名称不能为空"}
    entries = _entries()
    entry = entries.get(layer_id) or ensure(layer_id)
    entry = dict(entries.get(layer_id) or entry)
    entry["name"] = name
    entries[layer_id] = entry
    ok = save_entries(entries)
    return {"ok": ok, "source": entry} if ok else {"ok": False, "error": "写入失败（目录不可写）"}


def set_enabled(layer_id: str, enabled: bool) -> dict:
    entries = _entries()
    entry = dict(entries.get(layer_id) or ensure(layer_id))
    entry["enabled"] = bool(enabled)
    entries[layer_id] = entry
    ok = save_entries(entries)
    return {"ok": ok, "source": entry} if ok else {"ok": False, "error": "写入失败（目录不可写）"}


def _layer_hints() -> dict[str, str]:
    """从区域数据里收集每个层 id 的「原始名称」（模组名 / 数据包名 / 层标签）。"""
    hints: dict[str, str] = {}
    try:  # 延迟导入，避免循环依赖
        from . import region_store

        for _code, region in region_store.all_regions().items():
            for layer in region.get("layers") or []:
                lid = str(layer.get("id") or "")
                if not lid or lid in hints:
                    continue
                src = layer.get("source") or {}
                for candidate in (src.get("modName"), src.get("packLabel"), layer.get("label")):
                    if candidate and not is_generic(candidate):
                        hints[lid] = str(candidate).strip()
                        break
    except Exception:  # noqa: BLE001
        pass
    return hints


def _unique(name: str, entries: dict[str, dict], keep_id: str) -> str:
    """同名来源加序号，避免一堆「Mod」。—— name 已占用时追加 (2)(3)"""
    taken = {e.get("name") for lid, e in entries.items() if lid != keep_id}
    if name not in taken:
        return name
    i = 2
    while f"{name} ({i})" in taken:
        i += 1
    return f"{name} ({i})"


def normalize_generic() -> int:
    """把「Mod」这类占位名换回原始名称，返回改动条数。"""
    entries = _entries()
    hints = _layer_hints()
    changed = 0
    for lid, entry in entries.items():
        if not is_generic(entry.get("name")):
            continue
        hint = hints.get(lid)
        if not hint:
            continue
        entry["name"] = _unique(hint, entries, lid)
        changed += 1
    if changed:
        save_entries(entries)
    return changed


def list_sources() -> list[dict]:
    """注册表 + 实际出现过的层（保证老数据里的模组来源也能显示）。

    一次扫描同时做两件事：补齐缺失的来源、把「Mod」这类占位名换成原始名。
    """
    entries = _entries()
    hints: dict[str, str] = {}
    seen: set[str] = set()
    try:  # 延迟导入，避免循环依赖
        from . import region_store

        for _code, region in region_store.all_regions().items():
            for layer in region.get("layers") or []:
                lid = str(layer.get("id") or "")
                if not lid:
                    continue
                seen.add(lid)
                if lid in hints:
                    continue
                src = layer.get("source") or {}
                for candidate in (src.get("modName"), src.get("packLabel"), layer.get("label")):
                    if candidate and not is_generic(candidate):
                        hints[lid] = str(candidate).strip()
                        break
    except Exception:  # noqa: BLE001
        pass

    dirty = False
    for lid in seen:
        entry = entries.get(lid)
        if entry is None:
            entries[lid] = {
                "id": lid,
                "name": hints.get(lid) or default_name(lid),
                "kind": kind_of(lid),
                "enabled": True,
                "order": _KIND_ORDER.get(kind_of(lid), 100),
            }
            dirty = True
        elif is_generic(entry.get("name")) and hints.get(lid):
            entry["name"] = _unique(hints[lid], entries, lid)
            dirty = True

    if dirty:
        save_entries(entries)
    return sorted(entries.values(), key=lambda e: (int(e.get("order") or 0), str(e.get("name"))))


def registry() -> dict[str, dict]:
    """只读注册表 + 三个默认来源，不扫描区域数据（供装饰时高频调用）。"""
    return _entries()


def registry_enabled() -> dict[str, dict]:
    return _entries()


def enabled_map() -> dict[str, bool]:
    return {item["id"]: bool(item.get("enabled", True)) for item in _entries().values()}
