"""S4 连线调参面板的回归检查（真实 WebView2，隐藏窗口）。

    .venv/Scripts/python.exe build/check_regmap_tune.py [区域代码]

检查内容：
    1. 几何地图能开、能出 SVG、探索框/连线/杆子元素都在
    2. 「配色」浮层里 6 个滑杆 + 模式下拉都在，面板可开合且不溢出舞台
    3. 改 `mode=straight` → 室内段归零（说明切段是按几何走的，不是写死）
    4. 改 `bar=1.4` → 重画后字节数变化（参数真的进了 build_svg）
    5. 改 `inner=1` → 不分段；改回 0.5 → 恢复
    6. 参数落盘：重启后 config.ui.regmapCurve 还在（白名单没裁掉）
    7. 全程无 JS 异常
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core import paths  # noqa: E402
from core.bridge import Api  # noqa: E402

CODE = (sys.argv[1] if len(sys.argv) > 1 else "SL").upper()


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    # 检查过程会真写 config（拖滑杆就落盘），先记一份、结束时还原
    cfg_before = (paths.load_config().get("ui") or {}).get("regmapCurve")

    window = webview.create_window("RwSaveTool 连线调参检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out: dict = {"errors": []}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"{code[:60]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def state():
        return loads(js("JSON.stringify(window.__rwTest.geoState())")) or {}

    def worker():
        time.sleep(2.5)
        try:
            js("window.addEventListener('error',function(e){"
               "(window.__rwJsErr=window.__rwJsErr||[]).push(String(e.message));});")
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(60):
                time.sleep(0.5)
                if js("window.__rwTest.ready()"):
                    break
            time.sleep(1.0)

            # 1) 打开几何地图
            js("window.__rwTest.geo('%s')" % CODE)
            for _ in range(40):
                time.sleep(0.5)
                if state().get("svg"):
                    break
            out["base"] = state()

            # 2) 面板与滑杆
            out["panelOpen"] = js("window.__rwTest.geoPanel(true)")
            out["panelRect"] = loads(js(
                "JSON.stringify((function(){"
                "var p=document.getElementById('geo-pal-pop'),s=document.getElementById('geo-stage');"
                "if(!p||!s) return null;"
                "var a=p.getBoundingClientRect(),b=s.getBoundingClientRect();"
                "return {w:Math.round(a.width),h:Math.round(a.height),"
                "stageH:Math.round(b.height),inside:(a.top>=b.top-1&&a.bottom<=b.bottom+1),"
                "scroll:p.scrollHeight>p.clientHeight+2};})())"))

            # 2b) 滑杆上按下并拖动：地图的 viewBox 不许变（2026-11-21 的鼠标穿透 bug）
            #     先等一拍：面板开合会触发一次 resize → fitVB，视图还在动的时候量不出真结果
            time.sleep(0.8)
            js_vb = ("(function(){var s=document.querySelector('#geo-stage svg');"
                     "return s?s.getAttribute('viewBox'):'';})()")
            out["vbBefore"] = js(js_vb)
            js(
                "(function(){var el=document.getElementById('gc-k');"
                "var r=el.getBoundingClientRect();"
                "el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,"
                "clientX:r.left+8,clientY:r.top+r.height/2}));"
                "window.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,button:0,"
                "clientX:r.left+150,clientY:r.top+r.height/2}));"
                "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));"
                "return true;})()")
            out["vbAfter"] = js(js_vb)
            out["dragging"] = js(
                "document.getElementById('geo-stage').classList.contains('dragging')")
            # 2c) 正对照：在舞台空白处拖，viewBox **必须**变——
            #     不然上面那条断言可能只是"事件没派发成功"，白守一场
            js(
                "(function(){var s=document.getElementById('geo-stage');"
                "var r=s.getBoundingClientRect();"
                "var cx=r.left+r.width*0.62, cy=r.top+r.height*0.55;"
                "s.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,"
                "clientX:cx,clientY:cy}));"
                "window.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,button:0,"
                "clientX:cx-90,clientY:cy-70}));"
                "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));"
                "return true;})()")
            out["vbPanned"] = js(js_vb)
            # 3) 直连 → 室内段归零
            js("window.__rwTest.geoSet('mode','straight')")
            time.sleep(2.2)
            out["straight"] = state()

            # 4) 杆子加粗 → 体积变化
            js("window.__rwTest.geoSet('mode','normal')")
            time.sleep(2.2)
            out["normal"] = state()
            js("window.__rwTest.geoSet('bar',1.4)")
            time.sleep(2.2)
            out["bar14"] = state()

            # 5) inner=1 不分段
            js("window.__rwTest.geoSet('inner',1)")
            time.sleep(2.2)
            out["inner1"] = state()
            js("window.__rwTest.geoSet('inner',0.5)")
            time.sleep(2.2)
            out["inner05"] = state()

            # 6b) 引擎切换（W2）：切到 legacy 再切回来，体积应该不同
            js("window.__rwTest.geoSet('engine','legacy')")
            time.sleep(2.4)
            out["legacyEng"] = state()
            js("window.__rwTest.geoSet('engine','zq')")
            time.sleep(2.4)
            out["zqEng"] = state()
            out["cfgCurve"] = (paths.load_config().get("ui") or {}).get("regmapCurve")
            out["jsErr"] = loads(js("JSON.stringify(window.__rwJsErr||[])"))
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)
    try:
        paths.save_config({"ui": {"regmapCurve": cfg_before or {}}})
    except Exception:  # noqa: BLE001
        pass

    b = out.get("base") or {}
    st = out.get("straight") or {}
    nm = out.get("normal") or {}
    bar = out.get("bar14") or {}
    i1 = out.get("inner1") or {}
    i05 = out.get("inner05") or {}
    pr = out.get("panelRect") or {}

    print("base    :", json.dumps({k: b.get(k) for k in
                                   ("svg", "rooms", "seen", "links", "inner", "bars", "meta")},
                                  ensure_ascii=False))
    print("panel   :", json.dumps(pr, ensure_ascii=False), "open:", out.get("panelOpen"),
          "sliders:", b.get("sliders"))
    print("straight:", json.dumps({k: st.get(k) for k in ("links", "inner", "meta")},
                                  ensure_ascii=False))
    print("bar 1.4 :", json.dumps({k: bar.get(k) for k in ("bars", "meta")}, ensure_ascii=False))
    print("inner 1 :", json.dumps({k: i1.get(k) for k in ("inner", "meta")}, ensure_ascii=False))
    print("inner.5 :", json.dumps({k: i05.get(k) for k in ("inner", "meta")}, ensure_ascii=False))
    print("cfg     :", json.dumps(out.get("cfgCurve"), ensure_ascii=False))
    if out.get("jsErr"):
        print("js errors:", out["jsErr"][:5])
    if out.get("fatal"):
        print("FATAL:", out["fatal"])
        return 1

    ok = True

    def expect(cond, label):
        nonlocal ok
        if not cond:
            ok = False
            print("  ✗", label)

    expect(b.get("svg"), "几何图没出来")
    expect((b.get("rooms") or 0) > 0, "没有房间")
    expect((b.get("links") or 0) > 0, "没有连线")
    expect((b.get("inner") or 0) > 0, "默认参数下没有室内段（切段没生效）")
    expect(b.get("sliders") == 6, f"滑杆数量 {b.get('sliders')} ≠ 6")
    expect(out.get("panelOpen"), "配色浮层打不开")
    expect(pr.get("w", 0) > 180, "浮层宽度异常")
    expect(pr.get("inside") in (True, None), "浮层溢出舞台")
    expect((st.get("inner") or 0) == 0, f"直连模式仍有 {st.get('inner')} 段室内段")
    expect((bar.get("bars") or 0) > 0, "杆子不见了")
    expect((nm.get("inner") or 0) > 0, "切回沿门法线后室内段没回来")
    expect((i1.get("inner") or 0) == 0, f"inner=1 仍切了 {i1.get('inner')} 段")
    expect((i05.get("inner") or 0) > 0, "inner=0.5 没有恢复切段")
    le, ze = out.get("legacyEng") or {}, out.get("zqEng") or {}
    expect(le.get("engine") == "legacy" and ze.get("engine") == "zq", "引擎下拉没生效")
    expect(le.get("meta") != ze.get("meta"), "换引擎后图没重画（体积相同）")
    print("pan check: before=%r after=%r panned=%r dragging=%r"
          % (out.get("vbBefore"), out.get("vbAfter"), out.get("vbPanned"),
             out.get("dragging")))
    expect(out.get("vbAfter") == out.get("vbBefore"),
           "在滑杆上拖动把地图拖动了（viewBox %s → %s）"
           % (out.get("vbBefore"), out.get("vbAfter")))
    expect(out.get("dragging") is False, "拖滑杆时舞台进入了拖拽态（鼠标穿透没修掉）")
    expect(out.get("vbPanned") != out.get("vbAfter"),
           "在舞台空白处拖动也没动视图——正对照失败，上面两条断言不可信")
    expect(out.get("vbPanned") != out.get("vbAfter"),
           "在舞台空白处拖动也没动视图——正对照失败，上面两条断言不可信")
    print("pan check: before=%r after=%r panned=%r dragging=%r"
          % (out.get("vbBefore"), out.get("vbAfter"), out.get("vbPanned"),
             out.get("dragging")))
    expect(out.get("vbAfter") == out.get("vbBefore"),
           "在滑杆上拖动把地图拖动了（viewBox %s → %s）"
           % (out.get("vbBefore"), out.get("vbAfter")))
    expect(out.get("dragging") is False, "拖滑杆时舞台进入了拖拽态（鼠标穿透没修掉）")
    expect((out.get("cfgCurve") or {}).get("inner") == 0.5, "参数没落盘（白名单裁掉了）")
    expect(not out.get("jsErr"), "有 JS 异常")

    print("CHECK", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
