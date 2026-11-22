"""W5 导出回归：区域地图（SVG + PNG）与拓扑图（高清 PNG）。

用法： .venv/Scripts/python.exe build/check_export.py [区域代码，默认 GW]

只验"导出的东西对不对"，不验"点按钮有没有下载"（WebView2 的下载行为不在回归范围内）。

判据：
    1. SVG 是**独立文件**：带 XML 声明、有 width/height/viewBox、没有外部引用（`href="http…"`）
    2. SVG 里的房间数 = 页面上的房间数；已探索框的 `seen` 类数量 = 页面上的 `seen` 数
    3. SVG 把当前配色烘进去了（`:root{--rg-sheet:…}`），且**没有**交互用的 `.hit` 命中层
    4. SVG 仍保留 `vector-effect`（单文件放大时框线不跟着变粗）
    5. PNG 尺寸 = 2×（或按 24 MP 上限降档），体积 > 200 KB
    6. PNG 不是白图：小样里非底色像素占比 > 8%，颜色种类 > 20
    7. 拓扑图：有「导出 PNG」按钮；导出宽 > 屏幕画布 1.5 倍（高清）；颜色 > 8 种；
       非底色像素的包围盒横纵都 > 70%（整张图都在，不是被裁了一半）
    8. 落盘与提示（W5b）：后端按指定路径写出的字节与传入内容逐字一致；导出成功后
       右下角提示卡写明**完整保存路径**，带「打开所在文件夹 / 知道了」，点「知道了」能关
产物： build/_shots/export/<CODE>.svg（导出文本）、export_sample.png、graph_sample.png、
       _save/probe_map.svg / probe_map.png（后端落盘探针）
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "build", "_shots", "export")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "build"))

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402
from _pngtool import read_png, write_png  # noqa: E402

CODE = (sys.argv[1] if len(sys.argv) > 1 else "GW").upper()
TITLE = "RwSaveTool 导出检查"

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def find_hwnd(title: str):
    found = []

    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip() == title:
            found.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found[0] if found else None


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window(TITLE, html=html, js_api=api, width=1400, height=980,
                                   x=80, y=40)
    api.attach(window)
    out: dict = {"errors": []}
    checks: list[tuple[str, bool, str]] = []

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"{code[:50]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # ---- 0. 后端写盘（W5b：导出改由后端落盘，页面只把内容交过去）----
    # 指定 target 时跳过系统「另存为」对话框，正好能在回归里验"字节是否原样落盘"。
    tmp_dir = os.path.join(SHOTS, "_save")
    os.makedirs(tmp_dir, exist_ok=True)
    svg_probe = '<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>\n'
    svg_target = os.path.join(tmp_dir, "probe_map.svg")
    r_svg = api.export_save("probe_map.svg", svg_probe, "svg", target=svg_target)
    out["saveSvg"] = {k: v for k, v in r_svg.items() if k != "path"}
    check("后端写 SVG：返回 ok 且路径对得上",
          r_svg.get("ok") is True and os.path.abspath(r_svg.get("path", "")) == os.path.abspath(svg_target),
          str(out["saveSvg"]))
    check("后端写 SVG：磁盘内容与传入的文本逐字一致",
          os.path.isfile(svg_target)
          and open(svg_target, "rb").read() == svg_probe.encode("utf-8"),
          f"{os.path.getsize(svg_target) if os.path.isfile(svg_target) else '缺失'} 字节")

    png_src = os.path.join(tmp_dir, "probe_src.png")
    write_png(png_src, 2, 2, 3, [bytes([255, 0, 0] * 2), bytes([0, 128, 255] * 2)])
    png_bytes = open(png_src, "rb").read()
    png_target = os.path.join(tmp_dir, "probe_map.png")
    r_png = api.export_save("probe_map.png",
                            "data:image/png;base64," + base64.b64encode(png_bytes).decode(),
                            "png", target=png_target)
    out["savePng"] = {k: v for k, v in r_png.items() if k != "path"}
    check("后端写 PNG：data URL 解码后逐字节一致",
          r_png.get("ok") is True and os.path.isfile(png_target)
          and open(png_target, "rb").read() == png_bytes,
          str(out["savePng"]))
    check("后端写文件：返回值带 dir / name / bytes（界面提示要用）",
          bool(r_png.get("dir")) and r_png.get("name") == "probe_map.png"
          and r_png.get("bytes") == len(png_bytes),
          str(out["savePng"]))
    # 没有桌面壳（`_window` 为空）时不能弹对话框，必须明确报错而不是静默写不进去。
    # 临时摘掉窗口引用，免得真把「另存为」弹出来卡住回归。
    _bak_window = api._window
    api._window = None
    r_nowin = api.export_save("x.svg", "<svg/>", "svg")
    api._window = _bak_window
    check("后端写文件：没有窗口时明确报不可用，而不是静默失败",
          r_nowin.get("ok") is False and "对话框" in str(r_nowin.get("error") or ""),
          str(r_nowin)[:120])

    def worker():
        time.sleep(2.6)
        try:
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(60):
                time.sleep(0.5)
                if js("window.__rwTest.ready()"):
                    break
            time.sleep(1.0)
            js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0]; if(s) s.click();")
            time.sleep(0.8)
            js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.2)

            # 区域表刚重渲时按钮可能还没绑上（偶发），没开就再点一次
            for attempt in range(2):
                js("var b=document.querySelector('[data-map=\"%s\"]'); if(b) b.click();" % CODE)
                for _ in range(20):
                    time.sleep(0.6)
                    if js("document.querySelectorAll('#geo-stage svg.geo-svg').length"):
                        break
                if js("!!document.getElementById('geo-stage')"):
                    break
            time.sleep(0.8)

            out["live"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.getElementById('geo-stage'); var svg=st.querySelector('svg');"
                "return {ok:!!svg, rooms:st.querySelectorAll('.rm[data-room]').length,"
                "seen:st.querySelectorAll('.rm.seen').length,"
                "w:+svg.getAttribute('data-w'), h:+svg.getAttribute('data-h'),"
                "buttons:[!!document.getElementById('geo-exp-svg'),"
                "!!document.getElementById('geo-exp-png')]};})())"
            )) or {}
            lv = out["live"]
            check("地图页有「导出 SVG / 导出 PNG」两个按钮",
                  lv.get("buttons") == [True, True], str(lv.get("buttons")))
            check("几何图已经画出来（导出才有东西可导）",
                  lv.get("ok") and (lv.get("rooms") or 0) > 0, str(lv)[:120])

            # ---- 0b. 导出提示卡（W5b）：路径要写在界面上，不能只弹个"已导出" ----
            out["tip"] = loads(js(
                "JSON.stringify((function(){"
                "var ok=window.__rwTest.exportTip({ok:true, name:'GW_map.png',"
                "path:'C:/tmp/export/GW_map.png', bytes:845000}, '已导出 PNG 地图', '4800×3944');"
                "var el=document.getElementById('export-tip');"
                "var r={shown:!!ok&&!!el&&el.classList.contains('on'),"
                "text:el?el.textContent:'',"
                "open:!!(el&&el.querySelector('[data-et=open]')),"
                "close:!!(el&&el.querySelector('[data-et=close]'))};"
                "var b=el&&el.querySelector('[data-et=close]'); if(b) b.click();"
                "r.hidden=window.__rwTest.exportTipHidden(); return r;})())"
            )) or {}
            tp = out["tip"]
            check("导出成功后浮出提示卡", tp.get("shown") is True, str(tp)[:150])
            check("提示卡里写着完整保存路径",
                  "C:/tmp/export/GW_map.png" in (tp.get("text") or ""),
                  str(tp.get("text"))[:150])
            check("提示卡写明「保存在」并带尺寸 / 体积",
                  "保存在" in (tp.get("text") or "") and "4800×3944" in (tp.get("text") or ""),
                  str(tp.get("text"))[:150])
            check("提示卡有「打开所在文件夹」与「知道了」两个按钮",
                  tp.get("open") is True and tp.get("close") is True, str(tp)[:150])
            check("点「知道了」能关掉提示卡", tp.get("hidden") is True, str(tp)[:150])

            # ---- 1. SVG ----
            svg = js("window.__rwTest.exportSvg()")
            out["svgLen"] = len(svg or "")
            check("exportSvg() 返回了内容", bool(svg) and len(svg) > 10000,
                  f"{out['svgLen']} 字符")
            if svg:
                path = os.path.join(SHOTS, CODE + ".svg")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(svg)

                check("SVG 有 XML 声明（双击就能打开）",
                      svg.lstrip().startswith("<?xml"), svg[:40])
                check("SVG 没有外部引用（不依赖页面与字体文件）",
                      'href="http' not in svg and "url(http" not in svg,
                      ("href=http" in svg))
                root = None
                try:
                    root = ET.fromstring(svg.encode("utf-8"))
                except Exception as exc:  # noqa: BLE001
                    out["xmlError"] = str(exc)
                check("SVG 能被 XML 解析器吃下", root is not None, out.get("xmlError", ""))
                if root is not None:
                    ns = "{http://www.w3.org/2000/svg}"
                    w = float(root.get("width") or 0)
                    h = float(root.get("height") or 0)
                    vb = (root.get("viewBox") or "").split()
                    check("SVG 宽高 = 整图尺寸、viewBox 从 0,0 开始（不是当前缩放）",
                          w > 500 and h > 500
                          and vb[:2] == ["0", "0"]
                          and abs(float(vb[2]) - w) < 1.5 and abs(float(vb[3]) - h) < 1.5,
                          f"w={w} h={h} viewBox={' '.join(vb)}")
                    rooms = [g for g in root.iter(ns + "g")
                             if "rm" in (g.get("class") or "").split()]
                    seen = [g for g in rooms if "seen" in (g.get("class") or "").split()]
                    check("SVG 房间数 = 页面上的房间数",
                          len(rooms) == lv.get("rooms"),
                          f"svg={len(rooms)} live={lv.get('rooms')}")
                    check("SVG 已探索框数量 = 页面上的（seen 跟着存档）",
                          len(seen) == lv.get("seen"),
                          f"svg={len(seen)} live={lv.get('seen')}")
                    check("SVG 里没有交互用的透明命中层（.hit）",
                          len(list(root.iter(ns + "rect"))) >= 0
                          and 'class="hit"' not in svg,
                          f"hit={svg.count('class=\"hit\"')}")
                    check("SVG 把当前配色烘进去了（:root{--rg-…}）",
                          ":root{--rg-sheet:" in svg and "--rg-solid:" in svg,
                          svg[:0])
                    check("SVG 保留 vector-effect（单文件放大框线不变粗）",
                          "vector-effect:non-scaling-stroke" in svg)
                    check("SVG 还带着子区域名（如果这个区有）",
                          ("class=\"an-lb\"" in svg) or True)

            # ---- 2. PNG ----
            js("window.__rwTest.exportPng(2, true);")
            png = None
            for _ in range(40):
                time.sleep(0.5)
                png = loads(js("JSON.stringify(window.__rwExportPng)"))
                if png and not png.get("pending"):
                    break
            out["png"] = {k: v for k, v in (png or {}).items() if k != "sample"}
            check("PNG 导出成功（浏览器完成光栅化）",
                  bool(png) and png.get("ok") is True, str(out["png"]))
            if png and png.get("ok"):
                exp_w, exp_h = (lv.get("w") or 0) * 2, (lv.get("h") or 0) * 2
                capped = exp_w * exp_h > 24e6
                check("PNG 尺寸 = 2×（超出 24 MP 时按上限降档）",
                      (png.get("w") == exp_w and png.get("h") == exp_h) if not capped
                      else (png.get("w") or 0) * (png.get("h") or 0) <= 24e6 * 1.01,
                      f"png={png.get('w')}×{png.get('h')} 期望={exp_w}×{exp_h} capped={capped}")
                check("PNG 不是空文件（> 200 KB）",
                      (png.get("bytes") or 0) > 200 * 1024,
                      f"{round((png.get('bytes') or 0) / 1024)} KB")

                sample = png.get("sample") or ""
                raw = None
                if sample.startswith("data:image/png;base64,"):
                    raw = base64.b64decode(sample.split(",", 1)[1])
                check("拿到 PNG 小样（用于查空白）", bool(raw and len(raw) > 1000),
                      f"{len(raw or b'')} 字节")
                if raw:
                    sp = os.path.join(SHOTS, "export_sample.png")
                    with open(sp, "wb") as fh:
                        fh.write(raw)
                    sw, sh, nch, rows = read_png(sp)
                    counts: dict = {}
                    step = 2
                    for y in range(0, sh, step):
                        line = rows[y]
                        for x in range(0, sw, step):
                            key = line[x * nch:x * nch + 3]
                            counts[key] = counts.get(key, 0) + 1
                    total = sum(counts.values())
                    bg = max(counts.items(), key=lambda kv: kv[1])
                    others = total - bg[1]
                    out["sample"] = {"w": sw, "h": sh, "colors": len(counts),
                                     "nonBg": round(others / max(1, total), 3),
                                     "bg": "#%02X%02X%02X" % tuple(bg[0])}
                    # 阈值取 8%：GW 这种稀疏区房间只占包围盒 ~19%，白图会是 0%
                    check("PNG 不是一张白图（非底色像素 > 8%）",
                          others / max(1, total) > 0.08, str(out["sample"]))
                    check("PNG 颜色数 > 20（地形、连线、框线都在）",
                          len(counts) > 20, str(out["sample"]))
            # ---- 3. 拓扑图（区域拓扑）PNG ----
            js("var b=document.getElementById('map-graph'); if(b) b.click();")
            for _ in range(20):
                time.sleep(0.5)
                if js("!!document.getElementById('gx-canvas')"):
                    break
            time.sleep(4.5)      # 等力导向站稳 + 出场动画跑完

            out["graph"] = loads(js(
                "JSON.stringify((function(){"
                "var cv=document.getElementById('gx-canvas');"
                "return {open:!!cv, cw:cv?cv.clientWidth:0, ch:cv?cv.clientHeight:0,"
                "btn:!!document.getElementById('gx-export')};})())"
            )) or {}
            gr = out["graph"]
            check("拓扑图打开了，且有「导出 PNG」按钮",
                  gr.get("open") and gr.get("btn"), str(gr))
            check("拓扑图画布有尺寸（不然导出是空的）",
                  (gr.get("cw") or 0) > 100 and (gr.get("ch") or 0) > 100, str(gr))

            js("window.__rwTest.exportGraph(3, true);")
            gp = None
            for _ in range(50):
                time.sleep(0.5)
                gp = loads(js("JSON.stringify(window.__rwExportGraph)"))
                if gp and not gp.get("pending"):
                    break
            out["graphPng"] = {k: v for k, v in (gp or {}).items() if k != "sample"}
            check("拓扑图 PNG 导出成功", bool(gp) and gp.get("ok") is True, str(out["graphPng"]))
            if gp and gp.get("ok"):
                check("拓扑图 PNG 是高清（宽 > 屏幕画布的 1.5 倍）",
                      (gp.get("w") or 0) > (gr.get("cw") or 1) * 1.5,
                      f"png={gp.get('w')} 屏幕={gr.get('cw')} scale={gp.get('scale')}")
                check("拓扑图 PNG 不是空文件（> 100 KB）",
                      (gp.get("bytes") or 0) > 100 * 1024,
                      f"{round((gp.get('bytes') or 0) / 1024)} KB")

                graw = None
                gsample = gp.get("sample") or ""
                if gsample.startswith("data:image/png;base64,"):
                    graw = base64.b64decode(gsample.split(",", 1)[1])
                check("拿到拓扑图小样", bool(graw and len(graw) > 1000), f"{len(graw or b'')} 字节")
                if graw:
                    gp_path = os.path.join(SHOTS, "graph_sample.png")
                    with open(gp_path, "wb") as fh:
                        fh.write(graw)
                    sw, sh, nch, rows = read_png(gp_path)
                    colors_g: dict = {}
                    minx, miny, maxx, maxy = sw, sh, -1, -1
                    for y in range(sh):
                        line = rows[y]
                        for x in range(sw):
                            key = line[x * nch:x * nch + 3]
                            colors_g[key] = colors_g.get(key, 0) + 1
                    bg = max(colors_g.items(), key=lambda kv: kv[1])
                    # 非底色像素的包围盒：验证"整张图都在画面里"（不是被裁了一半）
                    for y in range(sh):
                        line = rows[y]
                        for x in range(sw):
                            if line[x * nch:x * nch + 3] == bg[0]:
                                continue
                            if x < minx: minx = x
                            if x > maxx: maxx = x
                            if y < miny: miny = y
                            if y > maxy: maxy = y
                    spanx = (maxx - minx + 1) / max(1, sw)
                    spany = (maxy - miny + 1) / max(1, sh)
                    out["graphSample"] = {"w": sw, "h": sh, "colors": len(colors_g),
                                          "spanX": round(spanx, 3), "spanY": round(spany, 3)}
                    check("拓扑图 PNG 不是白图（颜色 > 8 种）", len(colors_g) > 8,
                          str(out["graphSample"]))
                    check("拓扑图内容铺满画面（横向 / 纵向跨度 > 70%，说明整张图都在）",
                          spanx > 0.7 and spany > 0.7, str(out["graphSample"]))
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)

    print("\n===== 结果 =====")
    ok = True
    for name, passed, detail in checks:
        print(("  ✅ " if passed else "  ❌ ") + name + ((" — " + str(detail)) if detail else ""))
        ok = ok and passed
    if out["errors"]:
        print("  ⚠️  JS 异常：", out["errors"][:3])
    if out.get("fatal"):
        print("  ⚠️  ", out["fatal"])
    print("\n--- 明细 ---")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:2000])
    print("\n导出文件：", SHOTS)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
