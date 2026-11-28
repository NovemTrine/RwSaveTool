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
    {"id": "official:moreslugcats", "name": "Downpour（倾盆大雨）", "kind": "downpour", "order": 10},
    {"id": "official:watcher", "name": "The Watcher（观望者）", "kind": "watcher", "order": 20},
]

# 官方层「亦称」：玩家更熟悉、但官方数据源文件里没写的那个名字。
# 不塞进 `name` 是因为 chip 会挤爆（`Downpour（倾盆大雨）· 亦称 More Slugcats Expansion` 有 30 字），
# 放进 tooltip 一样能说清楚「这俩是同一个东西」。
AKA = {
    "official:moreslugcats": "More Slugcats Expansion",
}


def aka_of(layer_id: str) -> str:
    return AKA.get(str(layer_id or ""), "")

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


# --------------------------------------------------------------------------
# 等价层折叠（v1.3.2 №8）
#
# MSE 与 Downpour、The Watcher 与 Watcher 是**同一份内容的两条来源**：
# 一个来自游戏自带的 `consolefiles/`（装游戏就有），一个来自模组目录（卸了就没）。
# 两层都点亮时，同一批房间被算了两次，「来源 N/M」也重复。
#
# 判据不是相似度，而是**并集是否变化**：
#     模组层房间集 ⊆ 官方层房间集  →  熄灭它，分母不变、地图不变，纯减噪
# 只要有一个区域不满足，整层就不折叠（保守：并集真的会变）。
# 实测：`moreslugcats` 22/22 区、`watcher` 35/35 区，全部是子集。
# --------------------------------------------------------------------------

_dup_cache: dict[str, str] | None = None


def invalidate_duplicates() -> None:
    """区域数据变了（导入 / 删层 / 删来源）→ 折叠判定作废。"""
    global _dup_cache
    _dup_cache = None


def _scan_layer_rooms() -> list[tuple[str, frozenset[str]]]:
    """直接读 `region_data/*.json` 的 `layers[].id/rooms`，**不经过 `_decorate`**。

    为什么不用 `region_store.all_regions()`：`_decorate` 会回调
    `sources.registry_enabled()`，而这里又要判定折叠 —— 转一圈就是无限递归。
    """
    out: list[tuple[str, frozenset[str]]] = []
    try:
        names = os.listdir(paths.data_dir())
    except OSError:
        return out
    for name in names:
        if not name.lower().endswith(".json") or name.startswith("_"):
            continue
        try:
            with open(os.path.join(paths.data_dir(), name), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for layer in data.get("layers") or []:
            if not isinstance(layer, dict):
                continue
            lid = str(layer.get("id") or "")
            if not lid:
                continue
            rooms = frozenset(
                str(r.get("name") or "").upper()
                for r in (layer.get("rooms") or [])
                if isinstance(r, dict) and r.get("name")
            )
            out.append((lid, rooms))
    return out


def duplicate_pairs() -> dict[str, str]:
    """`{等价模组层 id: 它对应的官方层 id}`。

    键是「该被默认熄灭的那一层」，值是「保留的那一层」。
    只包含**所有区域都满足子集**的对子——有一个区不满足就整层不折叠。
    """
    global _dup_cache
    if _dup_cache is not None:
        return dict(_dup_cache)

    layers = _scan_layer_rooms()
    # 同一次扫描里，同 tail 的层可能出现在多个区域：先按 tail 归并
    by_tail: dict[str, dict[str, list[frozenset[str]]]] = {}
    for lid, rooms in layers:
        if ":" not in lid:
            continue
        group, tail = lid.split(":", 1)
        by_tail.setdefault(tail.lower(), {}).setdefault(group, []).append(rooms)

    ok: dict[str, str] = {}
    conflicted: set[str] = set()
    for tail, groups in by_tail.items():
        official = groups.get("official")
        mod = groups.get("mod")
        if not official or not mod:
            continue
        mod_id = f"mod:{tail}"
        off_id = f"official:{tail}"
        # 每个区域各判一次；只要出现「模组有、官方没有」的房间就放弃
        good = 0
        bad = False
        for mod_rooms in mod:
            if not mod_rooms:
                continue
            covered = any(mod_rooms <= off_rooms for off_rooms in official if off_rooms)
            if covered:
                good += 1
            else:
                bad = True
        if bad:
            conflicted.add(mod_id)
        elif good:
            ok[mod_id] = off_id

    for lid in conflicted:
        ok.pop(lid, None)
    _dup_cache = ok
    return dict(ok)


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
            "userSet": False,
        }
    for item in data.get("sources") or []:
        lid = str(item.get("id") or "")
        if not lid:
            continue
        base = out.get(lid) or {}
        # 官方内置来源（Original / Downpour / The Watcher）的显示名以 DEFAULT_SOURCES 为准：
        # 老版本的 `_sources.json` 里存着旧名（"Watcher"），不覆盖就永远改不过来。
        # 用户主动改过名的（`userName`）另说。
        if lid in _PACK_KIND and not item.get("userName") and base.get("name"):
            name = base["name"]
        else:
            name = item.get("name") or base.get("name") or lid
        out[lid] = {
            "id": lid,
            "name": name,
            "kind": item.get("kind") or base.get("kind") or kind_of(lid),
            "enabled": bool(item.get("enabled", base.get("enabled", True))),
            "order": int(item.get("order", base.get("order", _KIND_ORDER.get(kind_of(lid), 100)))),
            "userSet": bool(item.get("userSet")),
            "userName": bool(item.get("userName")),
        }

    # №8：等价层折叠。`dupOf` = 这一层和谁重复；`folded` = 按默认口径是否被隐藏。
    # `userSet` 是**用户点过开关**的痕迹（`set_enabled` 才写），
    # 有它就尊重用户的选择，没有才按折叠规则默认熄灭。
    dups = duplicate_pairs()
    for lid, entry in out.items():
        dup = dups.get(lid)
        entry["userSet"] = bool(entry.get("userSet"))
        entry["dupOf"] = dup
        entry["folded"] = bool(dup) and not entry["userSet"]
    return out


_PERSIST_KEYS = ("id", "name", "kind", "enabled", "order", "userSet", "userName")


def save_entries(entries: dict[str, dict]) -> bool:
    """落盘只写白名单字段：`dupOf` / `folded` 是每次算出来的派生量，写进去会变成脏数据。"""
    payload = {
        "schema": SCHEMA,
        "sources": [
            {k: e.get(k) for k in _PERSIST_KEYS if e.get(k) is not None}
            for e in sorted(
                entries.values(),
                key=lambda e: (int(e.get("order") or 0), str(e.get("id"))),
            )
        ],
    }
    return _write(payload)


def ensure(layer_id: str, layer_kind: str | None = None, name: str | None = None) -> dict:
    """确保某个层 id 在注册表里有一席之地，返回该来源。"""
    entries = _entries()
    current = entries.get(layer_id)
    if layer_id in _PACK_KIND:
        # 官方来源用固定默认名（Original / Downpour / The Watcher），除非用户改过名
        if (current or {}).get("userName"):
            want_name = current["name"]
        else:
            want_name = default_name(layer_id, layer_kind)
    else:
        want_name = name or (current or {}).get("name") or default_name(layer_id, layer_kind)
    entry = {
        "id": layer_id,
        "name": want_name,
        "kind": kind_of(layer_id, layer_kind),
        "enabled": bool((current or {}).get("enabled", True)),
        "order": int((current or {}).get("order", _KIND_ORDER.get(kind_of(layer_id, layer_kind), 100))),
    }
    # 比较裸字段：`_entries()` 现在带 `dupOf`/`folded`，直接比较会永远不相等、每次调用都写盘
    bare = {k: (current or {}).get(k) for k in _PERSIST_KEYS if (current or {}).get(k) is not None}
    if bare != entry:
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
    entry["userName"] = True
    entries[layer_id] = entry
    ok = save_entries(entries)
    return {"ok": ok, "source": entry} if ok else {"ok": False, "error": "写入失败（目录不可写）"}


def set_enabled(layer_id: str, enabled: bool) -> dict:
    """用户手动点亮 / 熄灭。同时记 `userSet`——之后折叠规则不再覆盖他的选择。"""
    entries = _entries()
    entry = dict(entries.get(layer_id) or ensure(layer_id))
    entry["enabled"] = bool(enabled)
    entry["userSet"] = True
    entry["folded"] = False
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
    """注册表 + **生效的** enabled（等价层默认算熄灭）。给装饰层用。"""
    out = _entries()
    for entry in out.values():
        if entry.get("folded"):
            entry["enabled"] = False
    return out


def enabled_map() -> dict[str, bool]:
    """来源 id → 是否参与计算（等价层默认熄灭）。"""
    return {
        item["id"]: (False if item.get("folded") else bool(item.get("enabled", True)))
        for item in _entries().values()
    }
