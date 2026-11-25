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

# 门房间（GATE_XX_YU 之类）。V1.24 起**也画进区域图**（附在区域边界那间房上），
# 这里只留前缀用于识别：`is_gate()` 决定渲染样式、业力提示与"没邻居就别硬画"。
GATE_PREFIX = ("GATE_",)
# 兼容旧名字（demo / check 脚本还按 `SKIP_PREFIX` 引用）
SKIP_PREFIX = GATE_PREFIX

_SIZE_RE = re.compile(r"^\s*(\d+)\s*\*\s*(\d+)\s*(?:\||$)")
# 变体件命名：`UW_A04RIV` / `SB_E05SAINT` / `TM_A01SPEAR` → 基名 + 后缀
_VARIANT_RE = re.compile(r"^(.*\d)([A-Z]+)$")


# ---------------------------------------------------------------- 角色（V1.24 №7）
# 与 `ui/rw_gui.html` 的 `SLUGCAT_ALIAS` / `mySlugcatNames()` **逐字一致**：
# 前端按存档原名（`White` / `Spear` / `Saint`…）算分母，地图这边必须算出同一套集合，
# 否则「图上 90 间、清单里 74 间」永远对不上。注意**不能**复用 `bridge._canon_slugcat`
# ——那是「房间 settings 文件名」的词表，不是 `CONDITIONAL LINKS` 的。
_SLUG_ALIAS = {
    "white": "survivor", "yellow": "monk", "red": "hunter", "night": "nightcat",
    "spear": "spearmaster", "pale": "monk", "enot": "enot",
}


def canon_slugcat(slugcat):
    key = re.sub(r"[\s\-_]", "", str(slugcat or "").strip().lower())
    return _SLUG_ALIAS.get(key, key)


def my_slugcat_names(slugcat):
    """「我叫什么」：白猫既是 `WHITE` 也是 `SURVIVOR`（条件链接里两种写法都有）。"""
    raw = str(slugcat or "").strip().upper()
    canon = canon_slugcat(slugcat).upper()
    if not raw:
        return [canon] if canon else []
    return [raw] if raw == canon else [raw, canon]


# 房间名里带角色后缀（`GW_A21SAINT` / `LM_BRIDGE04ARTY`）：模组大多没写 CONDITIONAL
# LINKS，只能靠「名字像某角色」+「在本层是孤岛」两条一起判。规则与前端 `ROOM_OWNER` 一致。
_OWNER_RULES = (
    (re.compile(r"SAINT"), ("SAINT",)),
    (re.compile(r"ARTIFICER|ARTY"), ("ARTIFICER",)),
    (re.compile(r"SPEARMASTER|SPEAR"), ("SPEARMASTER", "SPEAR")),
    (re.compile(r"RIVULET"), ("RIVULET",)),
    (re.compile(r"GOURMAND|GOURM"), ("GOURMAND",)),
    (re.compile(r"HUNTER"), ("HUNTER",)),
    (re.compile(r"NIGHT"), ("NIGHTCAT", "NIGHT")),
)


def room_owners(name):
    """房间名暗示的角色集合；名字不带角色后缀返回 `None`。"""
    up = str(name or "").upper()
    for rx, cats in _OWNER_RULES:
        if rx.search(up):
            return cats
    return None


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
                 "variant_of", "is_variant", "is_gate", "eff", "tags")

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
        self.is_gate = False     # 大门房（V1.24：会画进区域图，样式与房间不同）
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


def _gate_dirs(layer):
    """这一层能找门房间 `.txt` 的目录（V1.24）。

    门房的地形**不在** `sl-rooms/`，而在 `world/gates/`——它是区域目录的**兄弟**：
        world/sl-rooms  →  world/gates
        world/sl        →  world/gates
        modify/world/sl →  modify/world/gates      （模组自带的门）
    以前门被整类跳过，所以没人踩到这个坑；现在要画门，必须把这条目录补进候选。
    """
    bases = []
    src = layer.get("source") or {}
    for d in (src.get("roomsDirs") or []):
        if isinstance(d, str) and d:
            bases.append(d)
    for f in (src.get("files") or []):
        if isinstance(f, dict) and isinstance(f.get("dir"), str) and f["dir"]:
            bases.append(f["dir"])
    if isinstance(src.get("path"), str) and src["path"]:
        bases.append(src["path"])
    out = []
    for base in bases:
        for cand in (os.path.join(os.path.dirname(base), "gates"),
                     os.path.join(base, "gates")):
            if os.path.isdir(cand):
                key = os.path.normcase(os.path.abspath(cand))
                if all(os.path.normcase(os.path.abspath(x)) != key for x in out):
                    out.append(cand)
    return out


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


def _variant_body(layer, campaign):
    """`variants` 里这个战役的那一份（**键不区分大小写**）。

    数据里的键是小写（`saint` / `rivulet` / `artificer` / `inv` / `spear`…），而存档传的是
    原名 `Artificer` / `Spear`。V1.24 №7 修的真 bug：以前直接 `.get(campaign)`，
    前端真实值永远命中不了 → GW 传 `Artificer` 仍是 124 间（等于角色筛选没开）。
    """
    variants = layer.get("variants") or {}
    want = str(campaign or "").strip().lower()
    if not want:
        return {}
    body = variants.get(want)
    if isinstance(body, dict):
        return body
    for key, val in variants.items():
        if str(key).strip().lower() == want and isinstance(val, dict):
            return val
    return {}


def _variant_rooms(layers, campaign):
    """取该战役的房间表（`variants[campaign]["rooms"]`，值是地图矩形）。

    从最高层往下找第一个非空的——高层模组可以覆盖战役布局。
    """
    for layer in reversed(layers):
        body = _variant_body(layer, campaign)
        rooms = body.get("rooms") or {}
        if rooms:
            return rooms
    return {}


def _layer_kept(layer, off, campaign):
    """这一层参不参与装配（V1.24 №6）。

    * 来源被熄灭 → 不要（`config` 里的 `_sources.json`，没登记的层一律当启用）；
    * 「仅地图」层（有底图没有 world 文件）→ 只有它带着当前角色的地图变体时才要，
      否则它的房间表是从地图矩形凑的，既不全也没有庇护所/大门标记。
      判定与前端 `usableLayers()` 同口径。
    """
    lid = str(layer.get("id") or "")
    if lid and lid in off:
        return False
    stats = layer.get("stats")
    if isinstance(stats, dict) and "hasWorldFile" in stats and not stats.get("hasWorldFile"):
        return bool(campaign and _variant_body(layer, campaign))
    return True


def _merge_layers(layers):
    """多层按字段合并 → `(merged, has_map, variant_of)`，形状与旧实现一致。

    V1.24 起**不再剔掉 GATE_**：大门也是房间，要画进区域图（附在区域边界那间房上）。
    没邻居的门（另一侧的房不在本区）不会留在 `rooms` 里，见 `load_region` 的 `gates_off`。
    """
    per_name = {}
    has_map = {}
    for layer in layers:
        order = layer.get("order") or 0
        for raw in (layer.get("rooms") or []):
            name = str(raw.get("name") or "").strip().upper()
            if not name:
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
    return merged, has_map, variant_of


def _campaign_view(merged, has_map, variant_of, layers, campaign):
    """按战役装一遍 → `(keep, replaced)`：keep 是节点名集合，replaced 是「基名→后缀件」。"""
    replaced = {}          # 基名 → 后缀件名
    # 主线（没有战役）：后缀件是**别条战役的替换件**，不进图（UW 64 → 57）
    keep = set(merged) - set(variant_of)
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
        head = str(campaign).upper()
        for name in merged:
            base = variant_of.get(name)
            if not base or base not in keep:
                continue
            suffix = split_variant(name)[1] or ""
            if suffix and (head.startswith(suffix) or suffix.startswith(head[:3])):
                replaced.setdefault(base, name)
    # 大门**不受战役地图表约束**：`variants[].rooms` 是从地图图块里抽的，门一般不在里面，
    # 直接按表留房间会把整区的大门全删掉（V1.24 实测 SL 少 13 座）。
    keep |= {nm for nm in merged if is_gate(nm)}
    return keep, replaced


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


def load_region(region_json, index_json=None, campaign=None, parser=None,
                filters=None):
    """读一个区域的房间全集（多层合并，同名取层序最高者）。

    `campaign` 非空时按该战役的 `variants` 表装配：
      * 只留下该战役地图上的房间（∪ 「任何一版地图都没有矩形」的房间）；
      * `UW_A04RIV` 这类后缀件**顶替** `UW_A04`（节点名仍是基名，布局不重排）；
      * 后缀件里空目标的出口，用基房间同一格位的出口补。

    `filters`（V1.24 №6/№7）为 `None` 时**什么都不筛**——demo、对拍、形状评分走这条路；
    工具主路径传一份：

        {"off": ["mod:xxx"],       # 被熄灭的来源 id（№6，没登记的层当启用）
         "role": "Artificer",      # 存档里的角色名（№7，后端自己归一）
         "strict": True,           # 严格口径（config.ui.roomStrict）
         "ex": ["GW_A21"]}         # 手工剔除（config.ui.roomExcluded）

    过滤必须在**装配阶段**做：布局、BFS 根、连通块、配色都跟着房间集合走，
    画完再摘节点会留洞。返回里的 `color_rooms` 是**筛选前**的全量房间（取色用），
    这样切来源/切角色时颜色不会跟着跳。

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

    all_layers = sorted(data.get("layers") or [], key=lambda L: L.get("order") or 0)
    flt = filters if isinstance(filters, dict) else None
    off = {str(x) for x in (flt or {}).get("off") or []}
    layers = [L for L in all_layers if _layer_kept(L, off, campaign)]
    gates = sum(1 for L in layers for raw in (L.get("rooms") or [])
                if is_gate(str(raw.get("name") or "").strip().upper()))
    # 目录候选要**跨层回退**：高层的同名房间经常只是「改了几个字段」，房间 .txt 仍
    # 躺在官方目录里。只在高层自己的 roomsDirs 里找，会平白丢掉一半房间。
    # 这里用**全量层**：被熄灭的来源也可能揣着别的层要用的房间文件。
    all_dirs = []
    for layer in reversed(all_layers):
        for d in _room_dirs(layer):
            if d not in all_dirs:
                all_dirs.append(d)
    # 门房的地形在 `world/gates/`（区域目录的兄弟），与普通房间目录不重叠
    for layer in reversed(all_layers):
        for d in _gate_dirs(layer):
            if d not in all_dirs:
                all_dirs.append(d)

    merged, has_map, variant_of = _merge_layers(layers)
    keep, replaced = _campaign_view(merged, has_map, variant_of, layers, campaign)

    # 「没被筛过」的那一版只给两件事用：取色（切来源时配色不该跳）与孤岛判定
    # （度数用过滤前的邻居数，避免 №6/№7 两个筛选互相放大，见 `_filter_rooms`）。
    if flt:
        merged_all, has_map_all, variant_of_all = _merge_layers(all_layers)
        keep_all, _replaced_all = _campaign_view(merged_all, has_map_all, variant_of_all,
                                                 all_layers, campaign)
    else:
        merged_all, variant_of_all, keep_all = merged, variant_of, keep

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
        room.is_gate = is_gate(name)
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

    # 门的 txt 找不到（模组只在 world 里登了名字）：不算「缺地形」，也不算绘制失败——
    # 它本来是"区域之外"的门，进不了图是正常的。清单里仍能看到并点开房间卡。
    gate_missing = [nm for nm in missing_file if is_gate(nm)]
    missing_file = [nm for nm in missing_file if not is_gate(nm)]

    dropped = None
    color_rooms = None
    if flt:
        rooms, dropped = _filter_rooms(rooms, merged, merged_all, keep_all,
                                       variant_of_all, filters)
        # 「因为来源被熄灭而根本没装进来」的房间也记一笔，否则
        # `rooms_total - len(rooms)` 会对不上 `dropped` 的合计（界面上要能自洽）
        dropped["source"] = max(0, len(keep_all) - len(keep))
        color_rooms = _color_rooms(rooms, merged_all, keep_all, all_dirs)

    # ---- 大门：只留「在本区内至少有一条连线」的 ----
    # 另一侧的房在别的区域（`GATE_SL_MS` 只连 DM/MS 的房间）的门，图上没有可贴的地方；
    # 硬画会被布局当孤岛摆到主图右侧的「停车场」，整张图被拉宽、所有房间缩一圈。
    by_name = {r.name for r in rooms}
    linked = set()
    for room in rooms:
        for _x, _y, to in room.exits:
            if to in by_name:
                linked.add(room.name)
                linked.add(to)
    gates_off = sorted(r.name for r in rooms if r.is_gate and r.name not in linked)
    if gates_off:
        gone = set(gates_off)
        rooms = [r for r in rooms if r.name not in gone]
    dropped = dropped or {"source": 0, "exclusive": 0, "hidden": 0, "manual": 0, "role": 0}
    dropped["gate"] = len(gates_off) + len(gate_missing)

    hidden = sorted(set(merged) - keep)
    # 工具侧 JSON 没有 `name`，只有 `displayName`（英文）/ `nameZh`（中文）；
    # demo 的 `name` 留着兜底，这样两边都能读，页头不会空着。
    display = str(data.get("displayName") or "").strip()
    zh = str(data.get("nameZh") or "").strip()
    out = {
        "code": (data.get("code") or os.path.splitext(os.path.basename(region_json))[0]).upper(),
        "name": data.get("name") or display or zh,
        "displayName": display,
        "nameZh": zh,
        "rooms": rooms,
        "rooms_total": len(keep_all),
        "dropped": dropped or {"source": 0, "exclusive": 0, "hidden": 0, "manual": 0, "role": 0},
        "missing": missing_file,
        "gates": gates,
        # 进了 keep 但没上图的大门：`dropped["gate"]` 的两部分之一（另一部分是没有 txt）
        "gates_off": gates_off,
        "campaign": campaign or "",
        "replaced": sorted(replaced.items()),
        "hidden": hidden,
        "variant_rooms": sorted(n for n in merged if n in variant_of),
        "layers": [{"order": L.get("order"), "kind": (L.get("source") or {}).get("kind"),
                    "rooms": len(L.get("rooms") or [])} for L in layers],
    }
    if color_rooms:
        out["color_rooms"] = color_rooms
    return out


class _ColorRoom(object):
    """只给 `colors.for_region` 用的轻量房间：路径 + 子区域名，不带地形。

    为什么不用真 `Room`：取色的房间表要**过滤前**的全量（切来源配色不跳），
    为那些马上要被剔掉的房间解析一遍 .txt 是白花 0.4–0.6 s。
    """

    __slots__ = ("name", "path", "sub")

    def __init__(self, name, path, sub):
        self.name = name
        self.path = path
        self.sub = sub


def _name_index(dirs):
    """目录里所有房间 txt 的**小写名 → 路径**索引（只扫一遍目录）。

    取色只需要路径，不需要解析；逐个房间走 `_candidate_paths` 会退化成
    「房间数 × 目录数」次 `listdir`（GW 那种 11 层 124 间的区能白花好几百毫秒）。
    """
    idx = {}
    for d in dirs:
        if not isinstance(d, str) or not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith(".txt"):
                    idx.setdefault(fn[:-4].lower(), os.path.join(d, fn))
        except OSError:
            continue
    return idx


def _color_rooms(rooms, merged_all, keep_all, all_dirs):
    """取色用的房间表：战役范围内**未经过 №6/№7 筛选**的全量房间，名字排序。

    大门**不参与取色**：门房在 `world/gates/` 下、调色板跟区域主体不是一回事；
    而且 `colors.for_region` 用 `rooms[0].path` 反推区域目录，`GATE_*` 名字恰好
    排在 `GW_*` 前面——让它当第一间，整个区的配色会被算到门房间的目录上去。
    """
    path_by_name = {r.name: r.path for r in rooms}
    index = None
    out = []
    for name in sorted(keep_all):
        if is_gate(name):
            continue
        path = path_by_name.get(name)
        if not path:
            if index is None:
                index = _name_index(all_dirs)
            path = index.get(str(name).lower())
        raw = (merged_all.get(name) or (0, {}))[1]
        out.append(_ColorRoom(name, path, raw.get("subregion")))
    # `colors` 拿 `rooms[0].path` 找区域目录；第一个恰好没路径就把有路径的挪上来
    if out and not out[0].path:
        for i, cr in enumerate(out):
            if cr.path:
                out[0], out[i] = cr, out[0]
                break
    return out


def _clean_roles(values):
    """`exclusive` / `hidden` 里的角色名清洗（V1.24 №7）。

    模组写的 `{!PostBathScene,!ToySending}Watcher` 被旧解析器按 `,` 切碎成
    `["{POSTBATHSCENE", "!TOYSENDING}WATCHER"]`（`mod_importer` 已修，但已落盘的数据还在）。
    这里兜一次：`}` 之后那段才是角色名，只有 `{` 没有 `}` 的是剧情标记碎片，丢掉。
    """
    out = []
    for value in values or []:
        token = str(value or "").strip().upper()
        if not token:
            continue
        if "}" in token:
            token = token.rsplit("}", 1)[1]
        elif "{" in token:
            continue
        token = token.strip("{}! ").strip()
        if token and token not in out:
            out.append(token)
    return out


def _degree_map(merged, keep, variant_of):
    """每间房在「全量层」里的邻居数（孤岛判定用）。

    度数**故意用过滤前**的邻居：先按来源筛再算度数会让「只连着别的来源」的房间
    突然变成孤岛，№6/№7 两个筛选互相放大。变体件空目标的出口没做基名回填，
    这里只求「有没有邻居」，精度足够。
    """
    deg = {}
    for name in keep:
        raw = (merged.get(name) or (0, {}))[1]
        seen = set()
        for e in raw.get("exits") or []:
            to = str(e.get("to") or "").strip().upper()
            if not to:
                continue
            to = _base_name(to, keep)
            if to != name and to in keep:
                seen.add(to)
        deg[name] = len(seen)
    return deg


def _filter_rooms(rooms, merged, merged_all, keep_all, variant_of_all, filters):
    """№6/№7 的筛选口径（照抄前端 `applyConditional()`），返回 `(留下的房间, 计数)`。

    | 判据 | 是否受「严格」影响 |
    |---|---|
    | `exclusive`：当前角色不在名单 → 剔 | 否 |
    | `hidden`：当前角色在名单 → 剔 | 否 |
    | `config.ui.roomExcluded` 命中 → 剔 | 是 |
    | 名字带别的角色后缀 + 在本层是孤岛 → 剔 | 是 |
    """
    role = str(filters.get("role") or "")
    mine = set(my_slugcat_names(role))
    strict = bool(filters.get("strict", True))
    manual = {str(x).strip().upper() for x in (filters.get("ex") or []) if str(x).strip()}
    deg = _degree_map(merged_all, keep_all, variant_of_all)
    out = []
    dropped = {"exclusive": 0, "hidden": 0, "manual": 0, "role": 0}
    for room in rooms:
        raw = (merged.get(room.name) or (0, {}))[1]
        exclusive = _clean_roles(raw.get("exclusive"))
        if exclusive and not (mine & set(exclusive)):
            dropped["exclusive"] += 1
            continue
        hidden = _clean_roles(raw.get("hidden"))
        if hidden and (mine & set(hidden)):
            dropped["hidden"] += 1
            continue
        if strict and room.name in manual:
            dropped["manual"] += 1
            continue
        owners = room_owners(room.name)
        if strict and owners and not (mine & set(owners)) and deg.get(room.name, 0) <= 0:
            dropped["role"] += 1
            continue
        out.append(room)
    return out, dropped


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
