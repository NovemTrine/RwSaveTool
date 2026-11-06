"""雨世界模组目录 · 只读导入器。

严格只读：本模块只使用 open(..., 'r') 读取，绝不写入模组目录。
所有可写行为都在 region_store 里，且只写工具自己的数据目录。

支持的数据来源（按设计文档 5.4 的白名单，不递归大目录）：
  world/<REG>/world_<reg>.txt       房间清单 + 邻居 + SHELTER/GATE 标记
  world/<REG>/map_image_<reg>.txt   底图像素矩形  x,y,w,h
  world/<REG>/map_<REG>.txt         世界坐标 + 图层 + 子区域
  world/<REG>/map_<REG>.png         底图（只记录路径，不复制）
  world/<REG>/displayname.txt       区域英文名
  world/<REG>/Properties.txt        子区域列表
  modinfo.json                      模组 id / 名称 / 版本（容错解析）
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

REGION_DIR_RE = re.compile(r"^[A-Za-z0-9]{2,8}$")
ROOM_LINE_RE = re.compile(r"^\s*(?:\{[^}]*\})?\s*([A-Za-z0-9_]+)\s*:\s*(.*)$")
SECTION_RE = re.compile(r"^[A-Z][A-Z0-9 _]{2,}$")
SKIP_DIRS = {"gates", "levels", "text", "rooms", "scenes", "music", "palettes", "decals",
             "illustrations", "modify", "plugins", "sounds"}

SHELTER_FLAGS = {"SHELTER"}
GATE_FLAGS = {"GATE"}

# CONDITIONAL LINKS 段里的条件房间行：`Artificer : EXCLUSIVEROOM : LM_BRIDGE04ARTY`
CONDITION_RE = re.compile(
    r"^(.+?)\s*:\s*(EXCLUSIVEROOM|HIDEROOM)\s*:\s*([A-Za-z0-9_]+)\s*$", re.IGNORECASE
)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _fingerprint(path: str) -> dict | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return {"name": os.path.basename(path), "size": stat.st_size, "mtime": int(stat.st_mtime)}


def _file_map(directory: str) -> dict[str, str]:
    """目录内 文件名小写 → 真实路径（一层，不递归）。"""
    out: dict[str, str] = {}
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    out[entry.name.lower()] = entry.path
    except OSError:
        return out
    return out


def _pick(files: dict[str, str], *names: str) -> str | None:
    for name in names:
        hit = files.get(name.lower())
        if hit:
            return hit
    return None


# --------------------------------------------------------------------------
# modinfo.json（容错：本模组实测缺少逗号，标准 JSON 解析会失败）
# --------------------------------------------------------------------------
def parse_modinfo(path: str) -> dict:
    raw = _read_text(path)
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    out: dict[str, Any] = {}
    for key in ("id", "name", "version", "authors", "description"):
        match = re.search(r'"' + key + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        if match:
            out[key] = match.group(1).replace('\\"', '"')
    hits = re.findall(r'"([^"]+)"', raw)
    if hits:
        out["rawKeys"] = hits[:8]
    out["_tolerant"] = True
    return out


# --------------------------------------------------------------------------
# 各文件解析
# --------------------------------------------------------------------------
def parse_world_file(text: str) -> dict[str, dict]:
    """解析 world_*.txt 的 ROOMS 段 → {房间名大写: {neighbors, flags}}。"""
    rooms: dict[str, dict] = {}
    in_rooms = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_rooms:
            if line.upper() == "ROOMS":
                in_rooms = True
            continue
        if line.startswith("//"):
            continue
        upper = line.upper()
        if upper.startswith("END ROOMS"):
            break
        if SECTION_RE.match(line) and ":" not in line:
            break  # CREATURES / CONDITIONAL LINKS 之类的下一段
        match = ROOM_LINE_RE.match(line)
        if not match:
            continue
        name, rest = match.group(1), match.group(2)
        if not name:
            continue
        chunks = [chunk.strip() for chunk in rest.split(":")]
        neighbors = []
        if chunks and chunks[0]:
            neighbors = [
                token.strip()
                for token in chunks[0].split(",")
                if token.strip() and token.strip() != "DISCONNECTED"
            ]
        flags = set()
        if len(chunks) > 1 and chunks[1]:
            flags = {token.strip().upper() for token in chunks[1].split(",") if token.strip()}
        key = name.upper()
        record = rooms.setdefault(key, {"neighbors": [], "flags": set()})
        for neighbor in neighbors:
            if neighbor.upper() not in {n.upper() for n in record["neighbors"]}:
                record["neighbors"].append(neighbor.upper())
        record["flags"] |= flags
    return rooms


def parse_conditional(text: str) -> dict[str, dict]:
    """解析 world_*.txt 的 CONDITIONAL LINKS 段 → {房间名大写: {exclusive, hidden, story}}。

    只在「特定角色」下存在的房间：`Artificer : EXCLUSIVEROOM : LM_BRIDGE04ARTY`
    对特定角色隐藏的房间：      `Artificer : HIDEROOM : LM_LEGENTRANCE`

    角色名可能带剧情条件前缀（Watcher 的 `{!PostBathScene}Watcher`）——这类无法静态
    判定，只标 story=True，不参与分母筛选，免得把可能存在的房间算掉。
    """
    out: dict[str, dict] = {}
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_block:
            if line.upper().startswith("CONDITIONAL LINKS"):
                in_block = True
            continue
        if line.upper().startswith("END CONDITIONAL LINKS"):
            break
        if line.startswith("//"):
            continue
        match = CONDITION_RE.match(line)
        if not match:
            continue
        actor, kind, room = match.group(1).strip(), match.group(2).upper(), match.group(3)
        story = "{" in actor
        name = re.sub(r"\{[^}]*\}", "", actor).strip().upper()
        room = room.strip().upper()
        if not name or not room:
            continue
        entry = out.setdefault(room, {"exclusive": [], "hidden": [], "story": False})
        bucket = "exclusive" if kind == "EXCLUSIVEROOM" else "hidden"
        if name not in entry[bucket]:
            entry[bucket].append(name)
        if story:
            entry["story"] = True
    return out


def parse_map_image(text: str) -> dict[str, list[int]]:
    """map_image_*.txt → {房间名大写: [x, y, w, h]}（像素，左上加原点）。"""
    out: dict[str, list[int]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or ":" not in line:
            continue
        name, _, payload = line.partition(":")
        numbers: list[int] = []
        for token in payload.replace(" ", "").split(","):
            if not token:
                continue
            try:
                numbers.append(int(float(token)))
            except ValueError:
                numbers = []
                break
        if len(numbers) == 4:
            out[name.strip().upper()] = numbers
    return out


def parse_map_coords(text: str) -> dict[str, dict]:
    """map_<REG>.txt → {房间名大写: {world:[x1,y1,x2,y2], layer, subregion}}。"""
    out: dict[str, dict] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, _, payload = line.partition(":")
        fields = payload.split("><")
        if len(fields) < 6:
            continue
        try:
            world = [float(fields[i]) for i in range(4)]
        except ValueError:
            continue
        subregion = fields[5].strip()
        layer = fields[4].strip()
        out[name.strip().upper()] = {
            "world": world,
            "layer": layer,
            "subregion": subregion or None,
        }
    return out


def parse_display_name(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return None


# --------------------------------------------------------------------------
# 模组识别
# --------------------------------------------------------------------------
def _looks_like_mod_dir(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "world")) or os.path.isfile(
        os.path.join(path, "modinfo.json")
    )


def detect(path: str) -> dict:
    """判断传入路径是单个模组、模组集合，还是无效。"""
    if not path:
        return {"kind": "invalid", "reason": "路径为空"}
    path = os.path.abspath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if not os.path.isdir(path):
        return {"kind": "invalid", "reason": "路径不存在或不是目录"}

    if _looks_like_mod_dir(path):
        return {"kind": "single", "modRoots": [path]}

    children = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir() and _looks_like_mod_dir(entry.path):
                    children.append(entry.path)
    except OSError as exc:
        return {"kind": "invalid", "reason": f"无法读取目录：{exc}"}

    if children:
        return {"kind": "multi", "modRoots": sorted(children)}

    return {
        "kind": "invalid",
        "reason": "目录里既没有 world/ 也没有 modinfo.json，也不是模组集合",
    }


def _region_dirs_raw(world: str) -> dict[str, str]:
    """给定一个 world 目录，返回 {区域代码大写: 区域目录}。"""
    out: dict[str, str] = {}
    if not os.path.isdir(world):
        return out
    try:
        with os.scandir(world) as it:
            for entry in it:
                if not entry.is_dir():
                    continue
                name = entry.name
                if name.lower() in SKIP_DIRS or "-" in name or "_rooms" in name.lower():
                    continue
                if not REGION_DIR_RE.match(name):
                    continue
                if _file_map(entry.path):
                    out[name.upper()] = entry.path
    except OSError:
        return out
    return out


def _region_dirs(mod_root: str) -> dict[str, str]:
    """world/ 下的区域目录 → {区域代码大写: 目录路径}。"""
    return _region_dirs_raw(os.path.join(mod_root, "world"))


# --------------------------------------------------------------------------
# 单区域导入
# --------------------------------------------------------------------------
def _import_region(code: str, region_dir: str) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    files = _file_map(region_dir)
    lower_code = code.lower()

    world_file = _pick(files, f"world_{lower_code}.txt", f"world_{code}.txt")
    props_file = _pick(files, "properties.txt")
    name_file = _pick(files, "displayname.txt")

    # 地图图片：map_image_<reg>.txt 与各种变体（-saint / _saint / -inv …）
    variants: dict[str, str] = {}
    for lower_name, real_path in files.items():
        if not lower_name.startswith(f"map_image_{lower_code}") or not lower_name.endswith(".txt"):
            continue
        suffix = lower_name[len(f"map_image_{lower_code}") : -len(".txt")]
        suffix = suffix.lstrip("-_")
        variants[suffix or "normal"] = real_path

    if not variants and not world_file:
        return None, [f"{code}: 找不到 world_{lower_code}.txt 或 map_image_*.txt，跳过"]

    # 基础房间表
    rooms: dict[str, dict] = {}
    if world_file:
        rooms = parse_world_file(_read_text(world_file))
    else:
        warnings.append(f"{code}: 无 world 文件，只有地图数据（无连接与庇护所标记）")

    # 条件房间（只对某个角色存在 / 对某个角色隐藏）
    conditional: dict[str, dict] = {}
    if world_file:
        conditional = parse_conditional(_read_text(world_file))

    # 坐标表（子区域 / 世界坐标），非必需
    coord_file = None
    for lower_name, real_path in files.items():
        if lower_name in (f"map_{lower_code}.txt",):
            coord_file = real_path
            break
    coords = parse_map_coords(_read_text(coord_file)) if coord_file else {}

    # 变体矩形
    variant_maps: dict[str, dict[str, list[int]]] = {}
    for suffix, path in variants.items():
        variant_maps[suffix] = parse_map_image(_read_text(path))

    normal_map = variant_maps.get("normal") or (
        next(iter(variant_maps.values())) if variant_maps else {}
    )

    # 合并房间：世界文件 ∪ 地图条目
    names = set(rooms) | set(normal_map)
    for extra_map in variant_maps.values():
        names |= set(extra_map)

    room_list = []
    for name in sorted(names):
        info = rooms.get(name, {"neighbors": [], "flags": set()})
        flags = info.get("flags") or set()
        coord = coords.get(name) or {}
        entry = {
            "name": name,
            "neighbors": sorted(info.get("neighbors") or []),
            "shelter": bool(flags & SHELTER_FLAGS),
            "gate": bool(flags & GATE_FLAGS) or name.startswith("GATE_"),
            "subregion": coord.get("subregion"),
            "layer": coord.get("layer"),
            "map": (
                dict(zip(("x", "y", "w", "h"), normal_map[name])) if name in normal_map else None
            ),
        }
        if coord.get("world"):
            entry["world"] = coord["world"]
        cond = conditional.get(name)
        if cond:
            if cond["exclusive"]:
                entry["exclusive"] = list(cond["exclusive"])
            if cond["hidden"]:
                entry["hidden"] = list(cond["hidden"])
            if cond["story"]:
                # 带剧情条件的房间：不参与分母筛选，只在界面上标注
                entry["conditional"] = True
        room_list.append(entry)

    # 变体（圣徒等）：只存房间名集合 + 矩形
    variant_out: dict[str, dict] = {}
    for suffix, mapping in variant_maps.items():
        if suffix == "normal" or not mapping:
            continue
        image_path = _find_base_image(files, lower_code, suffix)
        variant_out[suffix] = {
            "rooms": {
                name: dict(zip(("x", "y", "w", "h"), rect)) for name, rect in mapping.items()
            },
            "imagePath": image_path,
        }

    base_image = _find_base_image(files, lower_code, "normal")

    display_name = parse_display_name(_read_text(name_file)) if name_file else None

    subregions: list[str] = []
    if props_file:
        for line in _read_text(props_file).splitlines():
            if line.lower().startswith("subregion:"):
                value = line.split(":", 1)[1].strip()
                if value and value not in subregions:
                    subregions.append(value)
    if not subregions:
        subregions = sorted({r["subregion"] for r in room_list if r["subregion"]})

    # 诊断：房间级文件里未被登记的房间（不进入分母，仅提示）
    ghost = _count_unlisted_room_files(files, names)

    read_files = [world_file, coord_file, name_file, props_file] + list(variants.values())
    fingerprint = [fp for fp in (_fingerprint(p) for p in read_files if p) if fp]

    region = {
        "schema": 1,
        "code": code,
        "displayName": display_name,
        "rooms": room_list,
        "variants": variant_out,
        "map": {
            "imagePath": base_image,
            "width": None,
            "height": None,
        },
        "stats": {
            "rooms": len(normal_map) if normal_map else len(room_list),
            "roomsListed": len(room_list),
            "shelters": sum(1 for r in room_list if r["shelter"]),
            "gates": sum(1 for r in room_list if r["gate"]),
            "subregions": len(subregions),
            "unlistedRoomFiles": ghost,
            "hasCoordinates": bool(normal_map),
            "hasWorldFile": bool(world_file),
            # 条件房间：只对某角色存在（EXCLUSIVEROOM）/ 对某角色隐藏（HIDEROOM）
            "conditionalRooms": len(conditional),
            "storyConditionalRooms": sum(1 for c in conditional.values() if c.get("story")),
            # partial = 该区域是「对基础区域的覆盖」，没有完整房间清单。
            # 这类区域的 rooms 只是模组改动过的房间，绝不能当完成度分母。
            "partial": not bool(world_file),
        },
        "subregions": subregions,
        "source": {
            "kind": "local_mod",
            "path": region_dir,
            "files": fingerprint,
        },
    }

    if ghost:
        warnings.append(f"{code}: 有 {ghost} 个房间级文件未登记在清单里，已忽略（不计入分母）")
    if not normal_map:
        warnings.append(f"{code}: 无 map_image 数据，无法给出点位")
    if not base_image:
        warnings.append(f"{code}: 未找到底图 PNG，地图视图不可用")

    return region, warnings


def _find_base_image(files: dict[str, str], lower_code: str, suffix: str) -> str | None:
    candidates = []
    if suffix and suffix != "normal":
        candidates += [f"map_{lower_code}-{suffix}.png", f"map_{lower_code}_{suffix}.png"]
    candidates += [f"map_{lower_code}.png"]
    for name in candidates:
        hit = files.get(name.lower())
        if hit:
            return hit
    # 兜底：任何 map_<code>*.png
    for lower_name, real_path in files.items():
        if lower_name.startswith(f"map_{lower_code}") and lower_name.endswith(".png"):
            return real_path
    return None


def _count_unlisted_room_files(files: dict[str, str], listed: set[str]) -> int:
    """统计同级 -Rooms 目录里、未登记在房间清单中的房间文件数（仅用于提示）。"""
    # 该函数在 _import_region 内被调用时拿不到父目录，这里由 import_mod 统一处理
    return 0


def count_unlisted_room_files(mod_root: str, code: str, listed: set[str]) -> int:
    rooms_dir = os.path.join(os.path.dirname(os.path.join(mod_root, "world", code)), f"{code}-Rooms")
    if not os.path.isdir(rooms_dir):
        alternatives = [
            os.path.join(mod_root, "world", name)
            for name in os.listdir(os.path.join(mod_root, "world"))
            if name.lower() == f"{code.lower()}-rooms"
        ]
        rooms_dir = alternatives[0] if alternatives else rooms_dir
    if not os.path.isdir(rooms_dir):
        return 0
    seen: set[str] = set()
    try:
        with os.scandir(rooms_dir) as it:
            for entry in it:
                if not entry.is_file() or not entry.name.lower().endswith(".txt"):
                    continue
                base = entry.name[:-4]
                base = re.sub(r"[_\-]sett?ings(-.+)?$", "", base, flags=re.I)
                seen.add(base.upper())
    except OSError:
        return 0
    return len(seen - listed)


# --------------------------------------------------------------------------
# 模组级导入
# --------------------------------------------------------------------------
def import_mod(
    path: str,
    progress: Callable[[str, int, str], None] | None = None,
    source_name: str | None = None,
) -> dict:
    """只读扫描一个模组（或模组集合），返回待写入的区域数据列表。"""
    def report(stage: str, pct: int, detail: str = "") -> None:
        if progress:
            try:
                progress(stage, pct, detail)
            except Exception:  # 进度回调不应影响主流程
                pass

    info = detect(path)
    if info["kind"] == "invalid":
        return {"ok": False, "error": info["reason"], "regions": [], "warnings": []}

    roots = info["modRoots"]
    # 自定义来源名只对「单个模组」有意义；批量导入时每个模组各用自己的名字
    custom_name = (source_name or "").strip() or None
    if custom_name and custom_name.strip().lower() in {"mod", "mods", "已导入数据", "已导入", "未命名"}:
        custom_name = None
    if info["kind"] == "multi":
        custom_name = None
    report("扫描模组", 5, f"{len(roots)} 个模组")

    regions: list[dict] = []
    warnings: list[str] = []
    mods: list[dict] = []

    for index, root in enumerate(roots):
        modinfo = parse_modinfo(os.path.join(root, "modinfo.json"))
        mod_entry = {
            "path": root,
            "id": modinfo.get("id"),
            "name": modinfo.get("name") or os.path.basename(root),
            "version": modinfo.get("version"),
            "tolerantParsed": bool(modinfo.get("_tolerant")),
        }
        mods.append(mod_entry)
        dirs = _region_dirs(root)
        report("读取模组", 10 + int(70 * index / max(1, len(roots))), mod_entry["name"])

        for code, region_dir in dirs.items():
            try:
                region, notes = _import_region(code, region_dir)
            except Exception as exc:  # 单区域失败不影响其它区域
                warnings.append(f"{code}: 导入异常 {type(exc).__name__}: {exc}")
                continue
            warnings.extend(notes)
            if not region:
                continue
            region["source"].update(
                {
                    "modId": mod_entry["id"],
                    "modName": mod_entry["name"],
                    "modVersion": mod_entry["version"],
                    "modRoot": root,
                }
            )
            region["layer"] = {
                "id": f"mod:{mod_entry['id']}" if mod_entry["id"] else f"mod:{os.path.basename(root)}",
                "kind": "mod",
                "label": mod_entry["name"],
                "sourceName": custom_name,
                "order": 100,
            }
            try:
                listed = {room["name"] for room in region["rooms"]}
                ghost = count_unlisted_room_files(root, code, listed)
                if ghost:
                    region["stats"]["unlistedRoomFiles"] = ghost
                    warnings.append(
                        f"{code}: 有 {ghost} 个房间级文件未登记在清单里，已忽略（不计入分母）"
                    )
            except OSError:
                pass
            regions.append(region)
            mod_entry.setdefault("regions", []).append(
                {"code": code, "rooms": region["stats"]["rooms"]}
            )

    report("整理结果", 95, f"{len(regions)} 个区域")
    regions.sort(key=lambda r: r["code"])
    return {
        "ok": True,
        "mods": mods,
        "regions": regions,
        "warnings": warnings,
        "multi": info["kind"] == "multi",
    }
