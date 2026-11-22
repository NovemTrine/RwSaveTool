"""W4-fx 特效层：水 / 酸液 / 水下空气区 / 沙 / 腐化。

这个模块只做**数据**：把「这间房哪里有水、沙子从哪条线往下堆、腐化圆在哪」算出来，
交给 `svg.py` 画。所有几何一律返回**房间格坐标、y 向下、原点左上**
（渲染口径，和 `room_geo` 的 y 向上相反 —— 只在 `room_fx()` 里翻一次）。

两个数据来源（都是实测确认过的，别凭印象改）：

1. 房间 `.txt` 第 2 行：`W*H|waterLevel|waterInFront`
   —— 第二段就是水位（单位：格，从**底边**往上数）。抽样 541 间房：535 间有三段，
   6 间是竞技场房只有 `W*H`（视为无水）；没有出现越界值。

2. `<room>_settings*.txt`（变体优先，其次基础名）：
   - `Effects:` 逐项 `名字-数值- x - y`（x/y 除以 20 得到格）
     · `LethalWater` / `Toxic Brine Water` → 酸液
     · `WaterFluxMinLevel` / `WaterFluxMaxLevel` → 水位上下限（取第 4 段 y）
     · `InvertedWater` → 水从天花板往下灌
   - `PlacedObjects:` 逐项 `类型><x><y><属性~…`
     · `WaterCycleTop` / `WaterCycleBottom` → 水位上下限（y 本身就是格）
     · `AirPocket` / `WaterCutoff` → 挖掉的水域矩形（前两位属性 /20 = 宽、高）
     · `TerrainHandle` → 沙面手柄（5 个属性：左向量 x/y、右向量 x/y、未知量，均 /20）
     · `Corruption` → 腐化圆（属性即半径向量，模长 /20 = 半径）

**不追 `Template:` 模板链**：模板只提供调色板与默认效果，参考实现（zq）也只读房间自己那份；
追模板会把「模板里有水」当成「这间房有水」，反而脏。需要时给房间补 `_settings.txt` 即可。

沙子算法照 `参考项目评估` §4.2（zq `assets.py:934 sand_mask`）重写：
相邻两个手柄之间用**三次贝塞尔**连一条沙面，两端沿手柄方向延伸出房间，
再按列取最高点、往下填到房间底（沙堆语义）。
"""
from __future__ import annotations

import math
import os
import re
from collections import OrderedDict

SCALE = 20.0                     # 手柄 / 尺寸向量的单位：1 格 = 20

_NUM = r"-?\d+(?:\.\d+)?"
_OBJ_RE = re.compile(r"^([^<>]+)><(%s)><(%s)><(.*)$" % (_NUM, _NUM))
_SIZE_RE = re.compile(r"^\s*(\d+)\s*\*\s*(\d+)")

ACID_EFFECTS = ("LethalWater", "Toxic Brine Water")


# --------------------------------------------------------------------------- 读盘
_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_MAX = 1024


def _stat_key(path: str) -> tuple | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (os.path.normcase(os.path.abspath(path)), int(st.st_mtime), st.st_size)


def _text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().replace("\r", "")
    except OSError:
        return ""


def _header_water(path: str) -> float:
    """第 2 行的水位（格，自底向上）；没有第二段就是 -1（无水）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            fh.readline()                      # 房间名
            line = fh.readline()
    except OSError:
        return -1.0
    parts = line.replace("\r", "").split("|")
    if len(parts) < 2:
        return -1.0
    try:
        return float(parts[1])
    except ValueError:
        return -1.0


def _kv(path: str) -> dict:
    """`Key: value` 行 → dict。同键后者覆盖前者（与游戏读取顺序一致）。"""
    out: dict = {}
    for line in _text(path).split("\n"):
        if ": " not in line:
            continue
        k, v = line.split(": ", 1)
        out[k.strip()] = v.strip()
    return out


def _split_effect(chunk: str):
    """`WaterFluxMinLevel-0.56-244-213` → ('WaterFluxMinLevel', [0.56, 244.0, 213.0])。

    名字里可能有空格（`Toxic Brine Water`）和连字符分隔的负数（`X-1--30--40`），
    所以不能直接按 `-` 切完就 float：空串代表"这是个负号"。
    """
    toks = chunk.split("-")
    if len(toks) < 2:
        return None
    name, nums, sign = toks[0].strip(), [], ""
    for tok in toks[1:]:
        tok = tok.strip()
        if tok == "":
            sign = "-"
            continue
        try:
            nums.append(float(sign + tok))
        except ValueError:
            return None
        sign = ""
    return name, nums


def _placed(value: str) -> list:
    """`PlacedObjects:` → [(类型, x, y, [属性串…])]，x/y 已换成格。"""
    out = []
    for chunk in value.split(", "):
        chunk = chunk.strip().rstrip(",")
        if not chunk:
            continue
        m = _OBJ_RE.match(chunk)
        if not m:
            continue
        try:
            x, y = float(m.group(2)) / SCALE, float(m.group(3)) / SCALE
        except ValueError:
            continue
        out.append((m.group(1).strip(), x, y, m.group(4).split("~")))
    return out


def _effects(value: str) -> dict:
    """`Effects:` → {名字: [数值…]}（只留第一条同名项，重名极少）。"""
    out: dict = {}
    for chunk in value.split(", "):
        got = _split_effect(chunk.strip().rstrip(","))
        if not got:
            continue
        name, nums = got
        out.setdefault(name, nums)
    return out


def _settings_path(path: str, slugcat: str = "") -> str:
    """房间自己那份 `_settings*.txt`：变体优先，其次基础名。"""
    if not path:
        return ""
    folder = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    names = []
    if slugcat:
        names.append("%s_settings-%s.txt" % (stem, slugcat.lower()))
        # 别名：saint/spearmaster 等变体在文件名里用别名（`_settings-saint`）
        for alias in _SLUGCAT_ALIASES.get(slugcat.lower(), ()):
            names.append("%s_settings-%s.txt" % (stem, alias))
    names.append("%s_settings.txt" % stem)
    lowered = {}
    try:
        for entry in os.listdir(folder):
            lowered.setdefault(entry.lower(), entry)
    except OSError:
        return ""
    for want in names:
        real = lowered.get(want.lower())
        if real:
            return os.path.join(folder, real)
    return ""


_SLUGCAT_ALIASES = {
    "saint": ("saint",),
    "spearmaster": ("spear", "spearmaster"),
    "artificer": ("artificer", "arti"),
    "rivulet": ("rivulet", "riv"),
    "gourmand": ("gourmand", "gour"),
    "hunter": ("hunter", "htr"),
}


# --------------------------------------------------------------------------- 几何
def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _water(level: float, settings: dict, placed: list, w: int, h: int):
    """水位 + 挖洞 → 屏幕口径的两个矩形 + 洞。

    `full` 是满不透明区（离水面最近的整段），`band` 是涨落区间（画淡一点）。
    都返回 (y0, y1)，y 向下。
    """
    lmin = lmax = float(level)
    acid = False
    inverted = False
    eff = settings.get("Effects")
    if eff:
        # 只有房间自己那份 settings 才有 Effects；模板不追（见模块 docstring）
        parsed = _effects(eff)
        acid = any(k in parsed for k in ACID_EFFECTS)
        inverted = "InvertedWater" in parsed
        for key in ("WaterFluxMinLevel", "WaterFluxMaxLevel"):
            nums = parsed.get(key)
            if nums and len(nums) >= 3:
                val = nums[2] / SCALE
                if key.endswith("MinLevel"):
                    lmin = val
                else:
                    lmax = val
    for name, x, y, _props in placed:
        if name == "WaterCycleTop":
            lmax = y
        elif name == "WaterCycleBottom":
            lmin = y

    if lmin < 0 and lmax < 0:
        return None
    lmin = _clamp(lmin, 0, h)
    lmax = _clamp(lmax, 0, h)
    if lmin > lmax:
        lmin, lmax = lmax, lmin
    # zq 的 +1：水位 0 时其实底下还有一层水
    lmin = _clamp(lmin + 1, 0, h)
    lmax = _clamp(lmax + 1, 0, h)

    if inverted:                       # 从天花板往下灌
        full = (0.0, float(h - lmax))
        band = (float(h - lmax), float(h - lmin))
    else:                              # 常规：从水面往下
        full = (float(h - lmin), float(h))
        band = (float(h - lmax), float(h - lmin))

    holes = []
    for name, x, y, props in placed:
        if name not in ("AirPocket", "WaterCutoff"):
            continue
        try:
            pw = float(props[0]) / SCALE
            ph = float(props[1]) / SCALE
        except (IndexError, ValueError):
            continue
        x0, x1 = sorted((x, x + pw))
        if name == "WaterCutoff":
            # 切断：从房间顶到这个物体高度都不画水（水只留物体下方）
            y0, y1 = 0.0, float(h - y)
        else:
            y0, y1 = float(h - (y + ph)), float(h - y)
        x0, x1 = _clamp(x0, 0, w), _clamp(x1, 0, w)
        y0, y1 = _clamp(y0, 0, h), _clamp(y1, 0, h)
        if x1 - x0 > 1e-6 and y1 - y0 > 1e-6:
            holes.append((x0, y0, x1, y1))

    if full[1] - full[0] <= 1e-6 and (band[1] - band[0] <= 1e-6):
        return None
    return {"full": full, "band": band, "holes": holes, "acid": acid,
            "level": lmin, "inverted": inverted}


def _bezier(p1, c1, c2, p2, n):
    out = []
    for i in range(n + 1):
        t = i / float(n) if n else 0.0
        u = 1.0 - t
        out.append((u * u * u * p1[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p2[0],
                    u * u * u * p1[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p2[1]))
    return out


def _rdp(pts, eps):
    """Ramer–Douglas–Peucker：沙面从上百个采样点压到二三十个。"""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        x0, y0 = pts[i]
        x1, y1 = pts[j]
        dx, dy = x1 - x0, y1 - y0
        norm = math.hypot(dx, dy) or 1.0
        best, idx = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = abs(dy * (px - x0) - dx * (py - y0)) / norm
            if d > best:
                best, idx = d, k
        if best > eps and idx > 0:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(pts, keep) if k]


def _sand(placed: list, w: int, h: int):
    """`TerrainHandle` → 沙面折线（屏幕口径，x 递增）。

    手柄属性顺序（zq `sand_mask` 就这么拆的）：`左x 左y 右x 右y 未知`，
    单位 1/20 格。相邻两手柄之间：`p1 → p1+右(p1) → p2+左(p2) → p2` 三次贝塞尔；
    两端沿最外侧手柄的方向延伸出房间边界。
    """
    hs = [(x, y, props) for (name, x, y, props) in placed if name == "TerrainHandle"]
    if len(hs) < 2:
        return None
    hs.sort(key=lambda t: t[0])
    pts = []
    for (x1, y1, p1), (x2, y2, p2) in zip(hs, hs[1:]):
        if len(p1) < 4 or len(p2) < 4:
            continue
        try:
            c1 = (x1 + float(p1[2]) / SCALE, y1 + float(p1[3]) / SCALE)
            c2 = (x2 + float(p2[0]) / SCALE, y2 + float(p2[1]) / SCALE)
        except ValueError:
            continue
        n = max(3, min(48, int(abs(x2 - x1) * 3)))
        pts.extend(_bezier((x1, y1), c1, c2, (x2, y2), n))
    if len(pts) < 2:
        return None

    def _tail(x, y, props, left_side):
        """沿手柄方向往外拖到房间外：左侧看左向量、右侧看右向量。"""
        try:
            vx, vy = float(props[0]) / SCALE, float(props[1]) / SCALE
            if not left_side:
                vx, vy = float(props[2]) / SCALE, float(props[3]) / SCALE
        except (IndexError, ValueError):
            return
        norm = math.hypot(vx, vy)
        if norm < 1e-9:
            return
        ux, uy = vx / norm, vy / norm
        length = abs(x) if left_side else abs(w - x)
        length = min(max(length, 1.0), w * 2.0)
        steps = max(2, int(length))
        for i in range(1, steps + 1):
            d = length * i / steps
            pts.append((x + ux * d, y + uy * d))

    # 两端延伸（直接追加进 pts，后面按列取最高点时自然会剪到房间内）
    _tail(hs[0][0], hs[0][1], hs[0][2], True)
    _tail(hs[-1][0], hs[-1][1], hs[-1][2], False)

    # 翻屏幕（y 向下）并按列取最高面：沙面若折回来，只留最上面那条
    prof = {}
    for (x, y) in pts:
        if x < 0 or x > w:
            continue
        ys = h - y
        if ys < 0 or ys > h:
            continue
        k = int(round(x * 2))
        if k not in prof or ys < prof[k]:
            prof[k] = ys
    if len(prof) < 2:
        return None
    line = [(k / 2.0, prof[k]) for k in sorted(prof)]
    line = _rdp(line, 0.45)
    # 两头补到房间边缘，保证沙一直铺到墙
    if line[0][0] > 0:
        line.insert(0, (0.0, line[0][1]))
    if line[-1][0] < w:
        line.append((float(w), line[-1][1]))
    return line


def _corrupt(placed: list, w: int, h: int):
    """腐化圆。圆心落在房间外的丢掉——画出去会糊到隔壁房间上。"""
    out = []
    for name, x, y, props in placed:
        if name != "Corruption":
            continue
        try:
            r = math.hypot(float(props[0]) / SCALE, float(props[1]) / SCALE)
        except (IndexError, ValueError):
            continue
        if r <= 0.2:
            continue
        cy = h - y
        if not (-1.0 <= x <= w + 1.0 and -1.0 <= cy <= h + 1.0):
            continue
        out.append((x, cy, r))
    return out


# --------------------------------------------------------------------------- 对外
# W4 标注层复用同一份 settings 解析（回响 / 传送点 / 珍珠都在 PlacedObjects 里）：
# 这三个是公开入口，带下划线的老名字保留，回归脚本与探针不用改。
settings_path = _settings_path
read_settings = _kv
placed_objects = _placed


def room_fx(room, slugcat: str = "") -> dict | None:
    """一间房的全部特效；什么都没有就返回 None。"""
    return room_fx_geom(getattr(room, "path", "") or "",
                        int(getattr(room, "w", 0) or 0),
                        int(getattr(room, "h", 0) or 0), slugcat)


def room_fx_geom(path: str, w: int, h: int, slugcat: str = "") -> dict | None:
    """同上，但直接给路径与尺寸（房间卡那条线只有一个 `path`，没有 `Room` 对象）。"""
    w, h = int(w or 0), int(h or 0)
    if not path or w <= 0 or h <= 0:
        return None
    key = (path, w, h, (slugcat or "").lower())
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return hit or None

    settings_path = _settings_path(path, slugcat)
    settings = _kv(settings_path) if settings_path else {}
    placed = _placed(settings.get("PlacedObjects", "")) if settings else []
    water = _water(_header_water(path), settings, placed, w, h)
    sand = _sand(placed, w, h)
    corrupt = _corrupt(placed, w, h)
    fx = None
    if water or sand or corrupt:
        fx = {"w": w, "h": h, "water": water, "sand": sand, "corrupt": corrupt,
              "settings": os.path.basename(settings_path) if settings_path else ""}

    _CACHE[key] = fx or {}
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return fx


def attach(nodes, slugcat: str = "", opts: dict | None = None) -> int:
    """给布局节点挂 `fx`；返回挂上的房间数。`opts["fx"]=False` 可整层关掉。"""
    if opts is not None and not opts.get("fx", True):
        return 0
    got = 0
    for node in nodes or []:
        room = node.get("room")
        if room is None:
            continue
        try:
            fx = room_fx(room, slugcat)
        except Exception:                       # noqa: BLE001 - 特效不该拖垮布局
            fx = None
        if fx:
            node["fx"] = fx
            got += 1
    return got
