"""角色变体 / 条件房间 / Markdown 导出的回归检查（真实 WebView2，隐藏窗口）。

用法： .venv/Scripts/python.exe build/check_variant.py

检查内容：
    1. 同一区域在不同角色下分母不同（圣徒 CC 用 saint 变体，白猫用普通版）
    2. 条件房间行内出现「条件房间 −N」
    3. 地图弹窗对圣徒使用变体底图（副标题出现「变体：saint」）
    4. Markdown 导出内容包含三张表
    5. 数字键 1–7 能切标签
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 回归产物统一放 build/_shots，不污染 docs（docs 只放被文档引用的图）
SHOTS = os.path.join(ROOT, "build", "_shots")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402

CODES = ("CC", "SB", "MS", "GW", "LM", "VS", "SU")
SLUGCATS = ("White", "Saint", "Artificer", "Spear")


def probe_js(slugcat: str, codes) -> str:
    codes_js = json.dumps(list(codes))
    return (
        "JSON.stringify((function(){"
        f"var out={{slugcat:{json.dumps(slugcat)}, regions:{{}}}};"
        f"{codes_js}.forEach(function(code){{out.regions[code]=window.__rwTest.region(code,{json.dumps(slugcat)});}});"
        "return out;})())"
    )


MD_JS = "JSON.stringify({mdLen: window.__rwTest.markdown().length, md: window.__rwTest.markdown()})"
SUMMARY_JS = "JSON.stringify({summary: window.__rwTest.summary(), mdLen: window.__rwTest.markdown().length})"
TAB_JS = "JSON.stringify({tab: window.__rwTest.tab()})"
MAP_SUB = (
    "JSON.stringify({sub: (document.querySelector('#modal-sub')||{}).textContent||'',"
    "legend: (document.querySelector('#modal-body .map-legend')||{}).textContent||'',"
    "opened: !!document.getElementById('map-svg'),"
    "rooms: document.querySelectorAll('#map-svg rect.room').length})"
)


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool 变体检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out.setdefault("errors", []).append(f"{code[:40]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def worker():
        time.sleep(2.5)
        try:
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            time.sleep(5.5)

            out["summary"] = loads(js(SUMMARY_JS))
            out["pearls"] = loads(js(
                "JSON.stringify((function(){var c=window.__rwTest.campaign('White')||{regions:[]};"
                "var hits=(c.regions||[]).filter(function(r){return r.pearlRooms && r.pearlRooms.length;});"
                "return {regions:hits.length, sample:hits.slice(0,4).map(function(r){"
                "return r.name+':'+r.pearlRooms.length;})};})())"
            ))
            for name in SLUGCATS:
                out[name] = loads(js(probe_js(name, CODES)))

            js("var ev=new KeyboardEvent('keydown',{key:'3',bubbles:true});"
               "document.dispatchEvent(ev);")
            time.sleep(0.8)
            out["tabByKey"] = loads(js(TAB_JS))

            js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /Saint/.test(e.textContent);})[0]; if(s) s.click();")
            time.sleep(0.8)
            js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.0)
            out["rows"] = loads(js(
                "JSON.stringify(['CC','LM','SB'].map(function(code){"
                "var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
                "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf(code)===0;})[0];"
                "if(!tr) return null;"
                "return {code:code, comp:(tr.cells[2]||{}).textContent||''};}))"
            ))
            out["buttons"] = loads(js(
                "JSON.stringify({md: !!document.getElementById('export-md'),"
                "json: !!document.getElementById('export'),"
                "mdText: (document.getElementById('export-md')||{}).textContent||''})"
            ))
            js("var tr=[].slice.call(document.querySelectorAll('#detail-body tbody tr')).filter("
               "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.trim().indexOf('CC')===0;})[0];"
               "if(tr){var b=tr.querySelector('[data-map]'); if(b) b.click();}")
            time.sleep(2.5)
            out["map"] = loads(js(MAP_SUB))
            out["md"] = loads(js(MD_JS))
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)

    summary = (out.get("summary") or {})
    print("summary:", json.dumps(summary.get("summary"), ensure_ascii=False)[:200])
    print("pearls:", json.dumps(out.get("pearls"), ensure_ascii=False))
    for name in SLUGCATS:
        item = out.get(name) or {}
        regs = item.get("regions") or {}
        brief = {}
        for code in CODES:
            v = regs.get(code) or {}
            if v.get("missing"):
                continue
            brief[code] = (v.get("visited"), v.get("total"), v.get("pct"), v.get("variant"), v.get("condDrop"))
        print(f"{name}:", brief)
    print("tabByKey:", out.get("tabByKey"))
    print("rows:", json.dumps(out.get("rows"), ensure_ascii=False)[:320])
    print("buttons:", json.dumps(out.get("buttons"), ensure_ascii=False))
    print("map:", json.dumps(out.get("map"), ensure_ascii=False)[:300])
    md = (out.get("md") or {}).get("md") or ""
    if md:
        sample = os.path.join(SHOTS, "sample_report.md")
        os.makedirs(os.path.dirname(sample), exist_ok=True)
        with open(sample, "w", encoding="utf-8") as fh:
            fh.write(md)
        print("sample report:", sample)
    print("mdLen:", len(md), "| has3tables:",
          all(k in md for k in ("## 一、", "## 二、区域完成度", "## 全部角色")))
    print("md head:", md[:160].replace("\n", " | "))
    if out.get("errors"):
        print("js errors:", out["errors"][:3])
    if out.get("fatal"):
        print("FATAL:", out["fatal"])
        return 1
    print("CHECK DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
