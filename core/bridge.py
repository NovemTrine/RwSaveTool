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

from . import (
    __release_date__,
    __version__,
    __version_name__,
    mod_importer,
    official_world,
    paths,
    region_store,
    room_geo,
    save_io,
    sources,
    translations,
)

try:  # webview 只在桌面壳里存在
    import webview
except Exception:  # pragma: no cover
    webview = None


class Api:
    def __init__(self) -> None:
        self._window = None

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

    def delete_region(self, code: str) -> dict:
        return region_store.delete_region(code)

    def delete_layer(self, code: str, layer_id: str) -> dict:
        return region_store.delete_layer(code, layer_id)

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
            return room_geo.geometry(region, room, layer_id)
        except room_geo.RoomGeoError as exc:
            return {"ok": False, "error": "unparsable", "detail": str(exc), "room": room}
        except Exception as exc:  # noqa: BLE001 - 桥接层不向外抛，界面显示错误即可
            return {"ok": False, "error": "unparsable", "detail": str(exc), "room": room}

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

    def builtin_regions(self) -> dict:
        return region_store.builtin_regions()
