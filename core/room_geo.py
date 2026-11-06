"""房间布局（地形网格）解析。

从 `<region>-rooms/<room>.txt` 里读出整个房间的 W×H 地形网格，供界面画矢量平面图。

实测格式（2026-11-02，3348 间验证通过）：
  - 第 2 行 `W*H|...`，单位是「格」，1 格 = 20 px
  - 地形网格是「按 | 切分后正好 W×H 个」的那一行（绝大多数是第 12 行）
  - **列优先**存储：index = x*H + y（按行优先读会把房间打成噪点）
  - 0 = 空气，1 = 满格实心，2..15 = 斜面/局部
  - 占文件 95% 体积的打包段（第 11 行）与布局无关，直接跳过
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

CELL_PX = 20          # 游戏内一格 20 像素
_MAX_CACHE = 48       # 单间最大约 32 KB 文本，48 间 ≈ 1.5 MB
_CHARS = "0123456789abcdef"

# 格子对象编号（已标定，见《房间几何渲染规范》）
OBJ_BEAM_V = 1        # 竖直杆子
OBJ_BEAM_H = 2        # 水平杆子
OBJ_PIPE = 3          # 管道路线
OBJ_EXIT = 4          # 房间出口（彻底离开本房间）
OBJ_DEN = 5           # 生物巢穴
OBJ_CLIMB = 6         # 可攀爬背景墙
OBJ_CREATURE = 9      # 生物通道

# 十字标记的代号，前端按这个决定颜色
MARK_EXIT = "exit"
MARK_DEN = "den"
MARK_CREATURE = "creature"
_MARK_CODES = ((OBJ_EXIT, MARK_EXIT), (OBJ_DEN, MARK_DEN), (OBJ_CREATURE, MARK_CREATURE))


class RoomGeoError(Exception):
    """解析失败，消息可直接展示给用户。"""


def rooms_dir_of(region_dir: str | None) -> str | None:
    """`.../world/su` → `.../world/su-rooms`。"""
    if not region_dir:
        return None
    return os.path.join(os.path.dirname(region_dir), os.path.basename(region_dir) + "-rooms")


def _layer_dirs(region: dict, layer_id: str | None = None) -> list[str]:
    dirs: list[str] = []
    layers = region.get("layers") or []
    ordered = []
    if layer_id:
        ordered.extend([l for l in layers if l.get("id") == layer_id])
    ordered.extend([l for l in layers if l.get("id") != layer_id])
    for layer in ordered:
        src = layer.get("source") or {}
        d = rooms_dir_of(src.get("path"))
        if d and d not in dirs:
            dirs.append(d)
    return dirs


def candidates(region: dict, room: str, layer_id: str | None = None) -> list[str]:
    """按优先级列出可能的房间文件路径（含门房间的另一种命名）。"""
    name = str(room).strip().lower()
    out: list[str] = []
    for d in _layer_dirs(region, layer_id):
        out.append(os.path.join(d, name + ".txt"))
    # 门房间住在同级的 gates/ 里，文件名是 gate_<小区域>_<小区域>.txt，两侧顺序不定
    parts = name.split("_")
    if len(parts) >= 3 and parts[0] == "gate":
        a, b = parts[1], parts[2]
        for d in _layer_dirs(region, layer_id):
            gdir = os.path.join(os.path.dirname(d), "gates")
            for pair in ((a, b), (b, a)):
                p = os.path.join(gdir, "gate_%s_%s.txt" % pair)
                if p not in out:
                    out.append(p)
    return out


def find_file(region: dict, room: str, layer_id: str | None = None) -> tuple[str | None, str | None]:
    """返回 (命中的路径, 首个存在的 -rooms 目录)。"""
    path = None
    first_dir = None
    for cand in candidates(region, room, layer_id):
        if first_dir is None and os.path.basename(os.path.dirname(cand)) != "gates":
            first_dir = os.path.dirname(cand)
        if os.path.isfile(cand):
            path = cand
            break
    return path, first_dir


def _header_size(lines: list[str]) -> tuple[int, int]:
    for line in lines[:4]:
        head = line.split("|")[0].strip()
        if "*" in head and head.replace("*", "").isdigit():
            w, h = head.split("*", 1)
            return int(w), int(h)
    raise RoomGeoError("尺寸行格式异常")


def _border(lines: list[str]) -> str:
    for line in lines[:8]:
        s = line.strip()
        if s.lower().startswith("border:"):
            return s.split(":", 1)[1].strip()
    return ""


def _camera_count(lines: list[str]) -> int:
    for line in lines[1:8]:
        s = line.strip()
        if not s or "|" in s and "*" in s:
            continue
        parts = s.split("|")
        if parts and all(_is_xy(p) for p in parts):
            return len(parts)
    return 1


def _is_xy(token: str) -> bool:
    bits = token.split(",")
    if len(bits) != 2:
        return False
    return all(b.strip().lstrip("-").isdigit() for b in bits)


def _port_dir(x: int, y: int, pipe_cells: set) -> tuple[int, int]:
    """管道口的朝向：指向同一段管道里相邻的那一格。

    段 = 4 邻接的编号 3 连通块。若两侧都连着（拐角格）取第一个命中的方向，
    实测 DS_A15 / DS_A09 的 13 个管道口里没有这种格子（规范 §6.2 记了这个口子）。
    """
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        if (x + dx, y + dy) in pipe_cells:
            return dx, dy
    return 0, 1


def _structure(w: int, h: int, cells: str, objects: list) -> dict:
    """把扁平的 objects 归并成三组可直接绘制的东西。

    - `pipes.ports`：管道口 `[[x, y, dx, dy]]`，编号 3 且同格带 6 的格子，dx/dy 是朝向
    - `pipes.dots` ：管道路线 `[[x, y]]`，编号 3 但不带 6
    - `marks`      ：十字 `[[x, y, "exit"|"den"|"creature"]]`，对应编号 4 / 5 / 9
    - `climb`      ：可攀爬背景墙 `[[x, y]]`，编号 6 **且地形为 0**，且不被上面几类占用
    """
    at: dict = {}
    for x, y, oid in objects:
        at.setdefault((x, y), set()).add(oid)

    pipe_cells = {p for p, s in at.items() if OBJ_PIPE in s}
    ports = []
    dots = []
    for (x, y) in pipe_cells:
        if OBJ_CLIMB in at[(x, y)]:
            dx, dy = _port_dir(x, y, pipe_cells)
            ports.append([x, y, dx, dy])
        else:
            dots.append([x, y])

    marks = []
    for (x, y), s in at.items():
        for oid, code in _MARK_CODES:
            if oid in s:
                marks.append([x, y, code])

    # 可攀爬墙只在"空的格子"上显示成底色；被管道/十字占用的格子让位给符号
    occupied = {p for p, s in at.items()
                if s & {OBJ_PIPE, OBJ_EXIT, OBJ_DEN, OBJ_CREATURE}}
    climb = []
    for (x, y), s in at.items():
        if OBJ_CLIMB not in s or (x, y) in occupied:
            continue
        if cells[y * w + x] == "0":
            climb.append([x, y])

    return {
        "pipes": {"ports": sorted(ports), "dots": sorted(dots)},
        "marks": sorted(marks, key=lambda m: (m[1], m[0], m[2])),
        "climb": sorted(climb),
    }


def parse_text(text: str) -> dict:
    """把一份房间文件解析成 {w, h, cells, border, cameras, objects}。

    cells 是**行优先**的字符串，每格一个字符：'0'..'9' / 'a'..'f'。

    objects 是格子上的对象 `[[x, y, 编号], ...]`，编号语义（2026-11-03 人工标定：
    《雨世界存档分析器_房间几何渲染规范.md》）：

      | 编号 | 含义 |
      |---|---|
      | 1 | 竖直杆子 |
      | 2 | 水平杆子 |
      | 3 | 管道路线（墙内走线） |
      | 4 | 房间之间的通道＝彻底离开房间的出口 |
      | 5 | 生物巢穴（生物生成点） |
      | 6 | 可攀爬背景墙（面状属性，只在空气格上显示成底色） |
      | 9 | 生物通道（玩家不可用、生物可用） |

    3 与 4/5/9 的关系：3 是一条管道在墙里走的那串格子，它的一端是**管道口**
    （那个格子同时带 6），另一端是 4（离开房间）/ 5（生物巢穴）/ 9（生物通道）。
    """
    if "\r" in text:
        text = text.replace("\r", "")
    lines = text.split("\n")
    if len(lines) < 3:
        raise RoomGeoError("房间文件不完整")
    w, h = _header_size(lines)
    total = w * h
    if not (0 < w <= 2000 and 0 < h <= 2000):
        raise RoomGeoError("尺寸异常：%d×%d" % (w, h))

    grid = None
    for line in lines:
        if line.count("|") < 8:          # 大段打包数据没有分隔符，快速跳过
            continue
        parts = line.rstrip("|").split("|")
        if len(parts) == total:
            grid = parts
            break
    if grid is None:
        raise RoomGeoError("没有找到 W×H 的地形网格")

    cells = ["0"] * total
    objects = []
    for i, token in enumerate(grid):
        fields = token.split(",")
        raw = fields[0].strip()
        try:
            value = int(raw)
        except ValueError:
            value = 0
        x, y = divmod(i, h)              # 列优先：x = i // h, y = i % h
        cells[y * w + x] = _CHARS[value] if 0 <= value < len(_CHARS) else "0"
        for extra in fields[1:]:
            try:
                objects.append([x, y, int(extra)])
            except ValueError:
                continue

    cells_str = "".join(cells)
    struct = _structure(w, h, cells_str, objects)
    return {
        "w": w,
        "h": h,
        "cells": cells_str,
        "objects": objects,
        "border": _border(lines),
        "cameras": _camera_count(lines),
        "pipes": struct["pipes"],
        "marks": struct["marks"],
        "climb": struct["climb"],
    }


_lock = threading.Lock()
_cache: "OrderedDict[tuple, dict]" = OrderedDict()


def load(path: str) -> dict:
    """读文件并解析，带按 (路径, mtime, 大小) 的 LRU 缓存。"""
    try:
        st = os.stat(path)
    except OSError as exc:
        raise RoomGeoError("找不到房间文件：%s" % exc)
    key = (path, st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        raise RoomGeoError("房间文件读取失败：%s" % exc)
    data = parse_text(text)
    data["path"] = path
    with _lock:
        _cache[key] = data
        while len(_cache) > _MAX_CACHE:
            _cache.popitem(last=False)
    return data


def geometry(region: dict, room: str, layer_id: str | None = None) -> dict:
    """给界面用的入口：返回可直接绘制的布局数据。"""
    path, first_dir = find_file(region, room, layer_id)
    if not path:
        if first_dir and not os.path.isdir(first_dir):
            return {"ok": False, "error": "missing_dir", "room": room}
        return {"ok": False, "error": "no_file", "room": room}
    data = load(path)
    return {
        "ok": True,
        "room": room,
        "w": data["w"],
        "h": data["h"],
        "cells": data["cells"],
        "objects": data.get("objects") or [],
        "pipes": data.get("pipes") or {"ports": [], "dots": []},
        "marks": data.get("marks") or [],
        "climb": data.get("climb") or [],
        "border": data["border"],
        "cameras": data["cameras"],
        "cellPx": CELL_PX,
        "path": path,
    }
