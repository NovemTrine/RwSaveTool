"""业力 / 分数 / 击杀环形图 / 各战役统计 的回归检查（真实 WebView2，隐藏窗口）。

用法： .venv/Scripts/python.exe build/check_score.py

检查内容：
    1. 业力显示 = 存档 0 基 +1（White 8/10、Saint 2/10、Artificer 1/1、新战役 1/5）
    2. 分数：白猫基础分 / 击杀分 / 通行证乘数
    3. 击杀页：没有「随身物品」、有环形图与滑块、Top N 合并「其他」
    4. 概览页：重要珍珠搬到「收集品」小节
    5. 全局解锁页：各战役统计表（总时长 / 存活占比 / 分数），不再有「数值 A/B」
    6. 标签：好感度 / 击杀统计
    7. 配置迁移：configVersion / killsTopN / tab 不含 items
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


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool 分数检查", html=html, js_api=api,
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
            # 大存档解析 + 区域数据装饰，等到 state.result 就绪为止（最多 25 秒）
            for _ in range(50):
                time.sleep(0.5)
                if js("window.__rwTest.ready()"):
                    break
            time.sleep(1.2)

            out["karma"] = loads(js(
                "JSON.stringify(['White','Saint','Artificer','Gourmand','Yellow','Void']"
                ".reduce(function(m,n){m[n]=window.__rwTest.karma(n);return m;},{}))"
            ))
            out["score"] = loads(js(
                "JSON.stringify(['White','Saint','Artificer'].reduce(function(m,n){"
                "var s=window.__rwTest.score(n); if(s){delete s.unknownNames;} m[n]=s; return m;},{}))"
            ))
            out["tabs"] = loads(js("JSON.stringify(window.__rwTest.tabKeys())"))

            # ---- 概览页：收集品（White 本存档没有重要珍珠，用 Artificer） ----
            js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /Artificer/.test(e.textContent);})[0]; if(s) s.click();")
            time.sleep(1.0)
            out["overview"] = loads(js(
                "JSON.stringify({hasPearlCard: /收集品/.test(document.getElementById('detail-body').textContent),"
                "chips: document.querySelectorAll('#detail-body .chips .chip').length,"
                "noItemWord: !/随身物品/.test(document.getElementById('detail-body').textContent)})"
            ))

            # ---- 击杀页（回到 White，物种最多）----
            js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0]; if(s) s.click();")
            time.sleep(0.9)
            js("var tb=document.querySelector('[data-tab=\"kills\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["kills"] = loads(js(
                "JSON.stringify((function(){"
                "var body=document.getElementById('detail-body');"
                "var sl=document.getElementById('kill-topn');"
                "return {hasSlider: !!sl, max: sl?+sl.max:0, value: sl?+sl.value:0,"
                "slices: document.querySelectorAll('#donut .slice').length,"
                "legend: document.querySelectorAll('#donut-legend .dl-row').length,"
                "other: /其他 \\d+ 种/.test(body.textContent),"
                "noItem: !/随身物品/.test(body.textContent),"
                "noPearl: !/重要珍珠/.test(body.textContent),"
                "center: (document.getElementById('dc-main')||{}).textContent||''};})())"
            ))

            # 拖到 Top N：应无「其他」
            js("var sl=document.getElementById('kill-topn');"
               "if(sl){sl.value=sl.max;"
               "sl.dispatchEvent(new Event('input',{bubbles:true}));}")
            time.sleep(0.8)
            out["killsAll"] = loads(js(
                "JSON.stringify({slices: document.querySelectorAll('#donut .slice').length,"
                "legend: document.querySelectorAll('#donut-legend .dl-row').length,"
                "other: /其他 \\d+ 种/.test(document.getElementById('detail-body').textContent),"
                "now: (document.getElementById('kill-topn-now')||{}).textContent||''})"
            ))

            # 拖回 Top 8
            js("var sl=document.getElementById('kill-topn');"
               "if(sl){sl.value=8;"
               "sl.dispatchEvent(new Event('input',{bubbles:true}));}")
            time.sleep(0.6)

            # ---- 全局解锁页 ----
            js("var tb=document.querySelector('[data-tab=\"global\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["global"] = loads(js(
                "JSON.stringify((function(){"
                "var body=document.getElementById('detail-body');"
                "var txt=body.textContent;"
                "var tr=[].slice.call(body.querySelectorAll('tbody tr')).filter("
                "function(t){return (t.cells[0]||{}).textContent && t.cells[0].textContent.indexOf('White')===0;})[0];"
                "return {hasTable: /各战役统计/.test(txt), rows: body.querySelectorAll('tbody tr').length,"
                "white: tr?[].slice.call(tr.cells).map(function(c){return c.textContent.trim();}):null,"
                "noRawAB: !/数值 A/.test(txt)};})())"
            ))

            out["config"] = None
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)

    # 配置走 Python 侧读，避免和异步桥接较劲
    try:
        from core import paths as _paths

        cfg = _paths.load_config()
        out["config"] = {
            "ver": cfg.get("configVersion"),
            "tab": (cfg.get("ui") or {}).get("tab"),
            "topN": (cfg.get("ui") or {}).get("killsTopN"),
            "noCompletionMode": "completionMode" not in (cfg.get("ui") or {}),
            "path": _paths.config_path(),
        }
    except Exception as exc:  # noqa: BLE001
        out["config"] = {"error": str(exc)}

    print("tabs:", out.get("tabs"))
    print("karma:", json.dumps(out.get("karma"), ensure_ascii=False))
    sc = out.get("score") or {}
    for name in ("White", "Saint", "Artificer"):
        s = sc.get(name) or {}
        print(f"score[{name}]:", {k: s.get(k) for k in
              ("base", "killScore", "multiplier", "saint", "total", "unknownKinds", "groups", "karma", "karmaCap")})
    print("overview:", json.dumps(out.get("overview"), ensure_ascii=False))
    print("kills:", json.dumps(out.get("kills"), ensure_ascii=False))
    print("killsAll:", json.dumps(out.get("killsAll"), ensure_ascii=False))
    print("global:", json.dumps(out.get("global"), ensure_ascii=False)[:400])
    print("config:", json.dumps(out.get("config"), ensure_ascii=False))
    if out.get("errors"):
        print("js errors:", out["errors"][:3])
    if out.get("fatal"):
        print("FATAL:", out["fatal"])
        return 1
    print("CHECK DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
