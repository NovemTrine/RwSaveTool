"""工具侧数据接入：把 `region_data/<CODE>.json` + 房间 `.txt` 装配成 regmap 要的 `Room` 列表。

为什么要有这一层：
  demo 自带一套 `.txt` 解析器（`model._parse_room`），结果塞进无上限 dict —— 预览进程
  跑完就退出没事，桌面工具常驻会涨到几百 MB。这里把它换成工具自己的 `room_geo`
  （已有 LRU 缓存、已在给房间卡用），布局算法本身一行不改。

关键约定（与 `model.load_region` 对齐，改一处要同时改两处）：
  - `cells`  行优先，**一格一个 hex 字符**（'0'..'f'），就是地形值原样：0 空气 / 1 实心 /
    2..15 斜面与局部。W1 之前这里压成了 "0"/"1"，把斜面和"墙"混成一类、也没法上色；
    布局侧一律用 `!= "0"` 判实心，所以放开精度不影响任何几何
  - `cameras` 格坐标、世界 y 向上；取自 `.txt` 第 4 行（与 demo 完全同一段代码逻辑）
  - `objects` {(x, y): (编号…)}；直接喂给 `room.objs`，`doorrule` 会优先用它，
    `thumbnail` 用它画覆盖层（管道/出口/巢穴/可攀爬/杆子/生物通道）
"""

from __future__ import annotations

import os
from collections import OrderedDict

from .. import paths, room_geo
from . import build_rooms, config, model

_CACHE_MAX = 48          # 与 room_geo 同量级；单间约 0.17 MB，48 间 ≈ 8 MB
_HEX = "0123456789abcdef"
_cache: "OrderedDict[tuple, tuple]" = OrderedDict()


def region_path(code: str) -> str:
    return os.path.join(paths.data_dir(), "%s.json" % str(code).upper())


def _camera_points(lines: list[str]) -> list[tuple[float, float]]:
    """`.txt` 第 4 行是摄像机：像素坐标（世界 y 向上，原点房间左下，单台 1400×800）。

    与 demo `model._parse_room` 同一套换算：/20 转格，+35/+20 是摄像机中心偏移。
    换成工具解析器时这里必须逐字保留，否则判边的最后一级证据会漂。
    """
    out = []
    if len(lines) <= 3:
        return out
    for tok in lines[3].split("|"):
        tok = tok.strip()
        if "," not in tok:
            continue
        a, _, b = tok.partition(",")
        try:
            px, py = float(a), float(b)
        except ValueError:
            continue
        out.append((px / 20.0 + 35.0, py / 20.0 + 20.0))
    return out


def _parse_room_file(path: str) -> tuple[int, int, list, str, dict]:
    """→ (w, h, cameras, cells, objects)，契约见模块 docstring。"""
    try:
        st = os.stat(path)
        key = (path, int(st.st_mtime), st.st_size)
    except OSError:
        key = None
    if key is not None:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    try:
        geo = room_geo.parse_text(text)
    except room_geo.RoomGeoError as exc:
        # model.load_region 只认 ValueError/OSError，翻译一下，让房间进 missing 而不是整区失败
        raise ValueError(str(exc))

    # 保留地形值（hex），不再压成 0/1：斜面/局部（2..15）交给缩略图分层上色。
    # 布局与包围盒只判 `!= "0"`，所以这一步不影响任何几何。
    cells = "".join(c if c in _HEX else "0" for c in geo["cells"])
    buckets = {}
    for item in geo.get("objects") or []:
        try:
            x, y, code = int(item[0]), int(item[1]), int(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        buckets.setdefault((x, y), []).append(code)
    objs = {k: tuple(v) for k, v in buckets.items()}

    out = (geo["w"], geo["h"], _camera_points(text.split("\n")), cells, objs)
    if key is not None:
        _cache[key] = out
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return out


def load_rooms(code: str, slugcat: str = "", filters: dict | None = None) -> dict:
    """装配一个区域的房间全集（多层合并 / 变体替换 / 战役 / 出口并集都在 `model` 里）。

    `filters` 是 №6/№7 的筛选口径（来源 / 角色 / 严格 / 手工剔除），`None` = 不筛。
    它由 `bridge` 按配置算好塞进 `opts["flt"]`，这里只负责转手。
    """
    path = region_path(code)
    if not os.path.isfile(path):
        raise FileNotFoundError("该区域没有导入数据：%s" % str(code).upper())
    return model.load_region(path, None, campaign=(slugcat or None),
                             parser=_parse_room_file, filters=filters)


def probe(code: str, slugcat: str = "", filters: dict | None = None) -> dict:
    """能不能排布：房间数、缺 txt 数、无地图矩形数、可用战役。"""
    try:
        region = load_rooms(code, slugcat, filters)
    except FileNotFoundError as exc:
        return {"ok": False, "error": "no_region", "detail": str(exc)}
    except Exception as exc:                       # noqa: BLE001 - 桥接层不抛
        return {"ok": False, "error": "load_failed", "detail": str(exc)}

    rooms = region.get("rooms") or []
    no_map = sum(1 for r in rooms if not r.map_rect)
    try:
        campaigns = model.campaign_names(region_path(code))
    except Exception:                              # noqa: BLE001
        campaigns = []
    return {
        "ok": bool(rooms),
        "error": "" if rooms else "no_rooms",
        "rooms": len(rooms),
        "rooms_total": region.get("rooms_total") or len(rooms),
        "dropped": region.get("dropped") or {},
        "missing": len(region.get("missing") or []),
        "no_map_rooms": no_map,
        "campaigns": campaigns,
        "campaign": region.get("campaign") or "",
    }


def build(code: str, slugcat: str = "", opts: dict | None = None, prepare: bool = True) -> dict:
    """跑一遍布局，返回纯数据（`nodes` / `edges` / `stats`）。

    `opts["flt"]`（筛选口径）在这里**摘掉**：它只影响装哪批房间，不属于布局参数，
    留着会污染 `result["params"]` 的回显（前端/回归脚本会把它当成可调项）。
    """
    o = dict(opts or {})
    flt = o.pop("flt", None)
    region = load_rooms(code, slugcat, flt if isinstance(flt, dict) else None)
    p = config.defaults()
    p.update(o)
    return build_rooms(region["rooms"], opts=p, region=region, code=code, prepare=prepare)
