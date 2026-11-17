"""房间「实机渲染」内核（V1.2 / M1）。

把游戏为每个摄像机烘焙的 `_N.png` 地形纹理，按 `LevelColor.shader` 的算法还原成
一张「接近实机观感」的房间图。算法移植自 RainworldRoomRender 的 `render_room.py`，
但**管线按本工具的数据模型重写**，不是整份照抄：

  * 房间文件用 `room_geo.find_file` 定位 —— 与房间卡矢量图**同一份文件**，
    避免「格子和颜色来自两份可能不一致的解析结果」；
  * 素材（palette / noise / effectcolors / 模板）按区域层的来源目录推导查找路径，
    沿用导入时记录的 `roomsDirs` / `worldDirs`，不用上游那套 mergedmods→mods→consolefiles 顺序；
  * 多个摄像机**拼接成一整间房**（上游是每个摄像机单独出一张图）；
  * 不移植 meta.json、CLI 参数、gamma / debug 调试图。

刻意保持的约束：
  * **零第三方依赖**：PNG 解码/编码用 `zlib` 手写，着色是纯 Python 逐像素移植。
    速度见 `bench()`；numpy 加速留到 M3，届时只替换 `_shade()` 内部，接口不变。
  * **只读**：不改游戏目录、不复制素材，输出只有 PNG 字节。
  * 天空固定填 `pal[7,0]`（`sky="fill"`）；`sky="none"` 只供调试与将来做背景合成。

关键公式出处（与 `render_room.py` 逐行对齐）：
  R = 90×受光 + 30×(调色板行-1) + (深度+1)
  G = 16×非地板暗部 + 8×彩色道具 + 特效索引(0..7) + 污渍(0..3)
  B = 彩色道具的贴图条横坐标（decal_x = 255 - B）
"""

from __future__ import annotations

import math
import os
import re
import struct
import threading
import time
import zlib
from collections import OrderedDict

from . import room_cache, room_geo

try:                      # 可选加速：有 Pillow 就让它解码，没有也不影响功能
    from PIL import Image as _pil
except Exception:         # noqa: BLE001
    _pil = None

TAU = math.pi * 2.0
PX_PER_TILE = 20          # 游戏内一格 20 像素，纹理也是这个比例
SRC_W, SRC_H = 1400, 800  # 游戏烘焙的单个摄像机纹理尺寸（实测恒为此值）

_SKY_WHITE = 255          # 天空像素是纯白 (255,255,255)

# 角色正式名 → 设置文件后缀候选（与界面 VARIANT_OF 的口径一致）
SLUGCAT_ALIASES = {
    "hunter": ("red", "hunter"),
    "spearmaster": ("spear", "spearmaster"),
    "artificer": ("artificer",),
    "rivulet": ("rivulet",),
    "gourmand": ("gourmand",),
    "saint": ("saint",),
    "monk": ("yellow", "monk"),
    "survivor": ("white", "survivor"),
}


class RenderError(Exception):
    """渲染失败。`code` 供上层做降级判断，`detail` 可直接展示。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# 素材定位
# ---------------------------------------------------------------------------
def _root_of(path: str) -> str | None:
    """从一个 world 子目录反推素材根。

    `.../StreamingAssets/world/cc-rooms`        → `.../StreamingAssets`
    `.../mods/msc/modify/world/cc-rooms`        → `.../mods/msc`
    `.../mods/msc/world/cc`                     → `.../mods/msc`

    模组的 `modify/world/` 是补丁层，素材根在 `modify` 的上一层。
    """
    if not path:
        return None
    parts = os.path.abspath(path).replace("\\", "/").rstrip("/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() == "world":
            if i > 0 and parts[i - 1].lower() == "modify":
                i -= 1
            if i <= 0:
                return None
            root = "/".join(parts[:i])
            return root if root else "/"
    return None


def asset_roots(region: dict, layer_id: str | None = None) -> list[str]:
    """按优先级列出素材根目录（先指定层，再其余层；层内 override 优先）。

    与 `room_geo._layer_dirs` 保持同样的层排序，保证「房间文件在哪、素材就在哪」。
    """
    layers = region.get("layers") or []
    ordered: list[dict] = []
    if layer_id:
        ordered.extend([l for l in layers if l.get("id") == layer_id])
    ordered.extend([l for l in layers if l.get("id") != layer_id])

    roots: list[str] = []
    seen: set[str] = set()

    def _key(raw: str) -> str:
        return os.path.normcase(os.path.abspath(raw))

    def push(p: str | None) -> None:
        r = _root_of(p) if p else None
        if not r:
            return
        k = _key(r)
        if k not in seen:
            seen.add(k)
            roots.append(r)

    for layer in ordered:
        src = layer.get("source") or {}
        for d in src.get("roomsDirs") or []:
            push(d)
        for p in (src.get("overridePaths") or []):
            push(p)
        push(src.get("path"))
        for d in src.get("worldDirs") or []:
            push(d)

    # 兜底：模组区域常常只有自己那一层（实测 CS 只剩一个 workshop 层），
    # 但 palette / 设置模板还在游戏本体里。补上「模组的 StreamingAssets 祖先」与游戏安装目录。
    def add(raw: str | None) -> None:
        if not raw:
            return
        k = _key(raw)
        if k not in seen:
            seen.add(k)
            roots.append(os.path.normpath(raw))

    for root in list(roots):
        low = root.replace("\\", "/").lower()
        idx = low.find("/mods/")
        if idx > 0:
            add(root[:idx])
    for base in _game_streaming_roots():
        add(base)
    return roots


_base_cache = {"at": 0.0, "list": []}


def _game_streaming_roots() -> list[str]:
    """游戏本体的 StreamingAssets 目录（60 秒缓存，探测 Steam 库有 IO 开销）。"""
    now = time.time()
    if now - _base_cache["at"] < 60.0:
        return list(_base_cache["list"])
    out: list[str] = []
    try:
        from . import official_world, paths as _paths
        game = (_paths.load_config() or {}).get("gamePath") or ""
        if game:
            cand = os.path.join(game, "RainWorld_Data", "StreamingAssets")
            if os.path.isdir(cand):
                out.append(cand)
        if not out:
            for item in official_world.find_installations():
                root = item.get("root") or ""
                cand = os.path.join(root, "RainWorld_Data", "StreamingAssets")
                if os.path.isdir(cand) and cand not in out:
                    out.append(cand)
    except Exception:      # noqa: BLE001 - 探测失败不该让渲染失败
        pass
    _base_cache["at"] = now
    _base_cache["list"] = list(out)
    return out


def _find_ci(directory: str, name: str) -> str | None:
    """大小写不敏感的单层查找（Windows 上无所谓，模组目录大小写很乱）。"""
    direct = os.path.join(directory, name)
    if os.path.isfile(direct):
        return direct
    try:
        for entry in os.listdir(directory):
            if entry.lower() == name.lower():
                p = os.path.join(directory, entry)
                if os.path.isfile(p):
                    return p
    except OSError:
        pass
    return None


def _find_asset(roots: list[str], rel: str) -> str | None:
    """在若干素材根里找 `rel`（相对 StreamingAssets 的路径）。"""
    rel = rel.replace("\\", "/")
    for root in roots:
        p = os.path.join(root, *rel.split("/"))
        if os.path.isfile(p):
            return p
        # 合并模组目录：游戏把 mods 的补丁层合到这里，素材可能只在里面
        p = os.path.join(root, "mergedmods", *rel.split("/"))
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------------------
# 房间设置（_settings.txt → 模板链）
# ---------------------------------------------------------------------------
def _read_kv(path: str) -> dict[str, str]:
    kv: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return kv
    for line in text.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        kv[key.strip()] = value.strip()
    return kv


def _parse_effects(value: str) -> dict[str, list[float]]:
    """`Hue-30,Darkness-0.4` → {Hue:[30.0], Darkness:[0.4]}。"""
    out: dict[str, list[float]] = {}
    for part in (value or "").split(","):
        bits = part.strip().split("-")
        if len(bits) < 2:
            continue
        try:
            out[bits[0]] = [float(b) for b in bits[1:]]
        except ValueError:
            continue
    return out


def _settings_candidates(room_path: str, slugcat: str | None, roots: list[str] | None = None,
                         region: str | None = None) -> list[str]:
    """`<room>_settings[-变体].txt` 的候选，按游戏优先级，返回所有已存在的。

    查找范围不能只看房间所在目录：变体设置常常在**另一个层**里
    （基础游戏的房间 + 模组提供的 `_settings-saint.txt`，实测 `cc_a02` 就是）。
    所以先看房间自己的目录，再按 `world/<region>-rooms/` 的相对路径在各素材根里找。
    """
    folder = os.path.dirname(room_path)
    stem = os.path.splitext(os.path.basename(room_path))[0]
    names: list[str] = []
    if slugcat:
        for suffix in SLUGCAT_ALIASES.get(slugcat.lower(), (slugcat.lower(),)):
            names.append("%s_settings-%s.txt" % (stem, suffix))
    names.append("%s_settings.txt" % stem)

    out: list[str] = []
    for n in names:
        p = _find_ci(folder, n)
        if p and p not in out:
            out.append(p)
            continue
        if roots and region:
            p = _find_asset(roots, "world/%s-rooms/%s" % (region, n))
            if p and p not in out:
                out.append(p)
    return out


def _template_path(roots: list[str], region: str, name: str) -> str | None:
    """`Template: Outside` → `world/<region>/<region>_settingstemplate_outside.txt`。"""
    short = name.strip().lower()
    prefix = "%s_settingstemplate_" % region
    if short.startswith(prefix):
        short = short[len(prefix):]
    elif "_settingstemplate_" in short:
        short = short.split("_settingstemplate_", 1)[1]
    fname = "%s_settingstemplate_%s.txt" % (region, short)
    cand = _find_asset(roots, "world/%s/%s" % (region, fname))
    if cand:
        return cand
    # 区域目录大小写与 region 名不一致时（模组常见）：在 world/ 下逐个目录找
    for root in roots:
        world = os.path.join(root, "world")
        try:
            entries = os.listdir(world)
        except OSError:
            continue
        for entry in entries:
            if entry.lower() != region:
                continue
            hit = _find_ci(os.path.join(world, entry), fname)
            if hit:
                return hit
    return None


def _region_props(roots: list[str], region: str, slugcat: str | None) -> dict[str, str]:
    """`properties[-变体].txt`；变体文件不存在就用通用的。"""
    if slugcat:
        p = _find_asset(roots, "world/%s/properties-%s.txt" % (region, slugcat.lower()))
        if p:
            return _read_kv(p)
    p = _find_asset(roots, "world/%s/properties.txt" % region)
    return _read_kv(p) if p else {}


class Settings:
    """合并后的房间设置（模板链：子层覆盖父层）。"""

    def __init__(self, roots: list[str], region: str, slugcat: str | None,
                 room_path: str) -> None:
        self.roots = roots
        self.region = region
        self.layers: list[dict[str, str]] = []
        self.path: str | None = None

        props = _region_props(roots, region, slugcat)
        templates = [t.strip() for t in (props.get("Room Setting Templates") or "").split(",") if t.strip()]
        default_tpl = templates[0] if templates else None

        cands = _settings_candidates(room_path, slugcat, roots, region)
        cur = cands[0] if cands else None
        self.path = cur
        # 关键降级：基础游戏大量房间没有 _settings.txt，游戏会用区域默认模板。
        # 上游 render_room.py 在这里直接 SystemExit，照抄会让一半房间点开就报错。
        if cur is None and default_tpl:
            cur = _template_path(roots, region, default_tpl)
        seen: set[str] = set()
        first = True
        while cur and os.path.isfile(cur) and cur not in seen:
            seen.add(cur)
            kv = _read_kv(cur)
            self.layers.append(kv)
            tpl = kv.get("Template")
            if tpl is not None:
                if tpl.strip().upper() == "NONE":
                    break
                cur = _template_path(roots, region, tpl)
            elif first and default_tpl:
                cur = _template_path(roots, region, default_tpl)
            else:
                break
            first = False

        merged: dict[str, str] = {}
        for layer in reversed(self.layers):
            merged.update(layer)
        self.kv = merged

        self.palette = self._int("Palette", 0)
        self.fade_palette = -1
        self.fades: list[float] = []
        fp = merged.get("FadePalette")
        if fp:
            bits = [b.strip() for b in fp.split(",")]
            try:
                self.fade_palette = int(float(bits[0]))
                self.fades = [float(b) for b in bits[1:] if b]
            except ValueError:
                self.fade_palette = -1
                self.fades = []
        self.effect_color_a = self._int("EffectColorA", 0)
        self.effect_color_b = self._int("EffectColorB", 0)
        self.grime = self._float("Grime", 0.5)
        self.clouds = self._float("Clouds", 0.0)
        self.wave_amplitude = self._float("WaveAmplitude", 0.0)
        self.wave_length = self._float("WaveLength", 0.5)
        self.wave_speed = self._float("WaveSpeed", 0.75)
        self.effects = _parse_effects(merged.get("Effects", ""))

    def _int(self, key: str, default: int) -> int:
        try:
            return int(float(self.kv.get(key) or default))
        except (TypeError, ValueError):
            return default

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.kv.get(key) or default)
        except (TypeError, ValueError):
            return default

    def effect(self, name: str) -> float:
        vals = self.effects.get(name)
        return vals[0] if vals else 0.0

    def has_effect(self, name: str) -> bool:
        return name in self.effects

    def fade_for_camera(self, index: int) -> float:
        if not self.fades:
            return 0.0
        return self.fades[index] if index < len(self.fades) else self.fades[-1]


# ---------------------------------------------------------------------------
# PNG 编解码（标准库，8bit 非隔行；RGB / RGBA / 调色板）
# ---------------------------------------------------------------------------
def decode_png(path: str) -> tuple[int, int, int, bytes]:
    """读文件并解码 → (w, h, 通道数, 像素字节)。

    装上 Pillow 就走它的 C 实现（1400×800 从 ~680 ms 降到 ~20 ms，因为纯 Python 反
    Paeth 是最慢的一环）；没有就退回自带的解码器。**两条路结果一致**，Pillow 那条
    即使 API 对不上也只会落回慢路径，不会把渲染弄坏。
    """
    if _pil is not None:
        try:
            with _pil.open(path) as img:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                w, h = img.size
                mode = "RGBA" if img.mode == "RGBA" else "RGB"
                return w, h, 4 if mode == "RGBA" else 3, img.tobytes()
        except Exception:      # noqa: BLE001 - 任何异常都退回纯 Python 解码
            pass
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise RenderError("io", "读不到 %s：%s" % (os.path.basename(path), exc)) from exc
    return decode_png_bytes(data, name=os.path.basename(path))


_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _unfilter(raw: bytes, pos: int, stride: int, rows: int, bpp: int) -> tuple[bytearray, int]:
    """反 PNG 行过滤器（0-4），返回拼接后的像素字节与新的读取位置。"""
    out = bytearray(stride * rows)
    prev = bytes(stride)
    for y in range(rows):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:                      # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:                      # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:                      # Average
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:                      # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise RenderError("bad_png", "未知的行过滤器 %s（%s）" % (ftype, name))
        out[y * stride:(y + 1) * stride] = line
        prev = bytes(line)
    return out, pos


def decode_png_bytes(data: bytes, name: str = "png") -> tuple[int, int, int, bytes]:
    """解码内存里的 PNG 字节。

    支持 8/16bit、灰度/灰度+alpha/RGB/RGBA/索引色、非隔行与 Adam7 隔行。
    模组素材什么格式都有——实测 `palette467.png` 就是隔行 PNG，不解就直接报错。
    输出统一压成 8bit：索引色展开成 RGB，灰度+alpha 丢掉 alpha，16bit 取高字节。
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RenderError("bad_png", "不是 PNG：%s" % name)

    pos = 8
    idat = bytearray()
    w = h = bit = ctype = interlace = None
    plte = b""
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            w, h, bit, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"PLTE":
            plte = body
        elif tag == b"IEND":
            break
        pos += 12 + length

    if not w or not h or ctype is None or bit is None:
        raise RenderError("bad_png", "PNG 头缺失：%s" % name)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise RenderError("unsupported_png", "不支持的色彩类型 %d：%s" % (ctype, name))

    raw = zlib.decompress(bytes(idat))
    bits_per_pixel = channels * bit
    bpp = max(1, (bits_per_pixel + 7) // 8)
    pix = bytearray(w * h * channels)          # 8bit 中间缓冲
    passes = _ADAM7 if interlace == 1 else ((0, 0, 1, 1),)
    pos = 0

    for x0, y0, dx, dy in passes:
        pw = (w - x0 + dx - 1) // dx
        ph = (h - y0 + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        stride = (pw * bits_per_pixel + 7) // 8
        lines, pos = _unfilter(raw, pos, stride, ph, bpp)

        for j in range(ph):
            base = j * stride
            row = lines[base:base + stride]
            if bit == 8:
                samples = row
                step = channels
            elif bit == 16:
                samples = row[0::2]           # 取高字节（低字节丢弃）
                step = channels
            else:                             # 1/2/4bit 索引色
                per_byte = 8 // bit
                mask = (1 << bit) - 1
                unpacked = bytearray(pw)
                for i in range(pw):
                    byte = row[i // per_byte]
                    shift = 8 - bit * ((i % per_byte) + 1)
                    unpacked[i] = (byte >> shift) & mask
                samples = unpacked
                step = 1
            dst_y = y0 + j * dy
            for i in range(pw):
                src = i * step
                dst = (dst_y * w + (x0 + i * dx)) * channels
                if channels == 1:
                    pix[dst] = samples[src]
                else:
                    pix[dst:dst + channels] = samples[src:src + channels]

    if ctype == 3:
        if not plte:
            raise RenderError("bad_png", "索引色 PNG 缺少调色板：%s" % name)
        rgb = bytearray(w * h * 3)
        max_idx = len(plte) // 3
        for i in range(w * h):
            k = pix[i]
            if k >= max_idx:
                k = max_idx - 1
            rgb[i * 3:i * 3 + 3] = plte[k * 3:k * 3 + 3]
        return w, h, 3, bytes(rgb)
    if ctype == 4:      # 灰度 + alpha → 只留灰度，调用方不需要 alpha
        return w, h, 1, bytes(pix[0::2])
    return w, h, channels, bytes(pix)


def encode_png(w: int, h: int, rgba: bytes | bytearray) -> bytes:
    """RGBA 字节 → PNG（行过滤器全 0，交给 zlib）。"""
    stride = w * 4
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        rows += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + chunk(b"IEND", b""))


# ---------------------------------------------------------------------------
# 调色板
# ---------------------------------------------------------------------------
_pal_lock = threading.Lock()
_pal_cache: "OrderedDict[tuple, list]" = OrderedDict()
_noise_cache: dict[tuple, tuple] = {}


def _load_palette_png(roots: list[str], number: int) -> tuple[int, int, list[list[tuple[float, float, float]]]]:
    """读 paletteN.png → 行优先 RGB 浮点，**行 0 = PNG 底部**（Unity 的 GetPixel(y=0)）。"""
    path = None
    for candidate in [number] + [number + 100 * i for i in range(1, 8)]:
        path = _find_asset(roots, "palettes/palette%d.png" % candidate)
        if path:
            break
    if not path:
        raise RenderError("no_palette", "找不到 palettes/palette%d.png" % number)
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (path, 0, 0)
    with _pal_lock:
        hit = _pal_cache.get(key)
        if hit is not None:
            _pal_cache.move_to_end(key)
            return hit
    w, h, ch, buf = decode_png(path)
    rows = []
    for y in range(h - 1, -1, -1):
        row = []
        base = y * w * ch
        for x in range(w):
            i = base + x * ch
            row.append((buf[i] / 255.0, buf[i + 1] / 255.0, buf[i + 2] / 255.0))
        rows.append(row)
    data = (w, h, rows)
    with _pal_lock:
        _pal_cache[key] = data
        _pal_cache.move_to_end(key)
        while len(_pal_cache) > 24:
            _pal_cache.popitem(last=False)
    return data


def _load_effect_colors(roots: list[str]) -> list[list[tuple[float, float, float]]] | None:
    path = _find_asset(roots, "palettes/effectcolors.png")
    if not path:
        return None
    w, h, ch, buf = decode_png(path)
    rows = []
    for y in range(h - 1, -1, -1):
        row = []
        base = y * w * ch
        for x in range(w):
            i = base + x * ch
            row.append((buf[i] / 255.0, buf[i + 1] / 255.0, buf[i + 2] / 255.0))
        rows.append(row)
    return rows


def _apply_effect_colors(pal: list, ec: list | None, color_a: int, color_b: int) -> list:
    """`RoomCamera.ApplyEffectColorsToPaletteTexture` 的 30/31 两列。"""
    if not ec:
        return pal
    out = [list(row) for row in pal]
    h = len(ec)
    w = len(ec[0])
    jobs = ((4, 6, 0, 2, color_a), (12, 14, 2, 4, color_a),
            (2, 4, 0, 2, color_b), (10, 12, 2, 4, color_b))
    for dst0, dst1, src0, src1, color in jobs:
        if color is None or color < 0:
            continue
        x = color * 2
        if x + 2 > w or src1 > h:
            continue
        for step, row in enumerate(range(dst0, dst1)):
            if row >= len(out) or src0 + step >= h:
                continue
            # 注意：dst 是 32×16 调色板的行，src 是 effectcolors.png（只有 4 行）的行
            out[row][30:32] = list(ec[src0 + step][x:x + 2])
    return out


def _effective_palette(a: list, b: list, blend: float, dark: float) -> list[list[tuple[float, float, float]]]:
    """`RoomCamera.ApplyFade()` 的 32×8 结果。dark=0 取每张 32×16 的上半，dark=1 取下半。"""
    out = []
    for r in range(8):
        row = []
        lo_a, hi_a = a[8 + r], a[r]
        lo_b, hi_b = b[8 + r], b[r]
        for c in range(32):
            ca = tuple(lo_a[c][i] * (1.0 - dark) + hi_a[c][i] * dark for i in range(3))
            cb = tuple(lo_b[c][i] * (1.0 - dark) + hi_b[c][i] * dark for i in range(3))
            row.append(tuple(ca[i] * (1.0 - blend) + cb[i] * blend for i in range(3)))
        out.append(row)
    return out


def _load_noise(roots: list[str]) -> tuple[int, int, list[float]]:
    """64×64 噪声图 → 灰度浮点，行 0 = PNG 顶部（采样函数按 v=0 对应行 0 处理）。"""
    path = _find_asset(roots, "palettes/noise.png")
    if not path:
        return 1, 1, [0.5]
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (path, 0, 0)
    hit = _noise_cache.get(key)
    if hit is not None:
        return hit
    w, h, ch, buf = decode_png(path)
    vals = [buf[i * ch] / 255.0 for i in range(w * h)]
    data = (w, h, vals)
    _noise_cache.clear()
    _noise_cache[key] = data
    return data


def _bilerp(noise: tuple[int, int, list[float]], u: float, v: float) -> float:
    """Unity 风格 repeat + 双线性采样（行 0 对应 v=0）。"""
    w, h, vals = noise
    x = u * w - 0.5
    y = v * h - 0.5
    x0 = math.floor(x)
    y0 = math.floor(y)
    fx = x - x0
    fy = y - y0
    x0 %= w
    y0 %= h
    x1 = (x0 + 1) % w
    y1 = (y0 + 1) % h
    c00 = vals[y0 * w + x0]
    c10 = vals[y0 * w + x1]
    c01 = vals[y1 * w + x0]
    c11 = vals[y1 * w + x1]
    return (c00 * (1 - fx) + c10 * fx) * (1 - fy) + (c01 * (1 - fx) + c11 * fx) * fy


# ---------------------------------------------------------------------------
# 房间文件
# ---------------------------------------------------------------------------
def _is_xy(token: str) -> bool:
    bits = token.split(",")
    if len(bits) != 2:
        return False
    return all(b.strip().lstrip("-").lstrip("+").replace(".", "", 1).isdigit() for b in bits)


def _parse_cameras(lines: list[str]) -> list[tuple[float, float]]:
    """摄像机偏移行（与 `room_geo._camera_count` 同一套判定，保证数量一致）。"""
    for line in lines[1:8]:
        s = line.strip()
        if not s or ("|" in s and "*" in s):
            continue
        parts = s.split("|")
        if parts and all(_is_xy(p) for p in parts):
            out = []
            for p in parts:
                x, y = p.split(",")
                out.append((float(x), float(y)))
            return out
    return [(0.0, 0.0)]


def _room_header(lines: list[str]) -> tuple[float, int]:
    """第 2 行 `W*H|水位|前后` → (水位, 是否在水前)。"""
    if len(lines) < 2:
        raise RenderError("unparsable", "房间文件行数不足")
    head = lines[1].split("|")
    water = -1.0
    front = 0
    if len(head) > 1:
        try:
            water = float(head[1])
        except ValueError:
            water = -1.0
    if len(head) > 2:
        try:
            front = int(float(head[2]))
        except ValueError:
            front = 0
    return water, front


def _region_name(room_path: str) -> str:
    """`.../world/cc-rooms/cc_s05.txt` → `cc`；门房间按 `gate_xx_yy` 取一侧。"""
    parent = os.path.basename(os.path.dirname(room_path)).lower()
    stem = os.path.splitext(os.path.basename(room_path))[0].lower()
    if parent.endswith("-rooms"):
        return parent[:-6]
    if parent == "gates":
        m = re.match(r"gate_([a-z0-9]{2})_", stem)
        if m:
            return m.group(1)
    return stem.split("_")[0]


# ---------------------------------------------------------------------------
# 纹理拼接
# ---------------------------------------------------------------------------
_tex_lock = threading.Lock()
_tex_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_TEX_CACHE_MAX = 6          # 单张 1400×800×3 ≈ 3.4 MB，6 张 ≈ 20 MB


def _load_texture(path: str) -> tuple[int, int, bytes]:
    try:
        st = os.stat(path)
        key = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (path, 0, 0)
    with _tex_lock:
        hit = _tex_cache.get(key)
        if hit is not None:
            _tex_cache.move_to_end(key)
            return hit
    w, h, ch, buf = decode_png(path)
    if ch == 1:                                   # 灰度
        rgb = bytearray(w * h * 3)
        rgb[0::3] = buf
        rgb[1::3] = buf
        rgb[2::3] = buf
        buf = bytes(rgb)
    elif ch == 4:                                 # 带 alpha：地形层用不到 alpha，直接丢
        rgb = bytearray(w * h * 3)
        rgb[0::3] = buf[0::4]
        rgb[1::3] = buf[1::4]
        rgb[2::3] = buf[2::4]
        buf = bytes(rgb)
    elif ch != 3:
        raise RenderError("bad_texture", "地形纹理通道数异常：%s" % ch)
    data = (w, h, buf)
    with _tex_lock:
        _tex_cache[key] = data
        _tex_cache.move_to_end(key)
        while len(_tex_cache) > _TEX_CACHE_MAX:
            _tex_cache.popitem(last=False)
    return data


class _Canvas:
    """整间房的像素画布（世界像素坐标，原点在左上，y 向下）。"""

    __slots__ = ("w", "h", "rgb", "covered", "cam_of", "cams", "decals")

    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self.rgb = bytearray(w * h * 3)
        self.covered = bytearray(w * h)
        self.cam_of = bytearray(w * h)      # 0 = 无，i+1 = 第 i 个摄像机
        self.cams: list[tuple[int, int, int, int]] = []   # (left, top, tex_w, tex_h)
        # 每个摄像机的「彩色道具贴图条」：shader 从 _MainTex 的 v≈1（PNG 第 0 行）取色，
        # x = 255-B。多摄像机房间各自的条可能不同，所以按摄像机分开存。
        self.decals: list[bytes] = []


def _stitch(room_path: str, geo: dict, cameras: list[tuple[float, float]],
            abort=None, rect: tuple[int, int, int, int] | None = None
            ) -> tuple[_Canvas, list[int]]:
    """把每个摄像机的 1400×800 贴到房间画布上（后贴覆盖先贴，重叠约 410 px）。

    返回 (画布, 缺纹理的摄像机序号)。

    `rect` 给出「画布上的一个矩形（px）」，只有与它**相交**的摄像机才解码贴图——
    解码是整条管线里最贵的一步（一间 6 摄像机的大房要 3 s，单张约 0.5 s）。
    视口裁剪（B 档）就靠它把放大后的重渲压到「1–2 张图」的量。
    画布本身仍然是整间房的尺寸：`_fill_void` / `_water` 的坐标换算全靠它，
    只裁输出像素，不裁画布，省掉一大票边界错误。

    被跳过的摄像机在 `cams` 里记下**标称矩形**（纹理尺寸按 1400×800 算），
    这样 `_fill_void` 用矩形判「这一格有没有摄像机」时不会把它们的区域当成空洞。
    """
    cw = geo["w"] * PX_PER_TILE
    chh = geo["h"] * PX_PER_TILE
    canvas = _Canvas(cw, chh)
    stem = os.path.splitext(os.path.basename(room_path))[0]
    folder = os.path.dirname(room_path)
    missing: list[int] = []

    for index, (cam_x, cam_y) in enumerate(cameras):
        if abort is not None and abort():
            raise RenderError("aborted", "渲染被更新的请求打断")
        tex_path = os.path.join(folder, "%s_%d.png" % (stem, index + 1))
        if not os.path.isfile(tex_path):
            missing.append(index + 1)
            canvas.cams.append((0, 0, 0, 0))      # 占位，保持 cams 下标 == 摄像机下标
            canvas.decals.append(b"")
            continue
        # Room.cs:5384 —— 摄像机世界 y 是把文件里的 y 换算到"画布底部对齐"后的值
        world_y = -(SRC_H - chh + cam_y)
        left = int(round(cam_x))
        top = int(round(chh - (world_y + SRC_H)))     # y 轴翻转：世界 y 朝上、行号朝下
        if rect is not None:
            rx0, ry0, rx1, ry1 = rect
            if (left + SRC_W <= rx0 or left >= rx1
                    or top + SRC_H <= ry0 or top >= ry1):
                canvas.cams.append((left, top, SRC_W, SRC_H))   # 标称矩形，没解码
                canvas.decals.append(b"")
                continue
        tw, th, buf = _load_texture(tex_path)

        x0 = max(0, -left)
        x1 = min(tw, cw - left)
        y0 = max(0, -top)
        y1 = min(th, chh - top)
        canvas.cams.append((left, top, tw, th))
        canvas.decals.append(buf[0:min(tw, 256) * 3])
        if x1 <= x0 or y1 <= y0:
            continue
        span = (x1 - x0) * 3
        for y in range(y0, y1):
            srow = (y * tw + x0) * 3
            drow = (top + y) * cw + left + x0
            canvas.rgb[drow * 3:(drow + x1 - x0) * 3] = buf[srow:srow + span]
            canvas.covered[drow:drow + x1 - x0] = b"\x01" * (x1 - x0)
            canvas.cam_of[drow:drow + x1 - x0] = bytes((index + 1,)) * (x1 - x0)

    return canvas, missing


# ---------------------------------------------------------------------------
# LevelColor 移植
# ---------------------------------------------------------------------------
class _Params:
    __slots__ = ("light", "rain", "clouds_speed", "darkness", "contrast", "saturation",
                 "hue", "brightness", "grime", "swarm_room", "wet_terrain",
                 "water_enabled", "water_time", "water_alpha", "water_overlay",
                 "fog_amount", "fog_col")

    def __init__(self) -> None:
        self.light = -1.0
        self.rain = 0.0
        self.clouds_speed = 1.0
        self.darkness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.hue = 0.0
        self.brightness = 0.0
        self.grime = 0.0
        self.swarm_room = 0.0
        self.wet_terrain = 1.0
        self.water_enabled = True
        self.water_time = 0.0
        self.water_alpha = 0.6
        # 已废弃：水体现在**一律**按半透明笼罩画（`WaterFront` 不再影响结果），
        # 这个开关保留只是为了不让旧的参数字典报未知键。见 `_water()` 里的注释。
        self.water_overlay = False
        self.fog_amount = 0.0
        self.fog_col = (0.0, 0.0, 0.0)

    def plain_color(self) -> bool:
        return (self.darkness == 1.0 and self.contrast == 1.0
                and self.saturation == 1.0 and self.hue == 0.0 and self.brightness == 0.0)


def _shadow_constant(params: _Params) -> float | None:
    """静止画面（rain=0）下 shadow 是一个常数，能省掉逐像素的噪声采样。

    推导：s = 0.5 + sin(...)*0.5 ∈ [0,1]，shadow = clamp((s-0.5)*6 + 0.5 - light*4, 0, 1)。
      light = +1 → (s-0.5)*6 ∈ [-3,3] → 上界恒 ≤ -0.5 → clamp 后恒为 0
      light = -1 → 下界恒 ≥ 1.5 → clamp 后恒为 1
    light 取其它值时退回逐像素计算。
    """
    if abs(params.rain) > 1e-9:
        return None
    if params.light == 1.0:
        return 0.0
    if params.light == -1.0:
        return 1.0
    return None


def _shade(canvas: _Canvas, pals: list, noise: tuple, params: _Params,
           px_per_tile: int, sky: str, geo: dict | None = None,
           abort=None, rect: tuple[int, int, int, int] | None = None
           ) -> tuple[int, int, bytearray]:
    """逐像素着色 → (out_w, out_h, RGBA)。

    `abort` 是可选中断回调：预取算到一半用户来点别的房间了，就靠它把 CPU 让出去。
    每 32 行查一次——一次迭代是几毫秒，够细；对正常渲染只是每行多一个 `is not None`。

    `rect` 是「整张输出图里的一个矩形」，给了就只算这一块（视口裁剪，B 档）。
    映射表始终按**整图**尺寸建，所以裁出来的像素与整图同位置逐像素一致——
    放大、平移时把两张图叠起来不会有半个像素的错位。
    """
    cw, ch = canvas.w, canvas.h
    tw, th = cw // PX_PER_TILE, ch // PX_PER_TILE
    full_w, full_h = tw * px_per_tile, th * px_per_tile
    if rect is None:
        x0, y0, x1, y1 = 0, 0, full_w, full_h
    else:
        x0, y0, x1, y1 = rect
        x0 = max(0, min(int(x0), full_w))
        y0 = max(0, min(int(y0), full_h))
        x1 = max(x0, min(int(x1), full_w))
        y1 = max(y0, min(int(y1), full_h))
    ow, oh = x1 - x0, y1 - y0

    # 输出像素 → 源像素（每个 tile 内均匀取点）
    sx_list, sy_list = _sample_maps(cw, ch, px_per_tile)

    canvas_rgb = canvas.rgb
    covered = canvas.covered
    cam_of = canvas.cam_of
    cams = canvas.cams
    cam_count = len(pals)
    decals = canvas.decals or [b""]
    decal_len = 0
    grime_on = params.grime > 0.0
    plain = params.plain_color()
    fill_sky = sky != "none"
    shadow_const = _shadow_constant(params)
    fog_amount = params.fog_amount
    rain = params.rain
    light = params.light
    hue = params.hue
    hue_cos = math.cos(math.radians(hue)) if hue else 1.0
    hue_sin = math.sin(math.radians(hue)) if hue else 0.0
    inv_sqrt3 = 0.5773502691896258

    out = bytearray(ow * oh * 4)
    # 没被任何摄像机覆盖的地方留到后面统一处理（`_fill_void`）：那里房间文件里
    # 就没有纹理，按格子分类取「周边同类的已着色像素」去补，见计划书 §20。
    for oy in range(y0, y1):
        if abort is not None and (oy & 31) == 0 and abort():
            raise RenderError("aborted", "渲染被更新的请求打断")
        sy = sy_list[oy]
        row_base = sy * cw
        row_oi = (oy - y0) * ow * 4
        for ox in range(x0, x1):
            sx = sx_list[ox]
            oi = row_oi + (ox - x0) * 4
            di = row_base + sx
            if not covered[di]:
                # 天空档为 none 时这里保持透明，交给前端露卡片底色
                if not fill_sky:
                    out[oi + 3] = 0
                continue
            j = di * 3
            r = canvas_rgb[j]
            g = canvas_rgb[j + 1]
            b = canvas_rgb[j + 2]

            ci = cam_of[di]
            pal = pals[ci - 1] if 0 < ci <= cam_count else pals[0]

            if r == _SKY_WHITE and g == _SKY_WHITE and b == _SKY_WHITE:
                if not fill_sky:
                    out[oi + 3] = 0
                    continue
                sky_c = pal[7][0]
                cr, cg, cb = sky_c[0], sky_c[1], sky_c[2]
            else:
                # ---- 解码 R：受光标志 / 调色板行 / 深度 --------------------
                # 与 LevelColor.shader:232-239 一致：
                #   if (red > 90) red -= 90; else shadow = 1;
                #   paletteColor = clamp(floor((red-1)/30), 0, 2);
                #   red = fmod(red-1, 30);          ← C 的 fmod 保留符号，red=0 时得 -1
                lit = r > 90
                r2 = r - 90 if lit else r
                row_idx = (r2 - 1) // 30
                if row_idx < 0:
                    row_idx = 0
                elif row_idx > 2:
                    row_idx = 2
                t_depth = r2 - 1
                depth = -1 if t_depth < 0 else t_depth % 30

                # ---- 解码 G：非地板暗部 / 彩色道具 / 特效 / 污渍 ----------
                gg = g
                nfd = 0 if gg >= 16 else 1
                if gg >= 16:
                    gg -= 16
                effect = 100 if gg >= 8 else gg
                if gg >= 8:
                    gg -= 8

                col_idx = depth * nfd
                if col_idx < 0:      # shader 里负数 u 会被采样器钳到第 0 列
                    col_idx = 0

                # ---- shadow：静止画面下是常数，否则逐像素算 --------------
                if lit:
                    if shadow_const is None:
                        if 0 < ci <= len(cams):
                            left, top, tw_, th_ = cams[ci - 1]
                            u = (sx_list[ox] - left + 0.5) / tw_ if tw_ else 0.5
                            v = 1.0 - (sy - top + 0.5) / th_ if th_ else 0.5
                        else:
                            u = (sx_list[ox] + 0.5) / cw
                            v = 1.0 - (sy + 0.5) / ch
                        shift = 0.003 * (r % 30)
                        n = _bilerp(noise, u * 0.5 + rain * 0.1 - shift,
                                    1.0 - v * 0.5 + rain * 0.2 - shift)
                        s = 0.5 + math.sin(math.fmod(n + rain * 0.1 - v, 1.0) * TAU) * 0.5
                        shadow = (s - 0.5) * 6.0 + 0.5 - light * 4.0
                        shadow = 0.0 if shadow < 0.0 else (1.0 if shadow > 1.0 else shadow)
                    else:
                        shadow = shadow_const
                else:
                    shadow = 1.0

                lit_row = pal[row_idx + 3 if row_idx + 3 <= 7 else 7][col_idx]
                dark_row = pal[row_idx][col_idx]
                inv = 1.0 - shadow
                cr = lit_row[0] * inv + dark_row[0] * shadow
                cg = lit_row[1] * inv + dark_row[1] * shadow
                cb = lit_row[2] * inv + dark_row[2] * shadow

                # ---- grime（污渍） ---------------------------------------
                if grime_on and gg >= 4:
                    if 0 < ci <= len(cams):
                        left, top, tw_, th_ = cams[ci - 1]
                        u = (sx_list[ox] - left + 0.5) / tw_ if tw_ else 0.5
                        v = 1.0 - (sy - top + 0.5) / th_ if th_ else 0.5
                    else:
                        u = (sx_list[ox] + 0.5) / cw
                        v = 1.0 - (sy + 0.5) / ch
                    n2 = _bilerp(noise, u * 2.0, v * 2.0)
                    rb = 0.5 + 0.5 * math.sin((rain + n2 * 4.0 + depth / 12.0) * TAU)
                    gi = int(5.5 + rb * 25.0)
                    gi = 0 if gi < 0 else (31 if gi > 31 else gi)
                    gc = pal[6][gi]
                    amt = 0.2 * params.grime
                    keep = 1.0 - amt
                    cr = cr * keep + gc[0] * amt
                    cg = cg * keep + gc[1] * amt
                    cb = cb * keep + gc[2] * amt

                # ---- 彩色道具贴图条（effectCol == 100） -------------------
                if effect == 100:
                    decal = decals[ci - 1] if 0 < ci <= len(decals) else decals[0]
                    decal_len = len(decal) // 3
                if effect == 100 and decal_len:
                    dxi = 255 - b
                    if dxi < 0:
                        dxi = 0
                    elif dxi >= decal_len:
                        dxi = decal_len - 1
                    dr = decal[dxi * 3] / 255.0
                    dg = decal[dxi * 3 + 1] / 255.0
                    db = decal[dxi * 3 + 2] / 255.0
                    if row_idx == 2:
                        k = 0.2 - shadow * 0.1
                        dr = dr * (1 - k) + k
                        dg = dg * (1 - k) + k
                        db = db * (1 - k) + k
                    fog_col = pal[7][1]
                    dt = depth / 60.0
                    dr = dr * (1 - dt) + fog_col[0] * dt
                    dg = dg * (1 - dt) + fog_col[1] * dt
                    db = db * (1 - dt) + fog_col[2] * dt
                    t = (depth - 3.5) * 0.3
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    mix = 0.9 * (1 - t) + (0.3 + 0.4 * shadow) * t
                    ar = cr * 0.3 + dr * 0.7
                    ag = cg * 0.3 + dg * 0.7
                    ab = cb * 0.3 + db * 0.7
                    br2 = cr * dr * 1.5
                    bg2 = cg * dg * 1.5
                    bb2 = cb * db * 1.5
                    keep = 1.0 - mix
                    cr = ar * keep + br2 * mix
                    cg = ag * keep + bg2 * mix
                    cb = ab * keep + bb2 * mix

                # ---- effectColor 1 / 2 / 3 -------------------------------
                # shader:327-340
                #   green>0 && green<3 → pal 第 (5.5-(ec-1)*2) 与 (4.5-(ec-1)*2) 行、30/31 列
                #   green==3           → 白色 × (B × SwarmRoom)
                elif effect in (1, 2, 3):
                    if effect == 3:
                        t = (b / 255.0) * params.swarm_room
                        keep = 1.0 - t
                        cr = cr * keep + t
                        cg = cg * keep + t
                        cb = cb * keep + t
                    else:
                        row_hi = 5 if effect == 1 else 3
                        row_lo = 4 if effect == 1 else 2
                        top_r = pal[row_hi][30][0] * (1 - shadow) + pal[row_hi][31][0] * shadow
                        top_g = pal[row_hi][30][1] * (1 - shadow) + pal[row_hi][31][1] * shadow
                        top_b = pal[row_hi][30][2] * (1 - shadow) + pal[row_hi][31][2] * shadow
                        bot_r = pal[row_lo][30][0] * (1 - shadow) + pal[row_lo][31][0] * shadow
                        bot_g = pal[row_lo][30][1] * (1 - shadow) + pal[row_lo][31][1] * shadow
                        bot_b = pal[row_lo][30][2] * (1 - shadow) + pal[row_lo][31][2] * shadow
                        dt = depth / 30.0
                        er = top_r * (1 - dt) + bot_r * dt
                        eg = top_g * (1 - dt) + bot_g * dt
                        eb = top_b * (1 - dt) + bot_b * dt
                        t = b / 255.0
                        keep = 1.0 - t
                        cr = cr * keep + er * t
                        cg = cg * keep + eg * t
                        cb = cb * keep + eb * t

                # ---- 雾 --------------------------------------------------
                if fog_amount:
                    ft = depth * ((0.5 + 0.5 * nfd) if depth < 10 else 1.0) * fog_amount / 30.0
                    if ft > 1.0:
                        ft = 1.0
                    elif ft < 0.0:
                        ft = 0.0
                    if ft > 0.0:
                        fc = pal[7][1]
                        keep = 1.0 - ft
                        cr = cr * keep + fc[0] * ft
                        cg = cg * keep + fc[1] * ft
                        cb = cb * keep + fc[2] * ft

            # ---- 全局颜色调整 --------------------------------------------
            if not plain:
                cr *= params.darkness
                cg *= params.darkness
                cb *= params.darkness
                cr = (cr - 0.5) * params.contrast + 0.5
                cg = (cg - 0.5) * params.contrast + 0.5
                cb = (cb - 0.5) * params.contrast + 0.5
                grey = cr * 0.222 + cg * 0.707 + cb * 0.071
                cr = grey + (cr - grey) * params.saturation
                cg = grey + (cg - grey) * params.saturation
                cb = grey + (cb - grey) * params.saturation
                if hue:
                    # 绕灰轴旋转（上游那份用了 np.cross/k·rgb，形状对不上会抛异常，这里按定义重写）
                    x = (cb - cg) * inv_sqrt3
                    y = (cr - cb) * inv_sqrt3
                    z = (cg - cr) * inv_sqrt3
                    dot = (cr + cg + cb) * inv_sqrt3
                    nr = cr * hue_cos + x * hue_sin + inv_sqrt3 * dot * (1 - hue_cos)
                    ng = cg * hue_cos + y * hue_sin + inv_sqrt3 * dot * (1 - hue_cos)
                    nb = cb * hue_cos + z * hue_sin + inv_sqrt3 * dot * (1 - hue_cos)
                    cr, cg, cb = nr, ng, nb
                cr += params.brightness
                cg += params.brightness
                cb += params.brightness

            out[oi] = 0 if cr <= 0.0 else (255 if cr >= 1.0 else int(cr * 255.0 + 0.5))
            out[oi + 1] = 0 if cg <= 0.0 else (255 if cg >= 1.0 else int(cg * 255.0 + 0.5))
            out[oi + 2] = 0 if cb <= 0.0 else (255 if cb >= 1.0 else int(cb * 255.0 + 0.5))
            out[oi + 3] = 255
    return ow, oh, out


def _sample_maps(cw: int, ch: int, px_per_tile: int) -> tuple[list[int], list[int]]:
    """输出像素 → 源像素的映射表（每个 tile 内均匀取点，放大时最近邻）。"""
    sub = [int((i + 0.5) / px_per_tile * PX_PER_TILE) for i in range(px_per_tile)]
    tw = cw // PX_PER_TILE
    th = ch // PX_PER_TILE
    sx = [x * PX_PER_TILE + sub[i % px_per_tile] for x in range(tw) for i in range(px_per_tile)]
    sy = [y * PX_PER_TILE + sub[i % px_per_tile] for y in range(th) for i in range(px_per_tile)]
    return ([v if v < cw else cw - 1 for v in sx], [v if v < ch else ch - 1 for v in sy])


def _water(out: bytearray, ow: int, oh: int, canvas: _Canvas, geo: dict,
           pal: list, cfg: Settings, params: _Params, px_per_tile: int,
           abort=None, rect: tuple[int, int, int, int] | None = None) -> None:
    """水面静态近似（就地改写 out）。

    水面在游戏里是两层网格（水面带 + 水体），这里只还原静止时的颜色与位置：
    水面带按 `surfaceColor1/2 + shine`，水体按 `waterColor1/2` 沿深度插值。
    波浪模拟、折射、气室都不做——本期只要「看得出是水」。

    水体统一按「整幅半透明笼罩」处理（见下方 2026-11-18 的决策注释），
    所以这里的输出**不再依赖 `cells`**：有没有水只看水面高度，不看格子类型。
    """
    water_level = geo.get("water_level", -1.0)
    if water_level < 0:
        return

    cw, chh = canvas.w, canvas.h
    gw = geo.get("w") or 0
    gh = geo.get("h") or 0
    covered = canvas.covered

    surface_y = 10.0 + water_level * 20.0
    amp = 1.0 + 39.0 * cfg.wave_amplitude
    wlen = 50.0 + 700.0 * cfg.wave_length
    wspeed = (-1.0 / 30.0) + (2.0 / 30.0) * cfg.wave_speed

    water1 = pal[7][4]
    water2 = pal[7][5]
    surface1 = pal[7][6]
    surface2 = pal[7][7]
    shine_col = pal[7][8]
    fog = params.fog_amount
    alpha = params.water_alpha
    t_water = params.water_time

    sx_list, sy_list = _sample_maps(cw, chh, px_per_tile)

    # 整张输出图的尺寸（裁剪时 `ow/oh` 只是其中一块）
    full_w = (cw // PX_PER_TILE) * px_per_tile
    full_h = (chh // PX_PER_TILE) * px_per_tile
    if rect is None:
        x0, y0, x1, y1 = 0, 0, full_w, full_h
    else:
        x0, y0, x1, y1 = rect
        x0 = max(0, min(int(x0), full_w))
        y0 = max(0, min(int(y0), full_h))
        x1 = max(x0, min(int(x1), full_w))
        y1 = max(y0, min(int(y1), full_h))

    # 逐列的水面高度（静止时只受 WaveAmplitude 影响，幅度 ±0.15 px）
    if amp > 0.05:
        surf_by_x = [surface_y + math.sin((x + 0.5) / wlen * TAU + t_water * wspeed * TAU) * amp * 0.15
                     for x in range(cw)]
        surf_max = max(surf_by_x)
    else:
        surf_by_x = None
        surf_max = surface_y

    # 「水面之上」的整行直接跳过——大多数房间水在下方，能省掉大半像素
    top_limit = surf_max + 0.9
    for oy in range(y0, y1):
        if abort is not None and (oy & 31) == 0 and abort():
            raise RenderError("aborted", "渲染被更新的请求打断")
        sy = sy_list[oy]
        wy = chh - sy - 0.5
        if wy > top_limit:
            continue
        row_oi = (oy - y0) * ow * 4
        for ox in range(x0, x1):
            sx = sx_list[ox]
            oi = row_oi + (ox - x0) * 4
            surf_y = surf_by_x[sx] if surf_by_x else surface_y
            dy = wy - surf_y
            if dy > 0.9:
                continue
            if not covered[sy * cw + sx]:
                continue

            wx = sx + 0.5
            tx = int(wx // PX_PER_TILE)
            # wy 是**世界 y（朝上）**，格子图的行号是**朝下**的：必须翻回来。
            # 以前这里直接 `int(wy // 20)`，等于查了整间房上下镜像的那一格。
            ty = int((chh - wy) // PX_PER_TILE)
            valid = (0 <= tx < gw) and (0 <= ty < gh)

            # 水体：**统一按 `WaterFront = 1` 的「整幅半透明笼罩」画**。
            #
            # 2026-11-18 02:23 主人拍板：不再区分 `WaterFront`，所有房间都照
            # `SL_F01` 那一套来——水体压在最前，alpha 混色，地形/道具/天空照旧透出来。
            # 理由是 `front = 0` 那条「只填空气格」的路子会渲成一块块**实色色块**，
            # 既看不到水下景象，边界还是 20 px 的硬台阶；而 `SL_F01` 那种笼罩写法
            # 在大房间里反而更像实机的「远处水体」，而且一套代码通吃，好维护。
            #
            # 代价（知情接受）：`front = 0` 的房间本该「地形在水之上」，现在也会被
            # 染上一层水色；这是刻意简化的结果，不是 bug。
            if dy < 0.0:
                t = (-dy) / surface_y if surface_y > 0 else 0.0
                if t > 1.0:
                    t = 1.0
                mix = ((1.0 - t) ** 3) * 0.4
                br = water2[0] + (water1[0] - water2[0]) * mix
                bg = water2[1] + (water1[1] - water2[1]) * mix
                bb = water2[2] + (water1[2] - water2[2]) * mix
                keep = 1.0 - alpha
                out[oi] = max(0, min(255, int(out[oi] * keep + br * 255.0 * alpha + 0.5)))
                out[oi + 1] = max(0, min(255, int(out[oi + 1] * keep + bg * 255.0 * alpha + 0.5)))
                out[oi + 2] = max(0, min(255, int(out[oi + 2] * keep + bb * 255.0 * alpha + 0.5)))
                out[oi + 3] = 255

            # 水面带：以水面为中心 ±0.9 px 的细带。
            #
            # 这里**不能**直接把像素替换成带色：`surface2` 在很多调色板里就等于天空色
            # （palette13 的 `pal[7][7]` 是 (104,105,106)），压在深色水体上会亮成一条
            # 死白线——就是主人 2026-11-18 01:20 报的「水面与空气交接面的白色部分」。
            # 改成半透明叠加：带中心强、上下边缘趋近 0，读起来是「水面反光」而不是
            # 「画了一条线」。
            if -0.9 <= dy <= 0.9:
                if valid:
                    band_t = (dy + 0.9) / 1.8
                    shine = (0.5 + 0.5 * math.sin((wx - surf_y) / 800.0 * TAU + t_water * 0.9)) ** 7
                    shine_mix = shine * (1.0 - fog)
                    shine_mix = 0.0 if shine_mix < 0.0 else (1.0 if shine_mix > 1.0 else shine_mix)
                    band_k = band_t * 0.55
                    for k in range(3):
                        mid = surface2[k] * (1.0 - shine_mix) + shine_col[k] * shine_mix
                        band_c = (surface1[k] * (1.0 - band_t) + mid * band_t) * 255.0
                        cur = out[oi + k]
                        out[oi + k] = max(0, min(255, int(cur + (band_c - cur) * band_k + 0.5)))
                    out[oi + 3] = 255


# ---------------------------------------------------------------------------
# 空洞填充（没有任何摄像机覆盖的区域）
# ---------------------------------------------------------------------------
VOID_SMOOTH_ITERS = 24


def _fill_void(out: bytearray, ow: int, oh: int, canvas: _Canvas, geo: dict | None,
               pals: list, px_per_tile: int, sky: str,
               rect: tuple[int, int, int, int] | None = None) -> int:
    """把「没有任何摄像机覆盖」的区域补上颜色，返回填了多少个输出像素。

    这些位置在游戏里永远进不了画面——房间文件里就没有那一块的纹理（计划书 §20.1），
    所以只要两件事：别留透明洞、别露出假地形。做法：

    1. 按 tile 判类别（`cells` 为 '0' → 空气，否则实心）。类别决定「这里该是天空还是岩体」，
       地形轮廓因此保留；
    2. 颜色取自该 tile 周边**已经着色**的像素（不是源纹理——源纹理是索引编码，取出来是彩色噪点），
       而且只在**同类**之间混合，否则一片红叶会把岩体区染红（§20.5 实测）；
    3. 空洞之间做 ≤24 次邻域迭代，把边界颜色往内部铺开；
    4. 写回时离边界 2 tile 以外直接填纯色（那里面颜色已经收敛），边界带按 tile 网格
       做双线性插值——否则放大就会看到一块块 20px 的方块。
    """
    if sky == "none" or not geo:
        return 0
    cw, chh = canvas.w, canvas.h
    covered = canvas.covered
    gw = int(geo.get("w") or 0)
    gh = int(geo.get("h") or 0)
    px = px_per_tile
    if gw <= 0 or gh <= 0:
        return 0
    # 整图尺寸；`rect` 给了就只处理其中一块（视口裁剪，B 档）
    full_w, full_h = gw * px, gh * px
    if rect is None:
        x0, y0, x1, y1 = 0, 0, full_w, full_h
    else:
        x0, y0, x1, y1 = rect
        x0 = max(0, min(int(x0), full_w))
        y0 = max(0, min(int(y0), full_h))
        x1 = max(x0, min(int(x1), full_w))
        y1 = max(y0, min(int(y1), full_h))
    if ow != x1 - x0 or oh != y1 - y0:
        return 0
    total = gw * gh
    inv = 1.0 / px
    tile_px = PX_PER_TILE
    # 与 `_shade` 同一张「输出像素 → 源像素」映射表。不能自己写 int(oy*20/px)：
    # px 不能整除 20 时（6、7、13…）会错开 1~2 行，兜底就会扫错行。
    sx_map, sy_map = _sample_maps(cw, chh, px)

    # ---- 1. 粗筛：只查 tile 中心。没有空洞的房间在这里就返回（约 5 ms） ----
    #
    # 覆盖判定用**摄像机矩形**而不是 `covered` 位图：裁剪渲染时不相干的摄像机
    # 是没解码的（`_stitch` 里跳过），它们的区域 `covered` 全是 0；照位图判会把
    # 半间房当空洞，颜色会被邻居的假色带偏。矩形判定与位图在整图渲染下完全等价
    # （位图就是矩形贴上去的），所以两种模式共用这一套。
    rects = [(ox_, oy_, ox_ + tw_, oy_ + th_)
             for (ox_, oy_, tw_, th_) in canvas.cams if tw_ > 0 and th_ > 0]
    st = bytearray(total)
    for ty in range(gh):
        cy = min(chh - 1, ty * tile_px + 10)
        base = ty * gw
        for tx in range(gw):
            cx = min(cw - 1, tx * tile_px + 10)
            for rx0, ry0, rx1, ry1 in rects:
                if rx0 <= cx < rx1 and ry0 <= cy < ry1:
                    st[base + tx] = 1
                    break
    if 0 not in st:
        return 0

    # ---- 2. 候选 tile 精判：区分「完全没覆盖」和「只覆盖了一部分」 ----
    voids: list[int] = []
    partials: list[int] = []
    for ti in range(total):
        if st[ti]:
            continue
        ty, tx = divmod(ti, gw)
        hit = False
        for j in range(5):
            sy = ty * tile_px + 2 + j * 4
            if sy >= chh:
                break
            row = sy * cw
            for i in range(5):
                sx = tx * tile_px + 2 + i * 4
                if sx < cw and covered[row + sx]:
                    hit = True
                    break
            if hit:
                break
        if not hit:
            voids.append(ti)
        else:
            partials.append(ti)
    if not voids:
        return 0

    # ---- 3. 类别（用行优先索引，与 room_geo 一致） ----
    cells = geo.get("cells") or ""
    if len(cells) != total:
        cells = ""
    cls = bytearray(total)
    if cells:
        for ti in range(total):
            cls[ti] = 0 if cells[ti] == "0" else 1

    voidset = set(voids)
    color: list = [None] * total

    def _tile_color(ti: int):
        """该 tile 已覆盖像素的平均色（从**着色后**的 out 取）。"""
        ty, tx = divmod(ti, gw)
        s0 = s1 = s2 = 0
        n = 0
        for j in (1, 3, 5):
            oy = ty * px + j * px // 6
            if oy < y0 or oy >= y1:          # 裁剪模式下只取裁块内的像素
                continue
            row = sy_map[oy] * cw
            for i in (1, 3, 5):
                ox = tx * px + i * px // 6
                if ox < x0 or ox >= x1:
                    continue
                if not covered[row + sx_map[ox]]:
                    continue
                o = ((oy - y0) * ow + (ox - x0)) * 4
                s0 += out[o]
                s1 += out[o + 1]
                s2 += out[o + 2]
                n += 1
        return (s0 / n, s1 / n, s2 / n) if n else None

    # ---- 4. 边界源 tile 的平均色（半径 3，双线性取样不会越界） ----
    need: set[int] = set()
    for ti in voids:
        ty, tx = divmod(ti, gw)
        for dy in range(-3, 4):
            yy = ty + dy
            if yy < 0 or yy >= gh:
                continue
            base = yy * gw
            for dx in range(-3, 4):
                xx = tx + dx
                if xx < 0 or xx >= gw:
                    continue
                nb = base + xx
                if nb not in voidset:
                    need.add(nb)
    for ti in need:
        c = _tile_color(ti)
        if c is not None:
            color[ti] = c
    for ti in partials:               # 部分覆盖的 tile 也要颜色（补边用）
        if color[ti] is None:
            c = _tile_color(ti)
            if c is not None:
                color[ti] = c

    # ---- 5. 逐圈扩散：每个空洞 tile 取邻居的颜色，同类优先 ----
    pending = list(voids)
    for _ in range(gw + gh):
        if not pending:
            break
        nxt: list[int] = []
        for ti in pending:
            ty, tx = divmod(ti, gw)
            c0 = cls[ti]
            s0 = s1 = s2 = 0.0
            n = 0
            a0 = a1 = a2 = 0.0
            na = 0
            for dy in (-1, 0, 1):
                yy = ty + dy
                if yy < 0 or yy >= gh:
                    continue
                base = yy * gw
                for dx in (-1, 0, 1):
                    xx = tx + dx
                    if xx < 0 or xx >= gw or (dx == 0 and dy == 0):
                        continue
                    nb = base + xx
                    c = color[nb]
                    if c is None:
                        continue
                    a0 += c[0]
                    a1 += c[1]
                    a2 += c[2]
                    na += 1
                    if cls[nb] == c0:
                        s0 += c[0]
                        s1 += c[1]
                        s2 += c[2]
                        n += 1
            if n:
                color[ti] = (s0 / n, s1 / n, s2 / n)
            elif na:
                color[ti] = (a0 / na, a1 / na, a2 / na)
            else:
                nxt.append(ti)
        if len(nxt) == len(pending):
            break
        pending = nxt

    sky_c = pals[0][7][0]
    for ti in voids:
        if color[ti] is None:      # 极端情况（整间房都没有已着色像素）
            color[ti] = (sky_c[0] * 255.0, sky_c[1] * 255.0, sky_c[2] * 255.0)

    # ---- 6. 邻域迭代：把边界色往内部铺平（只在同类之间） ----
    for _ in range(VOID_SMOOTH_ITERS):
        for ti in voids:
            ty, tx = divmod(ti, gw)
            c0 = cls[ti]
            s0 = s1 = s2 = 0.0
            n = 0
            if tx:
                nb = ti - 1
                c = color[nb]
                if c is not None and cls[nb] == c0:
                    s0 += c[0]
                    s1 += c[1]
                    s2 += c[2]
                    n += 1
            if tx + 1 < gw:
                nb = ti + 1
                c = color[nb]
                if c is not None and cls[nb] == c0:
                    s0 += c[0]
                    s1 += c[1]
                    s2 += c[2]
                    n += 1
            if ty:
                nb = ti - gw
                c = color[nb]
                if c is not None and cls[nb] == c0:
                    s0 += c[0]
                    s1 += c[1]
                    s2 += c[2]
                    n += 1
            if ty + 1 < gh:
                nb = ti + gw
                c = color[nb]
                if c is not None and cls[nb] == c0:
                    s0 += c[0]
                    s1 += c[1]
                    s2 += c[2]
                    n += 1
            if n:
                color[ti] = (s0 / n, s1 / n, s2 / n)

    # ---- 7. 边界带 = 距非空洞 ≤2 的空洞 tile（这里才需要双线性） ----
    band: set[int] = set()
    for ti in voids:
        ty, tx = divmod(ti, gw)
        near = False
        for dy in (-2, -1, 0, 1, 2):
            yy = ty + dy
            if near or yy < 0 or yy >= gh:
                continue
            base = yy * gw
            for dx in (-2, -1, 0, 1, 2):
                xx = tx + dx
                if 0 <= xx < gw and (base + xx) not in voidset:
                    near = True
                    break
        if near:
            band.add(ti)

    # ---- 8. 写回 ----
    filled = 0
    for ti in voids:
        if ti in band:
            continue
        c = color[ti]
        rec = bytes((int(c[0]), int(c[1]), int(c[2]), 255)) * px
        ty, tx = divmod(ti, gw)
        tx0p = tx * px
        ty0p = ty * px
        if tx0p >= x1 or tx0p + px <= x0 or ty0p >= y1 or ty0p + px <= y0:
            continue                                   # 整格在裁块之外
        seg_x0 = max(tx0p, x0)
        seg_x1 = min(tx0p + px, x1)
        seg_y0 = max(ty0p, y0)
        seg_y1 = min(ty0p + px, y1)
        piece = rec[(seg_x0 - tx0p) * 4:(seg_x1 - tx0p) * 4]
        for oy in range(seg_y0, seg_y1):
            o = ((oy - y0) * ow + (seg_x0 - x0)) * 4
            out[o:o + len(piece)] = piece
        filled += (seg_x1 - seg_x0) * (seg_y1 - seg_y0)

    gcol = color
    for ti in band:
        c = color[ti]
        ty, tx = divmod(ti, gw)
        tx0p = tx * px
        ty0p = ty * px
        if tx0p >= x1 or tx0p + px <= x0 or ty0p >= y1 or ty0p + px <= y0:
            continue
        for oy in range(max(ty0p, y0), min(ty0p + px, y1)):
            v = (oy + 0.5) * inv - 0.5
            vy0 = int(math.floor(v))
            if vy0 < 0:
                vy0 = 0
            elif vy0 > gh - 2:
                vy0 = gh - 2
            vy1 = vy0 + 1 if vy0 + 1 < gh else vy0
            fy = v - vy0
            fy = 0.0 if fy < 0.0 else (1.0 if fy > 1.0 else fy)
            row0 = vy0 * gw
            row1 = vy1 * gw
            base = (oy - y0) * ow
            for ox in range(max(tx0p, x0), min(tx0p + px, x1)):
                u = (ox + 0.5) * inv - 0.5
                ux0 = int(math.floor(u))
                if ux0 < 0:
                    ux0 = 0
                elif ux0 > gw - 2:
                    ux0 = gw - 2
                ux1 = ux0 + 1 if ux0 + 1 < gw else ux0
                fx = u - ux0
                fx = 0.0 if fx < 0.0 else (1.0 if fx > 1.0 else fx)

                c00 = gcol[row0 + ux0] or c
                c10 = gcol[row0 + ux1] or c
                c01 = gcol[row1 + ux0] or c
                c11 = gcol[row1 + ux1] or c
                o = (base + (ox - x0)) * 4
                for k in (0, 1, 2):
                    top = c00[k] + (c10[k] - c00[k]) * fx
                    bot = c01[k] + (c11[k] - c01[k]) * fx
                    out[o + k] = max(0, min(255, int(top + (bot - top) * fy + 0.5)))
                out[o + 3] = 255
                filled += 1

    # ---- 9. 兜底：任何还没填的像素（部分覆盖 tile 的边、摄像机矩形之间的细缝） ----
    # 用 alpha 通道按行探测——`0 in 切片` 是 C 级操作，只有真出现空洞的行才细扫。
    # 不补的话那些像素 alpha 还是 0，WebView 里会透出卡片底色，
    # 沿着摄像机边缘画出一条一像素宽的白线（实测 SL_F01 / OE_RUINCOURTYARD 都有）。
    sky_rgb = (sky_c[0] * 255.0, sky_c[1] * 255.0, sky_c[2] * 255.0)
    for oy in range(oh):
        if 0 not in out[oy * ow * 4 + 3:(oy + 1) * ow * 4:4]:
            continue
        sy = sy_map[oy + y0]
        ty = sy // tile_px
        row = sy * cw
        base = oy * ow
        cache: dict[int, tuple] = {}
        for ox in range(ow):
            o = (base + ox) * 4
            if out[o + 3]:
                continue
            # 就近取色：同一行左右各看 12 个像素，复制最近的已着色像素。
            # 用 tile 均值会脏——摄像机边缘那一排 tile 的均值里掺着亮天空，
            # 直接填会画出一条亮线（实测 OE_RUINCOURTYARD y=182）。
            c = None
            for d in range(1, 13):
                xx = ox - d
                if xx >= 0:
                    q = (base + xx) * 4
                    if out[q + 3]:
                        c = (out[q], out[q + 1], out[q + 2])
                        break
                xx = ox + d
                if xx < ow:
                    q = (base + xx) * 4
                    if out[q + 3]:
                        c = (out[q], out[q + 1], out[q + 2])
                        break
            if c is None:
                sx = sx_map[ox + x0]
                if covered[row + sx]:
                    continue      # 已着色过（理论到不了这里）
                tx = sx // tile_px
                ti = (ty if ty < gh else gh - 1) * gw + (tx if tx < gw else gw - 1)
                c = cache.get(ti)
                if c is None:
                    c = color[ti]
                    if c is None:                      # 该 tile 没算过色：退一步找邻居
                        ty2, tx2 = divmod(ti, gw)
                        for dy in (-1, 0, 1):
                            yy = ty2 + dy
                            if yy < 0 or yy >= gh or c is not None:
                                continue
                            for dx in (-1, 0, 1):
                                xx = tx2 + dx
                                if 0 <= xx < gw and color[yy * gw + xx] is not None:
                                    c = color[yy * gw + xx]
                                    break
                    if c is None:
                        c = sky_rgb
                    cache[ti] = c
            out[o] = max(0, min(255, int(c[0])))
            out[o + 1] = max(0, min(255, int(c[1])))
            out[o + 2] = max(0, min(255, int(c[2])))
            out[o + 3] = 255
            filled += 1
    return filled


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
_render_lock = threading.Lock()
_render_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_RENDER_CACHE_MAX = 8


def available() -> dict:
    """能力探测：内核永远可用（零第三方依赖），这里返回引擎与常量供界面显示。"""
    return {"ok": True, "engine": "python", "pxPerTile": PX_PER_TILE, "srcSize": [SRC_W, SRC_H]}


def probe(region: dict, layer_id: str | None = None) -> dict:
    """素材探测（**不渲染**）：界面据此决定「实机」开关出不出现。

    内核零第三方依赖，所以「能不能渲染」不取决于装了什么包，只取决于找不找得到素材根：
    没有 `palettes/` 就翻不出颜色，任何房间都会失败。这里只做几次 `isfile`，可以随时调。

    注意它只看**全局**素材（调色板），不看单间房的 `_N.png`——那是个别房间的缺失，
    该由渲染时的 `no_texture` 降级处理，不该让整个开关消失。
    """
    roots: list[str] = []
    try:
        roots = asset_roots(region, layer_id)
    except Exception:      # noqa: BLE001 - 探测失败一律当不可用，绝不向上抛
        roots = []
    palette = bool(roots) and bool(
        _find_asset(roots, "palettes/effectcolors.png") or
        _find_asset(roots, "palettes/palette0.png"))
    return {
        "ok": True,
        "available": palette,
        "roots": len(roots),
        "engine": "python",
        "reason": "" if palette else "no_assets",
    }


def _norm_crop(crop) -> tuple[int, int, int, int] | None:
    """把外部传进来的裁块规整成 `(tx0, ty0, tx1, ty1)`（单位 tile），非法就 None。"""
    if not crop:
        return None
    try:
        tx0, ty0, tx1, ty1 = (int(v) for v in crop)
    except (TypeError, ValueError):
        return None
    if tx1 <= tx0 or ty1 <= ty0:
        return None
    return (tx0, ty0, tx1, ty1)


def _cache_key_of(room_path: str, layer_id: str | None, slugcat: str | None,
                  px: int, fit: int, sky: str, water: bool, crop=None):
    try:
        st = os.stat(room_path)
    except OSError:
        return None, None
    key = (room_path, st.st_mtime_ns, st.st_size, layer_id or "",
           (slugcat or "").lower(), px, fit, sky, bool(water),
           tuple(crop) if crop else ())
    return key, st


def _from_cache(region_code: str, room_key: str, room_path: str, st, layer_id: str | None,
                slugcat: str | None, px: int, fit: int, sky: str, water: bool,
                use_memory: bool, use_disk: bool, started: float,
                crop=None) -> dict | None:
    """进程内存 → 磁盘，命中就返回结果。**不加渲染门闩**：查缓存不该排队。"""
    key, _ = _cache_key_of(room_path, layer_id, slugcat, px, fit, sky, water, crop)
    if use_memory and key:
        with _render_lock:
            hit = _render_cache.get(key)
            if hit is not None:
                _render_cache.move_to_end(key)
                return dict(hit, cached=True, source="memory",
                            ms=round((time.time() - started) * 1000.0, 1))

    if use_disk and key and region_code:
        disk = room_cache.load(
            region_code, room_key, slugcat, px, fit,
            room_path, st.st_mtime_ns, st.st_size, sky, bool(water), crop)
        if disk and disk.get("png"):
            result = {
                "ok": True,
                "room": room_key,
                "path": room_path,
                "png": disk["png"],
                "width": disk.get("w"),
                "height": disk.get("h"),
                "pxPerTile": disk.get("pxPerTile") or px,
                "sky": sky,
                "engine": "python",
                "bytes": disk.get("bytes") or len(disk["png"]),
                "meta": disk.get("meta") or {},
                "cached": True,
                "source": "disk",
                "ms": round((time.time() - started) * 1000.0, 1),
            }
            if use_memory and key:
                with _render_lock:
                    _render_cache[key] = dict(result)
                    _render_cache.move_to_end(key)
                    while len(_render_cache) > _RENDER_CACHE_MAX:
                        _render_cache.popitem(last=False)
            return result
    return None


def lookup(region: dict, room: str, layer_id: str | None = None, slugcat: str | None = None,
           px_per_tile: int = PX_PER_TILE, sky: str = "fill", water: bool = True,
           fit_width: int = 0, crop=None) -> dict | None:
    """只查缓存，**绝不渲染**。桥接用它决定「这次要不要占用渲染门闩」。

    存在这个函数的原因很具体：预取还在算 A 的时候用户去开已经缓存好的 B，
    如果也去抢门闩，就要白等一次完整渲染（实测 3.9 s）。命中缓存必须能插队。
    """
    px = max(4, min(int(px_per_tile or PX_PER_TILE), 40))
    fit = max(0, int(fit_width or 0))
    crop = _norm_crop(crop)
    room_key = str(room or "").strip()
    if not room_key:
        return None
    room_path, _first = room_geo.find_file(region, room_key, layer_id)
    if not room_path:
        return None
    key, st = _cache_key_of(room_path, layer_id, slugcat, px, fit, sky, bool(water), crop)
    if key is None:
        return None
    return _from_cache(str(region.get("code") or "").upper(), room_key, room_path, st,
                       layer_id, slugcat, px, fit, sky, bool(water),
                       True, True, time.time(), crop)


def render(region: dict, room: str, layer_id: str | None = None, slugcat: str | None = None,
           px_per_tile: int = PX_PER_TILE, sky: str = "fill", water: bool = True,
           use_cache: bool = True, fit_width: int = 0, use_disk: bool = True,
           abort=None, crop=None) -> dict:
    """渲染一间房，返回 PNG 字节与元信息。

    `region` 是 `region_store.get_region(code)` 的整份数据；房间文件与素材都从
    它记录的层来源里定位，因此和房间卡矢量图永远看同一份文件。

    `fit_width` > 0 时按「输出宽度不超过它」自动降采样——超宽房间（190 tile 以上）
    在卡片里本来就会被缩到 1000 px 显示，渲到 4000 px 是纯浪费。

    `crop=(tx0, ty0, tx1, ty1)`（单位 tile）只渲这一块，用于放大后的视口裁剪（B 档）：
    输出尺寸是 `(tx1-tx0)×px`，与整图**同位置逐像素一致**，前端按 tile 坐标叠上去即可。
    裁块**只进内存缓存，不落盘**——缩放/平移会不断产生新裁块，塞进 200 MB 的磁盘
    预算里会把整图挤掉。

    缓存三级：进程内 LRU（毫秒级）→ 磁盘（5~12 ms）→ 重算（0.4~8 s）。
    磁盘那级让「跳出口再跳回来」「重启后再看同一间」都不用重算。
    """
    started = time.time()
    room_key = str(room or "").strip()
    if not room_key:
        return {"ok": False, "error": "bad_room", "detail": "房间名为空"}

    room_path, first_dir = room_geo.find_file(region, room_key, layer_id)
    if not room_path:
        code = "missing_dir" if (first_dir and not os.path.isdir(first_dir)) else "no_file"
        return {"ok": False, "error": code, "room": room_key}

    px_per_tile = max(4, min(int(px_per_tile or PX_PER_TILE), 40))
    fit_width = max(0, int(fit_width or 0))
    crop = _norm_crop(crop)
    if crop:
        use_disk = False                     # 裁块只进内存（见 docstring）
        fit_width = 0
    cache_key, st = _cache_key_of(room_path, layer_id, slugcat, px_per_tile, fit_width,
                                  sky, bool(water), crop)
    region_code = str(region.get("code") or "").upper()

    if cache_key and (use_cache or use_disk):
        hit = _from_cache(region_code, room_key, room_path, st, layer_id, slugcat,
                          px_per_tile, fit_width, sky, bool(water),
                          use_cache, use_disk, started, crop)
        if hit is not None:
            return hit

    try:
        result = _render_uncached(region, room_path, layer_id, slugcat, px_per_tile, sky, water,
                                  fit_width, abort, crop)
    except RenderError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.detail, "room": room_key,
                "path": room_path}
    except Exception as exc:  # noqa: BLE001 - 桥接层不向外抛
        return {"ok": False, "error": "render_failed", "detail": "%s: %s" % (type(exc).__name__, exc),
                "room": room_key, "path": room_path}

    result["ms"] = round((time.time() - started) * 1000.0, 1)
    result["source"] = "render"

    if use_disk and cache_key and region_code:
        room_cache.store(
            region_code, room_key, slugcat, px_per_tile, fit_width, result.get("png") or b"",
            {
                "room": room_key,
                "slugcat": (slugcat or "").lower() or None,
                "layer": layer_id,
                "px": px_per_tile,
                "pxPerTile": result.get("pxPerTile"),
                "fit": fit_width,
                "crop": list(crop) if crop else None,
                "sky": sky,
                "water": bool(water),
                "w": result.get("width"),
                "h": result.get("height"),
                "builtAt": int(time.time()),
                "src": {"path": room_path, "mtime": st.st_mtime_ns, "size": st.st_size},
            }, crop)

    if use_cache and cache_key:
        with _render_lock:
            _render_cache[cache_key] = dict(result)
            _render_cache.move_to_end(cache_key)
            while len(_render_cache) > _RENDER_CACHE_MAX:
                _render_cache.popitem(last=False)
    return result


def _render_uncached(region: dict, room_path: str, layer_id: str | None, slugcat: str | None,
                     px_per_tile: int, sky: str, water: bool, fit_width: int = 0,
                     abort=None, crop: tuple[int, int, int, int] | None = None) -> dict:
    geo = room_geo.load(room_path)                     # w / h / cells（与矢量图同一份）

    rect_canvas = rect_out = None
    crop_box = None
    if crop:
        tx0, ty0, tx1, ty1 = crop
        tx0 = max(0, min(int(tx0), geo["w"]))
        ty0 = max(0, min(int(ty0), geo["h"]))
        tx1 = max(tx0 + 1, min(int(tx1), geo["w"]))
        ty1 = max(ty0 + 1, min(int(ty1), geo["h"]))
        if (tx0, ty0, tx1, ty1) != tuple(crop):
            crop = (tx0, ty0, tx1, ty1)
        crop_box = crop
        # 画布矩形按 PX_PER_TILE（20）算，输出矩形按实际密度算——两者必须都对齐到
        # tile 边界，否则裁出来的图叠在整图上会差半个像素。
        rect_canvas = (tx0 * PX_PER_TILE, ty0 * PX_PER_TILE,
                       tx1 * PX_PER_TILE, ty1 * PX_PER_TILE)
        rect_out = (tx0 * px_per_tile, ty0 * px_per_tile,
                    tx1 * px_per_tile, ty1 * px_per_tile)

    if fit_width and not crop:
        native = geo["w"] * PX_PER_TILE
        if native > fit_width:
            px_per_tile = max(4, min(px_per_tile, int(round(PX_PER_TILE * fit_width / native))))

    with open(room_path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    water_level, water_front = _room_header(lines)
    cameras = _parse_cameras(lines)
    region_name = _region_name(room_path)
    roots = asset_roots(region, layer_id)

    cfg = Settings(roots, region_name, slugcat, room_path)

    pal_a = _load_palette_png(roots, cfg.palette)[2]
    if cfg.fade_palette >= 0:
        pal_b = _load_palette_png(roots, cfg.fade_palette)[2]
    else:
        pal_b = pal_a
    ec = _load_effect_colors(roots)
    if ec:
        pal_a = _apply_effect_colors(pal_a, ec, cfg.effect_color_a, cfg.effect_color_b)
        pal_b = _apply_effect_colors(pal_b, ec, cfg.effect_color_a, cfg.effect_color_b)
    noise = _load_noise(roots)

    # RoomCamera.cs：clouds>=1 视为暗环境（light=-1），palette 走下半张（dark 行）
    params = _Params()
    params.light = -1.0 if cfg.clouds >= 1.0 else 1.0
    params.grime = cfg.grime
    params.darkness = 1.0 - cfg.effect("Darkness")
    params.contrast = 1.0 + cfg.effect("Contrast") * 2.0
    params.saturation = 1.0 - cfg.effect("Desaturation")
    params.hue = 360.0 * cfg.effect("Hue")
    params.brightness = cfg.effect("Brightness")
    params.water_enabled = bool(water)
    # 门房间的水深另有口径（0 / 1 / 2），本期静态近似不需要

    canvas, missing = _stitch(room_path, geo, cameras, abort, rect_canvas)
    # 裁剪模式下大部分摄像机没解码，`covered` 可能是空的——这时看「有没有摄像机
    # 存在」而不是看像素，否则一块全空洞的裁块会被误判成缺纹理。
    if not any(canvas.covered) and not any(c[2] > 0 for c in canvas.cams):
        raise RenderError("no_texture", "这间房没有任何地形纹理（_1.png 缺失）")

    # 每个摄像机的 fade 权重可能不同 → 各自一份 32×8 调色板，逐像素按来源摄像机取
    pals = []
    for index in range(len(cameras)):
        blend = cfg.fade_for_camera(index)
        pal = _effective_palette(pal_a, pal_b, blend, 0.0)
        fog = 1.0 - pal[7][9][0]
        if pal[7][9][0] == 0.0 and pal[7][9][2] > 0.0:
            fog = 1.0 + pal[7][9][2]
        params.fog_amount = fog
        pals.append(pal)

    ow, oh, rgba = _shade(canvas, pals, noise, params, px_per_tile, sky, geo, abort, rect_out)

    if params.water_enabled and water_level >= 0:
        _water(rgba, ow, oh, canvas, dict(geo, water_level=water_level, water_front=water_front),
               pals[0], cfg, params, px_per_tile, abort, rect_out)

    # 空洞（无摄像机覆盖）在着色/水面之后补，取色才是「最终颜色」
    void_px = _fill_void(rgba, ow, oh, canvas, geo, pals, px_per_tile, sky, rect_out)

    png = encode_png(ow, oh, rgba)
    return {
        "ok": True,
        "room": (lines[0].strip() if lines else "") or os.path.splitext(os.path.basename(room_path))[0],
        "path": room_path,
        "png": png,
        "width": ow,
        "height": oh,
        "pxPerTile": px_per_tile,
        "crop": list(crop_box) if crop_box else None,
        "sky": sky,
        "engine": "python",
        "bytes": len(png),
        "meta": {
            "region": region_name,
            "size": [geo["w"], geo["h"]],
            "cameras": [list(c) for c in cameras],
            "missingTextures": missing,
            "settings": cfg.path,
            "templateLayers": len(cfg.layers),
            "template": cfg.kv.get("Template"),
            "palette": cfg.palette,
            "fadePalette": cfg.fade_palette,
            "fades": cfg.fades,
            "effectColorA": cfg.effect_color_a,
            "effectColorB": cfg.effect_color_b,
            "grime": cfg.grime,
            "clouds": cfg.clouds,
            "light": params.light,
            "fog": round(params.fog_amount, 4),
            "effects": cfg.effects,
            "waterLevel": water_level,
            "waterFront": water_front,
            "slugcat": (slugcat or "").lower() or None,
            "skyColor": [round(c * 255) for c in pals[0][7][0]],
            "voidPixels": void_px,
        },
    }


def bench(region: dict, room: str, repeats: int = 1, **kwargs) -> dict:
    """计时用：跑 repeats 次（不吃缓存），返回各次耗时。"""
    times = []
    result = {}
    for _ in range(max(1, repeats)):
        result = render(region, room, use_cache=False, **kwargs)
        if not result.get("ok"):
            return result
        times.append(result.get("ms"))
    return {"ok": True, "times": times, "bytes": result.get("bytes"),
            "size": [result.get("width"), result.get("height")]}
