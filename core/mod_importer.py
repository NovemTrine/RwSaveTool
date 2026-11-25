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
  modify/world/<REG>/…              同一模组对上述文件的「补丁层」，优先级更高
  modinfo.json                      模组 id / 名称 / 版本（容错解析）

关于 modify/（设计文档 §5.5）：
  游戏的加载顺序是 `world/` → `modify/world/`，后者按房间/文件逐个覆盖前者。
  实例：`moreslugcats` 没有 `world/sl/`，SL 的 DLC 改动**只**写在
  `modify/world/sl/world_sl.txt`（43 间）里 —— 不读 modify 就整段丢失。
  因此 modify 不是一个独立来源，而是**同一层的补丁**：本模块把它合并进该模组的层。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from . import room_geo

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

# `world/gates/locks.txt` 的门锁行：`GATE_SU_DS : 4 : 2`，第 4 段是 `SWAPMAPSYMBOL`
# （两端在图上对调）。以前的正则只认三段，18 行里漏 3 行——这 3 行恰好是带对调标记的。
LOCK_LINE = re.compile(
    r"^\s*([A-Za-z0-9_\-]+)\s*:\s*(\d+)\s*:\s*(\d+)(?:\s*:\s*([A-Za-z_]+))?\s*$"
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
    # dir 让 region_store 在「基准目录 + modify 目录」混读时仍能逐个复查（schema 4 起）
    return {
        "name": os.path.basename(path),
        "dir": os.path.dirname(path),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
    }


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
    """解析 world_*.txt 的 ROOMS 段 → {房间名大写: {neighbors, connections, flags}}。

    `neighbors` 与 `connections` 的区别（schema 3 起）：
      neighbors   —— 去重后的邻接房间名，界面的拓扑/完成度一直只用它；
      connections —— **保序、不去重**，`DISCONNECTED` 占位保留为 None。
                     它对应「房间文件里第 i 个出口（objects 里 type==4）」，
                     供"某个管道口连到哪个房间"用（设计文档 P1）。
                     例：`GATE_DS_GW : GW_S05, DISCONNECTED, GW_B09`
                     → connections = ["GW_S05", None, "GW_B09"]，neighbors = ["GW_B09", "GW_S05"]（排序后）
    两者恒有关系：`{c for c in connections if c}` 与 `neighbors` 的集合相等。
    """
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
        connections: list[str | None] = []
        if chunks and chunks[0]:
            for token in chunks[0].split(","):
                token = token.strip()
                if not token:
                    continue
                # 空位必须留占位，否则后面的出口会整体前移一位
                connections.append(None if token.upper() == "DISCONNECTED" else token.upper())
        neighbors = [c for c in connections if c]
        flags = set()
        if len(chunks) > 1 and chunks[1]:
            flags = {token.strip().upper() for token in chunks[1].split(",") if token.strip()}
        key = name.upper()
        record = rooms.setdefault(
            key, {"neighbors": [], "connections": [], "flags": set(), "_connsSet": False}
        )
        # 一个房间可能出现多行：`{Saint}ROOM : …` / `{#!SBCameraScroll,TM}ROOM : …` 这类
        # 带花括号前缀的**条件行**。条件是否成立本工具无法判定，而 connections 是**按位置**
        # 对应出口的，累加会让槽位数翻倍（实测 AB_DT04 变成 5 出口 / 10 槽）。
        # 因此 connections 只认**文件里第一行**，neighbors / flags 仍然并集（保持旧行为）。
        if not record["_connsSet"]:
            record["connections"] = list(connections)
            record["_connsSet"] = True
        for neighbor in neighbors:
            if neighbor not in record["neighbors"]:
                record["neighbors"].append(neighbor)
        record["flags"] |= flags
    for record in rooms.values():
        record.pop("_connsSet", None)
    return rooms



def parse_conditional(text: str) -> dict[str, dict]:
    """解析 world_*.txt 的 CONDITIONAL LINKS 段 → {房间名大写: {exclusive, hidden, story}}。

    只在「特定角色」下存在的房间：`Artificer : EXCLUSIVEROOM : LM_BRIDGE04ARTY`
    对特定角色隐藏的房间：      `Artificer : HIDEROOM : LM_LEGENTRANCE`

    角色名可能带剧情条件前缀（Watcher 的 `{!PostBathScene}Watcher`）——这类无法静态
    判定，只标 story=True，不参与分母筛选，免得把可能存在的房间算掉。

    **一个条件名可以是逗号分隔的一组角色**（游戏里写作 `Artificer,Spear : EXCLUSIVEROOM : GW_TOWER01`，
    语义是「其中任一角色」）。早期实现把整串 `ARTIFICER,SPEAR` 当成一个角色名存下来，
    前端 `exclusive.some(n => mine[n])` 永远匹配不上，于是：
      - `EXCLUSIVEROOM: Artificer,Spear` 的房间对这两个角色本该保留，却被剔除；
      - `HIDEROOM: Artificer,Spear` 的房间本该剔除，却被保留。
    实测 GW 在 Artificer 战役下因此只算出 58 间（应为 99 间），TOWER/PIPE/EDGE 系列全丢。
    所以这里必须按 `,` / `;` 拆开，逐个存入。
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
        room = room.strip().upper()
        if not room:
            continue
        names: list[str] = []
        # **先剥 `{...}` 整块再按 `,;` 切**（V1.24 №7）：`{!PostBathScene,!ToySending}Watcher`
        # 里逗号在花括号内，先切会把角色名切碎（WAUA_A06B 就是这么落成
        # `["{POSTBATHSCENE", "!TOYSENDING}WATCHER"]` 的）。花括号是剧情条件，不是角色。
        for part in re.split(r"[,;]", re.sub(r"\{[^}]*\}", "", actor)):
            name = part.strip().upper()
            if name and name not in names:
                names.append(name)
        if not names:
            continue
        entry = out.setdefault(room, {"exclusive": [], "hidden": [], "story": False})
        bucket = "exclusive" if kind == "EXCLUSIVEROOM" else "hidden"
        for name in names:
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


def scan_region_dirs(base_world: str | None, modify_world: str | None) -> dict[str, dict]:
    """一次扫描「基准 world + modify/world」，返回 {区域代码: {base, override}}。

    override 是同名区域在 `modify/world/` 下的补丁目录（可能不存在）。
    游戏加载顺序为 base → override，出冲突时 override 优先。
    """
    out: dict[str, dict] = {}
    for code, directory in _region_dirs_raw(base_world or "").items():
        out[code] = {"base": directory, "override": None}
    for code, directory in _region_dirs_raw(modify_world or "").items():
        slot = out.setdefault(code, {"base": None, "override": None})
        slot["override"] = directory
    return out


def modify_world_dir(mod_root: str) -> str:
    """`<模组根>/modify/world`。"""
    return os.path.join(mod_root, "modify", "world")


# --------------------------------------------------------------------------
# 单区域导入
# --------------------------------------------------------------------------
def _import_region(
    code: str,
    region_dir: str | None,
    override_dir: str | None = None,
    fallback_dir: str | None = None,
) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    lower_code = code.lower()
    # 基底三明治：fallback（游戏原版）垫底 → 包自己的 world/ 覆盖 → modify/ 再覆盖。
    # 为什么要 fallback：DLC 的 world/<reg> 目录经常只放地图与 displayname，
    # 真正完整的 world_<reg>.txt 仍留在游戏原版里。不回退就会把整层判成
    # 「没有完整定义」→ 被当成仅地图 → 不进分母（实测 CC 44 vs 61、GW 85 vs 136）。
    # 注意这只补「缺什么」，包自己写了的一律优先，不会把原版数据盖回去。
    base_files: dict[str, str] = {}
    if fallback_dir:
        base_files.update(_file_map(fallback_dir))
    if region_dir:
        base_files.update(_file_map(region_dir))
    ovr_files = _file_map(override_dir) if override_dir else {}

    # 「这个包到底碰没碰过这个区域」必须只看它自己（world/ + modify/），不能把
    # fallback 算进来：原版基底是给「有改动但没写全」的包补缺的，不是给
    # 只放了个 vistas.txt 的包（如 expedition）凭空造出一份原版副本。
    own_files: dict[str, str] = {}
    if region_dir:
        own_files.update(_file_map(region_dir))
    own_files.update(ovr_files)
    own_has_world = bool(_pick(own_files, f"world_{lower_code}.txt", f"world_{code}.txt"))
    own_has_map = any(name.startswith(f"map_image_{lower_code}") for name in own_files)
    if not own_has_world and not own_has_map:
        # 正常跳过（包里有该区域的目录但只放了 vistas/properties 之类），
        # 不当警告报，否则会把真正的告警挤掉。
        return None, []
    # 文件级叠加：同名文件 modify 优先（底图 / 坐标 / 名称 / Properties 都按这个规矩）
    files = dict(base_files)
    files.update(ovr_files)

    base_world = _pick(base_files, f"world_{lower_code}.txt", f"world_{code}.txt")
    ovr_world = _pick(ovr_files, f"world_{lower_code}.txt", f"world_{code}.txt")
    # 两个不同的问法，别混用：
    #   has_world      —— 这一层有没有 **world 依据**（完整定义或 modify 补丁都算）。
    #                     有依据 = 房间清单来自 world 文件而不是地图矩形，可以用作分母。
    #                     modify 补丁虽然只列改动过的房间，但它解析出的房间是真实的，
    #                     与 base 层做并集正好补齐「原版 + 模组新增」。
    #   has_full_world —— 这一层有没有 **完整定义**（只看基底）。补丁层为 False，
    #                     用来告诉界面「这是个补丁层」，不影响能不能进分母。
    has_world = bool(base_world or ovr_world)
    has_full_world = bool(base_world)
    world_file = ovr_world or base_world
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

    # 基础房间表（modify 里同名的房间条目**整条覆盖**基准条目，与游戏加载顺序一致）
    rooms: dict[str, dict] = {}
    if base_world:
        rooms = parse_world_file(_read_text(base_world))
    if ovr_world:
        rooms.update(parse_world_file(_read_text(ovr_world)))
    if not has_world:
        warnings.append(f"{code}: 无 world 文件，房间表来自地图矩形（仅地图层）")

    # 条件房间（只对某个角色存在 / 对某个角色隐藏）
    conditional: dict[str, dict] = {}
    if base_world:
        conditional = parse_conditional(_read_text(base_world))
    if ovr_world:
        conditional.update(parse_conditional(_read_text(ovr_world)))

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
        info = rooms.get(name, {"neighbors": [], "connections": [], "flags": set()})
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
        # 保序出口表：只在有 world 文件时存在。缺了它不代表数据坏，
        # 只代表"这间房没有世界文件依据"（仅地图导入的房间），消费方必须能降级。
        conns = info.get("connections") or []
        if conns:
            entry["connections"] = list(conns)
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

    # 有定义文件但一间房都没解析出来：不落空层，免得又攒出一批「0 房间旧壳」
    if not room_list:
        return None, [f"{code}: 有定义文件但没解析出房间，跳过"]

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

    read_files = [base_world, ovr_world, coord_file, name_file, props_file] + list(variants.values())
    fingerprint = [fp for fp in (_fingerprint(p) for p in read_files if p) if fp]

    region = {
        # 这里是"单层"中间结构（会被 region_store 包装成 layers[i] 并按 SCHEMA 落盘），
        # 所以 schema 字段只作溯源标记，不代表最终文件版本。
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
            # 有 world 依据（完整定义或 modify 补丁）→ 房间清单可作分母
            "hasWorldFile": has_world,
            # 有完整定义（只看基底）→ False 表示这是一层补丁
            "hasFullWorld": has_full_world,
            # 条件房间：只对某角色存在（EXCLUSIVEROOM）/ 对某角色隐藏（HIDEROOM）
            "conditionalRooms": len(conditional),
            "storyConditionalRooms": sum(1 for c in conditional.values() if c.get("story")),
            # partial 与 mapOnly 同义：房间表来自地图矩形，不能用它算完成度分母
            "partial": not has_world,
        },
        "subregions": subregions,
        "source": {
            "kind": "local_mod",
            "path": region_dir or fallback_dir or override_dir,
            # 基底兜底目录（通常是游戏原版 world/<reg>）：只在包自己缺文件时生效
            "fallbackDir": fallback_dir,
            # modify 补丁目录：读取优先级高于 path，room_geo 会先查它的 -rooms/gates
            "overridePaths": [override_dir] if override_dir else [],
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
# 出口编号（设计文档 P1 / §5.4）
# --------------------------------------------------------------------------
def region_room_dirs(world_dirs: list[str | None], code: str) -> list[str]:
    """该区域的房间文件目录，按优先级排列（已过滤不存在的）。

    为什么不能只看区域目录：模组的房间文件常在 `<mod>/world/DS-rooms/`，而它的
    区域定义却在 `<mod>/modify/world/DS/` —— 两者是兄弟目录关系但分处 modify 两侧。
    所以这里按「world 根」逐个拼 `<code>-rooms`。
    """
    out: list[str] = []
    lower = code.lower()
    for world in world_dirs:
        if not world:
            continue
        for name in (f"{lower}-rooms", f"{code}-rooms"):
            candidate = os.path.join(world, name)
            if os.path.isdir(candidate):
                real = os.path.normcase(candidate)
                if all(os.path.normcase(d) != real for d in out):
                    out.append(candidate)
                break
    return out


def room_dirs(region_dir: str | None, override_dir: str | None) -> list[str]:
    """兼容旧调用：由区域目录推导房间目录（补丁目录在前）。"""
    out: list[str] = []
    for directory in (override_dir, region_dir):
        if directory:
            out.append(directory)
    return out


def _exit_marks(dirs: list[str], room: str) -> list[tuple[int, int]] | None:
    """读房间文件，返回按「行优先 `(y, x)`」排好序的出口格坐标。

    返回 None = 一个候选文件都没找到；返回 [] = 文件在但里面没有出口格。
    """
    if not dirs:
        return None
    # 借用 room_geo 的查找顺序（含门房间的 gate_a_b / gate_b_a 两种命名）。
    # 注意每层都必须带 id：room_geo._layer_dirs 在 layer_id=None 时会跳过没有 id 的层。
    fake = {
        "layers": [
            {"id": f"_exit_{index}", "source": {"roomsDirs": [directory]}}
            for index, directory in enumerate(dirs)
        ]
    }
    for path in room_geo.candidates(fake, room):
        if not os.path.isfile(path):
            continue
        try:
            data = room_geo.load(path)
        except Exception:  # noqa: BLE001 - 房间文件坏掉只应影响这一间
            return None
        marks = [
            (int(mark[0]), int(mark[1]))
            for mark in data.get("marks") or []
            if mark[2] == room_geo.MARK_EXIT
        ]
        # 行优先：先按 y 分行（严格相等），行内按 x 从左到右 —— 不用容差（§8）
        marks.sort(key=lambda pair: (pair[1], pair[0]))
        return marks
    return None


def _trim_padding(slots: list, marks_len: int) -> list:
    """剪掉**超出出口数**的尾部空位（作者写的纯填充）。

    只剪「比出口多出来的那部分」，因为出口数之内的 DISCONNECTED 是有意义的：
    它占一个号、表示那个口没接房间（§5.1）。实测 FW_A14 写满 12 个槽位，
    房间只有 5 个出口，后 7 个全是填充。
    """
    end = len(slots)
    while end > marks_len and slots[end - 1] is None:
        end -= 1
    return list(slots[:end])


def attach_exits(regions: list[dict], dirs_list: list[list[str]]) -> dict:
    """给每个房间算 `exits[]`（出口编号 + 通向哪间房），原地写入。

    编号规则（§5.4 方案 A）：
      编号 = 出口按 `(y, x)` 排序后的下标，**全覆盖**；
      `to` 只给前 `k = min(出口数, 连接数)` 个，多出的（必在尾部）`to = None`。

    门房间（§6）：连接是**跨区域**的一张表，每个区域只填自己那侧的槽位，
    所以先把同一层里同名门房间的槽位逐槽合并，再拿去配对。
    """
    conflicts: set[str] = set()
    gate_slots: dict[str, list] = {}
    for region, _dirs in zip(regions, dirs_list):
        for room in region.get("rooms") or []:
            if not room.get("gate"):
                continue
            conns = room.get("connections") or []
            if not conns:
                continue
            # 门房间**跨区域也跨包**：一个门的两侧可能分别由原版和某个包定义（GATE_GW_SH 的
            # 第三槽就在 CL 区，属 Downpour 层），所以按房间名全局合并，不按层分组。
            key = str(room.get("name", "")).upper()
            slots = gate_slots.setdefault(key, [])
            for index, conn in enumerate(conns):
                if index >= len(slots):
                    slots.append(conn)
                elif conn is not None:
                    if slots[index] is None:
                        slots[index] = conn
                    elif slots[index] != conn:
                        conflicts.add(key)  # 两侧对同一槽位给了不同房间：不猜，标 truncated

    stats = {"rooms": 0, "withExits": 0, "ok": 0, "truncated": 0, "noFile": 0, "conflict": 0}
    for region, dirs in zip(regions, dirs_list):
        layer_id = (region.get("layer") or {}).get("id")
        for room in region.get("rooms") or []:
            conns = room.get("connections") or []
            if not conns:
                continue
            stats["rooms"] += 1
            name = str(room.get("name", "")).upper()
            key = name if room.get("gate") else f"{layer_id}/{name}"
            slots = (gate_slots.get(name) if room.get("gate") else None) or conns
            if room.get("gate") and slots is not conns and len(slots) >= len(conns):
                # 门房间：把跨区域合并后的完整槽位表落盘（各区域看到同一张表，与游戏一致）
                room["connections"] = list(slots)
            marks = _exit_marks(dirs, room.get("name"))
            if not marks:
                stats["noFile"] += 1
                continue
            # 门房间不剪：它的空白槽位属于「另一个区域的那一侧」，语义上真实存在。
            effective = slots if room.get("gate") else _trim_padding(slots, len(marks))
            limit = min(len(marks), len(effective))
            room["exits"] = [
                {"x": x, "y": y, "to": effective[index] if index < limit else None}
                for index, (x, y) in enumerate(marks)
            ]
            complete = len(marks) == len(effective)
            room["exitNumbering"] = "ok" if complete else "truncated"
            # 冲突 = 同一个门的同一个槽位，被两个来源写成了不同房间（通常是模组重定义
            # 了原版的门）。槽位数仍然够、编号仍然可用，所以只标一个诊断位，不降级。
            if key in conflicts:
                room["exitConflict"] = True
            stats["withExits"] += 1

    # 收尾统一一遍：门房间的槽位表可能在上面的循环里被后来的区域改长（跨区域合并是
    # 全局的），逐房间算出来的 complete 会和最终落盘的数据对不上。这里以**最终数据**
    # 为准重算一次，保证「标 ok 的房间，其 exits 与 connections 条数一定相等」。
    for region in regions:
        for room in region.get("rooms") or []:
            exits = room.get("exits")
            if not exits:
                continue
            conns = room.get("connections") or []
            effective = conns if room.get("gate") else _trim_padding(conns, len(exits))
            complete = len(exits) == len(effective)
            room["exitNumbering"] = "ok" if complete else "truncated"
            stats["ok" if complete else "truncated"] += 1
            if room.get("exitConflict"):
                stats["conflict"] += 1
    return stats


# --------------------------------------------------------------------------
# 模组级导入
# --------------------------------------------------------------------------
def _find_locks(world_dir: str) -> str:
    """`<world>/gates/locks.txt`（目录名大小写不固定，也接受直接给 `gates/`）。"""
    if not isinstance(world_dir, str) or not os.path.isdir(world_dir):
        return ""
    try:
        names = os.listdir(world_dir)
    except OSError:
        return ""
    for fn in names:
        if fn.lower() == "locks.txt":
            return os.path.join(world_dir, fn)
        if fn.lower() != "gates":
            continue
        gdir = os.path.join(world_dir, fn)
        if not os.path.isdir(gdir):
            continue
        try:
            for sub in os.listdir(gdir):
                if sub.lower() == "locks.txt":
                    return os.path.join(gdir, sub)
        except OSError:
            continue
    return ""


def read_gate_locks(*world_dirs: str | None) -> dict[str, list[int]]:
    """从若干 `world/` 根读 `gates/locks.txt` → `{GATE_X: [左, 右]}`（后面的覆盖前面的）。

    只有游戏本体带这份文件（原版 18 门）。模组多半没有，读不到就返回空表，**不报错**。
    第 4 段 `SWAPMAPSYMBOL`（两端在图上对调）本轮不参与计算：房间卡只显示左右两个数字，
    将来若把门徽标放回地图，再按它翻转。
    """
    out: dict[str, list[int]] = {}
    for root in world_dirs:
        path = _find_locks(root or "")
        if not path:
            continue
        for line in _read_text(path).split("\n"):
            m = LOCK_LINE.match(line)
            if not m:
                continue
            out[m.group(1).upper()] = [int(m.group(2)), int(m.group(3))]
    return out


def bake_gate_karma(regions: list[dict], locks: dict[str, list[int]]) -> int:
    """把业力门槛写进各区域的**门房**：`rooms[].karma = [左, 右]`。返回写入条数。

    为什么要烘焙：`locks.txt` 在游戏目录里，发布包抹掉本机路径后就没了；
    区域地图会画门（V1.24 起门也上图），但图上只画框、不标数值——数值给房间卡用，
    所以只存两个数。
    找不到门槛的门房**留空，不猜**（模组门只能是「业力门（无数据）」）。
    """
    if not locks:
        return 0
    changed = 0
    for region in regions or []:
        for layer in region.get("layers") or []:
            for room in layer.get("rooms") or []:
                name = str(room.get("name") or "").strip().upper()
                if not name.startswith("GATE_"):
                    continue
                pair = locks.get(name)
                if not pair or room.get("karma") == pair:
                    continue
                room["karma"] = list(pair)
                changed += 1
    return changed


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
    region_dirs: list[list[str]] = []
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
        # world/ 与 modify/world/ 一起扫；后者是该模组对区域的补丁（游戏加载顺序 base → modify）
        world_base = os.path.join(root, "world")
        world_modify = modify_world_dir(root)
        dirs = scan_region_dirs(world_base, world_modify)
        report("读取模组", 10 + int(70 * index / max(1, len(roots))), mod_entry["name"])

        for code, slot in dirs.items():
            try:
                region, notes = _import_region(code, slot["base"], slot["override"])
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
            rooms_search = region_room_dirs([world_modify, world_base], code)
            region["source"]["roomsDirs"] = rooms_search
            # 门房间住在 <world>/gates/，与 -rooms 是兄弟目录；这里把 world 根也记下来
            region["source"]["worldDirs"] = [
                d for d in (world_modify, world_base) if os.path.isdir(d)
            ]
            regions.append(region)
            region_dirs.append(rooms_search)
            mod_entry.setdefault("regions", []).append(
                {"code": code, "rooms": region["stats"]["rooms"]}
            )

    report("整理结果", 95, f"{len(regions)} 个区域")
    # 出口编号：必须在所有区域收集完之后做（门房间要跨区域合并槽位）
    exit_stats = attach_exits(regions, region_dirs)
    # 业力门槛（V1.24 №8）：模组自己有 `world/gates/locks.txt` 就顺手烘焙进数据；
    # 没有就留空——房间卡显示「业力门（无数据）」，不去猜。
    locks = read_gate_locks(*[d for r in regions
                              for d in (r.get("source") or {}).get("worldDirs") or []])
    karma_stats = bake_gate_karma(regions, locks)
    order = sorted(range(len(regions)), key=lambda i: regions[i]["code"])
    regions = [regions[i] for i in order]
    region_dirs = [region_dirs[i] for i in order]
    return {
        "ok": True,
        "mods": mods,
        "regions": regions,
        "warnings": warnings,
        "multi": info["kind"] == "multi",
        "exitStats": exit_stats,
        "gateKarma": {"gates": len(locks), "rooms": karma_stats},
    }
