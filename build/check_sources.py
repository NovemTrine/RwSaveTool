"""来源功能的回归检查：真实启动 WebView2，验证数据列与点亮/熄灭。

用法： .venv/Scripts/python.exe build/check_sources.py

检查内容：
    1. 区域页出现「数据」列的来源 chips，且每个来源一行
    2. GW 这类区域同时出现 Original / Downpour / Coral Caves 三个来源
    3. 仅地图的来源带「仅地图」标记
    4. 点一下 chips 能切换参与计算，且百分比随之变化（口径可复现）
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402

JS_STATE = (
    "JSON.stringify({"
    "manageBtn: (document.getElementById('src-manage')||{}).textContent||'',"
    "topBar: document.querySelectorAll('.modebar').length,"
    "chips: document.querySelectorAll('#detail-body .src-col .src-chip').length,"
    "cols: document.querySelectorAll('#detail-body .src-col').length"
    "})"
)


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool 来源检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out.setdefault("errors", []).append(f"{code[:40]}: {exc}")
            return default

    def worker():
        time.sleep(2.5)
        try:
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            time.sleep(4.5)

            # 选中 White（区域最多的角色之一），切到「区域」页
            js("var ws=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0]; if(ws) ws.click();")
            time.sleep(0.8)
            js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["page"] = js(JS_STATE)

            # 找 GW 行，读出它的来源 chips
            out["gw"] = js(
                "var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
                "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('GW')===0;})[0];"
                "if(!tr) JSON.stringify({found:false}); else JSON.stringify({found:true,"
                "pct:(tr.querySelector('.pct')||{}).textContent,"
                "chips:[].slice.call(tr.querySelectorAll('.src-chip')).map(function(c){"
                "return {name:(c.querySelector('.sc-n')||{}).textContent,rooms:(c.querySelector('b')||{}).textContent,"
                "mapOnly:!!c.querySelector('i'),on:c.classList.contains('on')};})})"
            )

            # 熄灭 Original（GW 的分母来源），百分比应变成 —
            js("var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
               "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('GW')===0;})[0];"
               "tr.querySelector('.src-chip').click();")
            time.sleep(0.8)
            out["gwOff"] = js(
                "var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
                "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('GW')===0;})[0];"
                "JSON.stringify({pct:(tr.querySelector('.pct')||{}).textContent,"
                "tag:(tr.cells[tr.cells.length-1]||{}).textContent})"
            )

            # 恢复
            js("var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
               "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('GW')===0;})[0];"
               "tr.querySelector('.src-chip').click();")
            time.sleep(0.8)
            out["gwBack"] = js(
                "var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
                "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('GW')===0;})[0];"
                "JSON.stringify({pct:(tr.querySelector('.pct')||{}).textContent})"
            )

            # 区域数据弹窗：每个来源一行，带改名 / 移除 / 地图按钮
            js("var rb=document.getElementById('btn-regions'); if(rb) rb.click();")
            time.sleep(2.0)
            out["modal"] = js(
                "JSON.stringify({"
                "rows: document.querySelectorAll('#modal-body .layer-row').length,"
                "chips: document.querySelectorAll('#modal-body .src-chip').length,"
                "rename: document.querySelectorAll('#modal-body [data-rename]').length,"
                "delLayer: document.querySelectorAll('#modal-body [data-dellayer]').length"
                "})"
            )

            # 导入模组：先弹「来源名称」，取消后不应该再弹目录选择
            js("var mi=document.getElementById('m-import'); if(mi) mi.click();")
            time.sleep(1.0)
            out["srcDialog"] = js(
                "JSON.stringify({hasInput: !!document.getElementById('src-name'),"
                "presets: [].slice.call(document.querySelectorAll('#modal-body [data-preset]')).map("
                "function(b){return b.textContent.trim()})})"
            )
            js("var c=document.getElementById('src-cancel'); if(c) c.click();")
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)
    for key in ("page", "gw", "gwOff", "gwBack", "modal", "srcDialog"):
        print(key + ":", out.get(key))
    if out.get("errors"):
        print("js errors:", out["errors"][:3])
    if out.get("fatal"):
        print("FATAL:", out["fatal"])
        return 1
    print("CHECK DONE")


if __name__ == "__main__":
    raise SystemExit(main())
