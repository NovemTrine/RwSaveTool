"""路径与配置解析。

规则（见设计文档 3.2）：
- 优先「便携模式」：数据写在 exe / 项目根目录下的 region_data/
- 该目录不可写时，退回 %APPDATA%/RwSaveTool/
"""

from __future__ import annotations

import json
import os
import sys
import time

APP_NAME = "RwSaveTool"

_write_probe_cache: dict[str, bool] = {}


def app_root() -> str:
    """可写基准目录：冻结后为 exe 所在目录，源码运行时为项目根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundle_root() -> str:
    """只读资源基准目录：PyInstaller 打包后在 _internal（sys._MEIPASS）。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource(*parts: str) -> str:
    return os.path.join(bundle_root(), *parts)


def ui_path() -> str:
    return resource("ui", "rw_gui.html")


def builtin_region_map_path() -> str:
    return resource("data", "region_map.json")


def region_access_path() -> str:
    """区域可达性提示表（只读，供界面在挑选区域时给一句提示）。"""
    return resource("data", "region_access.json")


def region_reach_path() -> str:
    """角色可达区域表（只读）：哪些区域只有特定角色能进。"""
    return resource("data", "region_reach.json")


def _writable(directory: str) -> bool:
    """可写判定：能创建文件即可，删除失败不算「不可写」。

    早期实现用「建探针 → 删探针 → 成功即算可写」，在某些安全软件 / 沙箱下
    删除会被拦，导致明明可写却判成只读、缓存目录误退到 APPDATA。
    """
    if directory in _write_probe_cache:
        return _write_probe_cache[directory]
    ok = False
    try:
        os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".rw_write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("1")
        ok = True
        try:
            os.remove(probe)
        except OSError:
            pass  # 删不掉不影响可写性，探针文件已被下次覆盖
    except OSError:
        ok = False
    _write_probe_cache[directory] = ok
    return ok


def data_dir() -> str:
    """导入缓存目录（唯一可写位置）。"""
    portable = os.path.join(app_root(), "region_data")
    if _writable(portable):
        return portable
    fallback = os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME, "region_data"
    )
    os.makedirs(fallback, exist_ok=True)
    return fallback


def config_path() -> str:
    portable = os.path.join(app_root(), "config.json")
    if _writable(os.path.dirname(portable)) and _writable(app_root()):
        return portable
    fallback_dir = os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME
    )
    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, "config.json")


# 配置结构版本：只在结构发生不兼容变化时 +1，并补一条迁移分支
CONFIG_VERSION = 2

DEFAULT_UI = {
    "tab": "overview",
    "regionSort": "code",
    "regionSortDir": "asc",
    "killsExpanded": False,
    "killsTopN": 8,
    "regionPick": {},   # slugcat -> [区域代码]：手动加进「全域探索总览」的区域
    # 房间卡自定义配色：按主题分开存，只记用户改过的项；缺省 = 编辑器原始灰阶
    "roomPalette": {"dark": {}, "light": {}},
    # 房间关系图：力参数 / 显示项 / 动画节奏；缺省值见 ui/rw_gui.html 的 GX_OPT_DEFAULT
    "graph": {},
    # 关系图状态配色（槽位，暗/亮各一套），只记改过的项
    "graphColors": {"dark": {}, "light": {}},
    # 手动"探索过"标记：{区域: {房间: 1 强制已探索 / -1 强制未探索}}，缺省跟随存档
    "roomMarks": {},
    # 手动"这个角色到不了"的房间：{角色: {区域: [房间名]}}，直接不进完成度分母
    "roomExcluded": {},
    # 完成度口径：True = 只算当前角色可达的房间（严格），False = 全部房间（宽松）。
    # 必须在这里登记，否则 save_config 的白名单会把前端传来的值裁掉，重启即失效。
    "roomStrict": True,
}

DEFAULT_CONFIG = {
    "configVersion": CONFIG_VERSION,
    "lastSavePath": "",
    "lastSlugcat": "",
    "importDirs": [],
    "theme": "dark",
    "accent": "amber",
    "ui": dict(DEFAULT_UI),
    "saltPath": None,
}

# 最近一次 load_config 的状态（供界面提示：是否迁移过 / 是否只读）
_config_state = {"readOnly": False, "migrated": False, "note": ""}


def config_state() -> dict:
    return dict(_config_state)


def _broken_path() -> str:
    return os.path.join(os.path.dirname(config_path()), "config.broken.json")


def migrate_config(raw: dict | None) -> tuple[dict, bool, bool]:
    """把任意版本的配置迁移到当前版本。

    返回 (data, changed, read_only)：
    - changed 为 True 表示需要写回磁盘（版本升级或补齐缺省键）
    - read_only 表示文件来自更高版本的程序，本次只读不写
    """
    if not isinstance(raw, dict):
        return json.loads(json.dumps(DEFAULT_CONFIG)), True, False

    data = json.loads(json.dumps(raw))
    changed = False

    try:
        version = int(data.get("configVersion"))
    except (TypeError, ValueError):
        version = 1  # 没有版本字段 = v1
        data["configVersion"] = 1
        changed = True

    if version > CONFIG_VERSION:
        # 版本只升不降：更新的程序写的配置，本次只读
        return data, changed, True

    ui = data.get("ui")
    if not isinstance(ui, dict):
        ui = {}
        data["ui"] = ui
        changed = True

    if version < 2:
        # v1 → v2：删掉已废弃的 completionMode；tab "items" 改名 "kills"
        if "completionMode" in ui:
            ui.pop("completionMode", None)
            changed = True
        if ui.get("tab") == "items":
            ui["tab"] = "kills"
            changed = True
        if "killsTopN" not in ui:
            ui["killsTopN"] = 8
            changed = True
        data["configVersion"] = 2
        version = 2
        changed = True

    # 兜底：补齐缺省键，不覆盖用户已有值
    if data.get("configVersion") != CONFIG_VERSION:
        data["configVersion"] = CONFIG_VERSION
        changed = True
    for key, value in DEFAULT_UI.items():
        if key not in ui:
            # 深拷贝：DEFAULT_UI 里的 dict/list 不能跟运行中的配置共享引用
            ui[key] = json.loads(json.dumps(value))
            changed = True
    if ui.get("tab") == "items":
        ui["tab"] = "kills"
        changed = True

    # 顶层缺省键也补齐（旧文件可能没有 theme / importDirs 等）
    for key, value in DEFAULT_CONFIG.items():
        if key not in data:
            data[key] = json.loads(json.dumps(value))
            changed = True

    return data, changed, False


def load_config() -> dict:
    path = config_path()
    raw = None
    broken_note = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = None
            try:
                os.replace(path, _broken_path())
                broken_note = "配置文件损坏，已改名留档 config.broken.json，本次使用默认配置。"
            except OSError:
                broken_note = "配置文件损坏，本次使用默认配置。"

    data, changed, read_only = migrate_config(raw)
    _config_state.update(
        {
            "readOnly": read_only,
            "migrated": bool(changed and not read_only),
            "note": broken_note or (
                "配置文件来自更新版本的程序，本次只读，不会覆盖。" if read_only else ""
            ),
        }
    )
    if changed and not read_only:
        _write_config(data)
    return data


def _write_config(data: dict) -> bool:
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def save_config(patch: dict) -> dict:
    data = load_config()
    if _config_state.get("readOnly"):
        return data
    if isinstance(patch, dict):
        for key, value in patch.items():
            if key == "ui" and isinstance(value, dict):
                ui = dict(data.get("ui") or {})
                ui.update(value)
                data["ui"] = ui
            else:
                data[key] = value
    # 只存已知键，避免把界面传来的临时字段写进配置
    clean = {k: data.get(k, DEFAULT_CONFIG.get(k)) for k in DEFAULT_CONFIG}
    clean["ui"] = {k: (data.get("ui") or {}).get(k, DEFAULT_UI.get(k)) for k in DEFAULT_UI}
    clean["configVersion"] = CONFIG_VERSION
    _write_config(clean)
    return clean


def rain_world_dirs() -> list[str]:
    """返回该机器上可能的雨世界存档目录（只检测存在性，不创建）。"""
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    candidates = [os.path.join(profile, "AppData", "LocalLow", "Videocult", "Rain World")]
    out = [p for p in candidates if os.path.isdir(p)]
    return out


SLOT_NAMES = ("sav", "sav2", "sav3")


def list_slots() -> list[dict]:
    """列出默认路径下的三个存档槽位。"""
    slots: list[dict] = []
    for base in rain_world_dirs():
        for name in SLOT_NAMES:
            path = os.path.join(base, name)
            if os.path.isfile(path):
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                slots.append(
                    {
                        "name": name,
                        "path": path,
                        "size": stat.st_size,
                        "mtime": int(stat.st_mtime),
                        "mtimeText": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    }
                )
    return slots
