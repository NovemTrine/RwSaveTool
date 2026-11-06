"""验证打包产物：用包内的界面 + 包内的区域数据跑一遍，确认可以独立工作。

用法： .venv/Scripts/python.exe build/_verify_release.py
不读任何本机存档，只验证「界面能加载 / 版本号正确 / 区域数据可读」。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DIST = os.path.join(ROOT, "release", "RwSaveTool-v1.0.0-win64-20261106")

import webview  # noqa: E402

from core import paths  # noqa: E402

# 把可写数据目录指向打包出来的那份，等价于 exe 运行时看到的目录
paths.data_dir = lambda: os.path.join(DIST, "region_data")

from core.bridge import Api  # noqa: E402


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

    ok = (
        result.get("bridge") is True
        and result.get("version") == "1.0.0"
        and result.get("regionCount") == 52
    )
    print("RELEASE VERIFY", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
