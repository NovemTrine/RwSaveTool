"""区域地图（几何图 + 房间清单）与区域页总览的回归检查（真实 WebView2 窗口）。

用法： .venv/Scripts/python.exe build/check_map.py

V1.20（2026-11-22）起**区域地图就是几何图**，方块图整体下线，所以这里验的是：
    1. 区域页的总览 / 选择器 / 「没踏足过的区域」入口仍然可用
    2. 打开地图 → 弹窗里是 `#geo-stage` + `regmap_svg` 出的 SVG，没有 canvas
    3. 方块图遗物一个不剩：无 `#map-base`、无 `#map-layers`、无 `.map-sheet`、无 `rect.room`
    4. 右侧清单分母 = 几何图上的房间（唯一真值）；「图上没有」单独成栏
    5. 三个标签与地图联动：计数自洽、`data-filter` 压暗、点房号居中高亮
    6. 缩放/平移走 viewBox；放大 2.2 倍自动换高清层
    7. 「区域拓扑」还能进能回（回到几何图）
产物： build/_shots/map_geo.bmp / map_geo_light.bmp / map_zoom.bmp
"""

from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 回归产物统一放 build/_shots，不污染 docs（docs 只放被文档引用的图）
SHOTS = os.path.join(ROOT, "build", "_shots")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402

TITLE = "RwSaveTool 地图检查"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
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


def grab(path: str) -> bool:
    hwnd = find_hwnd(TITLE)
    if not hwnd:
        print("[截图] 未找到窗口")
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    if not user32.PrintWindow(hwnd, mem, 0x2):
        user32.PrintWindow(hwnd, mem, 0)

    class BIH(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    size = w * h * 4
    buf = ctypes.create_string_buffer(size)
    got = gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    with open(path, "wb") as fh:
        fh.write(b"BM")
        fh.write(struct.pack("<IHHI", 14 + 40 + size, 0, 0, 14 + 40))
        fh.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, size, 0, 0, 0, 0))
        fh.write(buf.raw)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print("[截图]", path, w, h, "行数", got, "字节", os.path.getsize(path))
    return True


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window(TITLE, html=html, js_api=api, width=1400, height=980, x=70, y=40)
    api.attach(window)
    out: dict = {"errors": []}
    checks: list[tuple[str, bool, str]] = []

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

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

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
            # 保证从干净状态开始（上一轮失败可能留下手动挑选）
            js("window.__rwTest.resetPick && window.__rwTest.resetPick();")
            time.sleep(0.5)

            out["untouched"] = loads(js(
                "JSON.stringify((function(){var d=document.querySelector('.untouched-box');"
                "return {exists:!!d, chips:d?d.querySelectorAll('.mu-chip').length:0,"
                "summary:d?d.querySelector('summary').textContent.trim():''};})())"
            ))
            check("区域页有「没踏足过的区域」入口",
                  out["untouched"] and out["untouched"]["exists"],
                  str(out["untouched"]))

            # ---- 全域探索总览 ----
            out["overviewUI"] = loads(js(
                "JSON.stringify((function(){"
                "var box=document.querySelector('.ov-box'); if(!box) return {exists:false};"
                "var grid=document.getElementById('ov-grid'); var btn=document.getElementById('ov-toggle');"
                "btn.click(); var collapsed=grid.classList.contains('collapsed');"
                "btn.click(); var expanded=!grid.classList.contains('collapsed');"
                "return {exists:true, cells:box.querySelectorAll('.ov-cell').length,"
                "full:box.querySelectorAll('.ov-cell.full').length,"
                "zero:box.querySelectorAll('.ov-cell.zero').length,"
                "head:box.querySelector('.ov-big').textContent.trim(),"
                "bars:box.querySelectorAll('.ov-bar>i').length,"
                "collapsed:collapsed, expanded:expanded,"
                "mapCells:box.querySelectorAll('.ov-cell[data-map]').length,"
                "pickBtn:(document.getElementById('ov-pick')||{}).textContent||'',"
                "cellsCode:[].slice.call(box.querySelectorAll('.ov-cell')).map("
                "function(c){return c.getAttribute('data-map');}),"
                "ov:window.__rwTest.overview()};})())"
            ))
            out["campRegions"] = loads(js(
                "JSON.stringify((window.__rwTest.campaign('White')||{regions:[]}).regions.map("
                "function(r){return {code:r.name,pct:(r.completion||{}).pct,"
                "total:(r.completion||{}).total,visited:(r.completion||{}).visited};}))"
            ))
            ov = (out["overviewUI"] or {}).get("ov") or {}
            ui = out["overviewUI"] or {}
            check("区域页有全域探索总览", ui.get("exists"))
            check("总览格子数 = 算了分母的区域数",
                  ui.get("cells") == ov.get("regions"),
                  f"cells={ui.get('cells')} ov.regions={ov.get('regions')}")
            # 默认只统计「这个角色有活动」的区域：格子集合 == 存档里有状态的区域
            camp_codes = {str(r["code"]).upper() for r in (out["campRegions"] or [])
                          if r.get("pct") is not None and r.get("total")}
            cells = {str(c).upper() for c in (ui.get("cellsCode") or [])}
            check("默认只统计有活动的区域（不多算别的区域）",
                  cells == camp_codes,
                  f"多出 {sorted(cells - camp_codes)} 少了 {sorted(camp_codes - cells)}")
            check("默认不含白猫进不去的 LM / WA*",
                  "LM" not in cells and not any(c.startswith("W") for c in cells),
                  f"cells={sorted(cells)}")
            check("总览可收起/展开", ui.get("collapsed") and ui.get("expanded"))
            # 总览的「已踏足」求和必须等于表格里各行之和
            sums = [0, 0]
            for r in out["campRegions"] or []:
                if r.get("pct") is None or not r.get("total"):
                    continue
                sums[0] += r["visited"] or 0
                sums[1] += r["total"] or 0
            check("总览已踏足合计 = 各区域完成度之和",
                  sums == [ov.get("touchedVisited"), ov.get("touchedTotal")],
                  f"表内 {sums[0]}/{sums[1]} vs 总览 {ov.get('touchedVisited')}/{ov.get('touchedTotal')}")
            check("没有手动添加时，合计 = 已踏足",
                  ov.get("added") == 0 and ov.get("total") == ov.get("touchedTotal"),
                  f"added={ov.get('added')} total={ov.get('total')} touched={ov.get('touchedTotal')}")

            # ---- 区域选择：手动加一个没去过的区域 ----
            out["picker"] = loads(js(
                "JSON.stringify((function(){"
                "var b=document.getElementById('ov-pick'); if(!b) return {open:false}; b.click();"
                "var list=document.getElementById('pick-list'); if(!list) return {open:false};"
                "var rows=list.querySelectorAll('.pick-row');"
                "var dis=list.querySelectorAll('input[data-pick][disabled]').length;"
                "var notes=list.querySelectorAll('.pr-note').length;"
                "var lm=list.querySelector('input[data-pick=\"LM\"]');"
                "var lmNote=lm?lm.closest('.pick-row').querySelector('.pr-note'):null;"
                "return {open:!document.getElementById('modal').hidden, rows:rows.length,"
                "disabled:dis, notes:notes,"
                "lmNote:lmNote?lmNote.textContent:'' ,"
                "stat:(document.getElementById('pick-stat')||{}).textContent||'',"
                "access:Object.keys(window.__rwTest.accessNotes()).length};})())"
            ))
            pk = out["picker"] or {}
            check("「区域选择」按钮能打开选择器", pk.get("open"), str(pk)[:120])
            check("选择器列出全部导入区域，有活动的不可取消",
                  (pk.get("rows") or 0) > (pk.get("disabled") or 0) > 0,
                  f"rows={pk.get('rows')} 锁定={pk.get('disabled')}")
            check("选择器带可达性提示（region_access.json 已加载）",
                  (pk.get("access") or 0) >= 5 and bool(pk.get("lmNote")),
                  f"notes={pk.get('notes')} lm={pk.get('lmNote')}")
            time.sleep(0.8)     # 等 WebView2 把弹窗渲染出来，否则 PrintWindow 拿到旧帧
            grab(os.path.join(SHOTS, "region_picker.bmp"))

            # 勾上 LM → 应用
            out["pickApply"] = loads(js(
                "JSON.stringify((function(){"
                "var lm=document.querySelector('#pick-list input[data-pick=\"LM\"]');"
                "if(!lm) return {skip:true}; lm.checked=true;"
                "lm.dispatchEvent(new Event('change',{bubbles:true}));"
                "document.getElementById('pick-apply').click();"
                "return {pick:window.__rwTest.pick(), ov:window.__rwTest.overview(),"
                "cells:document.querySelectorAll('.ov-cell').length,"
                "hasLM:!!document.querySelector('.ov-cell[data-map=\"LM\"]'),"
                "btn:(document.getElementById('ov-pick')||{}).textContent||''};})())"
            ))
            pa = out["pickApply"] or {}
            check("手动加入 LM 后总览多一格",
                  pa.get("hasLM") and (pa.get("cells") or 0) == (ui.get("cells") or 0) + 1,
                  f"cells={(ui.get('cells'))}→{pa.get('cells')} hasLM={pa.get('hasLM')}")
            check("手动加入的区域计入合计",
                  ((pa.get("ov") or {}).get("added") or 0) == 1 and
                  ((pa.get("ov") or {}).get("total") or 0) > (ov.get("total") or 0),
                  f"added={(pa.get('ov') or {}).get('added')} total={ov.get('total')}→{(pa.get('ov') or {}).get('total')}")
            check("选择写入配置（按角色记住）",
                  "LM" in ((pa.get("pick") or {}).get("White") or []),
                  str((pa.get("pick") or {}).get("White")))

            # 取消勾选 → 恢复原状
            out["pickClear"] = loads(js(
                "JSON.stringify((function(){"
                "document.getElementById('ov-pick').click();"
                "var lm=document.querySelector('#pick-list input[data-pick=\"LM\"]');"
                "if(lm){ lm.checked=false; lm.dispatchEvent(new Event('change',{bubbles:true})); }"
                "document.getElementById('pick-apply').click();"
                "return {pick:window.__rwTest.pick(), ov:window.__rwTest.overview(),"
                "cells:document.querySelectorAll('.ov-cell').length,"
                "hasLM:!!document.querySelector('.ov-cell[data-map=\"LM\"]')};})())"
            ))
            pc = out["pickClear"] or {}
            check("取消勾选后恢复默认统计范围",
                  not pc.get("hasLM") and (pc.get("cells") or 0) == ui.get("cells") and
                  ("White" not in (pc.get("pick") or {})),
                  f"cells={pc.get('cells')} pick={pc.get('pick')}")

            # 点总览格子 → 打开对应区域地图（V1.20：区域地图 = 几何图 + 房间清单）
            out["ovOpen"] = js(
                "(function(){var c=document.querySelector('.ov-cell[data-map]');if(!c) return null;"
                "var code=c.getAttribute('data-map'); c.click(); return code;})()"
            )
            time.sleep(4.2)          # 几何图是现算的（冷启动 3 s 上下）
            out["ovModal"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.getElementById('geo-stage');"
                "return {open:!document.getElementById('modal').hidden, stage:!!st,"
                "svg:!!(st&&st.querySelector('svg.geo-svg')),"
                "rooms:st?st.querySelectorAll('.rm[data-room]').length:0};})())"
            ))
            om = out["ovModal"] or {}
            check("点总览格子能打开地图", om.get("open") and om.get("stage"), str(out["ovOpen"]))
            check("地图是几何图（有 SVG、有房间组）",
                  om.get("svg") and (om.get("rooms") or 0) > 0, str(om))
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(0.5)
            grab(os.path.join(SHOTS, "overview.bmp"))

            # 打开 GW 的地图（没去过就退回第一个）
            out["openTarget"] = js(
                "(function(){var b=document.querySelector('[data-map=\"GW\"]')||document.querySelector('[data-map]');"
                "if(!b) return null; var code=b.getAttribute('data-map'); b.click(); return code;})()"
            )
            time.sleep(4.2)

            out["modal"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.getElementById('geo-stage'); var svg=st&&st.querySelector('svg');"
                "return {open:!document.getElementById('modal').hidden,"
                "title:(document.getElementById('modal-title')||{}).textContent,"
                "sub:(document.getElementById('modal-sub')||{}).textContent,"
                "hasSvg:!!svg, hasCanvas:!!document.querySelector('#modal-body canvas'),"
                "rooms:st?st.querySelectorAll('.rm[data-room]').length:0,"
                "seen:st?st.querySelectorAll('.rm.seen').length:0,"
                "links:svg?svg.querySelectorAll('.ln').length:0,"
                "layers:document.querySelectorAll('#map-layers [data-ml]').length,"
                # 方块图的三件遗物：底图、图纸底板、方块矩形。必须一个都不剩
                "block:!!document.getElementById('map-base')||!!document.querySelector('.map-sheet')"
                "||!!document.querySelector('#map-svg rect.room'),"
                "chips:document.querySelectorAll('#mu-body .mu-chip[data-focus]').length,"
                "nofile:document.querySelectorAll('#mu-body .mu-chip[data-nofile]').length,"
                "stat:(document.getElementById('map-stat')||{}).textContent||'',"
                "meta:(document.getElementById('geo-meta')||{}).textContent||'',"
                "empty:!!document.querySelector('.map-empty')};})())"
            ))
            m = out["modal"] or {}
            o = out["ovModal"] or {}
            check("地图弹窗打开", m.get("open"), str(m.get("title")))
            check("弹窗里没有 canvas（纯 SVG 矢量）",
                  m.get("hasSvg") and not m.get("hasCanvas"), str(m)[:120])
            check("画出了房间（.rm[data-room]）", (m.get("rooms") or 0) > 0, f"rooms={m.get('rooms')}")
            check("方块图彻底下线（无底图 / 层按钮 / 图纸底板 / 方块矩形）",
                  not m.get("block") and not m.get("layers"), str(m)[:160])
            check("几何图有连线", (m.get("links") or 0) > 0, f"links={m.get('links')}")
            check("工具栏只剩「区域拓扑 / 设置」，没有「几何图 / 底图」",
                  js("!document.getElementById('map-geo') && !document.getElementById('map-base-btn')"
                     " && !!document.getElementById('map-graph')"))

            # ---- 清单分母 = 几何图上的房间（唯一真值） ----
            out["muAll"] = loads(js(
                "JSON.stringify((function(){"
                "document.querySelector('[data-mu=\"all\"]').click();"
                "return {chips:document.querySelectorAll('#mu-body .mu-chip[data-focus]').length,"
                "nofile:document.querySelectorAll('#mu-body .mu-chip[data-nofile]').length,"
                "rooms:document.querySelectorAll('#geo-stage .rm[data-room]').length,"
                "split:document.querySelectorAll('#mu-body .mu-split').length,"
                "on:document.querySelector('[data-mu].on').getAttribute('data-mu')};})())"
            ))
            ma = out["muAll"] or {}
            check("「全部」标签的清单条数 = 几何图上的房间数（分母以图为真值）",
                  ma.get("chips") == ma.get("rooms") and (ma.get("rooms") or 0) > 0,
                  f"chips={ma.get('chips')} rooms={ma.get('rooms')}")
            check("清单有、图上没有的房间单独成栏（有就显示分隔）",
                  (ma.get("nofile") or 0) == 0 or ma.get("split") == 1,
                  f"nofile={ma.get('nofile')} split={ma.get('split')}")

            # ---- 三个标签与地图联动 ----
            out["muTabs"] = loads(js(
                "JSON.stringify((function(){var t=document.querySelectorAll('[data-mu]');"
                "var r={tabs:t.length, on:[], counts:{}};"
                "Array.prototype.forEach.call(t,function(b){"
                "  if(b.classList.contains('on')) r.on.push(b.getAttribute('data-mu'));"
                "  r.counts[b.getAttribute('data-mu')]=parseInt(b.querySelector('b').textContent,10);});"
                "r.seen=document.querySelectorAll('#geo-stage .rm.seen').length;"
                "return r;})())"
            )) or {}
            tabs = out["muTabs"]
            check("清单有三个标签：全部 / 未探索 / 已探索",
                  tabs.get("tabs") == 3 and tabs.get("on") == ["all"], str(tabs))
            check("标签计数自洽：全部 = 未探索 + 已探索",
                  tabs.get("counts", {}).get("all")
                  == (tabs.get("counts", {}).get("unseen") or 0) + (tabs.get("counts", {}).get("seen") or 0),
                  str(tabs.get("counts")))
            check("「已探索」数 = 图上带 seen 类的房间数",
                  tabs.get("counts", {}).get("seen") == tabs.get("seen"),
                  f"tab={tabs.get('counts', {}).get('seen')} svg={tabs.get('seen')}")

            out["muSeen"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.createElement('style');"
                "st.textContent='*{transition:none!important}';document.head.appendChild(st);"
                "document.querySelector('[data-mu=\"seen\"]').click();"
                "var chips=document.querySelectorAll('#mu-body .mu-chip[data-focus]');"
                "var marked=document.querySelectorAll('#mu-body .mu-chip.seen').length;"
                "var stage=document.getElementById('geo-stage');"
                "var filter=stage.getAttribute('data-filter');"
                "var dim=[].slice.call(stage.querySelectorAll('.rm.dim'));"
                "var op=dim.length?parseFloat(getComputedStyle(dim[0]).opacity):null;"
                "var keep=[].slice.call(stage.querySelectorAll('.rm.seen'));"
                "var opSeen=keep.length?parseFloat(getComputedStyle(keep[0]).opacity):null;"
                "document.querySelector('[data-mu=\"unseen\"]').click();"
                "var un=document.querySelectorAll('#mu-body .mu-chip[data-focus]').length;"
                "var hint=(document.getElementById('mu-hint')||{}).textContent||'';"
                "st.remove();"
                "return {chips:chips.length, marked:marked, filter:filter, dimOpacity:op,"
                "seenOpacity:opSeen, unseen:un, hint:hint};})())"
            )) or {}
            sw = out["muSeen"]
            check("「已探索」标签只列去过的房间，且都带标记",
                  sw.get("chips") == tabs["counts"]["seen"] and sw.get("marked") == sw.get("chips"),
                  str(sw))
            check("切标签把状态写到舞台（data-filter）", sw.get("filter") == "seen", str(sw))
            check("「已探索」标签下未探索的房间变暗",
                  sw.get("dimOpacity") is not None and sw.get("dimOpacity") < 0.3
                  and sw.get("seenOpacity") == 1, str(sw))
            check("切回「未探索」恢复原样",
                  sw.get("unseen") == tabs["counts"]["unseen"]
                  and "已探索" in (sw.get("hint") or ""), str(sw.get("hint")))

            # ---- 点房间号：居中放大 + 高亮（房间卡会盖在上面，验完关掉） ----
            out["focus"] = loads(js(
                "JSON.stringify((function(){"
                "var c=document.querySelector('#mu-body .mu-chip[data-focus]');"
                "if(!c) return {skip:true}; var name=c.getAttribute('data-focus');"
                "var svg=document.querySelector('#geo-stage svg');"
                "var before=svg.getAttribute('viewBox');"
                "var st=document.getElementById('geo-stage');"
                "var fitW=Math.min(st.clientWidth,st.clientHeight);"
                "c.click();"
                "var g=null; [].forEach.call(document.querySelectorAll('#geo-stage .rm[data-room]'),"
                "function(el){if(!g&&String(el.getAttribute('data-room')).toUpperCase()===name.toUpperCase()) g=el;});"
                "return {name:name, focused:!!(g&&g.classList.contains('focus')),"
                "before:before, after:svg.getAttribute('viewBox'),"
                "pct:(document.getElementById('geo-pct')||{}).textContent||'',"
                "card:!!document.querySelector('.room-modal:not([hidden])')};})())"
            )) or {}
            fc = out["focus"]
            check("点房间号能高亮对应房间", fc.get("focused"), str(fc)[:140])
            check("点房间号会把图居中放大（viewBox 变小、百分比变大）",
                  fc.get("before") != fc.get("after")
                  and int((fc.get("pct") or "0%").rstrip("%")) > 100,
                  f"{fc.get('before')} → {fc.get('after')} pct={fc.get('pct')}")
            check("点房间号顺带打开房间卡（沿用旧约定）", fc.get("card"), str(fc.get("card")))

            # ---- 缩放 / 平移：改 viewBox，不改 transform ----
            out["zoom"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.getElementById('geo-stage'), svg=st.querySelector('svg');"
                "document.querySelector('#geo-zoom [data-gz=\"fit\"]').click();"
                "var vb0=svg.getAttribute('viewBox'); var tf0=svg.style.transform||'';"
                "document.querySelector('#geo-zoom [data-gz=\"in\"]').click();"
                "document.querySelector('#geo-zoom [data-gz=\"in\"]').click();"
                "var vb1=svg.getAttribute('viewBox');"
                "var pct=(document.getElementById('geo-pct')||{}).textContent||'';"
                "var box=st.getBoundingClientRect();"
                "st.dispatchEvent(new MouseEvent('mousedown',{button:0,clientX:box.left+300,"
                "clientY:box.top+200,bubbles:true,cancelable:true}));"
                "window.dispatchEvent(new MouseEvent('mousemove',{clientX:box.left+240,"
                "clientY:box.top+160,bubbles:true}));"
                "var vb2=svg.getAttribute('viewBox');"
                "var dragCls=st.classList.contains('dragging');"
                "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));"
                "document.querySelector('#geo-zoom [data-gz=\"fit\"]').click();"
                "var vb3=svg.getAttribute('viewBox');"
                "return {vb0:vb0, vb1:vb1, vb2:vb2, vb3:vb3, pct:pct, tf:tf0, dragCls:dragCls,"
                "afterUp:st.classList.contains('dragging')};})())"
            )) or {}
            z = out["zoom"]
            check("滚轮/按钮缩放改的是 viewBox（不是 CSS transform）",
                  z.get("vb0") != z.get("vb1") and not z.get("tf"),
                  f"{z.get('vb0')} → {z.get('vb1')} tf={z.get('tf')!r}")
            check("缩放百分比跟着变", int((z.get("pct") or "0%").rstrip("%")) > 100, f"pct={z.get('pct')}")
            check("拖拽改变平移（viewBox 原点）", z.get("vb2") != z.get("vb1"),
                  f"{z.get('vb1')} → {z.get('vb2')}")
            check("松开鼠标后退出拖拽态", not z.get("afterUp"), str(z.get("dragCls")))
            check("「适应」把图复位到整图", z.get("vb3") == z.get("vb0"),
                  f"{z.get('vb3')} vs {z.get('vb0')}")

            # ---- 放大 2.2 倍 → 自动换高清层 ----
            for _ in range(4):
                js("document.querySelector('#geo-zoom [data-gz=\"in\"]').click();")
            time.sleep(3.4)
            out["hd"] = loads(js(
                "JSON.stringify({meta:(document.getElementById('geo-meta')||{}).textContent||'',"
                "svgs:document.querySelectorAll('#geo-stage svg').length})"
            )) or {}
            check("放大 2 倍以上自动换高清层", "高清" in (out["hd"].get("meta") or ""),
                  str(out["hd"]))
            js("document.querySelector('#geo-zoom [data-gz=\"fit\"]').click();")

            # 放大态截图（给文档用）
            js("(function(){var c=document.querySelector('#mu-body .mu-chip[data-focus]');"
               "if(c) c.click();})()")
            time.sleep(0.7)
            grab(os.path.join(SHOTS, "map_zoom.bmp"))
            js("var b=document.getElementById('rm-close'); if(b) b.click();")
            js("document.querySelector('#geo-zoom [data-gz=\"fit\"]').click();")
            time.sleep(0.4)
            grab(os.path.join(SHOTS, "map_geo.bmp"))

            # 亮色主题下的同一张图（直接改属性，避免动到用户 config）
            js("document.documentElement.setAttribute('data-theme','light');")
            time.sleep(0.7)
            grab(os.path.join(SHOTS, "map_geo_light.bmp"))
            js("document.documentElement.setAttribute('data-theme','dark');")

            # ---- 工具栏「区域拓扑」仍然可用，且能回得来 ----
            js("document.getElementById('map-graph').click();")
            time.sleep(1.8)
            check("「区域拓扑」能从地图页打开关系图",
                  bool(js("!!document.getElementById('gx-stage')")))
            js("var b=document.getElementById('gx-back'); if(b) b.click();")
            time.sleep(3.2)
            check("关系图「← 地图」回到的是几何图（不是方块图）",
                  bool(js("!!document.getElementById('geo-stage') && "
                          "!!document.querySelector('#geo-stage svg.geo-svg')")))
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(0.5)

            # ---- 窄长条区域（CC 宽高比 0.4）：几何图照样铺满舞台 ----
            js("var b=document.querySelector('[data-map=\"CC\"]'); if(b) b.click();")
            time.sleep(4.2)
            out["narrow"] = loads(js(
                "JSON.stringify((function(){var st=document.getElementById('geo-stage');"
                "var svg=st&&st.querySelector('svg');"
                "if(!svg) return {open:false};"
                "var b=st.getBoundingClientRect();"
                "return {open:true, rooms:st.querySelectorAll('.rm[data-room]').length,"
                "pct:(document.getElementById('geo-pct')||{}).textContent||'',"
                "fillsH:Math.abs(svg.getBoundingClientRect().height-b.height)<4,"
                "sub:(document.getElementById('modal-sub')||{}).textContent};})())"
            )) or {}
            nr = out["narrow"]
            check("窄长区域也能画出房间", nr.get("open") and (nr.get("rooms") or 0) > 0, str(nr)[:140])
            check("几何图撑满舞台高度", nr.get("fillsH"), f"pct={nr.get('pct')}")

            out["final"] = loads(js(
                "JSON.stringify({modalStillOpen:!document.getElementById('modal').hidden,"
                "errors:window.__rwErrors||null})"
            ))
        finally:
            window.destroy()

    webview.start(worker)

    print("\n===== 结果 =====")
    ok = True
    for name, passed, detail in checks:
        print(("  ✅ " if passed else "  ❌ ") + name + ((" — " + detail) if detail else ""))
        ok = ok and passed
    if out["errors"]:
        print("  ⚠️  JS 异常：", out["errors"])
    print("\n--- 明细 ---")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:2600])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
