"""区域地图（矢量版）与未探索清单的回归检查（真实 WebView2 窗口）。

用法： .venv/Scripts/python.exe build/check_map.py

检查内容：
    1. 区域表仍能打开地图弹窗，且弹窗里**没有 canvas**（底图已移除）
    2. SVG 房间方块数量 = 有坐标的房间数；已探索方块 = 完成度的 visited
    3. 未探索清单条数 = total − visited（与区域表同一口径）
    4. 地图层按钮：全部 + 各层；切层后 viewBox 变化
    5. 点未探索房间号 → 对应方块获得 focus 高亮
    6. 区域页底部出现「没踏足过的导入区域」入口
产物： docs/map_vector.png（窗口截图）
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
OUT_PNG = os.path.join(SHOTS, "map_vector.png")

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

            # 点总览格子 → 打开对应区域地图
            out["ovOpen"] = js(
                "(function(){var c=document.querySelector('.ov-cell[data-map]');if(!c) return null;"
                "var code=c.getAttribute('data-map'); c.click(); return code;})()"
            )
            time.sleep(0.8)
            check("点总览格子能打开地图",
                  bool(js("!document.getElementById('modal').hidden && "
                          "!!document.getElementById('map-svg')")),
                  str(out["ovOpen"]))
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(0.5)
            grab(os.path.join(SHOTS, "overview.bmp"))

            # 打开 GW 的地图（没去过就退回第一个）
            out["openTarget"] = js(
                "(function(){var b=document.querySelector('[data-map=\"GW\"]')||document.querySelector('[data-map]');"
                "if(!b) return null; var code=b.getAttribute('data-map'); b.click(); return code;})()"
            )
            time.sleep(1.0)

            out["modal"] = loads(js(
                "JSON.stringify((function(){"
                "var svg=document.getElementById('map-svg');"
                "return {open:!document.getElementById('modal').hidden,"
                "title:(document.getElementById('modal-title')||{}).textContent,"
                "sub:(document.getElementById('modal-sub')||{}).textContent,"
                "hasSvg:!!svg, hasCanvas:!!document.querySelector('#modal-body canvas'),"
                "rects:document.querySelectorAll('#map-svg rect.room').length,"
                "seen:document.querySelectorAll('#map-svg rect.room.seen').length,"
                "links:document.querySelectorAll('#map-svg line.link').length,"
                "pearls:document.querySelectorAll('#map-svg circle.pearl').length,"
                "layers:document.querySelectorAll('#map-layers [data-ml]').length,"
                "chips:document.querySelectorAll('#mu-body .mu-chip').length,"
                "nocoord:document.querySelectorAll('#mu-body .mu-chip.nocoord').length,"
                "empty:!!document.querySelector('.map-empty')};})())"
            ))
            m = out["modal"] or {}
            check("地图弹窗打开", m.get("open"))
            check("已移除底图（弹窗里没有 canvas）", m.get("hasSvg") and not m.get("hasCanvas"))
            check("画出了房间方块", (m.get("rects") or 0) > 0, f"rects={m.get('rects')}")
            check("分层按钮存在", (m.get("layers") or 0) >= 2, f"layers={m.get('layers')}")

            # 与完成度对账
            code = out.get("openTarget")
            out["completion"] = loads(js(
                "JSON.stringify(window.__rwTest.region('%s','White'))" % code
            ))
            cp = out["completion"] or {}
            expect_unvisited = None
            if cp.get("total") is not None and cp.get("visited") is not None:
                expect_unvisited = cp["total"] - cp["visited"]
            # 分母里有少数房间没有任何一版地图给坐标，画不出来但仍在清单里
            no_coord_total = (cp.get("total") or 0) - (m.get("rects") or 0)
            no_coord_seen = no_coord_total - (m.get("nocoord") or 0)
            check("已探索方块数 = visited − 无坐标的已访房间",
                  cp.get("visited") == (m.get("seen") or 0) + no_coord_seen,
                  f"visited={cp.get('visited')} seen={m.get('seen')} 无坐标已访={no_coord_seen}")
            check("未探索清单条数 = total − visited",
                  expect_unvisited == m.get("chips"),
                  f"expect={expect_unvisited} chips={m.get('chips')}")

            # ---- 清单三标签：全部 / 未探索 / 已探索 ----
            out["muTabs"] = loads(js(
                "JSON.stringify((function(){var t=document.querySelectorAll('[data-mu]');"
                "if(!t.length) return {none:true};"
                "var r={tabs:t.length, on:[], counts:{}};"
                "Array.prototype.forEach.call(t,function(b){"
                "  if(b.classList.contains('on')) r.on.push(b.getAttribute('data-mu'));"
                "  r.counts[b.getAttribute('data-mu')]=parseInt(b.querySelector('b').textContent,10);});"
                "r.chips=document.querySelectorAll('#mu-body .mu-chip').length;"
                "return r;})())"
            )) or {}
            tabs = out["muTabs"]
            check("清单有三个标签：全部 / 未探索 / 已探索",
                  tabs.get("tabs") == 3 and tabs.get("on") == ["unseen"], str(tabs))
            check("标签数字对账：全部 = 未探索 + 已探索",
                  tabs.get("counts", {}).get("unseen") == expect_unvisited
                  and tabs["counts"]["all"] == tabs["counts"]["unseen"] + tabs["counts"]["seen"],
                  f"{tabs.get('counts')}（未探索应 = {expect_unvisited}）")

            out["muSwitch"] = loads(js(
                "JSON.stringify((function(){"
                "document.querySelector('[data-mu=\\\"seen\\\"]').click();"
                "var seenN=document.querySelectorAll('#mu-body .mu-chip').length;"
                "var seenMarked=document.querySelectorAll('#mu-body .mu-chip.seen').length;"
                "var onSeen=document.querySelector('[data-mu].on').getAttribute('data-mu');"
                "document.querySelector('[data-mu=\\\"all\\\"]').click();"
                "var allN=document.querySelectorAll('#mu-body .mu-chip').length;"
                "var allSeen=document.querySelectorAll('#mu-body .mu-chip.seen').length;"
                "document.querySelector('[data-mu=\\\"unseen\\\"]').click();"
                "var backN=document.querySelectorAll('#mu-body .mu-chip').length;"
                "return {onSeen:onSeen, seenN:seenN, seenMarked:seenMarked,"
                "allN:allN, allSeen:allSeen, backN:backN};})())"
            )) or {}
            sw = out["muSwitch"]
            check("切到「已探索」列出所有去过的房间",
                  sw.get("onSeen") == "seen" and sw.get("seenN") == tabs["counts"]["seen"]
                  and sw.get("seenMarked") == sw.get("seenN"), str(sw))
            check("「全部」标签把两边合起来，并标出哪些去过",
                  sw.get("allN") == tabs["counts"]["all"] and sw.get("allSeen") == tabs["counts"]["seen"],
                  str(sw))
            check("切回「未探索」恢复原样", sw.get("backN") == expect_unvisited, str(sw))

            # 标签与地图联动：不在当前标签里的方块要压暗（先清掉之前点击留下的 focus）
            out["muDim"] = loads(js(
                "JSON.stringify((function(){"
                "var st=document.createElement('style');"
                "st.textContent='*{transition:none!important}';document.head.appendChild(st);"
                "var rs=[].slice.call(document.querySelectorAll('#map-svg rect.room'));"
                "rs.forEach(function(r){r.classList.remove('focus');});"
                "function op(el){return parseFloat(getComputedStyle(el).opacity);}"
                "var unseenRect=rs.filter(function(r){return r.getAttribute('data-seen')==='0';})[0];"
                "var seenRect=rs.filter(function(r){return r.getAttribute('data-seen')==='1';})[0];"
                "var r={};"
                "document.querySelector('[data-mu=\\\"unseen\\\"]').click();"
                "r.attrUnseen=document.getElementById('map-stage').getAttribute('data-filter');"
                "r.unseenOpUnseen=unseenRect?op(unseenRect):null;"
                "r.seenOpUnseen=seenRect?op(seenRect):null;"
                "r.hintUnseen=(document.getElementById('mu-hint')||{}).textContent||'';"
                "document.querySelector('[data-mu=\\\"seen\\\"]').click();"
                "r.attrSeen=document.getElementById('map-stage').getAttribute('data-filter');"
                "r.unseenOpSeen=unseenRect?op(unseenRect):null;"
                "r.seenOpSeen=seenRect?op(seenRect):null;"
                "document.querySelector('[data-mu=\\\"all\\\"]').click();"
                "r.unseenOpAll=unseenRect?op(unseenRect):null;"
                "r.seenOpAll=seenRect?op(seenRect):null;"
                "document.querySelector('[data-mu=\\\"unseen\\\"]').click();"
                "st.remove();"
                "return r;})())"
            )) or {}
            dim = out["muDim"]
            check("切标签会把状态写到地图上（data-filter）",
                  dim.get("attrUnseen") == "unseen" and dim.get("attrSeen") == "seen", str(dim))
            check("「未探索」标签下已探索方块变暗、未探索保持原样",
                  dim.get("seenOpUnseen") is not None and dim.get("seenOpUnseen") < 0.3
                  and dim.get("unseenOpUnseen") == 1, str(dim))
            check("「已探索」标签下未探索方块变暗、已探索保持原样",
                  dim.get("unseenOpSeen") is not None and dim.get("unseenOpSeen") < 0.3
                  and dim.get("seenOpSeen") == 1, str(dim))
            check("「全部」标签两边都不压暗",
                  dim.get("unseenOpAll") == 1 and dim.get("seenOpAll") == 1, str(dim))
            check("标签提示文案跟着变",
                  "已探索" in (dim.get("hintUnseen") or ""), str(dim.get("hintUnseen")))

            # 拍一张「已探索」标签：地图上没去过的那片是暗的
            js("document.querySelector('[data-mu=\\\"seen\\\"]').click();")
            time.sleep(0.5)
            grab(os.path.join(SHOTS, "map_tabs_dim.bmp"))
            js("document.querySelector('[data-mu=\\\"unseen\\\"]').click();")

            # 拍一张「全部」标签的清单：能同时看到去过 / 没去过的房间号
            js("document.querySelector('[data-mu=\\\"all\\\"]').click();")
            time.sleep(0.5)
            grab(os.path.join(SHOTS, "map_tabs.bmp"))
            js("document.querySelector('[data-mu=\\\"unseen\\\"]').click();")

            # 切层
            out["layer"] = loads(js(
                "JSON.stringify((function(){"
                "var svg=document.getElementById('map-svg'); var before=svg.getAttribute('viewBox');"
                "var b=document.querySelector('#map-layers [data-ml=\"1\"]');"
                "if(!b) return {skip:true}; b.click();"
                "var after=svg.getAttribute('viewBox');"
                "var vis=[].slice.call(document.querySelectorAll('#map-svg rect.room')).filter("
                "function(r){return getComputedStyle(r).display!=='none';}).length;"
                "return {before:before, after:after, visible:vis,"
                "onText:document.querySelector('#map-layers .sort-btn.on').textContent.trim()};})())"
            ))
            out["layerAll"] = loads(js(
                "JSON.stringify((function(){"
                "var b=document.querySelector('#map-layers [data-ml=\"all\"]'); if(b) b.click();"
                "var vis=[].slice.call(document.querySelectorAll('#map-svg rect.room')).filter("
                "function(r){return getComputedStyle(r).display!=='none';}).length;"
                "return {visible:vis};})())"
            ))
            check("切到某一层后可见房间变少",
                  (out["layer"].get("visible") or 0) < (m.get("rects") or 0),
                  f"layer={out['layer']}")

            # 点未探索房间号 → 高亮 + 居中放大
            out["focus"] = loads(js(
                "JSON.stringify((function(){"
                "var c=document.querySelector('#mu-body .mu-chip:not(.nocoord)');"
                "if(!c) return {skip:true}; var name=c.getAttribute('data-focus'); c.click();"
                "var r=document.querySelector('#map-svg [data-room=\"'+name+'\"]');"
                "var svg=document.getElementById('map-svg');"
                "return {name:name, focused:!!(r&&r.classList.contains('focus')),"
                "tf:svg.style.transform,"
                "pct:document.getElementById('map-zoom-pct').textContent};})())"
            ))
            check("点房间号能高亮对应方块", (out["focus"] or {}).get("focused"), str(out["focus"]))
            check("点房间号会把地图居中放大",
                  bool((out["focus"] or {}).get("tf")),
                  f"transform={(out['focus'] or {}).get('tf')} pct={(out['focus'] or {}).get('pct')}")

            # ---- 缩放 / 平移 ----
            out["zoom"] = loads(js(
                "JSON.stringify((function(){"
                "var stage=document.getElementById('map-stage'), svg=document.getElementById('map-svg');"
                "var b=document.getElementById('modal-body');"
                "var box=stage.getBoundingClientRect();"
                "document.querySelector('#map-zoom [data-zoom=\"reset\"]').click();"
                "var atFit=svg.style.transform || '';"
                "svg.dispatchEvent(new WheelEvent('wheel',{deltaY:-600,clientX:box.left+300,"
                "clientY:box.top+200,bubbles:true,cancelable:true}));"
                "var zoomed=svg.style.transform;"
                "var pct=document.getElementById('map-zoom-pct').textContent;"
                # 拖拽：放大后按住左键往左上拖 60 / 40 px
                "stage.dispatchEvent(new MouseEvent('mousedown',{button:0,clientX:box.left+400,"
                "clientY:box.top+300,bubbles:true,cancelable:true}));"
                "window.dispatchEvent(new MouseEvent('mousemove',{clientX:box.left+340,"
                "clientY:box.top+260,bubbles:true}));"
                "var dragged=svg.style.transform;"
                "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));"
                "var draggingCls=stage.classList.contains('dragging');"
                "document.querySelector('#map-zoom [data-zoom=\"reset\"]').click();"
                "var reset=svg.style.transform || '';"
                "svg.dispatchEvent(new WheelEvent('wheel',{deltaY:-600,clientX:box.left+300,"
                "clientY:box.top+200,bubbles:true,cancelable:true}));"
                "var again=svg.style.transform;"
                "stage.dispatchEvent(new WheelEvent('wheel',{deltaY:2400,clientX:box.left+300,"
                "clientY:box.top+200,bubbles:true,cancelable:true}));"
                "var outPct=document.getElementById('map-zoom-pct').textContent;"
                "return {atFit:atFit, zoomed:zoomed, pct:pct, dragged:dragged,"
                "draggingCls:draggingCls, reset:reset, again:again, outPct:outPct,"
                "svgW:svg.clientWidth, svgH:svg.clientHeight,"
                "stageH:stage.clientHeight,"
                "fill:Math.abs(svg.clientHeight-(stage.clientHeight-24))<5};})())"
            ))
            z = out["zoom"] or {}
            check("滚轮能把地图放大", bool(z.get("zoomed")), f"transform={z.get('zoomed')}")
            check("缩放百分比跟着变", (z.get("pct") or "100%") != "100%", f"pct={z.get('pct')}")
            check("拖拽改变平移量", bool(z.get("dragged")) and z.get("dragged") != z.get("zoomed"),
                  f"{z.get('zoomed')} → {z.get('dragged')}")
            check("松开鼠标后退出拖拽态", not z.get("draggingCls"))
            check("复位回到 100%", not z.get("reset"), f"transform={z.get('reset')!r}")
            check("缩小到下限不会小于 1 倍",
                  (z.get("outPct") or "") >= "100", f"outPct={z.get('outPct')}")
            check("SVG 撑满舞台高度（不再按内容自适应）", z.get("fill"),
                  f"svgH={z.get('svgH')} stageH={z.get('stageH')}")

            # 放大态截图（给文档用）
            js("(function(){var c=document.querySelector('#mu-body .mu-chip:not(.nocoord)');"
               "if(c) c.click();})()")
            time.sleep(0.7)
            grab(os.path.join(SHOTS, "map_zoom.bmp"))
            js("document.querySelector('#map-zoom [data-zoom=\"reset\"]').click();")
            time.sleep(0.3)

            time.sleep(0.6)
            grab(os.path.join(SHOTS, "map_vector.bmp"))

            # 亮色主题下的同一张图（直接改属性，避免动到用户 config）
            js("document.documentElement.setAttribute('data-theme','light');")
            time.sleep(0.7)
            grab(os.path.join(SHOTS, "map_vector_light.bmp"))
            js("document.documentElement.setAttribute('data-theme','dark');")

            # 竖长条区域（CC 宽高比 0.4）：等比铺满会缩成一条缝，默认要放大到看得清
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(0.5)
            js("var b=document.querySelector('[data-map=\"CC\"]'); if(b) b.click();")
            time.sleep(1.0)
            out["portrait"] = loads(js(
                "JSON.stringify((function(){var s=document.getElementById('map-svg');"
                "if(!s) return {open:false};"
                "return {open:true, pct:document.getElementById('map-zoom-pct').textContent,"
                "tf:s.style.transform||'', sheet:document.querySelectorAll('#map-sheet').length,"
                "async:document.getElementById('modal-sub').textContent};})())"
            ))
            pt = out["portrait"] or {}
            check("窄长区域默认放大到看得清", pt.get("open") and int((pt.get("pct") or "0%").rstrip("%")) > 100,
                  f"pct={pt.get('pct')} tb={pt.get('async')}")
            check("地图有「图纸」底板", pt.get("sheet") == 1, f"sheet={pt.get('sheet')}")

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
