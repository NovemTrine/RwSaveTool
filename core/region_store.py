"""导入区域的持久化（唯一可写位置）。

写入目标：paths.data_dir() 下的 <CODE>.json

数据结构（schema 2）：一个区域 = 多条「来源层」
    layers[0]  基础层：官方文件（原版 / DLC），没有官方文件时就是模组自己的完整定义
    layers[1:] 附加层：模组对该区域追加/覆盖的房间（典型是 GATE_RF_GW 这种连接房间）

为什么要分层（2026-10-31 修订）：
    模组可以给原版区域的地图**添加**房间，用来把原版区域和模组区域连起来。
    因此「这个区域有多少房间」有两个答案：
        只看源文件   → base
        加上附加区域 → base ∪ addons
    完成度必须两者都能算，并且能一键切换。

覆盖语义：
    同一 layer id 重复导入 = 该层整条覆盖（另一层的房间不受影响）
    新层房间数 < 旧层 70% → 调用方应二次确认（would_shrink）
    用户手工补充的中文名 / 备注存 _overrides.json，不随覆盖丢失
"""

from __future__ import annotations

import json
import os
import struct
import time
from typing import Any

from . import paths, sources

OVERRIDES_FILE = "_overrides.json"
SCHEMA = 2


def _region_path(code: str) -> str:
    return os.path.join(paths.data_dir(), f"{code.upper()}.json")


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data: Any) -> bool:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


# --------------------------------------------------------------------------
# 内置对照表
# --------------------------------------------------------------------------
_builtin_cache: dict[str, dict] | None = None


def builtin_regions() -> dict[str, dict]:
    global _builtin_cache
    if _builtin_cache is not None:
        return _builtin_cache
    data = _read_json(paths.builtin_region_map_path()) or {}
    entries = data.get("entries") or []
    out: dict[str, dict] = {}
    for entry in entries:
        abbr = str(entry.get("abbr", "")).upper()
        if abbr:
            out[abbr] = {"zh": entry.get("zh"), "en": entry.get("en")}
    _builtin_cache = out
    return out


# --------------------------------------------------------------------------
# 覆盖文件（用户手工字段）
# --------------------------------------------------------------------------
def overrides() -> dict[str, dict]:
    data = _read_json(os.path.join(paths.data_dir(), OVERRIDES_FILE))
    return data if isinstance(data, dict) else {}


def set_override(code: str, patch: dict) -> dict:
    data = overrides()
    key = code.upper()
    current = dict(data.get(key) or {})
    for name, value in (patch or {}).items():
        if value in (None, ""):
            current.pop(name, None)
        else:
            current[name] = value
    if current:
        data[key] = current
    else:
        data.pop(key, None)
    _write_json(os.path.join(paths.data_dir(), OVERRIDES_FILE), data)
    return data


# --------------------------------------------------------------------------
# PNG 尺寸（只读文件头 33 字节）
# --------------------------------------------------------------------------
def png_size(path: str | None) -> tuple[int, int] | None:
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        width, height = struct.unpack(">II", head[16:24])
    except struct.error:
        return None
    return int(width), int(height)


# --------------------------------------------------------------------------
# schema 迁移：把 v1（单层）升级成 v2（layers）
# --------------------------------------------------------------------------
def _layer_from_v1(data: dict) -> dict:
    source = data.get("source") or {}
    kind = "official" if source.get("kind") == "official" else "mod"
    layer_id = source.get("packId") or (
        f"mod:{source.get('modId')}" if source.get("modId") else "mod:unknown"
    )
    if kind == "mod" and source.get("modId"):
        layer_id = f"mod:{source['modId']}"
    return {
        "id": layer_id,
        "kind": kind,
        "label": source.get("packLabel") or source.get("modName") or "已导入数据",
        "order": 0 if kind == "official" else 100,
        "displayName": data.get("displayName"),
        "rooms": data.get("rooms") or [],
        "variants": data.get("variants") or {},
        "map": data.get("map") or {},
        "stats": data.get("stats") or {},
        "subregions": data.get("subregions") or [],
        "source": source,
    }


def _normalize(data: dict) -> dict:
    """把任意版本的记录统一成 schema 2。"""
    if not isinstance(data, dict):
        return {}
    data = dict(data)
    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        v1 = _layer_from_v1(data)
        layers = [v1]
        for key in ("rooms", "map", "stats", "variants", "subregions", "displayName"):
            data.pop(key, None)
        data.pop("source", None)
    data["layers"] = layers
    data["schema"] = SCHEMA
    # 排序：official 在前，其余按 order / id
    data["layers"].sort(key=lambda l: (0 if l.get("kind") == "official" else 1,
                                       int(l.get("order") or 0), str(l.get("id") or "")))
    return data


# --------------------------------------------------------------------------
# 装饰：底图可用性、漂移、中文名
# --------------------------------------------------------------------------
def _check_drift(layer: dict) -> list[str]:
    source = layer.get("source") or {}
    region_dir = source.get("path")
    if not region_dir:
        return []
    drift: list[str] = []
    for item in source.get("files") or []:
        candidate = os.path.join(region_dir, item.get("name", ""))
        try:
            stat = os.stat(candidate)
            if stat.st_size != item.get("size") or int(stat.st_mtime) != item.get("mtime"):
                drift.append(item.get("name"))
        except OSError:
            drift.append(item.get("name"))
    return drift


def _decorate(region: dict, ov: dict | None = None) -> dict:
    region = _normalize(region)
    builtin = builtin_regions()
    code = str(region.get("code", "")).upper()
    region["code"] = code
    override = (ov or {}).get(code) or {}
    info = builtin.get(code) or {}
    region["nameZh"] = override.get("nameZh") or region.get("nameZh") or info.get("zh")
    region["nameEn"] = region.get("displayName") or info.get("en")
    region["note"] = override.get("note")

    has_official = False
    has_world = False
    kept_layers = []
    src_reg = sources.registry_enabled()
    for layer in region["layers"]:
        map_info = layer.get("map") or {}
        image_path = map_info.get("imagePath")
        available = bool(image_path) and os.path.isfile(image_path)
        map_info["available"] = available
        if available and not map_info.get("width"):
            size = png_size(image_path)
            if size:
                map_info["width"], map_info["height"] = size
        layer["map"] = map_info
        layer["driftFiles"] = _check_drift(layer)
        layer["upToDate"] = not layer["driftFiles"]
        stats = layer.get("stats") or {}
        layer["rooms"] = layer.get("rooms") or []
        layer["roomCount"] = len(layer["rooms"])
        layer["shelters"] = sum(1 for r in layer["rooms"] if r.get("shelter"))
        layer["gates"] = sum(1 for r in layer["rooms"] if r.get("gate"))
        layer["hasMap"] = bool(available)
        # 丢掉「既没有房间也没有底图」的空层（早前测试残留 / 误写入）
        if not layer["rooms"] and not available:
            continue
        if layer.get("kind") == "official":
            has_official = True
        if stats.get("hasWorldFile"):
            has_world = True
        # 层 ↔ 来源：一一对应，界面按来源点亮/熄灭
        layer_id = str(layer.get("id") or "")
        entry = src_reg.get(layer_id) or {}
        layer["sourceId"] = layer_id
        layer["sourceKind"] = sources.kind_of(layer_id, layer.get("kind"))
        layer["sourceName"] = (
            entry.get("name")
            or layer.get("label")
            or sources.default_name(layer_id, layer.get("kind"))
        )
        layer["enabled"] = bool(entry.get("enabled", True))
        # 层级「仅地图」：有地图但没有 world 文件，房间清单不完整
        layer["mapOnly"] = not bool(stats.get("hasWorldFile"))
        # 该层带的地图变体（圣徒 / 矛大师 / 工匠……）：只存矩形与底图路径
        variants = layer.get("variants") or {}
        layer["variantSuffixes"] = sorted(variants.keys())
        layer["variantCount"] = len(variants)
        kept_layers.append(layer)
    if not kept_layers:
        kept_layers = region["layers"][:1]
    region["layers"] = kept_layers

    # 记录级派生字段
    enabled_layers = [l for l in region["layers"] if l.get("enabled")]
    base = (enabled_layers or region["layers"])[0]
    base_names = {str(r.get("name", "")).upper() for r in base.get("rooms") or []}
    addon_names: set[str] = set()
    for layer in region["layers"]:
        if layer is base:
            continue
        addon_names |= {str(r.get("name", "")).upper() for r in layer.get("rooms") or []}
    region["baseLayerId"] = base.get("id")
    region["baseRooms"] = len(base_names)
    # addonRooms 是其它层的原始条数；addonNewRooms 才是「相对基准层真正新增的房间」
    region["addonRooms"] = sum(
        (l.get("roomCount") or 0) for l in region["layers"] if l is not base
    )
    region["addonNewRooms"] = len(addon_names - base_names)
    region["unionRooms"] = len(base_names | addon_names)
    region["officialAvailable"] = has_official
    # 每个来源一条记录，界面按这个列表纵向排开
    region["sourceList"] = [
        {
            "id": l.get("sourceId") or l.get("id"),
            "name": l.get("sourceName"),
            "kind": l.get("sourceKind"),
            "enabled": bool(l.get("enabled")),
            "rooms": l.get("roomCount"),
            "shelters": l.get("shelters"),
            "gates": l.get("gates"),
            "hasMap": l.get("hasMap"),
            "mapOnly": l.get("mapOnly"),
            "mapWidth": (l.get("map") or {}).get("width"),
            "mapHeight": (l.get("map") or {}).get("height"),
            "upToDate": l.get("upToDate"),
        }
        for l in region["layers"]
    ]
    # 点亮且有完整清单的来源并集房间数（真正参与计算的分母）
    active: set[str] = set()
    active_ids = []
    for layer in kept_layers:
        if not layer.get("enabled") or layer.get("mapOnly"):
            continue
        active_ids.append(layer.get("sourceId") or layer.get("id"))
        active |= {str(r.get("name", "")).upper() for r in layer.get("rooms") or []}
    region["activeSources"] = active_ids
    region["activeRooms"] = len(active)
    # 条件房间（EXCLUSIVEROOM / HIDEROOM）：只为某个角色存在、或对某个角色隐藏
    cond_rooms: set[str] = set()
    story_rooms: set[str] = set()
    variant_suffixes: set[str] = set()
    for layer in region["layers"]:
        variant_suffixes |= set((layer.get("variants") or {}).keys())
        for room in layer.get("rooms") or []:
            name = str(room.get("name", "")).upper()
            if room.get("exclusive") or room.get("hidden"):
                cond_rooms.add(name)
            if room.get("conditional"):
                story_rooms.add(name)
    region["conditionalRooms"] = len(cond_rooms | story_rooms)
    region["conditionalList"] = sorted(cond_rooms | story_rooms)[:40]
    region["storyConditionalRooms"] = len(story_rooms)
    region["variants"] = sorted(variant_suffixes)
    # 所有来源都只有地图、没有 world 文件 → 房间清单不完整，不能当分母
    region["partial"] = bool(region["layers"]) and not has_world
    region["map"] = base.get("map") or {}
    region["mapUpToDate"] = base.get("upToDate", True)
    region["driftFiles"] = base.get("driftFiles") or []
    region["stats"] = base.get("stats") or {}
    region["source"] = base.get("source") or {}
    return region


def get_region(code: str) -> dict | None:
    data = _read_json(_region_path(code))
    if not isinstance(data, dict):
        return None
    return _decorate(data, overrides())


def all_regions() -> dict[str, dict]:
    out: dict[str, dict] = {}
    directory = paths.data_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return out
    ov = overrides()
    for name in names:
        if not name.lower().endswith(".json") or name.startswith("_"):
            continue
        data = _read_json(os.path.join(directory, name))
        if not isinstance(data, dict):
            continue
        code = str(data.get("code") or name[:-5]).upper()
        out[code] = _decorate(data, ov)
    return out


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------
def would_shrink(region: dict, threshold: float = 0.7) -> dict | None:
    """新层的数据是否明显小于同 id 的已有层。"""
    layer = region.get("layer") or {}
    layer_id = layer.get("id")
    code = str(region.get("code", "")).upper()
    existing = get_region(code)
    if not existing or not layer_id:
        return None
    old_layer = next((l for l in existing["layers"] if l.get("id") == layer_id), None)
    if not old_layer:
        return None
    old = int(old_layer.get("roomCount") or 0)
    new = len(region.get("rooms") or [])
    if old and new and new < old * threshold:
        return {"code": code, "layer": layer_id, "old": old, "new": new, "ratio": round(new / old, 2)}
    return None


def save_region(region: dict, force: bool = False) -> dict:
    """写入一个层。region 里必须带 layer={id,kind,label,order}。"""
    code = str(region.get("code", "")).upper()
    if not code:
        return {"ok": False, "error": "区域代码为空"}
    layer_meta = dict(region.get("layer") or {})
    if not layer_meta.get("id"):
        return {"ok": False, "error": f"{code}: 缺少 layer.id"}
    layer_meta.setdefault("kind", "mod")
    layer_meta.setdefault("label", "已导入数据")
    layer_meta.setdefault("order", 0 if layer_meta["kind"] == "official" else 100)
    # 导入时填写的来源名优先；但「Mod」这类占位名不用，保留数据自带的原始名（模组名）
    if layer_meta.get("sourceName"):
        if sources.is_generic(layer_meta["sourceName"]):
            layer_meta.pop("sourceName", None)
        else:
            layer_meta["label"] = layer_meta["sourceName"]

    shrink = None if force else would_shrink(region)
    if shrink:
        return {
            "ok": False,
            "needConfirm": True,
            "shrink": shrink,
            "error": f"{code}: 新数据 {shrink['new']} 间 < 已有 {shrink['old']} 间，需确认覆盖",
        }

    new_layer = {
        "id": layer_meta["id"],
        "kind": layer_meta["kind"],
        "label": layer_meta["label"],
        "order": layer_meta["order"],
        "displayName": region.get("displayName"),
        "rooms": region.get("rooms") or [],
        "variants": region.get("variants") or {},
        "map": region.get("map") or {},
        "stats": region.get("stats") or {},
        "subregions": region.get("subregions") or [],
        "source": dict(region.get("source") or {}),
    }
    new_layer["source"]["importedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    existing = _normalize(_read_json(_region_path(code)) or {"code": code})
    layers = [l for l in existing.get("layers") or [] if l.get("id") != new_layer["id"]]
    layers.append(new_layer)

    record = {
        "schema": SCHEMA,
        "code": code,
        "displayName": region.get("displayName") or existing.get("displayName"),
        "nameZh": existing.get("nameZh"),
        "layers": layers,
    }
    record = _normalize(record)

    ok = _write_json(_region_path(code), record)
    if not ok:
        return {"ok": False, "error": f"{code}: 写入失败（目录不可写）"}
    # 层写入成功 → 保证来源注册表里也有它
    src = sources.ensure(new_layer["id"], new_layer["kind"], new_layer.get("label"))
    return {
        "ok": True,
        "code": code,
        "layer": new_layer["id"],
        "label": new_layer.get("label"),
        "kind": new_layer.get("kind"),
        "rooms": len(new_layer.get("rooms") or []),
        "stats": new_layer.get("stats"),
        "path": _region_path(code),
    }


def save_regions(regions: list[dict], force: bool = False) -> dict:
    saved, failed, needs = [], [], []
    for region in regions or []:
        result = save_region(region, force=force)
        if result.get("ok"):
            saved.append(result)
        elif result.get("needConfirm"):
            needs.append(result)
        else:
            failed.append(result)
    return {"ok": not failed, "saved": saved, "failed": failed, "needsConfirm": needs}


def delete_region(code: str) -> dict:
    path = _region_path(code)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return {"ok": True, "code": code.upper()}
        return {"ok": False, "error": "该区域没有导入数据"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def delete_layer(code: str, layer_id: str) -> dict:
    """只删某一层；删空了就删文件。"""
    code = code.upper()
    data = _read_json(_region_path(code))
    if not isinstance(data, dict):
        return {"ok": False, "error": "该区域没有导入数据"}
    record = _normalize(data)
    remaining = [l for l in record["layers"] if l.get("id") != layer_id]
    if len(remaining) == len(record["layers"]):
        return {"ok": False, "error": f"没有这一层：{layer_id}"}
    if not remaining:
        return delete_region(code)
    record["layers"] = remaining
    _write_json(_region_path(code), _normalize(record))
    return {"ok": True, "code": code, "layer": layer_id}


# --------------------------------------------------------------------------
# 给前端用的精简列表
# --------------------------------------------------------------------------
def summary() -> list[dict]:
    out = []
    for code, region in sorted(all_regions().items()):
        layers = []
        for layer in region["layers"]:
            layers.append(
                {
                    "id": layer.get("id"),
                    "kind": layer.get("kind"),
                    "label": layer.get("label"),
                    "sourceId": layer.get("sourceId") or layer.get("id"),
                    "sourceName": layer.get("sourceName") or layer.get("label"),
                    "sourceKind": layer.get("sourceKind") or layer.get("kind"),
                    "enabled": bool(layer.get("enabled", True)),
                    "mapOnly": bool(layer.get("mapOnly")),
                    "rooms": layer.get("roomCount"),
                    "shelters": layer.get("shelters"),
                    "gates": layer.get("gates"),
                    "hasMap": layer.get("hasMap"),
                    "mapWidth": (layer.get("map") or {}).get("width"),
                    "mapHeight": (layer.get("map") or {}).get("height"),
                    "hasWorldFile": bool((layer.get("stats") or {}).get("hasWorldFile")),
                    "upToDate": layer.get("upToDate"),
                    "unlistedRoomFiles": (layer.get("stats") or {}).get("unlistedRoomFiles"),
                }
            )
        base = region["layers"][0]
        out.append(
            {
                "code": code,
                "nameZh": region.get("nameZh"),
                "nameEn": region.get("nameEn"),
                "layers": layers,
                "sourceList": region.get("sourceList") or [],
                "activeSources": region.get("activeSources") or [],
                "activeRooms": region.get("activeRooms"),
                "baseRooms": region.get("baseRooms"),
                "addonRooms": region.get("addonRooms"),
                "addonNewRooms": region.get("addonNewRooms"),
                "unionRooms": region.get("unionRooms"),
                "officialAvailable": region.get("officialAvailable"),
                "partial": region.get("partial"),
                # 兼容旧界面字段
                "rooms": base.get("roomCount"),
                "shelters": base.get("shelters"),
                "gates": base.get("gates"),
                "hasMap": base.get("hasMap"),
                "mapWidth": (base.get("map") or {}).get("width"),
                "mapHeight": (base.get("map") or {}).get("height"),
                "modName": (base.get("source") or {}).get("modName")
                or (base.get("source") or {}).get("packLabel"),
                "modVersion": (base.get("source") or {}).get("modVersion"),
                "importedAt": (base.get("source") or {}).get("importedAt"),
                "upToDate": base.get("upToDate"),
                "driftFiles": base.get("driftFiles"),
                "path": (base.get("source") or {}).get("path"),
            }
        )
    return out
