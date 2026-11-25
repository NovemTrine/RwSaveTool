"""验证打包产物：用包内的界面 + 包内的区域数据跑一遍，确认可以独立工作。

用法： .venv/Scripts/python.exe build/verify_release.py
不读任何本机存档，只验证「界面能加载 / 版本号正确 / 区域数据可读」。
发布目录与期望版本号都从仓库根的 VERSION 推出来，不写死 —— 否则每次发版都要改这个脚本。
"""

from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _meta() -> dict:
    meta: dict[str, str] = {}
    with io.open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                meta[key.strip()] = val.strip()
    return meta


META = _meta()
VERSION = META.get("version", "0.0.0")
DIST = os.path.join(ROOT, "release",
                    "RwSaveTool-v%s-win64-%s" % (VERSION, META.get("date", "").replace("-", "")))
EXPECT_REGIONS = len([n for n in os.listdir(os.path.join(DIST, "region_data"))
                      if n.endswith(".json") and not n.startswith("_")]) \
    if os.path.isdir(os.path.join(DIST, "region_data")) else 0

import webview  # noqa: E402

from core import paths  # noqa: E402

# 把可写数据目录指向打包出来的那份，等价于 exe 运行时看到的目录
paths.data_dir = lambda: os.path.join(DIST, "region_data")

from core.bridge import Api  # noqa: E402


def karma_ok() -> tuple[bool, str]:
    """№8：业力门槛必须**在包里**（来源是游戏目录的 `locks.txt`，发布后读不到）。

    只查一条已知真值：`SU` 的 `GATE_SU_DS` = 左 4 / 右 2（与 `locks.txt` 第 1 行一致）。
    """
    path = os.path.join(DIST, "region_data", "SU.json")
    try:
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return False, "读不到 SU.json：%s" % exc
    for layer in data.get("layers") or []:
        for room in layer.get("rooms") or []:
            if str(room.get("name") or "").upper() == "GATE_SU_DS":
                got = room.get("karma")
                return list(got or []) == [4, 2], "GATE_SU_DS karma=%r" % (got,)
    return False, "SU.json 里找不到 GATE_SU_DS"


def main() -> int:
    html_path = os.path.join(DIST, "_internal", "ui", "rw_gui.html")
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()

    api = Api()
    window = webview.create_window("release verify", html=html, js_api=api,
                                   width=1280, height=860, hidden=True)
    api.attach(window)
    result: dict = {}

    def worker() -> None:
        import time

        time.sleep(2.6)
        try:
            result["bridge"] = window.evaluate_js("!!window.pywebview")
            window.evaluate_js(
                "window.pywebview.api.app_info().then(function(i){window.__v=i;});"
            )
            window.evaluate_js(
                "window.pywebview.api.regions().then(function(l){window.__n=(l||[]).length;"
                "window.__first=(l&&l[0])?l[0].nameZh:'';});"
            )
            time.sleep(1.4)
            result["version"] = window.evaluate_js("(window.__v||{}).version || ''")
            result["versionName"] = window.evaluate_js("(window.__v||{}).versionName || ''")
            result["releaseDate"] = window.evaluate_js("(window.__v||{}).releaseDate || ''")
            result["dataDir"] = window.evaluate_js("(window.__v||{}).dataDir || ''")
            result["regionCount"] = window.evaluate_js("window.__n")
            result["firstRegion"] = window.evaluate_js("window.__first")
            result["title"] = window.evaluate_js("document.title")
        except Exception as exc:  # noqa: BLE001
            result["error"] = "%s: %s" % (type(exc).__name__, exc)
        finally:
            window.destroy()

    webview.start(worker)
    for key in ("bridge", "version", "versionName", "releaseDate",
                "regionCount", "firstRegion", "dataDir", "title"):
        print("%-13s %s" % (key + ":", result.get(key)))
    if result.get("error"):
        print("ERROR:", result["error"])
        return 1

    karma_good, karma_note = karma_ok()
    print("%-13s %s" % ("gateKarma:", karma_note))
    ok = (
        result.get("bridge") is True
        and result.get("version") == VERSION
        and result.get("regionCount") == EXPECT_REGIONS
        and karma_good
    )
    print("期望版本 %s / 期望区域 %d" % (VERSION, EXPECT_REGIONS))
    print("RELEASE VERIFY", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
