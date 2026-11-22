"""前端 ↔ Python 桥接 API。

只暴露必要能力：读存档、只读导入模组、管理导入缓存、读底图、读写配置。
不提供任何写存档 / 写模组目录的方法。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque, OrderedDict

from . import (
    __release_date__,
    __version__,
    __version_name__,
    mod_importer,
    official_world,
    paths,
    region_store,
    room_geo,
    room_cache,
    room_render,
    save_io,
    sources,
    translations,
)
from .regmap import adapter as regmap_adapter
from .regmap import svg as regmap_svg
from .regmap import thumbnail as regmap_thumb

try:  # webview 只在桌面壳里存在
    import webview
except Exception:  # pragma: no cover
    webview = None


# 渲染是 CPU 密集的，而 pywebview 给每个 JS 调用都单起一个线程：
# 连续点几间房会同时算，风扇起飞还不一定先算完用户要看的那间。
# 所以串成一条门闩，并且「后来者优先」——在门口排队时发现已经有更新的请求，
# 就直接作废自己，把 CPU 让出去。
_render_gate = threading.Lock()

# ---- 区域地图布局（regmap）-----------------------------------------------
# 布局也是 CPU 密集的（中位 0.7 s、最慢 4 s）。pywebview 每个 JS 调用一个线程，
# 用户连点几个区域就会几个布局同时跑；这里同样串成一条门闩，并按
# (区域, 战役, 参数摘要) 做内存缓存——同参数再打开应当 < 50 ms。
_regmap_gate = threading.Lock()
_regmap_cache: "OrderedDict[str, dict]" = OrderedDict()
_REGMA_CACHE_MAX = 6

# SVG 是字符串，单区 0.4–1.5 MB；只留最近 3 个，命中时省下 1 s 的拼串
_regmap_svg_cache: "OrderedDict[str, dict]" = OrderedDict()
_REGMA_SVG_MAX = 4

# 高清层要重新按密度铺缩略图，而缩略图要靠 `nodes[].room`（房间格数据）。
# `regmap_map` 的返回值为了省内存会把 room 摘掉，所以这里另存**一份带 room 的**
# 原始布局，只留最近 1 个区：换来"放大后按需换高清"，代价是最多一个区的房间格常驻。
_regmap_raw: "OrderedDict[str, dict]" = OrderedDict()
_REGMA_RAW_MAX = 1

# SVG 缓存 key 里带一个**渲染版本号**：改了画法（哪怕 key 的其他参数一个没动）就 +1，
# 否则同一次会话里切回来还是旧图——内存缓存不落盘，但进程是长活的，用户会以为没生效。
# 2 = V1.17（高清层：杆/管的假竖刺折回源格）；3 = V1.18（№2 删标注：图标/物件/业力门下线）。
_REGMA_RENDER_V = 3


def _room_colors(code: str, geo: dict, region: dict | None) -> dict | None:
    """这间房该用的「可通行 / 背景结构」色；按子区域分组取，取不到返回 `None`。

    `_colors.json` 是 `core/regmap/colors.py` 的缓存（区域地图算一次就落盘）。
    """
    from .regmap import colors as _colors
    rc = (_colors.load_cache() or {}).get(str(code or "").upper())
    if not rc:
        return None
    groups = {str(g.get("sub") or ""): g for g in (rc.get("groups") or [])}
    if not groups:
        return None
    want = ""
    target = str(geo.get("name") or geo.get("room") or "").upper()
    for layer in (region or {}).get("layers") or []:
        for r in layer.get("rooms") or []:
            if str(r.get("name") or "").upper() == target:
                sub = str(r.get("subregion") or "").strip()
                if sub and sub in groups:
                    want = sub
                break
    g = groups.get(want) or groups.get("")
    if not g:
        return None
    return {"air": g.get("air"), "struct": g.get("struct"), "sub": want}


def _regmap_key(code: str, slugcat: str, opts: dict | None) -> str:
    # `_REGMA_RENDER_V` 也进 key：页面 F5 重载时 Python 进程还活着，内存缓存不会清，
    # 不带版本号就会出现"改了画法、页面上还是旧图"。
    return json.dumps({"c": str(code).upper(), "s": str(slugcat or "").upper(),
                       "o": opts or {}, "v": _REGMA_RENDER_V},
                      sort_keys=True, default=str)


def _regmap_public(result: dict) -> dict:
    """给前端的瘦身版：`nodes[]` 去掉 `room`（Python 对象，不可序列化且占内存）。

    注意**不能原地 pop**：`_regmap_raw` 还指着同一批节点，摘掉就再也做不了高清层了。
    这里复制一层浅字典，runs / over / path 这些照样共用（只读）。
    """
    out = dict(result)
    out["nodes"] = [{k: v for k, v in n.items() if k != "room"}
                    for n in result.get("nodes") or []]
    return out

# ---- 预取队列（M3）-------------------------------------------------------
# 用户点开一间房后，他最可能点的下一间就是右栏那几个出口。与其等他点，
# 不如提前把图算好落盘——命中时从 2 s 变成 12 ms。
#
# 三条纪律：
#   · 永远让路：有用户请求在等门闩时，预取一个都不许算（`_user_waiting`）；
#   · 新款作废旧款：`_prefetch_serial` 一变，队列里的旧任务全部失效；
#   · 只入队不阻塞：`room_prefetch` 立刻返回，界面绝不等它。
_prefetch_q: "deque[tuple]" = deque()
_prefetch_lock = threading.Lock()
_prefetch_serial = 0
_prefetch_thread = None
_user_waiting = 0
_last_user_at = 0.0
_PREFETCH_MAX = 6
_PREFETCH_QUIET = 0.4
"""用户最后一次请求之后要静默这么久，预取才允许开工。用户连点几间房时它会一直让路。"""

# 存档里写的是 `White` / `Saint` 这种键，渲染内核按正式名找 `<room>_settings-<名>.txt`。
# 收敛成同一个键还有个副作用是好事：同一间房不会因为传了两种写法被算成两份缓存。
_SLUGCAT_CANON = {
    "white": "survivor", "survivor": "survivor",
    "yellow": "monk", "monk": "monk",
    "red": "hunter", "hunter": "hunter",
    "spear": "spearmaster", "spearmaster": "spearmaster",
}


def _canon_slugcat(value: str | None) -> str | None:
    raw = "".join(ch for ch in str(value or "").lower() if ch.isalnum())
    if not raw:
        return None
    return _SLUGCAT_CANON.get(raw, raw)


def _ensure_prefetch_worker() -> None:
    """按需起一个常驻线程。没有预取任务时它只是每 100 ms 醒一次，几乎不耗 CPU。"""
    global _prefetch_thread
    with _prefetch_lock:
        if _prefetch_thread is not None and _prefetch_thread.is_alive():
            return
        _prefetch_thread = threading.Thread(
            target=_prefetch_loop, name="room-prefetch", daemon=True)
        _prefetch_thread.start()


def _prefetch_loop() -> None:
    while True:
        if _user_waiting or (time.time() - _last_user_at) < _PREFETCH_QUIET:
            # 用户正在渲染、或者刚点完还在看：预取一个都不许算。
            # 连点几间房时这条会让预取一直让路——那是正确的，用户优先。
            time.sleep(0.05)
            continue
        with _prefetch_lock:
            job = _prefetch_q.popleft() if _prefetch_q else None
            current = _prefetch_serial
        if job is None:
            time.sleep(0.10)
            continue

        code, room, layer_id, slugcat, fit_width, serial = job
        if serial != current:
            continue                       # 这一批已经过期（用户换了房间）
        region = region_store.get_region(code)
        if not region:
            continue
        with _render_gate:
            if _user_waiting:
                # 排到门口时用户来了：这张直接放弃。宁可白排一次，
                # 也不能让用户等一个他并不需要的渲染。
                continue
            try:
                room_render.render(
                    region, room, layer_id, _canon_slugcat(slugcat),
                    px_per_tile=room_render.PX_PER_TILE, sky="fill", water=True,
                    use_cache=True, fit_width=max(0, int(fit_width or 0)),
                    # 用户一来就自断：预取占的是空闲时间，不该让任何人排队等它。
                    # 中断粒度是 32 行（几毫秒），放弃的那张不写盘，下次点开会重算。
                    abort=lambda: _user_waiting > 0 or _prefetch_serial != serial,
                )
            except Exception:  # noqa: BLE001 - 预取失败（含主动中断）没有任何后果
                pass
        time.sleep(0.05)                   # 两间之间留一口气，别把风扇拉满


class Api:
    def __init__(self) -> None:
        self._window = None
        self._render_ticket = 0
        self._ticket_lock = threading.Lock()

    def attach(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def app_info(self) -> dict:
        return {
            "name": "RwSaveTool",
            "version": __version__,
            "versionName": __version_name__,
            "releaseDate": __release_date__,
            "dataDir": paths.data_dir(),
            "configPath": paths.config_path(),
            "defaultSaveDir": save_io.default_dir(),
            "hasBridge": True,
        }

    def config(self) -> dict:
        data = paths.load_config()
        data["_state"] = paths.config_state()
        return data

    def save_config(self, patch: dict) -> dict:
        return paths.save_config(patch or {})

    # ------------------------------------------------------------------
    # 存档
    # ------------------------------------------------------------------
    def list_slots(self) -> list[dict]:
        return save_io.slots()

    def read_save(self, path: str) -> dict:
        result = save_io.read_save_file(path)
        if result.get("ok"):
            cfg = paths.load_config()
            cfg["lastSavePath"] = result["path"]
            paths.save_config(cfg)
        return result

    def pick_save(self) -> dict:
        if not self._window or webview is None:
            return {"ok": False, "error": "文件对话框不可用"}
        picked = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("雨世界存档 (sav;sav2;sav3;*.txt)", "所有文件 (*.*)"),
        )
        if not picked:
            return {"ok": False, "canceled": True}
        return self.read_save(picked[0])

    # ------------------------------------------------------------------
    # 模组导入（只读）
    # ------------------------------------------------------------------
    def pick_mod_dir(self, source_name: str | None = None) -> dict:
        if not self._window or webview is None:
            return {"ok": False, "error": "目录对话框不可用"}
        picked = self._window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if not picked:
            return {"ok": False, "canceled": True}
        return self.import_mod_path(picked[0], source_name=source_name)

    def import_mod_path(self, path: str, force: bool = False, source_name: str | None = None) -> dict:
        result = mod_importer.import_mod(path, source_name=source_name)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "导入失败"}

        save_result = region_store.save_regions(result.get("regions") or [], force=bool(force))
        if save_result.get("needsConfirm"):
            return {
                "ok": False,
                "needConfirm": True,
                "shrink": [item["shrink"] for item in save_result["needsConfirm"]],
                "message": save_result["needsConfirm"][0].get("error"),
                "path": path,
            }

        cfg = paths.load_config()
        dirs = list(cfg.get("importDirs") or [])
        norm = os.path.abspath(path)
        if norm not in dirs:
            dirs.append(norm)
            cfg["importDirs"] = dirs[-20:]
            paths.save_config(cfg)

        return {
            "ok": bool(save_result.get("ok")),
            "saved": save_result.get("saved") or [],
            "failed": save_result.get("failed") or [],
            "mods": result.get("mods") or [],
            "warnings": result.get("warnings") or [],
            "multi": result.get("multi", False),
            "sourceName": (source_name or "").strip() or None,
        }

    # ------------------------------------------------------------------
    # 官方源（游戏本体，只读）
    # ------------------------------------------------------------------
    def game_info(self) -> dict:
        installs = official_world.find_installations()
        cfg = paths.load_config()
        configured = cfg.get("gamePath")
        chosen = configured if configured and os.path.isdir(configured) else (
            installs[0]["root"] if installs else None
        )
        detail = official_world.describe(chosen) if chosen else None
        return {
            "ok": bool(chosen),
            "configured": configured,
            "found": [{"root": i["root"], "packs": [p["label"] for p in i["packs"]]} for i in installs],
            "root": chosen,
            "packs": (detail or {}).get("packs") or [],
            "regions": (detail or {}).get("regions") or {},
            "regionCount": (detail or {}).get("regionCount") or 0,
        }

    def pick_game_dir(self) -> dict:
        if not self._window or webview is None:
            return {"ok": False, "error": "目录对话框不可用"}
        picked = self._window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if not picked:
            return {"ok": False, "canceled": True}
        return self.set_game_path(picked[0])

    def set_game_path(self, path: str) -> dict:
        if not path or not os.path.isdir(path):
            return {"ok": False, "error": "目录不存在"}
        root = os.path.normpath(path)
        # 允许用户选中 StreamingAssets 或游戏根目录
        if os.path.basename(root).lower() == "streamingassets":
            root = os.path.dirname(os.path.dirname(root))
        if not os.path.isdir(os.path.join(root, "RainWorld_Data", "StreamingAssets")):
            return {"ok": False, "error": "这个目录里没有 RainWorld_Data/StreamingAssets，不像雨世界安装目录"}
        cfg = paths.load_config()
        cfg["gamePath"] = root
        paths.save_config(cfg)
        return {"ok": True, "root": root, **self.game_info()}

    def import_official_path(self, path: str | None = None, force: bool = False) -> dict:
        """导入游戏本体的官方区域数据（基础层）。"""
        result = official_world.import_official(path or None)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "导入失败"}

        save_result = region_store.save_regions(result.get("regions") or [], force=bool(force))
        if save_result.get("needsConfirm"):
            return {
                "ok": False,
                "needConfirm": True,
                "shrink": [item["shrink"] for item in save_result["needsConfirm"]],
                "message": save_result["needsConfirm"][0].get("error"),
            }

        cfg = paths.load_config()
        cfg["gamePath"] = result.get("root")
        paths.save_config(cfg)

        return {
            "ok": bool(save_result.get("ok")),
            "root": result.get("root"),
            "saved": save_result.get("saved") or [],
            "failed": save_result.get("failed") or [],
            "packs": result.get("packs") or [],
            "warnings": result.get("warnings") or [],
        }

    # ------------------------------------------------------------------
    # 来源（Original / Downpour / Watcher / Mod…）
    # ------------------------------------------------------------------
    def sources(self) -> dict:
        return {
            "ok": True,
            "sources": sources.list_sources(),
            "presets": sources.PRESETS,
        }

    def rename_source(self, layer_id: str, name: str) -> dict:
        return sources.rename(layer_id, name)

    def set_source_enabled(self, layer_id: str, enabled: bool) -> dict:
        return sources.set_enabled(layer_id, enabled)

    # ------------------------------------------------------------------
    # 自定义译名
    # ------------------------------------------------------------------
    def translations(self) -> dict:
        return translations.load()

    def translation_summary(self) -> dict:
        return translations.summary()

    def save_translations(self, payload: dict) -> dict:
        return translations.save(payload or {})

    def set_translation(self, kind: str, key: str, value: str) -> dict:
        return translations.set_one(kind, key, value)

    def reset_translations(self, kind: str = "") -> dict:
        return translations.reset(kind or "")

    def pick_text_file(self, max_bytes: int = 1024 * 1024) -> dict:
        """挑一个文本文件并读回内容（供「批量翻译」整批导入用）。

        解析与匹配留在界面侧（五张表在那里，抄一份到后端必然漂移），
        这里只负责：弹窗 → 读字节 → 猜编码 → 原样返回文本。
        """
        if not self._window or webview is None:
            return {"ok": False, "error": "文件对话框不可用"}
        picked = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("文本文件 (*.txt)", "所有文件 (*.*)"),
        )
        if not picked:
            return {"ok": False, "canceled": True}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return {"ok": False, "error": f"读不到文件：{exc}"}
        if size > max_bytes:
            return {"ok": False, "error": f"文件超过 {max_bytes // 1024 // 1024} MB，请先拆分"}
        # 老记事本存的 ANSI 是 GBK；utf-8-sig 先试，能吃掉 BOM
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                with open(path, "r", encoding=enc) as fh:
                    return {"ok": True, "path": path, "text": fh.read(), "encoding": enc}
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                return {"ok": False, "error": f"读取失败：{exc}"}
        return {"ok": False, "error": "无法识别文件编码，请另存为 UTF-8"}

    # ------------------------------------------------------------------
    # 导入缓存管理
    # ------------------------------------------------------------------
    def regions(self) -> list[dict]:
        return region_store.summary()

    def region_access(self) -> dict:
        """区域可达性提示表（只读）。

        只用于界面上「这个区域通常只有某角色能进」的说明，不做任何强制过滤：
        实际显示哪些区域由「有活动 + 手动挑选」决定，避免猜错把用户能去的地方藏掉。
        """
        path = paths.region_access_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("regions", {})
                return data
        except (OSError, ValueError):
            pass
        return {"regions": {}}

    def region_reach(self) -> dict:
        """角色可达区域表（只读）。

        `{"regions": {"LC": {"only": ["artificer"]}, "W": {"prefix": true, ...}}}`；
        没列出的区域一律按"所有角色都能到"处理，避免表写漏就把地方藏掉。
        """
        path = paths.region_reach_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("regions", {})
                return data
        except (OSError, ValueError):
            pass
        return {"regions": {}}

    def region_detail(self, code: str) -> dict:
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "该区域没有导入数据"}
        return {"ok": True, "region": region}

    # ------------------------------------------------------------------
    # 区域地图（几何布局）
    # ------------------------------------------------------------------
    def regmap_probe(self, code: str, slugcat: str = "") -> dict:
        """这个区域能不能排布：房间数、缺地形数、无地图矩形数、可用战役。

        只读 `region_data`，不写任何东西；界面用它决定「直接画」还是「给提示」。
        """
        return regmap_adapter.probe(code, slugcat or "")

    def regmap_map(self, code: str, slugcat: str = "", opts: dict | None = None) -> dict:
        """算一张区域地图的几何布局，返回纯数据（节点 / 连线 / 统计）。

        缓存键 = (区域, 战役, 参数)。命中时 `cached=True` 且通常 < 50 ms；
        未命中时串行计算（`_regmap_gate`），最慢的区域约 4 s。
        """
        key = _regmap_key(code, slugcat, opts)
        hit = _regmap_cache.get(key)
        if hit is not None:
            _regmap_cache.move_to_end(key)
            return dict(hit, cached=True, ms=0)

        with _regmap_gate:
            hit = _regmap_cache.get(key)          # 等锁期间可能已经有人算完
            if hit is not None:
                _regmap_cache.move_to_end(key)
                return dict(hit, cached=True, ms=0)
            t0 = time.time()
            try:
                result = regmap_adapter.build(code, slugcat or "", opts or {})
            except FileNotFoundError as exc:
                return {"ok": False, "error": "no_region", "detail": str(exc)}
            except ValueError as exc:
                return {"ok": False, "error": "bad_rooms", "detail": str(exc)}
            except Exception as exc:               # noqa: BLE001 - 桥接层不抛
                return {"ok": False, "error": "layout_failed", "detail": str(exc)}
            ms = int((time.time() - t0) * 1000)
            _regmap_raw[key] = result             # 带 room 的原件，留给高清层
            _regmap_raw.move_to_end(key)
            while len(_regmap_raw) > _REGMA_RAW_MAX:
                _regmap_raw.popitem(last=False)
            payload = _regmap_public(result)
            payload["ok"] = True
            payload["cached"] = False
            payload["ms"] = ms
            _regmap_cache[key] = payload
            while len(_regmap_cache) > _REGMA_CACHE_MAX:
                _regmap_cache.popitem(last=False)
            return dict(payload)

    def regmap_svg(self, code: str, slugcat: str = "", opts: dict | None = None,
                   width: int = 2400, labels: bool = False, density: int = 2,
                   curve: dict | None = None, link_inner: float | None = None,
                   link_width: float | None = None, bar_scale: float | None = None,
                   anno: dict | None = None) -> dict:
        """区域布局的**自包含 SVG**：地图页直接塞进 DOM，导出也是它。

        为什么不在前端画：画一遍、导出再画一遍，两套代码必然走形；这里出一次，
        页面看到的就是导出到文件的。`width=0` 表示用默认 2400。

        `density` 是缩略密度：2 = 默认（0.4–1.4 MB，远看够用）；4 = 高清层
        （放大后前端按需再要一次，体积约 2–3 倍，坐标空间与默认层**完全相同**，
        所以前端只要换 <svg> 元素、viewBox 不用动）。

        S4 的调参走 `curve`（mode/k/min/max）、`link_inner`、`link_width`、`bar_scale`；
        它们都要进缓存 key，否则拖完滑杆会拿到上一次的图。

        `anno`（W4 / №2）是标注开关（**只剩** `sub` 子区域色、`labels` 子区域名），
        同样进缓存 key——`True` = 全开，`None`/`False` = 全关。旧调用方传
        `kind/marks/gates` 不会报错，但那三类已经删了。

        高清层要拿带 `room` 的原始布局重新铺缩略图，所以先查 `_regmap_raw`；
        没命中才自己算一遍（慢，但只在天关掉页面又回来时发生）。
        """
        width = int(width or 2400)
        density = max(1, min(6, int(density or 2)))
        cv = curve if isinstance(curve, dict) else {}
        av = None
        if isinstance(anno, dict):
            av = "".join("%s=%d" % (k, int(bool(anno.get(k, 1)))) for k in sorted(anno))
        elif anno:
            av = "all"
        extra = "|%s/%.2f/%.2f/%.2f|%.2f|%s|%.3f|%s|r%d" % (
            (cv.get("mode") or "normal"),
            float(cv.get("k", 0.42)), float(cv.get("min", 1.5)), float(cv.get("max", 0) or 0),
            0.5 if link_inner is None else float(link_inner),
            "auto" if link_width is None else "%.2f" % float(link_width),
            1.0 if bar_scale is None else float(bar_scale),
            av or "-", _REGMA_RENDER_V)
        key = "%s|%d|%d|%d%s" % (_regmap_key(code, slugcat, opts), width,
                                 1 if labels else 0, density, extra)
        hit = _regmap_svg_cache.get(key)
        if hit is not None:
            _regmap_svg_cache.move_to_end(key)
            return dict(hit, cached=True)

        mapkey = _regmap_key(code, slugcat, opts)
        raw = _regmap_raw.get(mapkey)
        if raw is None:
            # 先让它把布局算出来（顺带把带 room 的原件放进 `_regmap_raw`）；
            # 注意命中 map 缓存时 raw 可能已经过期清掉了，那就只能用公开版（密度 2）。
            res = self.regmap_map(code, slugcat, opts)
            if not res.get("ok"):
                return res
            raw = _regmap_raw.get(mapkey)
        else:
            res = None

        layout = None
        if density != 2 and raw is not None:
            nodes = [dict(n) for n in raw["nodes"]]      # 浅拷贝：prepare 会改 runs/over
            try:
                regmap_thumb.prepare(nodes, density=density)
            except Exception:                            # noqa: BLE001 - 退回默认层
                nodes = None
            if nodes is not None:
                # `colors` 必须一起带过来：不带的话高清层会落回 `PALETTE` 的兜底色
                # （可通行变成 #8C97AF 那片灰蓝，而不是区域调色板提取色）——
                # №4 的"子区域色当可通行底色"就只在默认层生效了，放大一看是另一套颜色。
                layout = {"nodes": nodes, "edges": raw["edges"], "stats": raw["stats"],
                          "colors": raw.get("colors")}

        if layout is None:
            if res is None:
                res = self.regmap_map(code, slugcat, opts)
                if not res.get("ok"):
                    return res
            layout = res

        try:
            r = regmap_svg.build_svg(
                layout, width=width, labels=bool(labels), curve=cv,
                link_inner=link_inner, link_width=link_width,
                bar_scale=1.0 if bar_scale is None else float(bar_scale),
                anno=anno if isinstance(anno, dict) else (True if anno else False))
        except Exception as exc:                   # noqa: BLE001 - 桥接层不抛
            return {"ok": False, "error": "svg_failed", "detail": str(exc)}
        payload = {"ok": True, "svg": r["svg"], "w": r["w"], "h": r["h"],
                   "bytes": r["bytes"], "rooms": r["rooms"], "links": r["links"],
                   "annos": r.get("annos", 0),
                   "density": density, "cached": False, "ms": 0}
        _regmap_svg_cache[key] = payload
        while len(_regmap_svg_cache) > _REGMA_SVG_MAX:
            _regmap_svg_cache.popitem(last=False)
        return dict(payload)

    def delete_region(self, code: str) -> dict:
        return region_store.delete_region(code)

    def delete_layer(self, code: str, layer_id: str) -> dict:
        return region_store.delete_layer(code, layer_id)

    def preview_source_delete(self, source_id: str) -> dict:
        """只算不删：这个来源出现在哪些区域 / 多少层 / 多少间房。"""
        return region_store.preview_source_delete(source_id)

    def delete_source(self, source_id: str, clean_refs: bool = True) -> dict:
        """跨区域删掉某个来源的全部层，并清掉指向被删房间的引用。"""
        return region_store.delete_source(source_id, clean_refs)

    def set_override(self, code: str, patch: dict) -> dict:
        region_store.set_override(code, patch or {})
        return {"ok": True}

    def map_image(self, code: str, layer_id: str | None = None, variant: str = "normal") -> dict:
        """返回底图 data URL（只读读取，不复制到缓存）。"""
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "该区域没有导入数据"}

        layer = None
        for item in region.get("layers") or []:
            if layer_id and item.get("id") == layer_id:
                layer = item
                break
        if layer is None:
            layer = (region.get("layers") or [{}])[0]

        image_path = None
        if variant and variant != "normal":
            entry = (layer.get("variants") or {}).get(variant) or {}
            image_path = entry.get("imagePath")
        if not image_path:
            image_path = (layer.get("map") or {}).get("imagePath")
        if not image_path or not os.path.isfile(image_path):
            return {"ok": False, "error": "底图路径不可用"}
        try:
            with open(image_path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            return {"ok": False, "error": f"底图读取失败：{exc}"}
        size = region_store.png_size(image_path)
        return {
            "ok": True,
            "dataUrl": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            "path": image_path,
            "layerId": layer.get("id"),
        }

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def room_geometry(self, code: str, room: str, layer_id: str | None = None) -> dict:
        """房间地形网格（矢量布局用）。

        只读 `<region>-rooms/<room>.txt`（门房间读 `world/gates/`），
        返回 `cells`：行优先、每格一个字符（0=空气 1=实心 2..f=斜面）。
        """
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "no_region", "room": room}
        try:
            geo = room_geo.geometry(region, room, layer_id)
            if geo.get("ok"):
                # 特效层（W4-fx）：房间卡与区域地图共用同一份遮罩，别各算一遍。
                try:
                    from .regmap import fx as _regmap_fx
                    geo["fx"] = _regmap_fx.room_fx_geom(geo.get("path") or "",
                                                        geo.get("w"), geo.get("h"))
                except Exception:                  # noqa: BLE001 - 特效坏了不该影响地形
                    geo["fx"] = None
                # 配色（V1.15 №4/№5）：房间卡与区域地图共用同一份提取色。
                # 只读 `region_data/_colors.json`（地图页算过一次就有），**不**在这里
                # 调 `adapter.load_rooms`——那要 0.4–0.6 s，开卡会明显卡顿。
                try:
                    geo["colors"] = _room_colors(code, geo, region)
                except Exception:              # noqa: BLE001 - 配色坏了就用兜底
                    geo["colors"] = None
            return geo
        except room_geo.RoomGeoError as exc:
            return {"ok": False, "error": "unparsable", "detail": str(exc), "room": room}
        except Exception as exc:  # noqa: BLE001 - 桥接层不向外抛，界面显示错误即可
            return {"ok": False, "error": "unparsable", "detail": str(exc), "room": room}

    # ------------------------------------------------------------------
    # 房间实机渲染（V1.2 · M2）
    # ------------------------------------------------------------------
    def room_render_info(self, code: str) -> dict:
        """「实机」开关能不能出现：只探测素材根，不渲染、不读房间。"""
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "no_region", "available": False}
        return room_render.probe(region)

    def room_render(self, code: str, room: str, layer_id: str | None = None,
                    slugcat: str | None = None, fit_width: int = 1400,
                    crop=None, px=None) -> dict:
        """渲染一间房，返回 PNG 的 data URL。

        **这是同步调用**：冷渲染 0.4–3.7 s，命中磁盘 5~12 ms。界面上必须
        「发出去就不管」——绝不能在 `openRoomCard()` 里 await 它，否则开卡时间翻几倍。
        pywebview 会给每次调用单起线程，所以这里阻塞不会冻住界面。

        返回里的 `source` 说明这次是 memory / disk / render，界面和回归都靠它判断。

        `crop=(tx0, ty0, tx1, ty1)`（tile）是**放大后补细节**用的视口裁块：只解码与它
        相交的摄像机，只着色这一块，所以「整间 196×72 的房」放大到 20 px/tile 也只要
        1.3 s 而不是 20 s（实测 2026-11-18）。裁块只进内存缓存，不落盘。

        裁块**不抢 ticket 号**：它只是「把当前这张看得更清楚」，不该把用户正在等的
        那次开卡挤掉。反过来，一旦有新请求进来（ticket 变了），裁块会立刻中止让路。
        """
        global _prefetch_serial, _user_waiting, _last_user_at
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "no_region", "room": room}

        crop = room_render._norm_crop(crop)
        px = max(4, min(int(px or room_render.PX_PER_TILE), room_render.PX_PER_TILE))
        fit = 0 if crop else max(0, int(fit_width or 0))

        if crop:
            with self._ticket_lock:
                ticket = self._render_ticket          # 只记当前号，不占新号
        else:
            with self._ticket_lock:
                self._render_ticket += 1
                ticket = self._render_ticket
            with _prefetch_lock:
                _prefetch_serial += 1                 # 用户来了，队列里等待的预取全部作废
        _last_user_at = time.time()

        # 命中缓存必须能插队：预取正在算别的房间时，用户开一间**已经缓存好的**房
        # 不该在门闩后面白等一次完整渲染（实测会白等 3.9 s）。查缓存不占门闩。
        fast = room_render.lookup(
            region, room, layer_id, _canon_slugcat(slugcat),
            px, "fill", True, fit, crop)
        if fast:
            png = fast.pop("png", b"") or b""
            fast["dataUrl"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            fast["pngBytes"] = len(png)
            return fast

        _user_waiting += 1
        try:
            with _render_gate:
                with self._ticket_lock:
                    if ticket != self._render_ticket:
                        # 排队期间用户又换了房间：直接把这一次丢掉，别抢占 CPU
                        return {"ok": False, "error": "superseded", "room": room}
                result = room_render.render(
                    region, room, layer_id, _canon_slugcat(slugcat),
                    px_per_tile=px, sky="fill", water=True,
                    use_cache=True, fit_width=fit, crop=crop,
                    # 裁块占的是「用户在看图」的时间：一旦有新请求（ticket 变了）就自断
                    abort=(lambda: self._render_ticket != ticket) if crop else None,
                )
        finally:
            _user_waiting -= 1

        if not result.get("ok"):
            return result
        png = result.pop("png", b"") or b""
        result["dataUrl"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        result["pngBytes"] = len(png)
        return result

    def room_prefetch(self, code: str, rooms: list | None = None,
                      layer_id: str | None = None, slugcat: str | None = None,
                      fit_width: int = 1400) -> dict:
        """把「右栏那几个出口指向的房间」排进后台队列（M3）。

        立刻返回，绝不渲染。真正要不要算由 worker 决定：用户在等就让路，
        批次过期就作废。所以调它没有代价，前端可以放心在开卡后无条件调用。
        """
        global _prefetch_serial
        if not code or not rooms:
            return {"ok": True, "queued": 0}
        region = region_store.get_region(code)
        if not region:
            return {"ok": False, "error": "no_region", "queued": 0}

        want: list[str] = []
        for name in rooms:
            key = str(name or "").strip()
            if key and key.upper() not in (n.upper() for n in want):
                want.append(key)
            if len(want) >= 3:            # 一个房间平均 2.44 个出口，取前 3 就够
                break
        if not want:
            return {"ok": True, "queued": 0}

        with _prefetch_lock:
            _prefetch_serial += 1
            serial = _prefetch_serial
            if len(_prefetch_q) > _PREFETCH_MAX:
                _prefetch_q.clear()
            for name in want:
                _prefetch_q.append((code, name, layer_id, slugcat,
                                    max(0, int(fit_width or 0)), serial))
        _ensure_prefetch_worker()
        return {"ok": True, "queued": len(want)}

    def room_cache_info(self) -> dict:
        """渲染缓存的占用量（给「区域数据」弹窗那一行用）。"""
        info = room_cache.stats()
        info["ok"] = True
        info["regionDir"] = room_cache.region_dir("CC").rsplit(os.sep, 1)[0]
        return info

    def room_cache_clear(self) -> dict:
        """清空渲染缓存。删的只是我们自己建的 `_roomcache/`，不碰导入数据。"""
        with self._ticket_lock:
            self._render_ticket += 1       # 让在途的渲染结果别再写回来
        return room_cache.clear_all()

    def open_data_dir(self) -> dict:
        target = paths.data_dir()
        try:
            if sys.platform.startswith("win"):
                os.startfile(target)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", target])  # noqa: S603
            return {"ok": True, "path": target}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": target}

    # ------------------------------------------------------------------
    # W5b 导出：由后端写文件
    # ------------------------------------------------------------------
    def _export_start_dir(self) -> str:
        """另存为的起始目录：上次选过的 → 系统下载夹 → 桌面 → 家目录。

        页面自己 `<a download>` 时文件落进 WebView2 自己的下载目录，页面既拿不到路径、
        也没法提示，用户点完只能去翻「下载」文件夹（主人 2026-11-22 报的就是这个）。
        """
        cfg = paths.load_config()
        last = str(((cfg.get("ui") or {}).get("exportDir")) or "").strip()
        if last and os.path.isdir(last):
            return last
        home = os.path.expanduser("~")
        for name in ("Downloads", "下载", "Desktop", "桌面"):
            cand = os.path.join(home, name)
            if os.path.isdir(cand):
                return cand
        return home

    def export_save(self, name: str, data: str, kind: str = "svg",
                    target: str | None = None) -> dict:
        """导出内容 → 系统「另存为」→ 写盘，返回真实路径供界面提示。

        参数：
            name 建议文件名（可以带路径，取 basename；非法字符会被剔掉）
            data `svg` 传文本；`png` 传 `data:image/png;base64,…` 或裸 base64
            kind "svg" / "png"，决定扩展名与文件类型过滤
            target 指定落盘路径时**不弹对话框**（回归与将来的批量导出用；页面不传）

        返回值：`{ok, path, dir, name, bytes}`；用户取消是 `{ok: False, canceled: True}`
        （前端据此不提示失败）。
        """
        ext = ".png" if str(kind or "").lower() == "png" else ".svg"
        raw = str(name or "").replace("\\", "/")
        base = os.path.basename(raw) or ("export" + ext)
        base = "".join(ch for ch in base if ch not in '<>:"/\\|?*').strip() or ("export" + ext)
        if not os.path.splitext(base)[1]:
            base += ext

        if target:
            picked = [str(target)]
        else:
            if not self._window or webview is None:
                return {"ok": False, "error": "文件对话框不可用，无法选择保存位置"}
            dialog = getattr(webview, "FileDialog", None)
            dlg_id = getattr(dialog, "SAVE", None) if dialog is not None else None
            if dlg_id is None:  # 老版本 pywebview
                dlg_id = getattr(webview, "SAVE_DIALOG", 30)
            types = ("PNG 图片 (*.png)",) if ext == ".png" else ("SVG 矢量图 (*.svg)",)
            try:
                picked = self._window.create_file_dialog(
                    dlg_id, directory=self._export_start_dir(),
                    save_filename=base, file_types=types,
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
            if not picked:
                return {"ok": False, "canceled": True}
        target = picked[0] if isinstance(picked, (list, tuple)) else str(picked)
        target = str(target or "").strip()
        if not target:
            return {"ok": False, "canceled": True}
        if not os.path.splitext(target)[1]:
            target += ext

        try:
            if ext == ".png":
                payload = str(data or "")
                if payload.startswith("data:"):
                    payload = payload.split(",", 1)[1]
                blob = base64.b64decode(payload)
            else:
                blob = str(data or "").encode("utf-8")
            with open(target, "wb") as fh:
                fh.write(blob)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "写入失败：%s" % exc, "path": target}

        if not target:      # 只有用户亲手选的目录才值得记住；回归指定的临时路径不写配置
            try:
                cfg = paths.load_config()
                ui = cfg.setdefault("ui", {})
                ui["exportDir"] = os.path.dirname(target)
                paths.save_config(cfg)
            except Exception:  # noqa: BLE001
                pass  # 记不住目录不影响这一次导出

        return {
            "ok": True,
            "path": target,
            "dir": os.path.dirname(target),
            "name": os.path.basename(target),
            "bytes": len(blob),
        }

    def open_export_path(self, path: str) -> dict:
        """在文件管理器里定位刚导出的文件（Windows 是选中它，不是只打开目录）。"""
        target = str(path or "").strip()
        if not target or not os.path.exists(target):
            return {"ok": False, "error": "文件不存在（是不是被移动或删掉了）"}
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(  # noqa: S603
                    ["explorer", "/select," + os.path.normpath(target)]
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", target])  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(target)])  # noqa: S603
            return {"ok": True, "path": target}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "path": target}

    def builtin_regions(self) -> dict:
        return region_store.builtin_regions()
