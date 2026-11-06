"""房间布局卡（.txt 地形网格 → 画布）的回归检查（真实 WebView2 窗口）。

用法： .venv/Scripts/python.exe build/check_room.py

检查内容：
    1. 区域表 → 打开 GW 地图 → 未探索清单存在
    2. 点未探索房间号 → 房间卡打开，标题 = 房间号
    3. 卡片尺寸 / 格子数与 region_data 独立解析一致，cells 长度 = W×H
    4. 画布像素抽样：随机 160 格，像素颜色与 cells 的「空气/非空气」一致率 ≥ 90%
    5. 滚轮放大 → 百分比 > 100；拖拽 → 平移量变化；复位 → 回到 100%
    6. 「在地图上定位」→ 卡片关闭、地图仍在、对应方块高亮
    7. 在地图上点房间方块 → 卡片重新打开且是那间房
    8. Esc → 只关卡片，地图不关
产物： docs/room_card.bmp
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

from core import room_geo  # noqa: E402
from core.bridge import Api  # noqa: E402

TITLE = "RwSaveTool 房间卡检查"
OUT_BMP = os.path.join(SHOTS, "room_card.bmp")

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
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    with open(path, "wb") as fh:
        fh.write(b"BM")
        fh.write(struct.pack("<IHHI", 14 + 40 + size, 0, 0, 14 + 40))
        fh.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, size, 0, 0, 0, 0))
        fh.write(buf.raw)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print("[截图]", path, w, h)
    return True


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window(TITLE, html=html, js_api=api, width=1400, height=980, x=70, y=40)
    api.attach(window)
    checks: list[tuple[str, bool, str]] = []
    errors: list[str] = []

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{code[:70]}: {exc}")
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
            run_checks()
        finally:
            window.destroy()

    def run_checks():
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

        # ---- 1. 打开 GW 地图 ----
        js("var b=document.querySelector('[data-map=\"GW\"]'); if(b) b.click();")
        time.sleep(1.0)
        info = loads(js(
            "JSON.stringify({map:!document.getElementById('modal').hidden,"
            "chips:document.querySelectorAll('#mu-body .mu-chip').length})"
        ))
        check("GW 地图弹窗打开且有未探索清单",
              info and info.get("map") and info.get("chips", 0) > 0, str(info))

        # ---- 2. 点房间号 → 卡片 ----
        room = js(
            "(function(){var c=document.querySelector('#mu-body .mu-chip:not(.nocoord)');"
            "if(!c) return ''; var n=c.getAttribute('data-focus'); c.click(); return n;})()"
        )
        time.sleep(0.9)
        card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("点房间号打开房间卡", card.get("open") and card.get("room") == room,
              f"room={room} card={card.get('room')} open={card.get('open')}")
        check("卡片标题就是房间号", card.get("title") == room,
              f"title={card.get('title')}")

        # ---- 3. 与 region_data 独立解析对账 ----
        region = json.load(open(os.path.join(ROOT, "region_data", "GW.json"), encoding="utf-8"))
        ref = room_geo.geometry(region, room) if room else {}
        check("尺寸与后端解析一致",
              ref.get("ok") and card.get("w") == ref.get("w") and card.get("h") == ref.get("h"),
              f"卡片 {card.get('w')}×{card.get('h')} vs 解析 {ref.get('w')}×{ref.get('h')}")
        check("cells 长度 = W×H",
              card.get("cells") == (card.get("w") or 0) * (card.get("h") or 0),
              f"cells={card.get('cells')}")
        check("空气格数与后端一致",
              card.get("air") == (ref.get("cells") or "").count("0"),
              f"卡片 {card.get('air')} vs 解析 {(ref.get('cells') or '').count('0')}")
        check("卡片副标题带尺寸与状态",
              bool(card.get("sub")) and "格" in (card.get("sub") or ""), str(card.get("sub")))

        # ---- 4. 画布像素抽样 ----
        sample = loads(js("JSON.stringify(window.__rwTest.roomSample(160))")) or {}
        check("画布像素与 cells 一致（抽样 ≥90%）",
              sample.get("ready") and sample.get("ratio", 0) >= 0.9,
              f"{sample.get('hit')}/{sample.get('total')} = {sample.get('ratio')}")

        # ---- 5. 缩放 / 拖拽 / 复位 ----
        zoom = loads(js(
            "JSON.stringify((function(){"
            "var cv=document.getElementById('rm-canvas');var box=cv.getBoundingClientRect();"
            "var before=window.__rwTest.roomCard();"
            "cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-500,"
            "clientX:box.left+box.width/2,clientY:box.top+box.height/2,bubbles:true,cancelable:true}));"
            "var after=window.__rwTest.roomCard();"
            "return {before:before.scale, after:after.scale, tx0:before.tx, ty0:before.ty};})())"
        )) or {}
        check("滚轮能放大", zoom.get("after", 0) > zoom.get("before", 0) > 0,
              f"{zoom.get('before')}% → {zoom.get('after')}%")

        drag = loads(js(
            "JSON.stringify((function(){"
            "var cv=document.getElementById('rm-canvas');var box=cv.getBoundingClientRect();"
            "var t0=window.__rwTest.roomCard();"
            "cv.dispatchEvent(new MouseEvent('mousedown',{button:0,clientX:box.left+400,clientY:box.top+300,bubbles:true}));"
            "window.dispatchEvent(new MouseEvent('mousemove',{clientX:box.left+340,clientY:box.top+260,bubbles:true}));"
            "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));"
            "var t1=window.__rwTest.roomCard();"
            "return {tx0:t0.tx,ty0:t0.ty,tx1:t1.tx,ty1:t1.ty};})())"
        )) or {}
        check("拖拽改变平移量",
              (drag.get("tx1"), drag.get("ty1")) != (drag.get("tx0"), drag.get("ty0")),
              f"{drag.get('tx0')},{drag.get('ty0')} → {drag.get('tx1')},{drag.get('ty1')}")

        js("var b=document.querySelector('#rm-zoom [data-rzoom=\"reset\"]'); if(b) b.click();")
        time.sleep(0.35)
        reset = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("复位回到 100%", reset.get("scale") == 100, f"scale={reset.get('scale')}%")

        grab(OUT_BMP)

        # ---- 5.5 上一间 / 下一间（顺序 = 地图弹窗当前标签的清单，这里是「未探索」22 间） ----
        nav0 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        expect_unseen = int(js(
            "(function(){var b=document.querySelector('[data-mu=\\\"unseen\\\"] b');"
            "return b?b.textContent:'';})()"
        ) or 0)
        base = nav0.get("index") or 0
        check("卡片有上一间/下一间，顺序取当前标签的清单",
              nav0.get("order") == expect_unseen and (nav0.get("index") or 0) >= 0,
              f"order={nav0.get('order')} 未探索={expect_unseen} index={nav0.get('index')}")
        check("位次跟着当前房间走，首尾之外两边都可点",
              nav0.get("pos") == f"{base + 1} / {expect_unseen}"
              and nav0.get("prevOff") is (base == 0)
              and nav0.get("nextOff") is (base == expect_unseen - 1),
              f"pos={nav0.get('pos')} prevOff={nav0.get('prevOff')} nextOff={nav0.get('nextOff')}")

        want_next = nav0.get("nextRoom")
        js("document.getElementById('rm-next').click();")
        time.sleep(1.0)
        nav1 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("点「下一间」切到清单里的下一间",
              nav1.get("room") == want_next and nav1.get("index") == base + 1,
              f"期望 {want_next} 实际 {nav1.get('room')} index={nav1.get('index')}")
        check("切房间后画布重新适配（新房间重新算 fit、缩放回到 100%）",
              bool(nav1.get("w")) and nav1.get("scale") == 100,
              f"{nav1.get('w')}×{nav1.get('h')} scale={nav1.get('scale')}%")
        check("位次跟着走到下一格，两边都不再置灰",
              nav1.get("pos") == f"{base + 2} / {expect_unseen}" and nav1.get("prevOff") is False,
              f"pos={nav1.get('pos')} prevOff={nav1.get('prevOff')}")

        js("document.getElementById('rm-prev').click();")
        time.sleep(1.0)
        nav2 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("点「上一间」回到原来那间",
              nav2.get("room") == room and nav2.get("index") == base,
              f"room={nav2.get('room')} index={nav2.get('index')}")

        # 一路点到头：到头不循环，最后一间时「下一间」置灰
        js("(function(){var n=0;while(n<60&&!document.getElementById('rm-next').disabled){"
           "document.getElementById('rm-next').click();n++;}})();")
        time.sleep(1.6)
        navEnd = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("走到最后一间时「下一间」置灰、不循环",
              navEnd.get("index") == expect_unseen - 1 and navEnd.get("nextOff") is True
              and navEnd.get("pos") == f"{expect_unseen} / {expect_unseen}",
              f"index={navEnd.get('index')} pos={navEnd.get('pos')} nextOff={navEnd.get('nextOff')}")
        check("最后一间也能正常出图",
              bool(navEnd.get("w")) and navEnd.get("cells") == navEnd.get("w") * navEnd.get("h")
              and not (navEnd.get("sub") or "").startswith("无法显示"),
              f"{navEnd.get('w')}×{navEnd.get('h')} sub={navEnd.get('sub')}")

        # 回到第一间，后面的检查还用原来那间
        js("window.__rwTest.openRoom('GW','%s');" % room)
        time.sleep(0.8)

        # ---- 5.5 头部排版 + 文案（11-06 回归：按钮曾被压窄，中文逐字断成「自 / 动」） ----
        lay = loads(js(
            "JSON.stringify((function(){var mx=0,n=0;"
            "var bs=document.querySelectorAll('#rm-nav button, #rm-mark button, .rm-locate');"
            "for(var i=0;i<bs.length;i++){var h=bs[i].getBoundingClientRect().height;"
            "if(h>mx)mx=h;n++;}"
            "var sub=document.getElementById('rm-sub').getBoundingClientRect().height;"
            "return {maxBtn:Math.round(mx),btns:n,subH:Math.round(sub),"
            "cardW:Math.round(document.querySelector('.room-card').getBoundingClientRect().width)};"
            "})())"
        )) or {}
        check("房间卡头部按钮全部单行、副标题不折行（阈值：按钮 ≤30px / 副标题 ≤22px）",
              (lay.get("btns") or 0) >= 7 and (lay.get("maxBtn") or 99) <= 30
              and (lay.get("subH") or 99) <= 22, str(lay))
        check("原「在图里看」已改名「拓扑定位」",
              (js("(document.getElementById('rm-graph')||{}).textContent") or "").strip() == "拓扑定位",
              js("(document.getElementById('rm-graph')||{}).textContent") or "")

        # ---- 6. 定位按钮 ----
        js("var b=document.getElementById('rm-locate'); if(b) b.click();")
        time.sleep(0.9)
        loc = loads(js(
            "JSON.stringify({card:window.__rwTest.roomCard().open,"
            "map:!document.getElementById('modal').hidden,"
            "focus:document.querySelectorAll('#map-svg .room.focus').length})"
        )) or {}
        check("「在地图上定位」关闭卡片", loc.get("card") is False, str(loc))
        check("定位后地图仍在且方块高亮",
              loc.get("map") is True and loc.get("focus", 0) >= 1, str(loc))

        # ---- 7. 点方块开卡 ----
        clicked = js(
            "(function(){var r=document.querySelector('#map-svg [data-room]');"
            "if(!r) return ''; var n=r.getAttribute('data-room'); r.dispatchEvent("
            "new MouseEvent('click',{bubbles:true})); return n;})()"
        )
        time.sleep(0.9)
        card2 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("在地图上点方块也能开卡",
              card2.get("open") and card2.get("room") == clicked,
              f"clicked={clicked} card={card2.get('room')}")

        # ---- 8. Esc 只关卡片 ----
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
        time.sleep(0.4)
        esc = loads(js(
            "JSON.stringify({card:window.__rwTest.roomCard().open,"
            "map:!document.getElementById('modal').hidden})"
        )) or {}
        check("Esc 只关卡片，不关地图", esc.get("card") is False and esc.get("map") is True, str(esc))

        # ---- 9. 杆子（SU_A01 有竖杆与横杆） ----
        js("window.__rwTest.openRoom('SU','SU_A01');")
        time.sleep(1.0)
        su = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("SU_A01 解析出格子对象条目", (su.get("objects") or 0) > 300, f"objects={su.get('objects')}")
        check("竖杆合并成连续线段（段数 < 格数）",
              (su.get("beamV") or 0) > 0 and (su.get("beamV") or 0) < (su.get("objects") or 0),
              f"beamV={su.get('beamV')} objects={su.get('objects')}")
        check("横杆也画出来了", (su.get("beamH") or 0) > 0, f"beamH={su.get('beamH')}")
        beam = loads(js("JSON.stringify(window.__rwTest.roomBeamPixel())")) or {}
        check("杆子像素颜色 = 主题里的杆子色", beam.get("ready") and beam.get("match"), str(beam))

        check("管道口被标出来", (su.get("ports") or 0) > 0, f"ports={su.get('ports')}")
        port = loads(js("JSON.stringify(window.__rwTest.roomPortPixel())")) or {}
        check("管道口 T 形像素 = 管道色（≥30 点）",
              port.get("ready") and (port.get("hit") or 0) >= 30,
              f"hit={port.get('hit')} dir={port.get('dir')}")
        mark = loads(js("JSON.stringify(window.__rwTest.roomMarkPixel('exit'))")) or {}
        check("出口十字像素 = 出口色（≥60 点）",
              mark.get("ready") and (mark.get("hit") or 0) >= 60,
              f"hit={mark.get('hit')} cell={mark.get('cell')}")
        leg = loads(js(
            "JSON.stringify((function(){var l=document.getElementById('rm-legend');"
            "return {text:l.textContent, beam:l.querySelectorAll('.rm-lg-beam').length,"
            "port:l.querySelectorAll('.rm-lg-port').length,"
            "pipe:l.querySelectorAll('.rm-lg-pipe').length,"
            "cross:l.querySelectorAll('.rm-lg-cross').length};})())"
        )) or {}
        check("图例含杆子 / 管道口 / 管道 / 十字",
              leg.get("beam") == 1 and (leg.get("port") or 0) >= 1
              and (leg.get("pipe") or 0) >= 1 and (leg.get("cross") or 0) >= 1
              and "管道口" in (leg.get("text") or ""), str(leg))

        grab(os.path.join(SHOTS, "room_card_mark.bmp"))

        # ---- 10. 编号 5（生物巢穴）/ 6（可攀爬墙）：DS_A09 与 DS_A15 ----
        js("window.__rwTest.openRoom('DS','DS_A09');")
        time.sleep(1.3)
        ds9 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        kinds9 = ds9.get("markKinds") or {}
        check("DS_A09 有 1 个巢穴（编号 5）", kinds9.get("den") == 1, f"kinds={kinds9}")
        check("DS_A09 管道口 9 个 / 路线点 42 个 / 可攀爬墙 535 格",
              ds9.get("ports") == 9 and ds9.get("pipeDots") == 42 and ds9.get("climb") == 535,
              f"ports={ds9.get('ports')} dots={ds9.get('pipeDots')} climb={ds9.get('climb')}")
        den = loads(js("JSON.stringify(window.__rwTest.roomMarkPixel('den'))")) or {}
        check("巢穴十字像素 = 巢穴色（≥60 点）",
              den.get("ready") and (den.get("hit") or 0) >= 60, f"hit={den.get('hit')}")
        grab(os.path.join(SHOTS, "room_card_den.bmp"))

        js("window.__rwTest.openRoom('DS','DS_A15');")
        time.sleep(1.3)
        ds15 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("DS_A15 管道口 4 / 十字 4 / 路线点 13 / 可攀爬墙 139",
              ds15.get("ports") == 4 and ds15.get("marks") == 4
              and ds15.get("pipeDots") == 13 and ds15.get("climb") == 139,
              f"ports={ds15.get('ports')} marks={ds15.get('marks')} "
              f"dots={ds15.get('pipeDots')} climb={ds15.get('climb')}")
        tog = loads(js(
            "JSON.stringify((function(){var b=document.getElementById('rm-climb-toggle');"
            "if(!b) return {none:true}; var before=b.classList.contains('on'); b.click();"
            "return {before:before, after:b.classList.contains('on'),"
            "shown:window.__rwTest.roomCard().climbShown};})())"
        )) or {}
        check("可攀爬墙底色可一键开关",
              tog.get("before") is True and tog.get("after") is False
              and tog.get("shown") is False, str(tog))
        grab(os.path.join(SHOTS, "room_card_climb_off.bmp"))

        # ---- 11. 配色：默认＝编辑器灰阶，可自定义、可恢复 ----
        pal = loads(js(
            "JSON.stringify((function(){var cs=getComputedStyle(document.documentElement);"
            "function g(n){return cs.getPropertyValue(n).trim();}"
            "return {air:g('--rm-air'),solid:g('--rm-solid'),climb:g('--rm-climb'),"
            "pipe:g('--rm-pipe'),exit:g('--rm-exit')};})())"
        )) or {}
        check("默认配色 = 编辑器灰阶（空气 #535353 / 实心 #2f2f2f / 可攀爬 #3c3c3c / 管道 #777777）",
              pal.get("air") == "#535353" and pal.get("solid") == "#2f2f2f"
              and pal.get("climb") == "#3c3c3c" and pal.get("pipe") == "#777777",
              str(pal))

        rp = loads(js(
            "JSON.stringify((function(){document.getElementById('rm-palette').click();"
            "var m=document.getElementById('rp-modal');"
            "return {open:!m.hidden, items:m.querySelectorAll('[data-rp-k]').length,"
            "tabs:m.querySelectorAll('[data-rp-t]').length};})())"
        )) or {}
        check("「配色」弹窗打开：9 个颜色项 + 2 个主题页",
              rp.get("open") and rp.get("items") == 9 and rp.get("tabs") == 2, str(rp))
        time.sleep(0.7)
        grab(os.path.join(SHOTS, "room_palette.bmp"))

        chg = loads(js(
            "JSON.stringify((function(){"
            "var i=document.querySelector('#rp-grid [data-rp-k=\\\"air\\\"]');"
            "i.value='#123456'; i.dispatchEvent(new Event('input',{bubbles:true}));"
            "var cs=getComputedStyle(document.documentElement);"
            "return {css:cs.getPropertyValue('--rm-air').trim(),"
            "saved:window.__rwTest.roomPalette().custom.dark.air};})())"
        )) or {}
        check("改「空气」色 → CSS 变量与配置同时更新",
              chg.get("css") == "#123456" and chg.get("saved") == "#123456", str(chg))

        js("document.getElementById('rp-reset').click();")
        back = js(
            "(function(){return getComputedStyle(document.documentElement)"
            ".getPropertyValue('--rm-air').trim();})()"
        )
        check("「恢复本主题默认」回到编辑器灰阶", back == "#535353", str(back))

        js("document.getElementById('rp-close').click();")
        js("window.__rwTest.resetRoomPalette();")
        after = loads(js("JSON.stringify(window.__rwTest.roomPalette())")) or {}
        check("配色可完全恢复（不留自定义项）",
              not (after.get("custom") or {}).get("dark")
              and not (after.get("custom") or {}).get("light"), str(after.get("custom")))

    window.events.loaded += lambda: None
    webview.start(worker)

    print()
    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(("✅ " if ok else "❌ ") + name + ((" — " + detail) if detail else ""))
    print(f"\n{passed}/{len(checks)} 通过")
    if errors:
        print("JS 报错：")
        for e in errors:
            print("  ", e)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
