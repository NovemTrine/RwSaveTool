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


def effective_exits(region: dict, name: str) -> list:
    """口径 A（《出口编号规则》§15.4）：所有层里 order 最高、且含这间房、
    且这间房有 exits 的那条记录。前端 effectiveRoom() 必须与它逐条一致。"""
    best, best_order = None, -1e9
    for layer in region.get("layers") or []:
        order = layer.get("order") or 0
        for room in layer.get("rooms") or []:
            if str(room.get("name", "")).upper() != str(name).upper():
                continue
            if not room.get("exits"):
                continue
            if order >= best_order:
                best_order, best = order, room
    return (best or {}).get("exits") or []


def canvas_exit_cells(code: str, name: str) -> list:
    """画布实际会画的出口格（房间文件里 type=4 的格子）。

    画布画十字用「房间文件」，右栏读「生效层」，两者可能来自不同层（实测 76 间房
    出口条数不等），P4 的「行 → 格子」对应就是拿这两份数据对齐出来的。"""
    path = os.path.join(ROOT, "region_data", code + ".json")
    region = json.load(open(path, encoding="utf-8"))
    hit, _ = room_geo.find_file(region, name, None)
    if not hit:
        return []
    try:
        data = room_geo.load(hit)
    except Exception:
        return []
    return [(m[0], m[1]) for m in data.get("marks") or [] if m[2] == room_geo.MARK_EXIT]


def exit_links(ex: list, cells: list) -> list:
    """镜像前端 rmBuildExitLinks()：出口行 → 画布格子能不能对上（1/0）。

    规则必须一致：先按坐标匹配十字；条数相同才退化成按序号；都对不上记 0。
    这份镜像用来在前端之外独立算出「哪些行该标无对应格」，避免自我验证。"""
    used = [False] * len(cells)
    same = len(cells) == len(ex)
    out = []
    for i, e in enumerate(ex):
        hit = -1
        for k, c in enumerate(cells):
            if used[k]:
                continue
            if c[0] == e.get("x") and c[1] == e.get("y"):
                hit = k
                break
        if hit < 0 and same and i < len(cells) and not used[i]:
            hit = i
        if hit < 0:
            out.append(0)
            continue
        used[hit] = True
        out.append(1)
    return out


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
        # 区域地图是现算的几何图：冷启动 2–4 s，加上 117 个区域的 detail 并发加载会更久。
        # 死等 4.2 s 在大区上会偶发抢跑（读到还没渲染的清单），改成轮询到第一个 .rm 出现。
        for _ in range(30):
            time.sleep(0.5)
            if js("document.querySelectorAll('#geo-stage .rm[data-room]').length > 0"):
                break
        time.sleep(0.6)
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
        js("(function(){var n=0;var cap=%d;"
           "while(n<cap&&!document.getElementById('rm-next').disabled){"
           "document.getElementById('rm-next').click();n++;}})();" % (expect_unseen + 4))
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
        # 地图可能是现算的（几何图冷启动 3 s），高亮只亮 2.8 s，所以轮询"有没有亮过"，
        # 不能靠一个固定 sleep：睡太短抓不到、睡太长高亮已经自己灭了。
        seen_focus = 0
        for _ in range(14):
            time.sleep(0.4)
            seen_focus = js("document.querySelectorAll('#geo-stage .rm.focus').length") or 0
            if seen_focus:
                break
        loc = loads(js(
            "JSON.stringify({card:window.__rwTest.roomCard().open,"
            "map:!document.getElementById('modal').hidden})"
        )) or {}
        check("「在地图上定位」关闭卡片", loc.get("card") is False, str(loc))
        check("定位后地图仍在且房间高亮",
              loc.get("map") is True and seen_focus >= 1, f"{loc} focus={seen_focus}")

        # ---- 7. 点房间开卡（V1.20 起地图是几何图） ----
        clicked = js(
            "(function(){var r=document.querySelector('#geo-stage .rm[data-room]');"
            "if(!r) return ''; var n=r.getAttribute('data-room'); r.dispatchEvent("
            "new MouseEvent('click',{bubbles:true})); return n;})()"
        )
        time.sleep(0.9)
        card2 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("在地图上点房间也能开卡",
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

        # ---- 10.1 №3：图例各类**独立**开关（V1.24）----
        # 关掉「管道」：绘制要停，但图例上的计数不能消失（只是变灰）。
        tog2 = loads(js(
            "JSON.stringify((function(){var b=document.querySelector('#rm-legend [data-k=\\\"pipe\\\"]');"
            "if(!b) return {none:true}; var before=b.classList.contains('on'); b.click();"
            "var card=window.__rwTest.roomCard();"
            "return {before:before, after:b.classList.contains('on'),"
            "shown:card.marksShown && card.marksShown.pipe, dots:card.pipeDots,"
            "legend:document.getElementById('rm-legend').textContent};})())"
        )) or {}
        check("图例「管道」能单独关掉（其余类不受影响）",
              tog2.get("before") is True and tog2.get("after") is False
              and tog2.get("shown") is False and (tog2.get("dots") or 0) > 0
              and "管道" in (tog2.get("legend") or ""), str(tog2))
        back2 = loads(js(
            "JSON.stringify((function(){var b=document.querySelector('#rm-legend [data-k=\\\"pipe\\\"]');"
            "if(b) b.click(); return {on:b?b.classList.contains('on'):null,"
            "shown:window.__rwTest.roomCard().marksShown.pipe};})())"
        )) or {}
        check("再点一下恢复显示", back2.get("on") is True and back2.get("shown") is True, str(back2))

        # ---- 10.2 №8：门房的业力门槛（烘焙进 region_data，只显示文字）----
        js("window.__rwTest.openRoom('SU','GATE_SU_DS');")
        time.sleep(1.4)
        gate = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("门房标题显示「业力门 左4/右2」",
              "业力门 左4/右2" in (gate.get("sub") or ""), gate.get("sub"))
        grab(os.path.join(SHOTS, "room_card_gate_karma.bmp"))

        # ---- 10.5 P4：默认全屏两栏 + 右侧出口清单 ----
        # P4 起默认全屏：右栏清单只在全屏可见，默认紧凑会让「出口跳转 / 悬停高亮」没有入口。
        js("window.__rwTest.openRoom('GW','%s');" % room)
        time.sleep(1.2)
        wide = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("默认就是全屏两栏（P4 起，右栏才有入口）",
              wide.get("full") is True and wide.get("sideShown") is True
              and (wide.get("sideW") or 0) >= 200 and (wide.get("stageH") or 0) > 200,
              f"full={wide.get('full')} side={wide.get('sideShown')} "
              f"sideW={wide.get('sideW')} stageH={wide.get('stageH')}")

        js("document.getElementById('rm-full').click();")
        time.sleep(1.0)
        compact = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("点「紧凑」后卡片变窄、右栏收起、画布仍撑开",
              compact.get("full") is False and compact.get("sideShown") is False
              and (compact.get("cardW") or 0) < (wide.get("cardW") or 0)
              and (compact.get("stageH") or 0) > 200,
              f"full={compact.get('full')} side={compact.get('sideShown')} "
              f"cardW={compact.get('cardW')} stageH={compact.get('stageH')}")

        js("document.getElementById('rm-full').click();")
        time.sleep(1.0)
        wide = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("点回「全屏」两栏还原且不横向溢出",
              wide.get("full") is True and wide.get("sideShown") is True
              and (wide.get("bodyOverflow") or 0) <= 1,
              f"full={wide.get('full')} side={wide.get('sideShown')} "
              f"overflow={wide.get('bodyOverflow')}")

        # ---- 10.6 全屏时关闭键不能被操作组压住（S1-B）----
        # .modal-card.full .modal-head 的 padding 会盖掉 .room-head 的 padding-right:58px，
        # 全屏后 × 会正好落进按钮组尾部按钮的矩形里，肉眼就是「关闭键消失了」。
        geo = loads(js(
            "JSON.stringify((function(){"
            "var c=document.getElementById('rm-close');"
            "var a=document.querySelector('#room-modal .rm-actions');"
            "if(!c||!a) return null;"
            "var rc=c.getBoundingClientRect(), ra=a.getBoundingClientRect();"
            "var overlap=!(rc.right<=ra.left||rc.left>=ra.right||rc.bottom<=ra.top||rc.top>=ra.bottom);"
            "return {overlap:overlap,"
            " close:[Math.round(rc.left),Math.round(rc.top),Math.round(rc.right)],"
            " actsRight:Math.round(ra.right),"
            " visible:rc.width>0&&rc.height>0};})())"
        )) or {}
        check("全屏时关闭键可见且不与操作组重叠",
              geo.get("visible") is True and geo.get("overlap") is False,
              f"overlap={geo.get('overlap')} close={geo.get('close')} "
              f"actsRight={geo.get('actsRight')}")

        ref_ex = effective_exits(region, room)
        n_ref = len(ref_ex)
        n_unk = sum(1 for e in ref_ex if not e.get("to"))
        check("出口清单条数 = 数据里的出口数（同一口径）",
              wide.get("exits") == n_ref and wide.get("exitsCounted") == n_ref,
              f"行 {wide.get('exits')} / 读数 {wide.get('exitsCounted')} / 数据 {n_ref}")
        check("没有去向的出口在清单里标成「未知」",
              wide.get("exitsUnknown") == n_unk,
              f"未知行 {wide.get('exitsUnknown')} / 数据 {n_unk} "
              f"（截断={wide.get('exitTruncated')}）")
        grab(os.path.join(SHOTS, "room_card_full.bmp"))

        # ---- 10.7 出口清单点击跳转（S2）----
        row0_to = (ref_ex[0].get("to") if ref_ex else None)
        js("var r=document.querySelector('#rm-exits .rm-exit-row'); if(r) r.click();")
        time.sleep(1.4)
        jumped = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        if row0_to:
            check("点出口清单第一行跳到目标房间",
                  jumped.get("open") is True
                  and str(jumped.get("room") or "").upper() == str(row0_to).upper(),
                  f"{room} 的 1 号口 → {row0_to}，卡片 {jumped.get('room')}")
            check("跳转后副标题标出来路",
                  "来自" in (jumped.get("sub") or ""),
                  f"sub={jumped.get('sub')}")
        else:
            check("点没有去向的出口行不跳转（只提示）",
                  jumped.get("open") is True
                  and str(jumped.get("room") or "").upper() == str(room).upper(),
                  f"卡片仍在 {jumped.get('room')}")
        js("window.__rwTest.openRoom('GW','%s');" % room)
        time.sleep(1.0)

        # 小窗口（1366×768 笔记本的可用区）下两栏仍然各自成立
        try:
            window.resize(1180, 720)
        except Exception:
            pass
        time.sleep(1.0)
        small = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("小窗口（1180×720）全屏两栏仍不溢出",
              (small.get("bodyOverflow") or 0) <= 1 and small.get("sideShown") is True
              and (small.get("stageH") or 0) > 200,
              f"overflow={small.get('bodyOverflow')} side={small.get('sideShown')} "
              f"stageH={small.get('stageH')} card={small.get('cardW')}×{small.get('cardH')}"
              f"（画面 {small.get('viewW')}×{small.get('viewH')}）")
        try:
            window.resize(1400, 980)
        except Exception:
            pass
        time.sleep(0.8)

        # ---- 10.8 P4：悬停右栏某行 → 画布点亮对应出口（方案 C）----
        # 常驻不画徽章；悬停第 i 行才在画布上叠「环 + 数字」，一次只亮一个，不会叠在一起。
        js("window.__rwTest.openRoom('GW','%s');" % room)
        time.sleep(1.3)
        base = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        ref_ex = effective_exits(region, room)
        links = base.get("exitLinks") or []
        want_links = exit_links(ref_ex, canvas_exit_cells("GW", room))
        check("「行 → 格子」的对应与独立复算一致",
              links == want_links and any(links),
              f"行 {len(ref_ex)} 期望 {want_links} 实测 {links} "
              f"无格={base.get('exitNoCell')}")

        # 挑第一行「画布上确有格子」的出口来悬停（极少数房间第 1 行就缺格）
        good = [i for i, v in enumerate(links) if v]
        if good:
            gi = good[0]
            js("var r=document.querySelector('#rm-exits .rm-exit-row[data-rmexit=\"%d\"]');"
               "if(r) r.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));" % gi)
            time.sleep(0.5)
            h0 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            px0 = loads(js("JSON.stringify(window.__rwTest.roomBadgePixel())")) or {}
            want0 = [ref_ex[gi].get("x"), ref_ex[gi].get("y")]
            check("悬停某行：行加高亮、画布点亮同一个出口格、徽章画出强调色",
                  h0.get("hoverExit") == gi and h0.get("hoverRowMark") == 1
                  and (h0.get("hoverCell") or [None, None])[:2] == want0
                  and px0.get("match") is True,
                  f"行 {gi + 1} hover={h0.get('hoverExit')} mark={h0.get('hoverRowMark')} "
                  f"cell={h0.get('hoverCell')} want={want0} pixel={px0}")
            grab(os.path.join(SHOTS, "room_card_hover.bmp"))

            if len(good) >= 2:
                gi2 = good[1]
                js("var r=document.querySelector('#rm-exits .rm-exit-row[data-rmexit=\"%d\"]');"
                   "if(r) r.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));" % gi2)
                time.sleep(0.5)
                h1 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
                want1 = [ref_ex[gi2].get("x"), ref_ex[gi2].get("y")]
                check("换到另一行：高亮跟着换，且仍然只亮一个",
                      h1.get("hoverExit") == gi2 and h1.get("hoverRowMark") == 1
                      and (h1.get("hoverCell") or [None, None])[:2] == want1,
                      f"行 {gi2 + 1} hover={h1.get('hoverExit')} "
                      f"mark={h1.get('hoverRowMark')} cell={h1.get('hoverCell')} want={want1}")
        else:
            check("悬停高亮样本（这间房画布没有出口格，跳过）", True, "skipped")

        js("var b=document.getElementById('rm-exits');"
           "if(b) b.dispatchEvent(new MouseEvent('mouseleave'));")
        time.sleep(0.4)
        hz = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("鼠标移出清单：高亮消失、画布回到常态",
              hz.get("hoverExit") == -1 and hz.get("hoverRowMark") == 0,
              f"hover={hz.get('hoverExit')} mark={hz.get('hoverRowMark')}")

        # 层不一致的房间：行比画布格子多的那些，悬停时不许画「悬空徽章」
        mm_room = None
        mm_expect = []
        seen_mm = set()
        for layer in region.get("layers") or []:
            for r in layer.get("rooms") or []:
                nm = str(r.get("name") or "")
                if not nm or nm in seen_mm:
                    continue
                seen_mm.add(nm)
                ex = effective_exits(region, nm)
                if not ex:
                    continue
                ok = exit_links(ex, canvas_exit_cells("GW", nm))
                if 0 in ok:
                    mm_room, mm_expect = nm, ok
                    break
            if mm_room:
                break
        if mm_room:
            js("window.__rwTest.openRoom('GW','%s');" % mm_room)
            time.sleep(1.3)
            mm = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            mm_links = mm.get("exitLinks") or []
            bad = [i for i, v in enumerate(mm_links) if not v]
            check("层不一致的房间：对不上的行标「画布无对应格」",
                  mm_links == mm_expect and (mm.get("exitNoCell") or 0) == len(bad)
                  and len(bad) >= 1,
                  f"{mm_room} 期望 {mm_expect} 实测 {mm_links} "
                  f"无格 {mm.get('exitNoCell')} 行 {mm.get('exitsCounted')}")
            if bad:
                js("var r=document.querySelector('#rm-exits .rm-exit-row[data-rmexit=\"%d\"]');"
                   "if(r) r.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));" % bad[0])
                time.sleep(0.5)
                mb = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
                mbpx = loads(js("JSON.stringify(window.__rwTest.roomBadgePixel())")) or {}
                check("悬停「无对应格」的行：行高亮但不画悬空徽章",
                      mb.get("hoverExit") == bad[0] and mb.get("hoverRowMark") == 1
                      and mbpx.get("match") is not True,
                      f"{mm_room} 第 {bad[0] + 1} 行 hover={mb.get('hoverExit')} "
                      f"mark={mb.get('hoverRowMark')} pixel={mbpx}")
            js("var b=document.getElementById('rm-exits');"
               "if(b) b.dispatchEvent(new MouseEvent('mouseleave'));")
            time.sleep(0.3)
        else:
            check("层不一致样本（GW 里没找到，跳过）", True, "skipped")

        time.sleep(0.4)
        cfg_now = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("全屏状态写进 config.ui.roomCardFull",
              (cfg_now.get("ui") or {}).get("roomCardFull") is True,
              f"roomCardFull={(cfg_now.get('ui') or {}).get('roomCardFull')}")

        js("document.getElementById('rm-full').click();")
        time.sleep(0.7)
        back = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        cfg_back = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("切到紧凑也会落盘（不污染配置）",
              back.get("full") is False and back.get("sideShown") is False
              and (cfg_back.get("ui") or {}).get("roomCardFull") is False,
              f"full={back.get('full')} cfg={(cfg_back.get('ui') or {}).get('roomCardFull')}")

        # 默认是全屏，测完要切回去，别把主人的配置留在紧凑上
        js("document.getElementById('rm-full').click();")
        time.sleep(0.7)
        cfg_rest = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("切回全屏并落盘（恢复默认）",
              (cfg_rest.get("ui") or {}).get("roomCardFull") is True,
              f"roomCardFull={(cfg_rest.get('ui') or {}).get('roomCardFull')}")

        # 截断房间：SL_D01 是 4 个出口 / 3 条连接（方案 A 的典型样本）
        js("window.__rwTest.openRoom('SL','SL_D01');")
        time.sleep(1.3)
        sl = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        sl_ref = effective_exits(
            json.load(open(os.path.join(ROOT, "region_data", "SL.json"), encoding="utf-8")),
            "SL_D01")
        sl_unk = sum(1 for e in sl_ref if not e.get("to"))
        check("截断房间：行数照给，尾部标「未知」而不是少一行",
              sl.get("exits") == len(sl_ref) == sl.get("exitsCounted")
              and sl.get("exitTruncated") is True
              and (sl.get("exitsUnknown") or 0) == sl_unk and sl_unk >= 1,
              f"行 {sl.get('exits')} / 数据 {len(sl_ref)} / 未知 {sl.get('exitsUnknown')} "
              f"/ 应为 {sl_unk} / 截断={sl.get('exitTruncated')} note={sl.get('exitNote')}")
        check("截断房间的右栏有说明文案",
              "编号" in (sl.get("exitNote") or "") and "未知" in (sl.get("exitNote") or ""),
              sl.get("exitNote"))

        # ---- 11. 配色：默认＝区域地图那套，可自定义、可恢复 ----
        pal = loads(js(
            "JSON.stringify((function(){var cs=getComputedStyle(document.documentElement);"
            "function g(n){return cs.getPropertyValue(n).trim();}"
            "return {air:g('--rm-air'),solid:g('--rm-solid'),climb:g('--rm-climb'),"
            "pipe:g('--rm-pipe'),exit:g('--rm-exit')};})())"
        )) or {}
        # V1.15 定案：房间卡与区域地图合并成一套色卡（地图覆盖房间卡），所以默认不再是自己那套灰阶
        check("默认配色 = 与区域地图同一套（空气 #8C97AF / 岩壁 #000000 / 背景结构 #637178 / 管道 #FFFFFF）",
              pal.get("air") == "#8C97AF" and pal.get("solid") == "#000000"
              and pal.get("climb") == "#637178" and pal.get("pipe") == "#FFFFFF",
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
        check("「恢复本主题默认」回到同一套默认色", back == "#8C97AF", str(back))

        js("document.getElementById('rp-close').click();")
        js("window.__rwTest.resetRoomPalette();")
        after = loads(js("JSON.stringify(window.__rwTest.roomPalette())")) or {}
        check("配色可完全恢复（不留自定义项）",
              not (after.get("custom") or {}).get("dark")
              and not (after.get("custom") or {}).get("light"), str(after.get("custom")))

        # ---- 12. 实机视图（V1.2 · M2）----
        # 先回到矢量，并挑一间这一轮还没渲过的房（L1 空着才测得出「首次要等」）
        js("var b=document.getElementById('rm-close'); if(b) b.click();")
        time.sleep(0.3)
        js("window.__rwTest.setRoomStyle('vector');")
        time.sleep(0.2)
        js("window.__rwTest.openRoom('GW','GW_B08');")
        time.sleep(1.8)
        vec_card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        vec_px = loads(js("JSON.stringify(window.__rwTest.roomPixels(8))")) or []
        check("默认是矢量：画布上没有实机位图",
              vec_card.get("style") == "vector" and not vec_card.get("live")
              and not vec_card.get("liveFlagOn"),
              f"style={vec_card.get('style')} live={vec_card.get('live')}")
        check("「实机」开关自动出现（素材探测通过）",
              vec_card.get("styleShown") is True,
              f"styleShown={vec_card.get('styleShown')}")

        t_live = time.time()
        js("window.__rwTest.setRoomStyle('live');")
        time.sleep(0.35)
        early = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("切到实机：0.35 s 时卡片已可交互、矢量仍在（渲染没堵住开卡）",
              early.get("open") is True and early.get("style") == "live"
              and (early.get("liveFlagOn") or (early.get("live") or {}).get("ok")),
              f"open={early.get('open')} flag={early.get('liveFlag')!r} live={early.get('live')}")

        live_card, waited = {}, 0.0
        for _ in range(24):
            time.sleep(0.5)
            live_card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            waited = time.time() - t_live
            if (live_card.get("live") or {}).get("ok"):
                break
        lv = live_card.get("live") or {}
        check("实机图渲完并贴到画布", lv.get("ok") is True and (lv.get("w") or 0) > 0,
              f"live={lv} 等待 {waited:.1f}s")
        check("位图分辨率与房间格数一致（w ÷ 每格像素 = 格数）",
              bool(lv.get("px")) and (lv.get("w") or 0) == (live_card.get("w") or -1) * (lv.get("px") or 1),
              f"{lv.get('w')}×{lv.get('h')} / {lv.get('px')}px = "
              f"{(lv.get('w') or 0) / max(1, lv.get('px') or 1)} vs 格数 {live_card.get('w')}")

        # 淡入是 rAF 驱动的（120 ms），窗口在后台会被节流；采样像素前先把它收尾，
        # 否则读到的可能是「alpha 还是 0」的画布，等于拿矢量图当实机图比对。
        js("window.__rwTest.revealLive();")
        time.sleep(0.15)
        live_px = loads(js("JSON.stringify(window.__rwTest.roomPixels(8))")) or []
        pairs = [(a, b) for a, b in zip(vec_px, live_px) if a and b]
        # 改没改要按「肉眼可辨」算：重绘同一帧时抗锯齿会有 1~2/255 的抖动，
        # 把它当成变化会让这条断言变成噪声测试。差 8 以上才算真的换了内容。
        changed = sum(1 for a, b in pairs if max(abs(x - y) for x, y in zip(a, b)) > 8)
        ratio = (changed / len(pairs)) if pairs else 0.0
        check("位图真的画出去了（抽样点大面积改变 ≥ 1/3）",
              len(pairs) >= 40 and ratio >= 0.34,
              f"{changed}/{len(pairs)} = {ratio:.2f}")

        # 悬停时出口十字会被**故意**压到 0.28（让位给徽章），那是设计不是 bug。
        # 这条断言问的是「谁在谁上面」，所以要先把悬停收干净，否则测到的是压暗后的混色。
        js("var b=document.getElementById('rm-exits');"
           "if(b) b.dispatchEvent(new MouseEvent('mouseleave'));")
        time.sleep(0.4)
        marks = loads(js("JSON.stringify(window.__rwTest.roomMarkPixels())")) or {}
        mk = marks.get("marks") or []
        hit = sum(1 for m in mk if m.get("match"))
        check("出口十字仍在位图之上（位图没盖住交互层）",
              marks.get("ready") and len(mk) >= 1 and hit == len(mk),
              f"{hit}/{len(mk)} 个出口格仍是强调色 (期望 {marks.get('expect')}) "
              f"实测 {[m.get('rgb') for m in mk]} hover={live_card.get('hoverExit')}")

        cfg_live = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("画法写进 config.ui.roomCardStyle",
              (cfg_live.get("ui") or {}).get("roomCardStyle") == "live",
              f"roomCardStyle={(cfg_live.get('ui') or {}).get('roomCardStyle')}")

        grab(os.path.join(SHOTS, "room_live.bmp"))

        # 切回矢量：位图必须退出绘制，画布回到切之前那一帧
        js("window.__rwTest.setRoomStyle('vector');")
        time.sleep(0.5)
        back_card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        back_px = loads(js("JSON.stringify(window.__rwTest.roomPixels(8))")) or []
        # 容差 3/255：同一帧重绘时画布的抗锯齿本就会有 1~2 级的抖动（实测 15/64 点差 1~2），
        # 那不是「位图还在」，位图真留着会是几十级的差（同 A vs C 的 64/64）。
        same = sum(1 for a, b in zip(vec_px, back_px)
                   if a and b and max(abs(x - y) for x, y in zip(a, b)) <= 3)
        total = sum(1 for a, b in zip(vec_px, back_px) if a and b)
        check("切回矢量：位图退出绘制，画布回到原样",
              back_card.get("style") == "vector" and total > 0 and same / total >= 0.95,
              f"style={back_card.get('style')} 同色(±3) {same}/{total}")

        cfg_rest2 = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("配置恢复成矢量（不把用户的默认值留在实机上）",
              (cfg_rest2.get("ui") or {}).get("roomCardStyle") == "vector",
              f"roomCardStyle={(cfg_rest2.get('ui') or {}).get('roomCardStyle')}")

        # ---- 13. 渲染缓存与预取（V1.2 · M3）----
        from core import room_cache, room_render  # noqa: PLC0415 - 回归脚本局部导入

        info1 = api.room_cache_info()
        check("实机图已落盘（L2 目录有文件、有体积）",
              info1.get("ok") and (info1.get("files") or 0) >= 1 and (info1.get("bytes") or 0) > 0,
              f"{info1.get('files')} 张 / {(info1.get('bytes') or 0) // 1024} KB @ {info1.get('path')}")

        # SLO：L2 命中。三级缓存要一起清（JS 的 L1 + 后端的进程内 LRU）才轮得到磁盘。
        # 顺序很关键：先用矢量开卡（不触发渲染），再清缓存，最后切实机——只发一次请求。
        # 否则「切档位」这一步会先渲一次，把结果塞回内存 LRU，测到的就是 memory 0 ms。
        js("window.__rwTest.setRoomStyle('vector');")
        time.sleep(0.3)
        js("window.__rwTest.openRoom('GW','GW_B08');")
        time.sleep(1.6)
        js("window.__rwTest.clearLiveCache();")
        room_render._render_cache.clear()
        js("window.__rwTest.setRoomStyle('live');")
        hit = {}
        for _ in range(24):
            time.sleep(0.4)
            hit = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            lv2 = hit.get("live") or {}
            if lv2.get("ok"):
                break
        lv2 = hit.get("live") or {}
        check("清空 L1 后重开同一间：直接吃磁盘缓存（≤ 200 ms）",
              lv2.get("src") == "disk" and (lv2.get("ms") or 9999) <= 200,
              f"source={lv2.get('src')} ms={lv2.get('ms')}")

        # 预取：开卡 300 ms 后会把右栏前 3 个出口排进后台队列。
        # 先清空缓存再开卡——否则那几个出口房间早就在盘上了，预取命中缓存不写新文件、
        # 张数不会变。这条断言以前是"看运气"过的（一旦前一步已经把缓存填满就必红）。
        room_cache.clear_all()
        room_render._render_cache.clear()
        room_render._tex_cache.clear()
        js("window.__rwTest.clearLiveCache();")
        js("window.__rwTest.setRoomStyle('live');")
        js("window.__rwTest.openRoom('GW','GW_B08');")
        for _ in range(40):                 # 先等它把自己这张写下去
            time.sleep(0.4)
            if (api.room_cache_info().get("files") or 0) >= 1:
                break
        before = api.room_cache_info().get("files") or 0
        grew = before
        for _ in range(30):
            time.sleep(0.5)
            grew = api.room_cache_info().get("files") or 0
            if grew > before:
                break
        check("开卡后自动预取出口房间（缓存张数变多）", grew > before,
              f"{before} → {grew} 张")

        # L1 内存也按字节算账（密度一提上来，按张数会撑爆）
        card_l1 = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
        check("L1 内存缓存有字节预算（≤ 48 MB）",
              (card_l1.get("liveBytes") or 0) <= 48 * 1024 * 1024,
              f"liveBytes={card_l1.get('liveBytes')} 张数={card_l1.get('liveCached')}")

        # 失效：删区域 / 重导 / 删层都会走 purge_region，这里直接验这个原语
        gw_dir = room_cache.region_dir("GW")
        had_dir = os.path.isdir(gw_dir)
        room_cache.purge_region("GW")
        info2 = api.room_cache_info()
        check("区域级失效：整目录删除（重导/删层/删来源都走这条路）",
              had_dir and not os.path.isdir(gw_dir) and (info2.get("files") or 0) < grew,
              f"删前 {grew} 张 → 删后 {info2.get('files')} 张，目录还在={os.path.isdir(gw_dir)}")

        # ---- 14. B 档：放大后按视口裁剪补细节 ----
        # 用 SUMP05（196×72，整图只有 11 px/tile）——这正是 B 档唯一有意义的场景。
        js("window.__rwTest.setRoomStyle('live');")
        js("window.__rwTest.openRoom('CC','CC_SUMP05');")
        base_card = {}
        for _ in range(50):
            time.sleep(0.4)
            base_card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            if (base_card.get("live") or {}).get("ok"):
                break
        lv0 = base_card.get("live") or {}
        files_after_full = api.room_cache_info().get("files") or 0

        js("window.__rwTest.zoomRoom(8);")
        hi_card = {}
        for _ in range(40):
            time.sleep(0.4)
            hi_card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            if hi_card.get("hi"):
                break
        hi = hi_card.get("hi") or {}
        check("放大 8× 后补到高密度裁块（顶到素材上限 20 px/tile）",
              hi and (hi.get("px") or 0) == 20 and (hi.get("px") or 0) > (lv0.get("px") or 0),
              f"整图 px={lv0.get('px')} 裁块 px={hi.get('px') if hi else None}")
        check("裁块只覆盖可见范围（不是整间重渲）",
              hi and 0 < (hi.get("tw") or 0) < (hi_card.get("w") or 1)
              and 0 < (hi.get("th") or 0) <= (hi_card.get("h") or 1),
              f"裁块 {hi.get('tw')}×{hi.get('th')} tile vs 房间 "
              f"{hi_card.get('w')}×{hi_card.get('h')}")
        files_after_hi = api.room_cache_info().get("files") or 0
        check("裁块只进内存、不落盘（别把 200 MB 预算挤掉）",
              files_after_hi == files_after_full,
              f"整图后 {files_after_full} 张 → 裁块后 {files_after_hi} 张")

        # ---- 15. 缓存清理入口（M4）----
        # 入口在「区域数据」弹窗顶部：占用多少、几张、一个清理按钮。
        # 清完必须同时倒掉前端 L1，否则界面上还是旧图，用户会以为「点了没用」。
        js("window.__rwTest.setRoomStyle('vector');")     # 停掉预取，免得清理后又被写回一张
        time.sleep(0.6)
        js("var b=document.getElementById('btn-regions'); if(b) b.click();")
        bar = {}
        for _ in range(40):                               # openRegionsModal 要等 loadRegions 回包
            time.sleep(0.5)
            bar = loads(js("JSON.stringify(window.__rwTest.cacheBar())")) or {}
            if bar.get("hasButton"):
                break
        # 等这一轮渲染 / 预取彻底停下来：否则「清理 → 立刻被在途请求写回一张」，
        # 断言会假红（实测过：清理后 0.2 s 内又冒出 3 张，是预取在收尾）。
        stable, last = 0, -1
        for _ in range(40):
            time.sleep(0.5)
            now_files = api.room_cache_info().get("files") or 0
            cur = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            if now_files == last and (cur.get("live") or {}).get("ok"):
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last = now_files
        files_before_clear = api.room_cache_info().get("files") or 0
        bar_txt = str(bar.get("text") or "")
        check("区域数据弹窗有「房间渲染缓存」一行（占用 + 张数 + 清理按钮）",
              bar.get("hasButton") and "MB" in bar_txt and "张" in bar_txt
              and "统计中" not in bar_txt,
              f"files={files_before_clear} bar={bar_txt[:60]}")

        js("var b=document.getElementById('m-room-clear'); if(b) b.click();")
        # 缓存里有几张时后端要先统计一遍，确认框弹得慢；0.4 s 死等会点空（偶发红）
        for _ in range(20):
            time.sleep(0.2)
            if js("!!document.querySelector('#confbox [data-cf=\"yes\"]')"):
                break
        js("var b=document.querySelector('#confbox [data-cf=\"yes\"]'); if(b) b.click();")
        card_after, bar2 = {}, {}
        for _ in range(30):
            time.sleep(0.3)
            card_after = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            bar2 = loads(js("JSON.stringify(window.__rwTest.cacheBar())")) or {}
            if (api.room_cache_info().get("files") or 0) == 0 \
                    and (card_after.get("liveCached") or 0) == 0 \
                    and "0 张" in str(bar2.get("text") or ""):
                break
        after_clear = api.room_cache_info().get("files") or 0
        check("点「清理」真的清空磁盘缓存",
              files_before_clear > 0 and after_clear == 0,
              f"{files_before_clear} 张 → {after_clear} 张")
        check("清理后当前房间画面还在（不闪白、不重渲）且 L1 已倒掉",
              (card_after.get("live") or {}).get("ok")
              and (card_after.get("liveCached") or 0) == 0,
              f"live.ok={(card_after.get('live') or {}).get('ok')} "
              f"liveCached={card_after.get('liveCached')}")
        check("清空后清理按钮置灰、数字归零",
              bar2.get("disabled") is True and "0 张" in str(bar2.get("text") or ""),
              str(bar2.get("text") or "")[:60])

        room_cache.clear_all()
        js("window.__rwTest.setRoomStyle('vector');")
        time.sleep(0.5)
        cfg_end = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        check("收尾：配置回到矢量（不留副作用）",
              (cfg_end.get("ui") or {}).get("roomCardStyle") == "vector",
              f"roomCardStyle={(cfg_end.get('ui') or {}).get('roomCardStyle')}")

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
