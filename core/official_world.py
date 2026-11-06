"""游戏本体（官方源）的只读发现与导入。

为什么需要它：
    原版区域的地图可以被模组「添加/修改」——模组通过 GATE_XX_YY、XX_YY02 这类
    房间把原版区域和模组区域连起来。因此同一块区域的房间其实有两类：
      · 源文件声明的房间（游戏原版 / DLC，或纯模组区域自己的文件）
      · 模组附加到该区域的房间
    完成度必须能把这两类分开算，否则分母永远是错的。

数据来源（全部只读，绝不写入）：
    <游戏目录>/RainWorld_Data/StreamingAssets/world/<reg>/          基础游戏 12 区
    <游戏目录>/RainWorld_Data/StreamingAssets/mods/<pack>/world/<reg>/   DLC 区域

每个区域目录内的文件与模组目录完全同构，因此解析直接复用 mod_importer。
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from . import mod_importer


# --------------------------------------------------------------------------
# 游戏安装目录发现
# --------------------------------------------------------------------------
def _steam_roots() -> list[str]:
    """从注册表与常见路径推测 Steam 安装位置（只读）。"""
    roots: list[str] = []

    if sys.platform == "win32":
        try:
            import winreg

            for hive, key in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                value, _ = winreg.QueryValueEx(handle, value_name)
                            except OSError:
                                continue
                            if value:
                                roots.append(str(value))
                except OSError:
                    continue
        except Exception:  # noqa: BLE001 - 注册表不可用不应影响主流程
            pass

    for drive in ("C:", "D:", "E:", "F:", "G:"):
        roots.append(os.path.join(drive + os.sep, "Program Files (x86)", "Steam"))
        roots.append(os.path.join(drive + os.sep, "Program Files", "Steam"))
        roots.append(os.path.join(drive + os.sep, "Steam"))
        roots.append(os.path.join(drive + os.sep, "SteamLibrary"))
        roots.append(os.path.join(drive + os.sep, "Games", "Steam"))

    seen: set[str] = set()
    out: list[str] = []
    for root in roots:
        norm = os.path.normpath(root).lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(os.path.normpath(root))
    return out


def _libraries(steam_root: str) -> list[str]:
    """解析 libraryfolders.vdf 里的所有库目录。"""
    out = [steam_root]
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return out
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        path = match.group(1).replace("\\\\", "\\")
        if path and path not in out:
            out.append(path)
    return out


def find_installations() -> list[dict]:
    """返回所有找到的雨世界安装：{root, streaming, packs}。"""
    found: list[dict] = []
    seen: set[str] = set()

    candidates: list[str] = []
    for steam_root in _steam_roots():
        if not os.path.isdir(steam_root):
            continue
        for library in _libraries(steam_root):
            candidates.append(os.path.join(library, "steamapps", "common", "Rain World"))

    for root in candidates:
        norm = os.path.normpath(root).lower()
        if norm in seen or not os.path.isdir(root):
            continue
        seen.add(norm)
        streaming = os.path.join(root, "RainWorld_Data", "StreamingAssets")
        if not os.path.isdir(streaming):
            continue
        found.append(
            {
                "root": os.path.normpath(root),
                "streaming": streaming,
                "packs": discover_packs(root),
            }
        )
    return found


def discover_packs(root: str) -> list[dict]:
    """列出一个游戏目录下的所有 world 包（基础游戏 + 各 DLC）。"""
    streaming = os.path.join(root, "RainWorld_Data", "StreamingAssets")
    packs: list[dict] = []

    base = os.path.join(streaming, "world")
    if os.path.isdir(base):
        packs.append({"id": "official:base", "label": "游戏原版", "worldDir": base, "order": 0})

    mods_dir = os.path.join(streaming, "mods")
    if os.path.isdir(mods_dir):
        try:
            with os.scandir(mods_dir) as it:
                children = sorted((e for e in it if e.is_dir()), key=lambda e: e.name.lower())
        except OSError:
            children = []
        for index, entry in enumerate(children, start=1):
            world = os.path.join(entry.path, "world")
            if os.path.isdir(world):
                packs.append(
                    {
                        "id": f"official:{entry.name.lower()}",
                        "label": _pack_label(entry.name),
                        "worldDir": world,
                        "order": index,
                    }
                )
    return packs


def _pack_label(folder: str) -> str:
    known = {
        "moreslugcats": "Downpour（倾盆大雨）",
        "watcher": "The Watcher（观望者）",
        "rivulet": "Rivulet",
    }
    return known.get(folder.lower(), folder)


def describe(root: str) -> dict:
    """给界面用的简介：装了哪些包、覆盖哪些区域。"""
    packs = discover_packs(root)
    regions: dict[str, list[str]] = {}
    for pack in packs:
        for code in mod_importer._region_dirs_raw(pack["worldDir"]):
            regions.setdefault(code, []).append(pack["label"])
    return {
        "root": root,
        "packs": [{"id": p["id"], "label": p["label"], "regions": len(mod_importer._region_dirs_raw(p["worldDir"]))} for p in packs],
        "regions": {code: labels for code, labels in sorted(regions.items())},
        "regionCount": len(regions),
    }


# --------------------------------------------------------------------------
# 导入
# --------------------------------------------------------------------------
def import_official(
    root: str | None = None,
    progress=None,
    include_packs: list[str] | None = None,
) -> dict:
    """只读扫描游戏本体的 world 包，返回与 mod_importer.import_mod 同构的结果。

    root 为空时自动探测；探测不到返回 ok=False 并给出提示。
    """
    def report(stage: str, pct: int, detail: str = "") -> None:
        if progress:
            try:
                progress(stage, pct, detail)
            except Exception:  # noqa: BLE001
                pass

    installs = find_installations()
    if root:
        root = os.path.normpath(root)
        if not os.path.isdir(os.path.join(root, "RainWorld_Data", "StreamingAssets")):
            # 允许用户直接选 StreamingAssets 或游戏根目录
            alt = os.path.join(root, "StreamingAssets")
            if os.path.isdir(alt):
                root = os.path.dirname(os.path.dirname(os.path.normpath(root)))
            else:
                return {"ok": False, "error": f"这个目录不像雨世界安装目录：{root}", "regions": [], "packs": [], "warnings": []}
    else:
        if not installs:
            return {
                "ok": False,
                "error": "没有找到雨世界安装目录，请手动指定游戏根目录",
                "regions": [], "packs": [], "warnings": [],
            }
        root = installs[0]["root"]

    packs = discover_packs(root)
    if include_packs:
        wanted = {p.lower() for p in include_packs}
        packs = [p for p in packs if p["id"].lower() in wanted]

    report("扫描游戏本体", 5, f"{len(packs)} 个数据包")

    regions: list[dict] = []
    warnings: list[str] = []
    # 同一个区域可能在多个包里有不同版本（原版 / Downpour / Watcher）。
    # 它们不是重复数据，而是三个「来源」，全部保留，由用户在界面上决定哪个参与计算。
    seen_codes: dict[str, list[str]] = {}

    for index, pack in enumerate(packs):
        report("读取数据包", 10 + int(80 * index / max(1, len(packs))), pack["label"])
        dirs = mod_importer._region_dirs_raw(pack["worldDir"])
        for code, region_dir in sorted(dirs.items()):
            try:
                region, notes = mod_importer._import_region(code, region_dir)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{code}: 读取异常 {type(exc).__name__}: {exc}")
                continue
            warnings.extend(notes)
            if not region:
                continue
            source = region.setdefault("source", {})
            source.update(
                {
                    "kind": "official",
                    "packId": pack["id"],
                    "packLabel": pack["label"],
                    "gameRoot": root,
                }
            )
            region["layer"] = {
                "id": pack["id"],
                "kind": "official",
                "label": pack["label"],
                "order": pack["order"],
            }
            seen_codes.setdefault(code, []).append(pack["label"])
            regions.append(region)

    report("整理结果", 95, f"{len(regions)} 个区域")
    regions.sort(key=lambda r: r["code"])
    return {
        "ok": True,
        "root": root,
        "packs": [{"id": p["id"], "label": p["label"], "order": p["order"]} for p in packs],
        "regions": regions,
        "warnings": warnings,
    }


def official_region_codes(root: str | None = None) -> dict[str, str]:
    """{区域代码: 数据包标签}，用于判断某区域是否有官方源。"""
    if root:
        roots = [root]
    else:
        roots = [i["root"] for i in find_installations()]
    out: dict[str, str] = {}
    for item in roots:
        for pack in discover_packs(item):
            for code in mod_importer._region_dirs_raw(pack["worldDir"]):
                out.setdefault(code, pack["label"])
    return out
