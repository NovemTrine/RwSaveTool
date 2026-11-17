"""房间渲染图的磁盘缓存（V1.2 · M3）。

位置：`region_data/_roomcache/<CODE>/<ROOM>__<角色>__<px>__<fit>.png` + 同名 `.json`

**为什么要落盘**：冷渲染 0.4~8 s（大头是反 PNG 行过滤器），而读盘只要 5~12 ms。
房间卡是"来回翻"的用法——看一间、点出口跳走、再跳回来。内存缓存（进程内几张）
救不了重启，也救不了跳转后的第一次，只有落盘能。

**失效原则：宁多删，不可错用。** 三类触发：

| 触发 | 处理 |
|---|---|
| 房间文件的 mtime / size 变了 | `load()` 对不上就返回 None，重渲 |
| 缓存格式版本升了 | 同上（`CACHE_VER`） |
| 区域被重导 / 删层 / 删来源 | 整目录删掉（`region_store` 里的调用点） |

**参数走文件名而不是元数据**：角色（`_settings-<角色>.txt` 会换调色板）、密度、
天空、水面各自一份，互不覆盖。所以切角色回来不需要重算——这也是计划书 §4.9 的要求。

写盘一律 temp + `os.replace`，断电最多丢一格，不会留半张图让下次读到花屏。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading

from . import paths

CACHE_VER = 4
"""缓存格式版本。渲染算法一变（比如水面改了）就在这里 +1，旧图全部作废。

v2：修正 `cells` 索引（行优先）与水面行号朝向，并新增空洞填充（计划书 §19/§20）
    —— v1 的图全都是错的，必须整体作废。
v3：水面掩码改「只看格子」（此前 `R<=1` 在 8 位值下把天空全排除了，1368 间有水
    房间几乎没水），水面带改成半透明叠加 —— v2 的图在**有水房间**上全部要重算。
v4：水体统一按 `SL_F01` 的「整幅半透明笼罩」画，`WaterFront` 不再影响结果
    （2026-11-18 02:23 拍板）—— v3 里 `front = 0` 的房间是实色色块，必须作废。
"""

MAX_BYTES = 200 * 1024 * 1024
"""总盘占用上限，超了按最久没写入的淘汰。计划书 §4.5：400 间约 50~100 MB。"""

TRIM_EVERY = 8
"""每写这么多张才扫一次目录。扫一次约 5 ms，但没必要每张都扫。"""

DIR_NAME = "_roomcache"

_write_count = 0
_trim_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def cache_root() -> str:
    return os.path.join(paths.data_dir(), DIR_NAME)


def region_dir(code: str) -> str:
    return os.path.join(cache_root(), _safe(str(code or "").upper() or "UNKNOWN"))


def _safe(name: str) -> str:
    """文件名白名单。房间名/区域名理论上都很干净，但模组什么都可能起。"""
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch in "-_. ") else "_")
    text = "".join(out).strip() or "x"
    if text != str(name):      # 改过名就补一段哈希，避免两个怪名字撞到一起
        text += "~" + hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:6]
    return text


def entry(code: str, room: str, slugcat: str | None, px: int, fit: int,
          crop: tuple | None = None) -> tuple[str, str]:
    base = "%s__%s__%d__%d" % (_safe(room), _safe(slugcat or "none"), int(px), int(fit or 0))
    if crop:
        # 视口裁块（B 档）：`c<tx0>-<ty0>-<tw>-<th>`，单位是 tile
        base += "__c%d-%d-%d-%d" % (int(crop[0]), int(crop[1]),
                                    int(crop[2]) - int(crop[0]), int(crop[3]) - int(crop[1]))
    folder = region_dir(code)
    return os.path.join(folder, base + ".png"), os.path.join(folder, base + ".json")


def _norm(path: str | None) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------
def load(code: str, room: str, slugcat: str | None, px: int, fit: int,
         src_path: str | None, src_mtime: int | None, src_size: int | None,
         sky: str = "fill", water: bool = True, crop: tuple | None = None) -> dict | None:
    """命中就返回 `{png, w, h, pxPerTile, builtAt}`，否则 None。

    所有「能不能用」的判断都在这里，调用方不需要再校验——这样只有一个地方会错。
    """
    png_path, meta_path = entry(code, room, slugcat, px, fit, crop)
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or info.get("ver") != CACHE_VER:
        return None
    if info.get("sky") != sky or bool(info.get("water")) != bool(water):
        return None
    src = info.get("src") or {}
    if (_norm(src.get("path")) != _norm(src_path)
            or src.get("mtime") != src_mtime
            or src.get("size") != src_size):
        return None
    try:
        with open(png_path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if not data or not data.startswith(b"\x89PNG"):
        return None
    _internal = ("ver", "src", "sky", "water", "w", "h", "pxPerTile", "builtAt", "bytes")
    return {
        "png": data,
        "w": info.get("w"),
        "h": info.get("h"),
        "pxPerTile": info.get("pxPerTile"),
        "builtAt": info.get("builtAt"),
        "bytes": info.get("bytes") or len(data),
        # 侧车文件里本来就是整份渲染 meta（store 是 dict(meta) + 几个内部键），
        # 命中时原样还回去，否则调用方拿到空的 meta（帧率信息、尺寸、摄像机全丢）。
        "meta": {k: v for k, v in info.items() if k not in _internal},
    }


def store(code: str, room: str, slugcat: str | None, px: int, fit: int,
          png: bytes, meta: dict, crop: tuple | None = None) -> bool:
    """写盘。先图后元数据——元数据存在即代表整张图可用。"""
    global _write_count
    if not png:
        return False
    purge_stale()
    png_path, meta_path = entry(code, room, slugcat, px, fit, crop)
    payload = dict(meta)
    payload["ver"] = CACHE_VER
    payload["bytes"] = len(png)
    try:
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        _atomic(png_path, png)
        _atomic(meta_path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except OSError:
        return False

    with _trim_lock:
        _write_count += 1
        need_trim = (_write_count % TRIM_EVERY) == 0
    if need_trim:
        trim()
    return True


def _atomic(path: str, data: bytes) -> None:
    tmp = "%s.tmp%d" % (path, threading.get_ident())
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 统计与清理
# ---------------------------------------------------------------------------
def _iter_entries():
    root = cache_root()
    if not os.path.isdir(root):
        return
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".png") or name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            try:
                yield path, os.stat(path)
            except OSError:
                continue


def stats() -> dict:
    purge_stale()
    total = count = 0
    for _path, st in _iter_entries():
        total += st.st_size
        count += 1
    return {"bytes": total, "files": count, "path": cache_root(), "limit": MAX_BYTES}


_stale_done = False


def purge_stale() -> int:
    """删掉版本号对不上的旧缓存，返回删了几张。

    渲染算法一改（比如这次的 `cells` 索引与水面行号），旧图**全是错的**，但文件名
    里不带版本，所以 `load()` 只是拒绝使用——那些文件会一直占着 200 MB 的额度，
    还不如直接清掉。只在第一次 `stats()` / `store()` 时扫一遍（几百个文件约 5 ms）。
    """
    global _stale_done
    if _stale_done:
        return 0
    _stale_done = True
    root = cache_root()
    if not os.path.isdir(root):
        return 0
    removed = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".json") or name.startswith("."):
                continue
            meta_path = os.path.join(dirpath, name)
            try:
                with open(meta_path, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
                ver = info.get("ver") if isinstance(info, dict) else None
            except (OSError, ValueError):
                ver = None
            if ver == CACHE_VER:
                continue
            try:
                png_path = meta_path[:-5] + ".png"
                if os.path.isfile(png_path):
                    os.remove(png_path)
                os.remove(meta_path)
                removed += 1
            except OSError:
                continue
    return removed


def trim(max_bytes: int = MAX_BYTES) -> int:
    """按 mtime 从旧到新删，直到回到上限以内。返回删掉几张。"""
    entries = sorted(_iter_entries(), key=lambda item: item[1].st_mtime)
    total = sum(st.st_size for _p, st in entries)
    removed = 0
    while total > max_bytes and entries:
        path, st = entries.pop(0)
        try:
            os.remove(path)
            meta = path[:-4] + ".json"
            if os.path.isfile(meta):
                os.remove(meta)
            total -= st.st_size
            removed += 1
        except OSError:
            total -= st.st_size      # 删不掉就别死循环，当它不存在
    return removed


def _inside_cache(target: str) -> bool:
    """只允许删缓存目录里的东西——这个函数存在的唯一理由是防止路径拼错删到别处。"""
    root = os.path.abspath(cache_root())
    path = os.path.abspath(target)
    return path == root or path.startswith(root + os.sep)


def purge_region(code: str) -> int:
    """删掉某个区域的全部缓存。区域不存在也当成功（幂等）。"""
    target = region_dir(code)
    if not _inside_cache(target):
        return 0
    if not os.path.isdir(target):
        return 0
    try:
        shutil.rmtree(target)
        return 1
    except OSError:
        return 0


def clear_all() -> dict:
    before = stats()
    root = cache_root()
    if not _inside_cache(root) or not os.path.isdir(root):
        return {"ok": True, "freed": 0, "removed": 0}
    try:
        shutil.rmtree(root)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "freed": 0, "removed": 0}
    return {"ok": True, "freed": before.get("bytes") or 0, "removed": before.get("files") or 0}
