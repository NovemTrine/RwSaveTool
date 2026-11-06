"""桌面壳冒烟测试：真实启动 WebView2 窗口，验证桥接与页面加载。

用法： .venv/Scripts/python.exe build/smoke.py
窗口以隐藏方式创建，2 秒后自动关闭，不打扰使用。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool 冒烟测试", html=html, js_api=api,
                                   width=1200, height=800, hidden=True)
    api.attach(window)
    result: dict = {}

    def worker():
        import time

        time.sleep(2.5)
        try:
            result["basic"] = window.evaluate_js(
                "JSON.stringify({bridge: !!window.pywebview, "
                "toolbarHidden: document.getElementById('toolbar').hidden, "
                "slotsHidden: document.getElementById('slot-list').hidden})"
            )
            window.evaluate_js(
                "window.pywebview.api.regions().then(function(list){"
                "window.__smokeCount = (list||[]).length;})"
            )
            time.sleep(1.2)
            result["regionCount"] = window.evaluate_js("window.__smokeCount")

            window.evaluate_js(
                "window.pywebview.api.app_info().then(function(i){window.__smokeData = i.dataDir;})"
            )
            time.sleep(1.0)
            result["dataDir"] = window.evaluate_js("window.__smokeData || ''")

            # 端到端：点第一个槽位 → 真实读文件 → Worker 解析 → 渲染
            window.evaluate_js(
                "var b=document.querySelector('#slot-list .slot'); if(b) b.click();"
            )
            # 大存档解析需要时间，轮询等待渲染完成（最多 40 秒）
            for _ in range(80):
                time.sleep(0.5)
                ready = window.evaluate_js(
                    "!!(window.__rwTest && window.__rwTest.ready && window.__rwTest.ready())"
                )
                if ready:
                    break
            time.sleep(0.6)
            result["afterOpen"] = window.evaluate_js(
                "JSON.stringify({"
                "resultVisible: !document.getElementById('result').hidden,"
                "campaigns: document.querySelectorAll('#camplist .camp').length,"
                "meta: (document.getElementById('meta-grid')||{}).textContent ? "
                "document.getElementById('meta-grid').textContent.replace(/\\s+/g,' ').slice(0,120) : ''"
                "})"
            )
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)
    print("basic:", result.get("basic"))
    print("regionCount:", result.get("regionCount"))
    print("dataDir:", result.get("dataDir"))
    print("afterOpen:", result.get("afterOpen"))
    if result.get("error"):
        print("ERROR:", result["error"])
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
