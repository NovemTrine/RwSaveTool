"""数据层：读 region_data/*.json 与房间 .txt。

刻意不 import 原工具的任何模块——只依赖标准库与磁盘上的数据文件，
这样整个 region_map/ 目录可以原样拷进工具（或独立跑）。

三个数据坑（都踩过，注释里写清楚，别再改回去）：

1. 尺寸行可能**没有**尾随 `|`（工作坊版 `48*35` 就是），正则必须允许行尾。
2. 房间 `.txt` 可能有多份来源，第一份可能损坏——找不到就读下一份，不能读到坏的就放弃。
3. 地形是 `|` 分隔、**列优先**的 token 流，不是字符矩阵；同一个文件里还有别的
   `|` 层（背景等），必须按 token 数精确匹配。
"""
from __future__ import annotations

import json
import os
import re
from collections import OrderedDict

from . import config

# 门房间（GATE_XX_YU 之类）坐标在地图之外，不属于区域内部布局
SKIP_PREFIX = ("GATE_",)

_SIZE_RE = re.compile(r"^\s*(\d+)\s*\*\s*(\d+)\s*(?:\||$)")
# 变体件命名：`UW_A04RIV` / `SB_E05SAINT` / `TM_A01SPEAR` → 基名 + 后缀
_VARIANT_RE = re.compile(r"^(.*\d)([A-Z]+)$")


class Room(object):
    """一间房：尺寸、出口、摄像机、地形网格。坐标约定见下。

    坐标系（2026-11-18 用真实地图坐标标定，11-19 二次复核）
    --------------------------------------
    * 房间格坐标：`x` 向右增，`y` **向上**增（世界坐标）。`y = 0` 是房间**底边**，
      `y = h-1` 是顶边。`exits[].x/y` 与 `cells` 的 y 都是这个口径。
    * 摄像机：`.txt` 里是像素、世界 y 向上、原点在房间左下角，单台 1400×800 px。
      这里换算成格：(x/20 + 35, y/20 + 20) —— 加的是半宽半高，得到**中心点**。
    * 游戏内地图矩形 `map_rect`：y **向下**（和屏幕一致）。这份数据只用于交叉验，
      不参与房间内部几何。

    渲染布局时统一转成屏幕坐标（y 向下），转换只在 `thumbnail` 与 `layout` 里做。
    """

    __slots__ = ("name", "w", "h", "exits", "cameras", "cells", "objs",
                 "sub", "map_rect", "world", "order", "kind", "path",
                 "variant_of", "is_variant", "eff", "tags")

    def __init__(self, name, w, h):
        self.name = name
        self.w = w
        self.h = h
        self.exits = []          # [(x, y, to)]
        self.cameras = []        # [(x, y)]，房间格坐标
        self.cells = ""          # 行优先，长度 w*h，一格一个 hex：0 空 / 1 实心 / 2..15 斜面
        self.objs = None         # {(x,y): (对象编号…)}，按需解析（见 room_objects）
        self.sub = None
        self.map_rect = None     # (x, y, w, h) 游戏内地图坐标，y 向下
        self.world = None        # (x0, y0, x1, y1) 世界像素坐标
        self.order = 0           # 来源层序，越大越优先
        self.kind = ""
        self.path = ""
        self.variant_of = None   # 变体件的基名（`UW_A04RIV` → `UW_A04`）
        self.is_variant = False
        self.eff = None          # 有效区包围盒缓存，(x0,y0,x1,y1)；见 effective_bbox
        self.tags = ()           # 房间标签，见 `_room_tags`（W4 标注用）

    def camera_count(self):
        return len(self.cameras)

    def __repr__(self):
        return "<Room %s %dx%d exits=%d cams=%d>" % (
            self.name, self.w, self.h, len(self.exits), len(self.cameras))


# ---------------------------------------------------------------- 房间 txt

_PARSE_CACHE = OrderedDict()
# 上限 64 间：demo 里这是无上限 dict，常驻工具会涨到几百 MB（单间约 0.09–0.17 MB）。
# 工具主路径其实走注入解析器（adapter 的 LRU 48），这里只保护「对拍/独立运行」那条路径。
_PARSE_CACHE_MAX = 64

# 热插拔接口：工具侧把「读 .txt」换成自己的解析器（`core/regmap/adapter.py`）。
# 契约：fn(path) -> (w, h, cameras, cells, objects)
#   cameras  [(cx, cy)]（格坐标，世界 y 向上）
#   cells    "0"/"1" 行优先，长度 w*h
#   objects  {(x, y): (编号…)} 或 None（None = 回调自己再去读文件，等于没换）
# 为 None 时走本模块自带的 `_parse_room`，保持 demo 可独立运行、也可用来对拍。
PARSER = None


def _load_room(path, parser=None):
    """→ (w, h, cameras, cells, objects)。统一出口，供 load_region 使用。

    `parser` 优先于模块级 `PARSER`：并发调用（pywebview 每个 JS 调用一个线程）时
    不要把 PARSER 当成可变全局来切换，直接传参最稳。
    """
    fn = parser or PARSER
    if fn is not None:
        return fn(path)
    w, h, cams, cells, _grid = _parse_room(path)
    return w, h, cams, cells, None


def _parse_room(path):
    """→ (w, h, cameras, cells, grid)。grid 是原始 token 列表（可能为 None）。"""
    hit = _PARSE_CACHE.get(path)
    if hit is not None:
        _PARSE_CACHE.move_to_end(path)
        return hit
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().replace("\r", "").split("\n")
    if len(lines) < 2:
        raise ValueError("room file too short: %s" % path)
    m = _SIZE_RE.match(lines[1])
    if not m:
        raise ValueError("bad size line in %s: %r" % (path, lines[1][:60]))
    w, h = int(m.group(1)), int(m.group(2))
    total = w * h

    cameras = []
    if len(lines) > 3:
        for tok in lines[3].split("|"):
            tok = tok.strip()
            if "," not in tok:
                continue
            a, _, b = tok.partition(",")
            try:
                px, py = float(a), float(b)
            except ValueError:
                continue
            # 像素 → 格；+700/+400 px 是摄像机中心（与出口同一个 y 朝上的系）
            cameras.append((px / 20.0 + 35.0, py / 20.0 + 20.0))

    grid = None
    for line in lines:
        if line.count("|") < total - 1:
            continue
        parts = line.rstrip("|").split("|")
        if len(parts) == total:
            grid = parts
            break

    cells = ["0"] * total
    if grid is not None:
        for i, tok in enumerate(grid):
            head = tok.partition(",")[0].strip()
            if head in ("", "0"):
                continue
            try:
                val = int(head)
            except ValueError:
                continue
            if val == 0:
                continue
            x, y = divmod(i, h)          # 列优先
            if 0 <= x < w and 0 <= y < h:
                cells[y * w + x] = "1"
    out = (w, h, cameras, "".join(cells), grid)
    _PARSE_CACHE[path] = out
    while len(_PARSE_CACHE) > _PARSE_CACHE_MAX:
        _PARSE_CACHE.popitem(last=False)
    return out


def parse_room_txt(path):
    """解析房间 `.txt`，返回 (w, h, cameras, cells)。

    地形**不是**逐行字符矩阵，而是一行 `|` 分隔的 token，共 `w*h` 个，**列优先**
    （`x = i // h, y = i % h`）。每个 token 形如 `1` 或 `0,6`——逗号前是地形值
    （0 空气，1 实心，2/3 斜坡，4 天花板），后面是对象编号（管道、杆子等）。
    """
    w, h, cameras, cells, _grid = _parse_room(path)
    return w, h, cameras, cells


def room_objects(room):
    """{(x,y): (对象编号…)}，惰性解析并挂在 room.objs 上。

    工具侧如果自己已经有对象数据，直接给 `room.objs` 赋值即可——`doorrule` 会优先用它，
    不再回头读文件。这是热插拔的关键接口之一。
    """
    if room.objs is not None:
        return room.objs
    out = {}
    try:
        _w, _h, _cams, _cells, grid = _parse_room(room.path) if room.path else (0, 0, [], "", None)
    except (OSError, ValueError):
        grid = None
    if grid:
        h = room.h
        for i, tok in enumerate(grid):
            parts = tok.split(",")
            if len(parts) < 2:
                continue
            ids = []
            for f in parts[1:]:
                f = f.strip()
                if not f:
                    continue
                try:
                    ids.append(int(f))
                except ValueError:
                    pass
            if ids:
                x, y = divmod(i, h)
                out[(x, y)] = tuple(ids)
    room.objs = out
    return out


def effective_bbox(room):
    """有效区包围盒 `(x0, y0, x1, y1)`（含端点）；没地形 / 全是空气时返回 None。

    「有效区」= 实心格 ≥ `config.INTERNAL["solid_min"]` 的行/列围出来的框。
    声明尺寸常带空白边距（`UW_D05` 声明 228 宽，实心只到 215——右边 13 列全空），
    所以判边、房间外框、缩略图裁切统一用它；否则那 13 列会在图上变成一条死白。
    """
    if room.eff is not None:
        return room.eff or None
    w, h, cells = room.w, room.h, room.cells
    if not cells or len(cells) < w * h:
        room.eff = ()
        return None
    need = config.INTERNAL["solid_min"]
    cols = [c for c in range(w)
            if sum(1 for yy in range(h) if cells[yy * w + c] != "0") >= need]
    rows = [yy for yy in range(h)
            if sum(1 for c in range(w) if cells[yy * w + c] != "0") >= need]
    if not cols or not rows:
        room.eff = ()
        return None
    room.eff = (min(cols), min(rows), max(cols), max(rows))
    return room.eff


def effective_size(room):
    """有效区的 `(宽, 高)`；没有有效区就退回声明尺寸。"""
    bb = effective_bbox(room)
    if not bb:
        return room.w, room.h
    return bb[2] - bb[0] + 1, bb[3] - bb[1] + 1


# ---------------------------------------------------------------- 区域 JSON

def _room_dirs(layer):
    src = layer.get("source") or {}
    dirs = []
    for d in (src.get("roomsDirs") or []):
        if isinstance(d, str) and d not in dirs:
            dirs.append(d)
    for f in (src.get("files") or []):
        if not isinstance(f, dict):
            continue
        d = f.get("dir")
        if isinstance(d, str) and d not in dirs:
            dirs.append(d)
    if isinstance(src.get("path"), str):
        base = src["path"]
        for cand in (base, os.path.join(base, "world", "uw-rooms")):
            if cand not in dirs:
                dirs.append(cand)
    return dirs


def _candidate_paths(dirs, name):
    """所有可能命中的路径，按目录顺序。"""
    out = []
    for d in dirs:
        if not isinstance(d, str) or not os.path.isdir(d):
            continue
        for cand in (name.lower() + ".txt", name + ".txt"):
            p = os.path.join(d, cand)
            if os.path.isfile(p) and p not in out:
                out.append(p)
        # 名字带模组前缀或不规则大小写时，退化为扫目录（区域房间数不多）
        try:
            for fn in os.listdir(d):
                if fn.lower() == name.lower() + ".txt":
                    p = os.path.join(d, fn)
                    if p not in out:
                        out.append(p)
        except OSError:
            pass
    return out


def _locate(dirs, name):
    """在若干目录里找 `name` 对应的房间 txt —— **跳过解析不了的坏文件**。

    旧实现读到第一份就返回；工作坊版的 `uw_a05.txt` 尺寸行没有尾随 `|`，
    解析失败后整间房被丢掉，连带把 UW 切成两块。
    """
    for p in _candidate_paths(dirs, name):
        try:
            _parse_room(p)
            return p
        except (OSError, ValueError):
            continue
    return None


def split_variant(name):
    """`UW_A04RIV` → ('UW_A04', 'RIV')；不是变体命名则 (None, None)。"""
    m = _VARIANT_RE.match(name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _field_merge(items):
    """同名房间多层出现时**按字段合并**：低层先填，高层非空值覆盖。

    整条覆盖会让高层记录（模组常只写 name/shelter）把 exits、map 清空，
    房间随即变成孤岛（UW 实测 64 间里 59 间没有出口）。
    """
    fields = {}
    for _order, raw in items:
        for key, val in raw.items():
            if val not in (None, "", [], {}):
                fields[key] = val
            elif key not in fields:
                fields[key] = val
    return fields


def _variant_rooms(layers, campaign):
    """取该战役的房间表（`variants[campaign]["rooms"]`，值是地图矩形）。

    从最高层往下找第一个非空的——高层模组可以覆盖战役布局。
    """
    for layer in reversed(layers):
        body = (layer.get("variants") or {}).get(campaign) or {}
        rooms = body.get("rooms") or {}
        if rooms:
            return rooms
    return {}


def campaign_names(region_json):
    """一个区域 JSON 里出现过哪些战役键（demo 的下拉框用）。"""
    try:
        with open(region_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    seen = []
    for layer in data.get("layers") or []:
        for k in (layer.get("variants") or {}):
            if k and k not in seen:
                seen.append(k)
    return sorted(seen)


def load_region(region_json, index_json=None, campaign=None, parser=None):
    """读一个区域的房间全集（多层合并，同名取层序最高者）。

    `campaign` 非空时按该战役的 `variants` 表装配：
      * 只留下该战役地图上的房间（∪ 「任何一版地图都没有矩形」的房间）；
      * `UW_A04RIV` 这类后缀件**顶替** `UW_A04`（节点名仍是基名，布局不重排）；
      * 后缀件里空目标的出口，用基房间同一格位的出口补。

    返回的 `rooms` 在主线模式下**已剔除**后缀变体件（UW 64 → 57）。
    """
    with open(region_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    sources = None
    if index_json and os.path.isfile(index_json):
        try:
            with open(index_json, "r", encoding="utf-8") as fh:
                sources = json.load(fh)
        except ValueError:
            sources = None

    layers = sorted(data.get("layers") or [], key=lambda L: L.get("order") or 0)
    gates = 0
    # 目录候选要**跨层回退**：高层的同名房间经常只是「改了几个字段」，房间 .txt 仍
    # 躺在官方目录里。只在高层自己的 roomsDirs 里找，会平白丢掉一半房间。
    all_dirs = []
    for layer in reversed(layers):
        for d in _room_dirs(layer):
            if d not in all_dirs:
                all_dirs.append(d)

    per_name = {}
    has_map = {}
    for layer in layers:
        order = layer.get("order") or 0
        for raw in (layer.get("rooms") or []):
            name = str(raw.get("name") or "").strip().upper()
            if not name:
                continue
            if is_gate(name):
                gates += 1
                continue
            per_name.setdefault(name, []).append((order, raw))
            mr = raw.get("map")
            if isinstance(mr, dict) and mr.get("w") and mr.get("h"):
                has_map[name] = True

    merged = {}
    for name, items in per_name.items():
        items.sort(key=lambda it: it[0])          # 低层 → 高层
        merged[name] = (items[-1][0], _field_merge(items))

    # ---- 变体件识别（不依赖战役表：后缀 + 基名存在）----
    variant_of = {}
    for name in merged:
        base, _suffix = split_variant(name)
        if base and base in merged and base != name:
            variant_of[name] = base

    # ---- 战役装配 ----
    replaced = {}          # 基名 → 后缀件名
    # 主线（没有战役）：后缀件是**别条战役的替换件**，不进图（UW 64 → 57）
    keep = set(merged) - set(variant_of)
    hidden = []
    table = _variant_rooms(layers, campaign) if campaign else {}
    if campaign and table:
        vis = {str(k).strip().upper() for k in table}
        alias = {nm: variant_of[nm] for nm in vis if nm in variant_of}
        visible = {alias.get(nm, nm) for nm in vis}
        # 「任何一版地图都没有矩形」的房间要保留（地图上不画，但它是能进的）；
        # 但后缀变体件不算——它们只是替换件，别当独立房间画出来
        nomap = {nm for nm in merged
                 if not has_map.get(nm) and nm not in variant_of}
        keep = (visible | nomap) & set(merged)
        replaced = {alias[nm]: nm for nm in vis if nm in alias}
    elif campaign:
        # 该区域没有这份战役表（例如 SD 的 rivulet）：不过滤，只做后缀替换探测
        keep = set(merged)

    if campaign:
        # 后缀探测兜底：没有表、或表里没列出的替换件，按「后缀像这个战役」认。
        # RIV 之于 rivulet、SAINT 之于 saint、ARTY 之于 artificer 都是前缀关系。
        head = campaign.upper()
        for name in merged:
            base = variant_of.get(name)
            if not base or base not in keep:
                continue
            suffix = split_variant(name)[1] or ""
            if suffix and (head.startswith(suffix) or suffix.startswith(head[:3])):
                replaced.setdefault(base, name)

    rooms = []
    missing_file = []
    world_tags = _layer_world_tags(layers)
    for name in sorted(keep):
        _order, raw = merged[name]
        src_name = replaced.get(name, name)
        src_raw = merged.get(src_name, (0, raw))[1]
        path = _locate(all_dirs, src_name) or _locate(all_dirs, name)
        if not path:
            missing_file.append(src_name)
            continue
        try:
            w, h, cams, cells, objs = _load_room(path, parser)
        except (OSError, ValueError):
            missing_file.append(src_name)
            continue
        room = Room(name, w, h)
        room.order = _order
        room.kind = (raw.get("layer") or "") if raw else ""
        room.path = path
        room.cameras = cams
        room.cells = cells
        room.objs = objs          # 注入解析器给的 {} 也算「已解析」，room_objects 不再读文件
        room.sub = raw.get("subregion")
        mr = raw.get("map") or src_raw.get("map")
        if isinstance(mr, dict) and mr.get("w") and mr.get("h"):
            room.map_rect = (mr.get("x") or 0, mr.get("y") or 0,
                             mr.get("w"), mr.get("h"))
        wr = raw.get("world")
        if isinstance(wr, list) and len(wr) >= 4:
            room.world = tuple(wr[:4])
        room.variant_of = variant_of.get(src_name) if src_name != name else None
        room.is_variant = src_name != name
        room.exits = _merge_exits(src_name, src_raw, name, raw, keep)
        # 标签按**基名**取世界文件里的那一行（变体件 `UW_A04RIV` 在世界文件里通常不单列）
        room.tags = _room_tags(raw, world_tags) if raw else _room_tags(
            {"name": name}, world_tags)
        rooms.append(room)

    hidden = sorted(set(merged) - keep)
    # 工具侧 JSON 没有 `name`，只有 `displayName`（英文）/ `nameZh`（中文）；
    # demo 的 `name` 留着兜底，这样两边都能读，页头不会空着。
    display = str(data.get("displayName") or "").strip()
    zh = str(data.get("nameZh") or "").strip()
    return {
        "code": (data.get("code") or os.path.splitext(os.path.basename(region_json))[0]).upper(),
        "name": data.get("name") or display or zh,
        "displayName": display,
        "nameZh": zh,
        "rooms": rooms,
        "missing": missing_file,
        "gates": gates,
        "gate_locks": _gate_locks(layers),
        "campaign": campaign or "",
        "replaced": sorted(replaced.items()),
        "hidden": hidden,
        "variant_rooms": sorted(n for n in merged if n in variant_of),
        "layers": [{"order": L.get("order"), "kind": (L.get("source") or {}).get("kind"),
                    "rooms": len(L.get("rooms") or [])} for L in layers],
    }


def _merge_exits(src_name, src_raw, name, base_raw, keep):
    """出口合并：取**并集**，空目标的用基房间同格位补，目标映射回基名。

    为什么要并集而不是「用变体的」：变体件偶尔少一条边（UW_A05RIV 就没有去 `UW_4B`
    的那扇门），只取变体的话图少了边 → BFS 的根与顺序都变 → 一切战役整张图重排。
    并集保证「切战役不搬家」，代价是可能多画一条该战役里不存在的连线（UW 0 条）。
    """
    own = list(src_raw.get("exits") or [])
    base = list(base_raw.get("exits") or []) if src_name != name else []
    fill = {}
    for e in base:
        try:
            fill[(int(e.get("x")), int(e.get("y")))] = str(e.get("to") or "").strip().upper()
        except (TypeError, ValueError):
            continue
    out = []
    seen = set()
    for e in own + base:
        try:
            x, y = int(e.get("x")), int(e.get("y"))
        except (TypeError, ValueError):
            continue
        to = str(e.get("to") or "").strip().upper() or fill.get((x, y), "")
        if not to:
            continue
        to = _base_name(to, keep)
        if to == name or (x, y, to) in seen:
            continue
        seen.add((x, y, to))
        out.append((x, y, to))
    return out


def _base_name(name, keep):
    """把指向变体件的目标映射回基名（节点名一律用基名）。"""
    if name in keep:
        return name
    base, _suffix = split_variant(name)
    if base and base in keep:
        return base
    return name


def is_gate(name):
    return any(name.startswith(p) for p in SKIP_PREFIX)


# ---------------------------------------------------------------- 世界文件（W4）
# 房间标签（SHELTER / SCAVOUTPOST / …）与业力门锁**只在 world_*.txt 与 gates/locks.txt 里**，
# 区域 JSON 只留了 `shelter` / `gate` 两个布尔。所以这里补一条读世界文件的线：
#   · 一层可能有多个 world 文件（`world_su.txt` / `World_SU.txt` / 模组覆盖版），按层序合并；
#   · 标签取**第三段**（`SU_S04 : SU_A37 : SHELTER`），实测全库房间行只有 2/3 段；
#   · 条件行前缀 `{Saint}ROOM` 要剥掉，否则房间名对不上。
# 缓存按 (路径, mtime, 大小)：一次布局会问同一个世界的几十次，不能每次都读盘。

_WORLD_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_WORLD_CACHE_MAX = 32
_COND_PREFIX = re.compile(r"^\{[^}]*\}")
_LOCK_LINE = re.compile(r"^\s*([A-Za-z0-9_\-]+)\s*:\s*(\d+)\s*:\s*(\d+)\s*$")


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().replace("\r", "")
    except OSError:
        return ""


def _parse_world_tags(path):
    """`world_*.txt` 的 ROOMS 段 → {房间名大写: 标签}。"""
    try:
        st = os.stat(path)
        key = (os.path.normcase(os.path.abspath(path)), int(st.st_mtime), st.st_size)
    except OSError:
        return {}
    hit = _WORLD_CACHE.get(key)
    if hit is not None:
        _WORLD_CACHE.move_to_end(key)
        return hit
    out = {}
    in_rooms = False
    for line in _read_text(path).split("\n"):
        s = line.strip()
        if not s:
            continue
        if not in_rooms:
            if s.upper() == "ROOMS":
                in_rooms = True
            continue
        if s.upper().startswith("END ROOMS"):
            break
        if s.startswith("//"):
            continue
        parts = [x.strip() for x in s.split(":")]
        if len(parts) < 3 or not parts[2]:
            continue
        name = _COND_PREFIX.sub("", parts[0]).strip().upper()
        if name:
            out[name] = parts[2].upper()
    _WORLD_CACHE[key] = out
    while len(_WORLD_CACHE) > _WORLD_CACHE_MAX:
        _WORLD_CACHE.popitem(last=False)
    return out


def _world_files(layer):
    """一层里所有 `world_*.txt` 的路径（先看 source.files 的记录，再扫 source.path 目录）。"""
    src = layer.get("source") or {}
    out = []
    for f in (src.get("files") or []):
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        low = name.lower()
        if not (low.startswith("world_") and low.endswith(".txt")):
            continue
        d = f.get("dir") or src.get("path") or ""
        if d:
            p = os.path.join(d, name)
            if os.path.isfile(p) and p not in out:
                out.append(p)
    base = src.get("path")
    if isinstance(base, str) and os.path.isdir(base):
        try:
            for fn in os.listdir(base):
                low = fn.lower()
                if low.startswith("world_") and low.endswith(".txt"):
                    p = os.path.join(base, fn)
                    if os.path.isfile(p) and p not in out:
                        out.append(p)
        except OSError:
            pass
    return out


def _layer_world_tags(layers):
    """按层序合并所有世界文件的房间标签：高层覆盖低层。"""
    tags = {}
    for layer in layers:
        for path in _world_files(layer):
            tags.update(_parse_world_tags(path))
    return tags


def _gate_locks(layers):
    """业力门锁：`{GATE_XX_YY: (左, 右)}`，取自区域目录旁边的 `gates/locks.txt`。

    区域目录是 `…/world/su`，门目录是它旁边的 `…/world/gates`（大小写不固定，
    模组里还可能叫 `Gates`）。行格式 `GATE_SU_DS : 4 : 2`，数字是两侧的业力等级。
    """
    out = {}
    seen = set()
    for layer in layers:
        base = (layer.get("source") or {}).get("path")
        if not isinstance(base, str):
            continue
        parent = os.path.dirname(base.rstrip("\\/"))
        if not parent or parent in seen:
            continue
        seen.add(parent)
        path = ""
        try:
            for fn in os.listdir(parent):
                if fn.lower() == "gates" or fn.lower() == "locks.txt":
                    cand = os.path.join(parent, fn)
                    if os.path.isdir(cand):
                        for sub in os.listdir(cand):
                            if sub.lower() == "locks.txt":
                                path = os.path.join(cand, sub)
                                break
                    elif fn.lower() == "locks.txt":
                        path = cand
                    if path:
                        break
        except OSError:
            continue
        if not path:
            continue
        for line in _read_text(path).split("\n"):
            m = _LOCK_LINE.match(line)
            if m:
                out[m.group(1).upper()] = (int(m.group(2)), int(m.group(3)))
    return out


def _room_tags(raw, world_tags):
    """一间房的标签集合：区域 JSON 的布尔 + 世界文件的第三段。

    第三段可能有多个标签（逗号分隔），模组还会写别名（`PERFHEAVY` / `HEAVYPERF`），
    所以统一过一遍别名表；认不出的标签原样留着（不画图标，只做诊断）。
    """
    tags = set()
    if (raw or {}).get("shelter"):
        tags.add("SHELTER")
    if (raw or {}).get("gate"):
        tags.add("GATE")
    extra = world_tags.get(str((raw or {}).get("name") or "").strip().upper()) or ""
    for tok in extra.split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        # 少数模组的房间行第三段写的是**另一个房间名**（`GU_IA10` 这种），
        # 真标签里从不出现数字，用这条把它挡掉，免得脏数据跑进标签表。
        if any(ch.isdigit() for ch in tok):
            continue
        tags.add(TAG_ALIAS.get(tok, tok))
    return tuple(sorted(tags))


# 标签别名：世界文件里同一个意思有好几种写法（原版 / 模组各写各的）
TAG_ALIAS = {
    "PERFHEAVY": "PERF_HEAVY",
    "PERF-HEAVY": "PERF_HEAVY",
    "HEAVYPERF": "PERF_HEAVY",
    "ANCIENT_SHELTER": "ANCIENTSHELTER",
    "SCAV_OUTPOST": "SCAVOUTPOST",
    "SCAV_TRADER": "SCAVTRADER",
    "SWARM": "SWARMROOM",
}


def is_variant_name(name):
    return split_variant(name)[0] is not None
