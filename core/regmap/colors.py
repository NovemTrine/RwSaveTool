"""区域配色（V1.15 №0 / №4 / №5）：从**调色板**提取「可通行色」，再派生「背景结构色」。

为什么不用 `map_<reg>.png`
--------------------------
实测全库只有 4 种像素（绿 138 万 / 黑 13.8 万 / 红 11.3 万 / 暗红 4.6 千），
SU、HI、GW 完全一样——那个绿是**透明色键**，不是"草原绿"。这条路是死的。
`map_image_*.txt` 的图标矩形同样不可引用（2026-11-21 主人定案，布局侧已清干净）。

真色源
------
`properties.txt` 的 `Palette: N` → `palettes/paletteN.png`（32×16）。
**行 0 在 PNG 底部**（Unity 口径，同 `room_render._load_palette_png`），
`row7` 是最亮光照档的材质行。

取样规则（踩过坑，别凭直觉改）
------------------------------
1. **不能**拿 row7 全 12 列或整张 96 格求均值：暗部是紫调虚空色，12 个区里 8 个会变紫
   （SU 取出来是 `#A480BB`，H289）。正确做法是 row7 里取**亮度 ≥ 40 的最亮 2 格**。
2. 得到 `(H, S)` 后统一 `HLS(H, 0.62, clamp(S, 0.18, 0.45))`：冷暖倾向保留，
   明度拉到可读区间，饱和度夹住防止品红。
3. 全黑调色板（SB/SH/SS 这类亚区域）→ row5 回退，出来是中性灰，这是**正确结果**。

背景结构色
----------
按主人给的 `corlor.py` 原样派生（HSV 空间）：`V * 0.65`、`S * 0.60`，参数不改。
这里内联实现，不再运行时读桌面文件。

子区域
------
每个子区域取"该子区域房间调色板众数"；色相与主体太近（ΔH < 25°）时按名字 hash 挪开，
明度按序交替 ±0.06，保证相邻子区域能分辨。
"""
from __future__ import annotations

import colorsys
import json
import os
import re
import struct
import zlib
from collections import Counter, OrderedDict

# 亮度阈值：低于这个值的格子是"暗部/虚空"，会把色相污染成紫
LUM_FLOOR = 40.0
# 目标明度（V1.24 №4 定案：0.62 → 0.55）。
# 0.55 是唯一让「黑岩壁 / 白管道」两侧 WCAG 对比度都 > 4 的一档：
#   L0.50 → 白 5.33:1 / 黑 3.94:1（岩壁与地面开始分不开）
#   L0.55 → 白 4.38:1 / 黑 4.79:1   ← 取这档
#   L0.62 → 白 3.33:1（白管道发飘）/ 黑 6.31:1
TARGET_L = 0.55
SAT_MAX = 0.45
# 取样行：调色板是 32 列 × 16 行的「材质 × 光照」矩阵，`row0` 在 PNG 底部。
# `row12` 才是"材质本体"那一档；旧规则用的 `row7` 在多数区是暗部/中性灰
# （实测 SL 那行最亮两格是 `#68696A`，S=0.01 → 色相纯属噪声）。
SAMPLE_ROW = 12
SAMPLE_SPAN = 12          # 只取前 12 列（与旧口径的列范围一致，避开 30/31 的白色占位）

# 背景结构（`c`）相对「可通行」（`air`）的派生比例：HSV 下 `V*ratio`、`S*sat`。
#
# 参数来历（V1.24 №1，主人给的参考色对）：
#   水 `#4C93DD`（H210.6 S0.656 V0.867）→ c `#4074AC`（H211.1 S0.628 V0.675）
#   ⇒ V ratio = 0.675/0.867 = **0.778**、S ratio = 0.628/0.656 = **0.957**，色相不动。
# 旧值 0.65 / 0.60 是把结构压成"比水暗一大截的灰块"——地图上看就是水被灰块切断。
#
# 中途试过 0.68（V1.24 №9），但那是**整体压暗**：主人要的是"水下的结构更深"，
# 而水下那一层根本不是靠 `c` 的明度决定的——水是半透明盖在 `c` 上面，
# α 越高 `c` 的权重越低（α=0.88 时只剩 12%，水下「空气 vs 结构」ΔE 只有 1.4，几乎看不见）。
# 所以 0.78 保留（干区观感按原样），**水下深度交给水的 α**（见 `svg._fx_water`：0.88 → 0.62）。
STRUCT_V = 0.78
STRUCT_S = 0.96

# 取色算法版本：改取样规则 / 夹值 / 派生参数时**必须**加一，否则 `_colors.json`
# 里的旧值会被当成命中（实测：改了子区域 hash 参数后 SVG 里还混着旧色）。
# 4 = V1.24 №4（取样 row7 最亮 → row12 按饱和度；TARGET_L 0.62 → 0.55；去掉 SAT_MIN）。
# 5 = V1.24 №1（背景结构 0.65/0.60 → 0.78/0.96）。
# 6 = V1.24 №9（背景结构 V 0.78 → 0.68）。
# 7 = V1.24 №11（背景结构**回到 0.78**，水下深度改用水的 α；旧缓存里存的是 0.68 的暗色，必须作废）。
CACHE_VERSION = 7

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "region_data", "_colors.json")

_PAL_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_PAL_MAX = 64


# --------------------------------------------------------------------------- PNG
def _png_rgb(path: str):
    """读 8 位 PNG → `(w, h, rows)`，`rows[y][x] = (r, g, b)`，**行 0 = 图顶**（自然序）。

    只支持调色板图会出现的格式（灰度 / 真彩 / 真彩+α，位深 8、非隔行）。
    用标准库自己解：`room_render` 的解码器带了整条渲染链，为了取一个 32×16 的图不值当。
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not png: %s" % path)
    pos = 8
    w = h = depth = ctype = 0
    idat = []
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if body[12] != 0:
                raise ValueError("interlaced png not supported: %s" % path)
            if depth != 8:
                raise ValueError("bit depth %d not supported: %s" % (depth, path))
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if not ch:
        raise ValueError("color type %d not supported: %s" % (ctype, path))
    raw = zlib.decompress(b"".join(idat))
    stride = w * ch
    rows = []
    prev = bytearray(stride)
    p = 0
    for _y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:                      # Sub
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:                    # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:                    # Average
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:                    # Paeth
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        prev = line
        row = []
        for x in range(w):
            i = x * ch
            if ctype == 0:
                g = line[i]
                row.append((g, g, g))
            elif ctype == 4:
                g = line[i]
                row.append((g, g, g))
            else:
                row.append((line[i], line[i + 1], line[i + 2]))
        rows.append(row)
    return w, h, rows


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# --------------------------------------------------------------------------- 调色板
def _ci(d: str, name: str):
    """大小写不敏感地取子路径（模组常见 `World/` `Palettes/` 首字母大写）。"""
    if not d:
        return None
    p = os.path.join(d, name)
    if os.path.exists(p):
        return p
    try:
        for e in os.listdir(d):
            if e.lower() == name.lower():
                return os.path.join(d, e)
    except OSError:
        pass
    return None


_ROOTS: "OrderedDict[str, list]" = OrderedDict()


def assets_roots(room_path: str) -> list:
    """房间 `.txt` → 候选资源根列表（**模组根优先，游戏 StreamingAssets 兜底**）。

    模组房间常在 `workshop/content/312520/<id>/world/<reg>-rooms/`，调色板在**同一个模组根**
    的 `Palettes/` 下；但模组往往只带改过的几个区，`properties.txt` 要回退到游戏本体。
    早期只往上推三层、拿到模组根就停，结果 `paletteN.png` 一个都找不到（全库退化成同一个色）。
    """
    key = os.path.dirname(os.path.abspath(room_path))
    hit = _ROOTS.get(key)
    if hit is not None:
        return hit
    roots = []
    d = key
    for _ in range(6):
        if _ci(d, "palettes"):
            roots.append(d)
            break
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    try:
        from .. import official_world
        for inst in official_world.find_installations():
            base = os.path.join(inst["root"], "RainWorld_Data", "StreamingAssets")
            if os.path.isdir(base) and base not in roots:
                roots.append(base)
            # DLC / 大型内容包的调色板在 `StreamingAssets/mods/<pack>/palettes/palette1xx.png`，
            # 游戏本体那份没有 37 号（MS 实测：117 间房读不到 Palette，全退成同一个色）。
            mods = os.path.join(base, "mods")
            try:
                for name in sorted(os.listdir(mods)):
                    sub = os.path.join(mods, name)
                    if os.path.isdir(sub) and _ci(sub, "palettes") and sub not in roots:
                        roots.append(sub)
            except OSError:
                pass
    except Exception:                            # noqa: BLE001
        pass
    if not roots:
        roots.append(key)
    _ROOTS[key] = roots
    while len(_ROOTS) > 512:
        _ROOTS.popitem(last=False)
    return roots


def palette_path(root: str, number: int) -> str | None:
    """`palettes/paletteN.png`；模组常用 `N+100*i` 覆盖，按同序回退。"""
    pal = _ci(root, "palettes")
    if not pal:
        return None
    for n in [number] + [number + 100 * i for i in range(1, 8)]:
        p = _ci(pal, "palette%d.png" % n)
        if p:
            return p
    return None


def _palette(number: int, root: str):
    path = palette_path(root, number)
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, int(st.st_mtime), st.st_size)
    hit = _PAL_CACHE.get(key)
    if hit is not None:
        _PAL_CACHE.move_to_end(key)
        return hit
    try:
        data = _png_rgb(path)
    except Exception:                            # noqa: BLE001 - 坏图不该拖垮取色
        return None
    _PAL_CACHE[key] = data
    while len(_PAL_CACHE) > _PAL_MAX:
        _PAL_CACHE.popitem(last=False)
    return data


def _row(pal, row: int):
    """`row` 按 Unity 口径（0 = PNG 底部）。"""
    w, h, rows = pal
    y = h - 1 - row
    if y < 0 or y >= h:
        return []
    return rows[y]


def sample_palette(number: int, root):
    """→ `(hex, H, S, src)`；拿不到就 `None`。

    **V1.24（№4）定案**：`row12`（材质本体档）前 12 列里**按饱和度降序取前 2 格**求均值。

    为什么不再用 `row7` 的"最亮 2 格"：实测 `row7` 在多数区是暗部/中性灰，最亮那两格
    几乎无彩（SL `#68696A` S=0.01、SU S=0.07），色相完全是噪声；旧代码再用
    `SAT_MIN=0.18` 强行提饱和，结果 SL/GW/SU/HI 被拉成同一个蓝灰（`#8x9xB0`）。

    回退链：够亮（`≥ LUM_FLOOR`）的格 → `row12` 全部非纯黑格 → `row5` 前 8 列
    → 中性灰（全黑调色板，属正常回退）。
    """
    pal = None
    for r in (root if isinstance(root, (list, tuple)) else [root]):
        pal = _palette(number, r)
        if pal:
            break
    if not pal:
        return None
    w = pal[0]
    row = _row(pal, SAMPLE_ROW)[:max(8, min(w, SAMPLE_SPAN))]
    src = "row%d" % SAMPLE_ROW
    picked = [c for c in row if _lum(c) >= LUM_FLOOR]
    if not picked:
        picked = [c for c in row if _lum(c) > 0]
        src = "row%d-dark" % SAMPLE_ROW
    if not picked:
        row5 = _row(pal, 5)[:8]
        picked = [c for c in row5 if _lum(c) >= LUM_FLOOR] or \
                 [c for c in row5 if _lum(c) > 0]
        src = "row5"
    if not picked:
        return ("#8C8C8C", 0.0, 0.0, "empty")
    # 按饱和度降序（同样饱和时把更亮的放前面，避免两个格都取到几乎同色）
    picked.sort(key=lambda c: (colorsys.rgb_to_hls(
        c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)[2], _lum(c)), reverse=True)
    picked = picked[:2]
    m = [sum(c[i] for c in picked) / float(len(picked)) for i in range(3)]
    h, _l, s = colorsys.rgb_to_hls(m[0] / 255.0, m[1] / 255.0, m[2] / 255.0)
    return (hls_hex(h, TARGET_L, min(SAT_MAX, s)), h * 360.0, s, src)


def hls_hex(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return "#%02X%02X%02X" % (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))


def struct_color(hex_color: str, ratio: float = STRUCT_V, sat: float = STRUCT_S) -> str:
    """主人 `corlor.py` 的 `generate_dark_color_pro`：HSV 下 `V*0.65`、`S*0.60`。"""
    s = hex_color.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, sat0, v = colorsys.rgb_to_hsv(r, g, b)
    v = max(0.0, min(1.0, v * ratio))
    sat1 = max(0.0, min(1.0, sat0 * sat))
    rr, gg, bb = colorsys.hsv_to_rgb(h, sat1, v)
    # 与 `corlor.py` 逐位一致：那边是 `int(x * 255)`（截断），四舍五入会差 1–3 个色阶
    return "#%02X%02X%02X" % (int(rr * 255), int(gg * 255), int(bb * 255))


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex_hue(hex_color: str) -> float:
    """`#RRGGBB` → 色相（0–360）。只给 `groups[].hue` 记账用。"""
    return round(colorsys.rgb_to_hls(
        *[int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)])[0] * 360.0, 1)


def norm_override(ov) -> dict:
    """把「背景取色」的三种历史形态归一成 `{子区域名: '#RRGGBB'}`。

    - `None` / `""` → `{}`
    - `"#RRGGBB"`（rev.1 只支持主体）→ `{"": "#RRGGBB"}`，老配置不用手改
    - `{子区域名: '#RRGGBB'}` → 逐项校验，非法值直接丢（手改 config 也不该炸）

    `""` 是**主体**（没有子区域的房间）那一组的键；其余键就是子区域名
    （`Looks to the Moon` / `Filtration System` 这种，与 `groups[].sub` 同源）。
    """
    if not ov:
        return {}
    if isinstance(ov, str):
        s = ov.strip()
        return {"": s.upper()} if _HEX_RE.match(s) else {}
    if not isinstance(ov, dict):
        return {}
    out = {}
    for k, v in ov.items():
        s = str(v or "").strip()
        if _HEX_RE.match(s):
            out[str(k or "")] = s.upper()
    return out


def with_override(pal: dict, override) -> dict:
    """按区自定义「背景取色」（V1.24 №4）：**主体与每个子区域都能单独指定**。

    主人定案：子区域颜色一般与主区域不同 → 不能只改主体，也不能"改主体就顺带全改"。
    `override` 是 `{子区域名: '#RRGGBB'}`（`""` = 主体），只改传进来的那几组，
    没传的保持派生色。`struct`（背景结构）跟着 `air` 重派生，不单独配
    （§2.4b：结构是空气色的暗化派生，两者必须配对）。

    不认识的子区域名**忽略不报错**：子区域集合会随模组/游戏版本变，写进配置的旧名字
    可能已经不存在了；同理，`""` 那组万一缺失就补一个头组（极端情况兜底）。

    `pal` 是 `cached()` 的返回值，**不改原对象**（它可能正躺在 `_colors.json` 缓存里）。
    """
    ov = norm_override(override)
    if not isinstance(pal, dict) or not ov:
        return pal
    out = dict(pal)
    groups = [dict(g) for g in (pal.get("groups") or [])]
    hit = set()
    for g in groups:
        sub = str(g.get("sub") or "")
        hex_color = ov.get(sub)
        if not hex_color:
            continue
        g["air"] = hex_color
        g["struct"] = struct_color(hex_color)
        g["src"] = "override"
        g["hue"] = _hex_hue(hex_color)
        hit.add(sub)
    if "" in ov and "" not in hit:
        groups.insert(0, {"sub": "", "air": ov[""], "struct": struct_color(ov[""]),
                          "palette": pal.get("palette"), "src": "override",
                          "hue": _hex_hue(ov[""])})
        hit.add("")
    if not hit:
        return pal                                # 全是已经不存在的子区域名
    out["groups"] = groups
    # 顶层 `air/struct` 永远取"主体"那一组（`groups[0]` 正常就是它，但别假设顺序）
    head = next((g for g in groups if not g.get("sub")), groups[0])
    out["air"] = head.get("air")
    out["struct"] = head.get("struct")
    out["src"] = "override"
    return out


def hue_gap(a: float, b: float) -> float:
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def hash_hue(name: str) -> float:
    h = 0
    for ch in (name or ""):
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return (h % 3600) / 10.0


# --------------------------------------------------------------------------- 区域
def _region_dir(room_path: str) -> str:
    """`.../world/cc-rooms/x.txt` → `.../world/cc`。"""
    d = os.path.dirname(os.path.abspath(room_path))
    base = os.path.basename(d)
    if base.endswith("-rooms"):
        return os.path.join(os.path.dirname(d), base[:-6])
    return os.path.dirname(d)


def _props_palette(roots, code: str = ""):
    """`world/<reg>/properties.txt` 的 `Palette:`。模组没有就回退游戏本体。"""
    seen = set()
    for root in (roots if isinstance(roots, (list, tuple)) else [roots]):
        wdir = _ci(root, "world")
        if not wdir:
            continue
        for name in (code, code.lower(), code.upper()):
            if not name:
                continue
            d = _ci(wdir, name)
            if not d or d in seen:
                continue
            seen.add(d)
            path = _ci(d, "properties.txt")
            if not path:
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        s = line.strip()
                        if s.lower().startswith("palette:"):
                            return int(float(s.split(":", 1)[1].split(",")[0].strip()))
            except (OSError, ValueError):
                continue
    return None


def room_palette(room):
    """单间房的 `Palette:`（`_settings.txt`），没有就 `None`。

    `fx.settings_path` 认变体优先，直接复用，避免两套"找 settings"的规则。
    """
    try:
        from . import fx
        sp = fx.settings_path(getattr(room, "path", "") or "")
        if not sp:
            return None
        raw = fx.read_settings(sp).get("Palette")
        if raw is None:
            return None
        return int(float(str(raw).split(",")[0]))
    except Exception:                             # noqa: BLE001
        return None


def _group(sub: str, number, root, base_hue: float | None, idx: int):
    got = sample_palette(number, root) if number is not None else None
    if got:
        air, hue, _sat, src = got
    else:
        hue = hash_hue(sub) if sub else 200.0
        air = hls_hex(hue / 360.0, TARGET_L, 0.28)
        src = "hash"
    # 子区域色相太贴主体（或彼此）就按名字挪开，否则整片看起来一个色
    if sub and base_hue is not None and hue_gap(hue, base_hue) < 25.0:
        hue = hash_hue(sub)
        air = hls_hex(hue / 360.0, TARGET_L - 0.04 + (0.05 if idx % 2 else 0.0), 0.26)
        src = "hash"
    return {"sub": sub or "", "air": air, "struct": struct_color(air),
            "palette": number, "src": src, "hue": round(hue, 1)}


def _sub_of(room, region: dict | None) -> str:
    """这间房"真正的"子区域名；等于区域名本身时视为没有子区域。

    `SU` 的 67 间房里 60 多间 `sub == "Outskirts"`（就是区域名），不过滤的话整区会
    挂到"Outskirts 子区域"那组、拿到 hash 色，把调色板提取的冷蓝白白丢掉。
    过滤规则直接用 `anno._sub_is_default`，别在两地各写一套。
    """
    sub = (getattr(room, "sub", None) or "").strip()
    if not sub:
        return ""
    try:
        from . import anno
        if anno._sub_is_default(sub, region or {}):
            return ""
    except Exception:                            # noqa: BLE001
        pass
    return sub


def for_region(code: str, rooms, region: dict | None = None) -> dict:
    """一个区的配色表（主体 + 每个子区域一组）。`rooms` 是 `Room` 列表。"""
    rooms = list(rooms or [])
    if not rooms:
        air = hls_hex(0.58, TARGET_L, 0.28)
        return {"code": code, "palette": None, "src": "none", "air": air,
                "struct": struct_color(air), "groups": [{"sub": "", "air": air,
                                                         "struct": struct_color(air)}]}

    roots = assets_roots(rooms[0].path)
    pal = _props_palette(roots, (code or "").upper())
    src = "properties"
    if pal is None:
        cnt = Counter(room_palette(r) for r in rooms)
        cnt.pop(None, None)
        if cnt:
            pal = cnt.most_common(1)[0][0]
            src = "rooms"
        else:
            # 区域 properties 里**没有 `Palette:` 行**（CS/IN/MD/WAO7/WDSR/WPGA/WSUR 等
            # 模组与 Watcher 区都这样）。游戏自己的行为就是回落到 0 号调色板，
            # 所以这里照做并在 `src` 上标 `default`——不编造颜色，也不用 hash 假装有特色。
            pal = 0
            src = "default"

    head = _group("", pal, roots, None, 0)
    groups = [head]
    subs = Counter()
    for r in rooms:
        sub = _sub_of(r, region)
        if sub:
            subs[sub] += 1

    # 子区域调色板：该子区域房间里出现最多的那个
    for i, (sub, _n) in enumerate(sorted(subs.items())):
        cnt = Counter(room_palette(r) for r in rooms if _sub_of(r, region) == sub)
        cnt.pop(None, None)
        sp = cnt.most_common(1)[0][0] if cnt else pal
        groups.append(_group(sub, sp, roots, head["hue"], i + 1))

    return {"code": code, "palette": pal, "src": src, "air": head["air"],
            "struct": head["struct"], "groups": groups}


# --------------------------------------------------------------------------- 缓存
def load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def cached(code: str, rooms, region: dict | None = None) -> dict:
    """缓存优先；房间子区域集合变了就重算（模组换版本时最常变的就是这个）。"""
    key = (code or "").upper()
    data = load_cache()
    hit = data.get(key)
    rooms = list(rooms or [])
    subs = sorted({_sub_of(r, region) for r in rooms})
    if hit and hit.get("_v") == CACHE_VERSION and hit.get("_subs") == subs and hit.get("groups"):
        return hit
    got = for_region(key, rooms, region)
    got["_v"] = CACHE_VERSION
    got["_subs"] = subs
    data[key] = got
    save_cache(data)
    return got
