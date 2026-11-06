"""房间关系图（DFS 逐步探索）回归检查（真实 WebView2，隐藏窗口）。

用法： .venv/Scripts/python.exe build/check_graph.py

检查内容：
    1. 区域页有「关系」入口，点开能画出来；节点数 == 该区域房间清单（GW 52）
    2. 边数 == neighbors 对称化去重后的数量（GW 57）
    3. 默认全部房间可见（含 0 度）；RF 开启「折叠无连接」后从 80 减到 65
    4. 单步：每按一次只多点亮 1 间（不是一层一批）
    5. 播放：能自己往下走，光带长度 > 0；暂停能停住
    6. 起点切到庇护所后，第一个节点确实是庇护所
    7. 改「已探索」颜色 → 写进 config.json 的 ui.graphColors
    8. 点节点 → 打开房间布局卡，且房间号一致
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

from core import paths  # noqa: E402
from core.bridge import Api  # noqa: E402

CONFIG = os.path.join(paths.app_root(), "config.json")
GW_JSON = os.path.join(ROOT, "region_data", "GW.json")
RF_JSON = os.path.join(ROOT, "region_data", "RF.json")



TITLE = "RwSaveTool 关系图检查"
OUT1 = os.path.join(SHOTS, "graph_all.bmp")
OUT2 = os.path.join(SHOTS, "graph_play.bmp")
OUT3 = os.path.join(SHOTS, "graph_panel.bmp")
OUT4 = os.path.join(SHOTS, "map_entry.bmp")
OUT5 = os.path.join(SHOTS, "graph_menu.bmp")
OUT6 = os.path.join(SHOTS, "graph_end.bmp")
OUT7 = os.path.join(SHOTS, "graph_pin.bmp")
OUT8 = os.path.join(SHOTS, "graph_world.bmp")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()


def find_hwnd(title):
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


def grab(path, tries=1):
    """PrintWindow 偶尔会抓到弹窗还没合成的旧帧，隔 0.2s 多抓几次、以最后一次为准。"""
    for i in range(tries):
        ok = _grab_once(path)
        if i + 1 < tries:
            time.sleep(0.2)
    return ok


def _grab_once(path):
    hwnd = find_hwnd(TITLE)
    if not hwnd:
        print("[截图] 未找到窗口")
        return False
    # PrintWindow 在 WebView2 上偶尔会返回合成前的旧帧（拍到主界面而不是弹窗），
    # 所以优先提到前台从屏幕抓；抢不到前台（主人正在用电脑）就退回 PrintWindow，
    # 免得把别人的窗口拍进来。
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    time.sleep(0.3)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if user32.GetForegroundWindow() == hwnd:
        hdc = user32.GetWindowDC(0)
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, hdc, rect.left, rect.top, 0x00CC0020)
    else:
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

CFG = os.path.join(ROOT, "config.json")


def clear_hover(js):
    js("(function(){var cv=document.getElementById('gx-canvas');"
       "var r=cv.getBoundingClientRect();"
       "cv.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,"
       "clientX:r.left+2,clientY:r.top+2}));})()")
    time.sleep(0.35)


def base_layer(code_file):
    with open(code_file, encoding="utf-8") as fh:
        data = json.load(fh)
    best = None
    for layer in data.get("layers") or []:
        rooms = layer.get("rooms") or []
        if not rooms or not any(r.get("neighbors") for r in rooms):
            continue
        if best is None or len(rooms) > len(best):
            best = rooms
    return best or []


def edge_count(rooms):
    names = {str(r["name"]).upper() for r in rooms}
    seen = set()
    for r in rooms:
        a = str(r["name"]).upper()
        for t in r.get("neighbors") or []:
            b = str(t).upper()
            if b in names and b != a:
                seen.add(tuple(sorted((a, b))))
    return len(seen)


def main() -> int:
    gw_rooms = base_layer(GW_JSON)
    rf_rooms = base_layer(RF_JSON)
    gw_gates = {str(r["name"]).upper() for r in gw_rooms if r.get("gate")}
    gw_shelters = {str(r["name"]).upper() for r in gw_rooms if r.get("shelter")}
    gw_edges = edge_count(gw_rooms)
    rf_edges = edge_count(rf_rooms)

    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window(TITLE, html=html, js_api=api,
                                   width=1400, height=900, hidden=False)
    api.attach(window)
    out: dict = {"errors": []}
    cfg_backup = None
    if os.path.exists(CFG):
        with open(CFG, "rb") as fh:
            cfg_backup = fh.read()
    results: list[tuple[bool, str, str]] = []

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

    def g():
        return loads(js("JSON.stringify(window.__rwTest.graph())")) or {}

    def check(name, cond, detail=""):
        results.append((bool(cond), name, detail))

    def config_graph():
        try:
            with open(CONFIG, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            return {}
        return (cfg.get("ui") or {}).get("graphColors") or {}

    def worker():
        time.sleep(2.5)
        try:
            for _ in range(40):
                if js("document.querySelectorAll('#slot-list .slot').length > 0"):
                    break
                time.sleep(0.4)
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(80):
                time.sleep(0.5)
                if js("window.__rwTest.ready() && document.querySelectorAll('#camplist .camp').length > 0"):
                    break
            time.sleep(1.0)
            js("[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0].click();")
            time.sleep(0.8)
            js("var t=document.querySelector('[data-tab=\"regions\"]'); if(t) t.click();")
            time.sleep(1.2)

            check("区域页有「关系」入口",
                  js("!!document.querySelector('#detail-body [data-graph=\"GW\"]')"),
                  "")
            # ---- 从区域地图一键进关系图（用户 11-04 要的入口） ----
            js("document.querySelector('#detail-body [data-map=\"GW\"]').click();")
            time.sleep(1.2)
            check("区域地图里有「区域拓扑」入口",
                  js("!!document.getElementById('map-graph') && "
                     "/区域拓扑/.test(document.getElementById('map-graph').textContent)"),
                  js("(document.getElementById('map-graph')||{}).textContent") or "")
            grab(OUT4)
            js("document.getElementById('map-graph').click();")
            time.sleep(1.2)
            gm = g()
            out["mapEntry"] = {"code": gm.get("code"), "open": gm.get("open")}
            check("从区域地图能一键进区域拓扑",
                  gm.get("open") and gm.get("code") == "GW", str(out["mapEntry"]))
            out["title"] = js("(document.querySelector('#modal-card h3')||{}).textContent")
            check("弹窗标题已改名为「区域拓扑 · GW」，不再叫「关系图」",
                  out["title"] == "区域拓扑 · GW", str(out["title"]))

            js("window.__rwTest.openGraph('GW');")
            # 开场动画很吃机器速度，别用"睡 0.15s 再看"这种写法：
            # 连续采样 0.8s，取"铺开程度最小 / 逐个淡入得最少"的那一刻当证据
            samples = []
            for _ in range(10):
                time.sleep(0.08)
                sm = loads(js(
                    "JSON.stringify((function(){var a=0,b=0;"
                    "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                    "if(n&&n.appear>0.02)a++; if(n&&n.appear>0.6)b++;}"
                    "return {on:a,full:b,total:window.__rwTest.graph().total,"
                    "spread:(window.__rwTest.graph().total?0:0)};})())"
                )) or {}
                sm["spread"] = (g().get("quality") or {}).get("spread")
                samples.append(sm)
            grow = min(samples, key=lambda s: (s.get("on") or 0)) if samples else {}
            out["grow"] = grow
            out["growSamples"] = [(s.get("on"), s.get("spread")) for s in samples]
            q_start = min([s.get("spread") or 1 for s in samples] or [1])
            time.sleep(3.6)          # 从中心炸开 + alpha 衰减，约 3.5s 才定住
            s0 = g()
            q_end = (s0.get("quality") or {}).get("spread")
            out["unfold"] = {"start": q_start, "end": q_end}
            check("打开时先缩成一个点，再自己铺开",
                  (q_start or 1) < 0.25 and (q_end or 0) > 0.4, str(out["unfold"]))
            check("打开时从中心向外逐个淡入（不是一下子全亮）",
                  (grow.get("on") or 0) > 2 and (grow.get("on") or 0) < (grow.get("total") or 0),
                  str(grow))
            out["gw"] = s0
            print("[布局]", s0.get("quality"), s0.get("size"), "full=", s0.get("full"))
            check("GW 关系图打开，节点数 = 房间清单",
                  s0.get("open") and s0.get("rooms") == len(gw_rooms) == s0.get("setsTotal"),
                  f"rooms={s0.get('rooms')} expect={len(gw_rooms)} sets={s0.get('setsTotal')}")
            check("边数 = neighbors 对称化去重",
                  s0.get("edges") == gw_edges, f"edges={s0.get('edges')} expect={gw_edges}")
            radii = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "if(n)a.push(n.r);} return a;})())"
            )) or []
            out["radii"] = {"min": min(radii) if radii else 0, "max": max(radii) if radii else 0}
            check("节点是小点（半径 ≤8px），且随连接数有一点差别",
                  radii and max(radii) <= 8 and max(radii) - min(radii) >= 1.0,
                  str(out["radii"]))
            q0 = s0.get("quality") or {}
            out["edge"] = q0
            check("连线长度不再是死值：最长边 ≥ 中位数的 1.6 倍",
                  (q0.get("edgeMax") or 0) >= (q0.get("edgePx") or 1) * 1.6,
                  f"min={q0.get('edgeMin')} 中位={q0.get('edgePx')} p90={q0.get('edgeP90')} max={q0.get('edgeMax')}")
            check("默认显示全部节点（含 0 度），未开启折叠",
                  s0.get("folded") == 0 and s0.get("rooms") == s0.get("setsTotal"),
                  f"folded={s0.get('folded')}")

            time.sleep(0.8)
            clear_hover(js)
            grab(OUT1)
            time.sleep(1.8)          # 等物理彻底停下来，否则下面拖拽的起点会漂

            # ---- 全屏 / 筛选 / 名字密度 / 世界拓扑 / 返回地图 / 手动标记 ----
            check("关系图是全屏展开", s0.get("full") is True, str(s0.get("size")))

            js("document.querySelector('[data-gxview=\"visited\"]').click();")
            time.sleep(0.5)
            fv = g()
            js("document.querySelector('[data-gxview=\"unvisited\"]').click();")
            time.sleep(0.5)
            fu = g()
            js("document.querySelector('[data-gxview=\"all\"]').click();")
            time.sleep(0.5)
            fa = g()
            out["filter"] = {"v": fv.get("rooms"), "u": fu.get("rooms"), "all": fa.get("rooms"),
                             "visited": s0.get("visited"), "total": s0.get("total")}
            check("筛选：已探索 / 未探索 各自只显示自己那半，加起来等于全部",
                  fv.get("rooms") == s0.get("visited")
                  and fu.get("rooms") == s0.get("total") - s0.get("visited")
                  and fa.get("rooms") == s0.get("total"), str(out["filter"]))

            def hidden_labels():
                return loads(js(
                    "JSON.stringify((function(){var a=0;"
                    "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                    "if(n&&n.lab<0.5)a++;} return a;})())"
                )) or 0

            # 名字显隐：默认（A 关）= 名字只跟缩放走，密度参数完全不参与
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.5)
            dep_off = js("getComputedStyle(document.querySelector('[data-gxdep=\"labelCrowd\"]')).display === 'none'")
            # 缩到 44% 让节点挤起来
            js("(function(){var cv=document.getElementById('gx-canvas');var b=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new WheelEvent('wheel',{deltaY:240,bubbles:true,cancelable:true,"
               "clientX:b.left+b.width/2,clientY:b.top+b.height/2}));})()")
            time.sleep(1.2)
            js("var r=document.querySelector('[data-gxopt=\"labelGap\"]'); r.value=60;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));")
            time.sleep(1.4)
            lab_off = hidden_labels()
            out["labelsDefault"] = {"hidden": lab_off, "depHidden": dep_off}
            check("默认（A 关）：名字只跟缩放走，间距拉到 60 也不让位",
                  lab_off == 0, str(out["labelsDefault"]))
            check("默认（A 关）：「名字间距」滑块收起",
                  dep_off is True, str(out["labelsDefault"]))

            # 勾上 A 之后，密度让位才生效，滑块也随之出现
            js("var c=document.querySelector('[data-gxflag=\"labelCrowd\"]'); c.checked=true;"
               "c.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(0.7)
            dep_on = js("getComputedStyle(document.querySelector('[data-gxdep=\"labelCrowd\"]')).display !== 'none'")
            js("(function(){var cv=document.getElementById('gx-canvas');var b=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new WheelEvent('wheel',{deltaY:240,bubbles:true,cancelable:true,"
               "clientX:b.left+b.width/2,clientY:b.top+b.height/2}));})()")
            time.sleep(1.0)
            js("var r=document.querySelector('[data-gxopt=\"labelGap\"]'); r.value=0;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));")
            time.sleep(1.3)
            lab0 = hidden_labels()
            js("var r=document.querySelector('[data-gxopt=\"labelGap\"]'); r.value=60;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));")
            time.sleep(1.4)
            lab60 = hidden_labels()
            out["labels"] = {"gap0": lab0, "gap60": lab60, "depShown": dep_on}
            check("可选项 A 打开后：间距设 0 全显示，设 60 会藏掉一部分",
                  lab0 == 0 and lab60 > 0, str(out["labels"]))
            check("可选项 A 打开后：「名字间距」滑块出现", dep_on is True, str(out["labels"]))

            # 复原：关掉 A、间距回 26、关面板、fit
            js("var c=document.querySelector('[data-gxflag=\"labelCrowd\"]'); c.checked=false;"
               "c.dispatchEvent(new Event('change',{bubbles:true}));")
            js("var r=document.querySelector('[data-gxopt=\"labelGap\"]'); r.value=26;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));")
            js("document.getElementById('gx-settings').click();")
            js("document.querySelector('[data-gzoom=\"fit\"]').click();")
            time.sleep(1.0)

            js("window.__rwTest.openWorld();")
            time.sleep(4.2)
            wd = g()
            pg_hidden = js("getComputedStyle(document.querySelector('.gx-playgrp')).display === 'none'")
            wtot = wd.get("total") or 0
            wnodes = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "if(n)a.push({name:n.name,label:n.label,zh:n.zh,en:n.en,ghost:!!n.ghost});} return a;})())"
            )) or []
            with_zh = [x for x in wnodes if (x.get("zh") or "").strip()]
            no_zh = [x for x in wnodes if not (x.get("zh") or "").strip()]
            def ok_label(x):
                lb = (x.get("label") or "").strip()
                nm = (x.get("name") or "").strip()
                zh = (x.get("zh") or "").strip()
                en = (x.get("en") or "").strip()
                if not lb:
                    return False
                if zh and zh != nm:
                    return lb == zh + " " + nm
                if en and en != nm:
                    return lb == en + " " + nm
                return lb == nm

            labeled = [x for x in wnodes if ok_label(x)]
            out["world"] = {"world": wd.get("world"), "rooms": wd.get("rooms"), "edges": wd.get("edges"),
                            "playHidden": pg_hidden, "total": wtot,
                            "withZh": len(with_zh), "noZh": len(no_zh),
                            "labeled": len(labeled),
                            "sample": [x.get("label") for x in wnodes[:4]]}
            grab(OUT8)
            check("世界拓扑：区域当节点、业力门当边，播放控件收起",
                  wd.get("world") is True and (wd.get("total") or 0) >= 60
                  and (wd.get("edges") or 0) >= 10 and pg_hidden is True, str(out["world"]))
            check("世界拓扑收录所有导入过的区域（不再只有存档里那 32 个）",
                  (wd.get("total") or 0) >= 60, f"total={wd.get('total')}")
            check("世界拓扑标签 = 中文名 + 区域缩写（没译名的用英文原名）",
                  len(labeled) == len(wnodes) and len(with_zh) >= len(wnodes) * 0.5,
                  f"labeled={len(labeled)}/{len(wnodes)} withZh={len(with_zh)} 样例={out['world']['sample']}")
            has_cjk = any(any("\u4e00" <= ch <= "\u9fff" for ch in (x.get("label") or "")) for x in wnodes)
            check("没有译名的区域退回英文原名（标签里至少有一条中文）", has_cjk,
                  str(out["world"]["sample"]))

            # ---- 可达过滤：不能到的区域默认不画 ----
            ghosts = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){"
                "var n=window.__rwTest.graphNode(i); if(n&&n.ghost)a.push(n.name);} return a;})())"
            )) or []
            out["reach"] = {"shown": wd.get("rooms"), "total": wd.get("total"), "ghost": ghosts[:8],
                            "nGhost": len(ghosts)}
            shown_names = [x.get("name") for x in wnodes if not x.get("ghost")]
            check("白猫的世界拓扑里剔掉了去不了的区域（LC/RM/CL/UG/HR）",
                  not any(g in ("LC", "RM", "CL", "UG", "HR") for g in shown_names),
                  str(out["reach"]) + " shown=" + str(shown_names[:10]))
            check("可达过滤默认生效：显示数 = 总数 − 不可达数",
                  (wd.get("rooms") or 0) == (wd.get("total") or 0) - len(ghosts) and len(ghosts) > 0,
                  str(out["reach"]))

            js("var s=document.getElementById('gx-reach'); s.value='ghost';"
               "s.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(1.2)
            wd2 = g()
            out["reachGhost"] = {"rooms": wd2.get("rooms"), "total": wd2.get("total")}
            check("切到「可达+灰显」后不可达区域也画出来",
                  (wd2.get("rooms") or 0) == (wd2.get("total") or 0), str(out["reachGhost"]))
            js("var s=document.getElementById('gx-reach'); s.value='reach';"
               "s.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(0.8)

            # 手动标记 → 返回地图 → 二次确认还原
            js("window.__rwTest.openRoom('GW', 'GW_A01');")
            time.sleep(1.0)
            js("document.querySelector('#rm-mark [data-rmmark=\"1\"]').click();")
            time.sleep(1.0)
            mk = loads(js("JSON.stringify(window.__rwTest.marks())")) or {}
            out["mark"] = mk
            check("房间卡能把一间房手动标成已探索",
                  (mk.get("GW") or {}).get("GW_A01") == 1, str(mk))
            js("document.getElementById('rm-close').click();")
            time.sleep(0.4)
            js("window.__rwTest.openGraph('GW');")
            time.sleep(1.6)
            js("document.getElementById('gx-back').click();")
            time.sleep(1.6)
            check("关系图的「← 地图」能回到区域地图",
                  js("!!document.getElementById('map-stage')")
                  and js("!!document.getElementById('map-side')"), "")
            has_reset = js("!!document.getElementById('map-mark-reset')")
            check("地图左侧栏看得到手动标记并给出还原按钮", has_reset, "")
            js("document.getElementById('map-mark-reset').click();")
            time.sleep(0.6)
            has_cf = js("!!document.querySelector('#confbox [data-cf=\"yes\"]')")
            js("var b=document.querySelector('#confbox [data-cf=\"yes\"]'); if(b) b.click();")
            time.sleep(1.4)
            mk2 = loads(js("JSON.stringify(window.__rwTest.marks())")) or {}
            out["mark2"] = mk2
            check("还原要先二次确认，确认后标记清空",
                  has_cf is True and not (mk2.get("GW") or {}), str(mk2))

            js("window.__rwTest.openGraph('GW');")
            time.sleep(3.4)

            # ---- 悬停：自己与一度邻居保持不透明，其余压到 0.2 ----
            hn = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            js("(function(){var cv=document.getElementById('gx-canvas');"
               "var r=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,"
               "clientX:r.left+%s,clientY:r.top+%s}));})()" % (hn.get("sx", 0), hn.get("sy", 0)))
            time.sleep(0.8)
            al = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);a.push(n?n.appear:-1);}"
                "return a;})())"
            )) or []
            nb = set(hn.get("nb") or [])
            self_a = al[0] if al else 0
            nb_low = min([al[i] for i in nb]) if nb else 1
            other_high = max([al[i] for i in range(len(al)) if i not in nb and i != 0] or [0])
            out["hover"] = {"self": self_a, "nbMin": nb_low, "otherMax": other_high}
            check("悬停：自己与一度邻居不透明，其余压到 0.2 附近",
                  self_a > 0.95 and nb_low > 0.9 and other_high <= 0.35,
                  str(out["hover"]))

            # ---- 拖拽：拖走 100px 后钉住，松手不回弹 ----
            hn = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
               "function ev(t,x,y){cv.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,"
               "clientX:r.left+x,clientY:r.top+y,button:0}));}"
               "ev('mousedown',%s,%s); ev('mousemove',%s,%s); ev('mousemove',%s,%s);"
               "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));})()"
               % (hn.get("sx", 0), hn.get("sy", 0),
                  hn.get("sx", 0) + 60, hn.get("sy", 0) + 40,
                  hn.get("sx", 0) + 100, hn.get("sy", 0) + 70))
            time.sleep(1.0)
            dn = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            out["drag"] = {"from": [round(hn.get("sx") or 0, 1), round(hn.get("sy") or 0, 1)],
                           "to": [round(dn.get("sx") or 0, 1), round(dn.get("sy") or 0, 1)],
                           "pinned": dn.get("pinned")}
            check("拖动默认「不固定」：松手后交回力导向，不会被钉在原地",
                  dn.get("pinned") is False, str(out["drag"]))

            # ---- 拖动"有劲"：拖住不放时，邻居被明显拉过来；远端基本不动 ----
            # 等力导向真正冻结（上一步拖拽刚给它加了能量）
            for _ in range(30):
                if g().get("frozen"):
                    break
                time.sleep(0.25)
            base = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            nb0 = set(base.get("nb") or [])
            before_pos = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "a.push(n?[n.sx,n.sy]:null);} return a;})())"
            )) or []
            js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
               "window.__dragEv=function(t,x,y){cv.dispatchEvent(new MouseEvent(t,{bubbles:true,"
               "cancelable:true,clientX:r.left+x,clientY:r.top+y,button:0}));};"
               "window.__dragEv('mousedown',%s,%s);"
               "window.__dragEv('mousemove',%s,%s);"
               "window.__dragEv('mousemove',%s,%s);})()"
               % (base.get("sx", 0), base.get("sy", 0),
                  base.get("sx", 0) + 60, base.get("sy", 0) + 50,
                  base.get("sx", 0) + 120, base.get("sy", 0) + 90))
            time.sleep(0.9)      # 拖着不放，量"被拉过来多少"
            held_pos = loads(js(
                "JSON.stringify((function(){var a=[];"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "a.push(n?[n.sx,n.sy]:null);} return a;})())"
            )) or []
            js("window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));")
            time.sleep(2.4)

            nb_move, far_move = [], []
            for i in range(min(len(before_pos), len(held_pos))):
                if not before_pos[i] or not held_pos[i] or i == 0:
                    continue
                d0 = ((before_pos[i][0] - held_pos[i][0]) ** 2 +
                      (before_pos[i][1] - held_pos[i][1]) ** 2) ** 0.5
                (nb_move if i in nb0 else far_move).append(round(d0, 1))
            dragged = 0.0
            if before_pos and held_pos and before_pos[0] and held_pos[0]:
                dragged = round(((before_pos[0][0] - held_pos[0][0]) ** 2 +
                                 (before_pos[0][1] - held_pos[0][1]) ** 2) ** 0.5, 1)
            out["pull"] = {"dragged": dragged,
                           "nb": sorted(nb_move, reverse=True)[:3],
                           "farMax": max(far_move) if far_move else 0,
                           "farAvg": round(sum(far_move) / max(1, len(far_move)), 1)}
            check("节点确实被拖走了（拖动本身生效）", dragged >= 60, str(out["pull"]))
            check("拖一个节点，邻居被明显拉动（连线有力）",
                  nb_move and max(nb_move) >= 25, str(out["pull"]))
            check("拖动不会让整张图重排（远端平均位移 < 40px）",
                  (out["pull"]["farAvg"] or 0) < 40 and (out["pull"]["farMax"] or 0) < 120,
                  str(out["pull"]))

            # ---- 拖动拉力量化 A/B：1× vs 4×。每次先 reloadGraph 回到同一初始布局（同种子
            #      → 同一形状），否则两次拖动起点不同、数字没法比。 ----
            def pos_all():
                return loads(js(
                    "JSON.stringify((function(){var a=[];"
                    "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                    "a.push(n?[n.sx,n.sy]:null);} return a;})())"
                )) or []

            js("document.getElementById('gx-settings').click();")
            time.sleep(0.4)

            def drag_sample(pull):
                js("var r=document.querySelector('[data-gxopt=\"dragPull\"]'); r.value=%s;"
                   "r.dispatchEvent(new Event('input',{bubbles:true}));" % pull)
                js("window.__rwTest.reloadGraph();")
                time.sleep(0.6)
                n0 = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
                b = pos_all()
                js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
                   "function ev(t,x,y){cv.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,"
                   "clientX:r.left+x,clientY:r.top+y,button:0}));}"
                   "ev('mousedown',%s,%s); ev('mousemove',%s,%s); ev('mousemove',%s,%s);})()"
                   % (n0.get("sx", 0), n0.get("sy", 0),
                      n0.get("sx", 0) + 60, n0.get("sy", 0) + 50,
                      n0.get("sx", 0) + 120, n0.get("sy", 0) + 90))
                time.sleep(0.9)
                h = pos_all()
                js("window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));")
                time.sleep(0.4)
                nb = set(n0.get("nb") or [])
                nbm, farm = [], []
                for i in range(min(len(b), len(h))):
                    if i == 0 or not b[i] or not h[i]:
                        continue
                    dd = ((b[i][0] - h[i][0]) ** 2 + (b[i][1] - h[i][1]) ** 2) ** 0.5
                    (nbm if i in nb else farm).append(dd)
                # 邻居到被拖节点的平均距离：这才是"拉得更近"的直接度量。
                # 单看位移会饱和（邻居贴到节点上就停住了），比值上不去。
                near = []
                if h and h[0]:
                    for i in nb:
                        if i < len(h) and h[i]:
                            near.append(((h[0][0] - h[i][0]) ** 2 + (h[0][1] - h[i][1]) ** 2) ** 0.5)
                return ((max(nbm) if nbm else 0.0),
                        (sum(farm) / max(1, len(farm))),
                        (sum(near) / max(1, len(near))))

            n1, f1, d1 = drag_sample(1)
            n4, f4, d4 = drag_sample(4)
            js("var r=document.querySelector('[data-gxopt=\"dragPull\"]'); r.value=1.5;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));")
            js("document.getElementById('gx-settings').click();")
            shrink = (d4 / d1) if d1 > 1 else 1.0
            out["pullAB"] = {"nb1": round(n1, 1), "nb4": round(n4, 1),
                             "far1": round(f1, 1), "far4": round(f4, 1),
                             "near1": round(d1, 1), "near4": round(d4, 1),
                             "nearShrink": round(shrink, 2)}
            check("4× 拉力把邻居拉得更近（邻居到被拖节点的平均距离 ≤ 1× 的 70%）",
                  shrink <= 0.70, str(out["pullAB"]))
            check("4× 的邻居位移也明显更大（≥ 1.5×）",
                  n4 >= n1 * 1.5, str(out["pullAB"]))
            check("两种拉力下远端都不跟着重排（平均位移 < 40px）",
                  f1 < 40 and f4 < 40, str(out["pullAB"]))

            # 打开「拖动后固定」再拖一次
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.4)
            js("var f=document.querySelector('[data-gxflag=\"pin\"]'); f.checked=true;"
               "f.dispatchEvent(new Event('change',{bubbles:true}));")
            # 展开「显示」组拍一张，留档看这三项开关
            js("var hs=document.querySelectorAll('#gx-panel .gx-sec-h'); if(hs[1]) hs[1].click();")
            time.sleep(0.5)
            grab(OUT7)
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.5)
            hn2 = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
               "function ev(t,x,y){cv.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,"
               "clientX:r.left+x,clientY:r.top+y,button:0}));}"
               "ev('mousedown',%s,%s); ev('mousemove',%s,%s); ev('mousemove',%s,%s);"
               "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));})()"
               % (hn2.get("sx", 0), hn2.get("sy", 0),
                  hn2.get("sx", 0) + 55, hn2.get("sy", 0) - 35,
                  hn2.get("sx", 0) + 90, hn2.get("sy", 0) - 60))
            time.sleep(1.0)
            dn2 = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            out["pin"] = {"from": [round(hn2.get("sx") or 0, 1), round(hn2.get("sy") or 0, 1)],
                          "to": [round(dn2.get("sx") or 0, 1), round(dn2.get("sy") or 0, 1)],
                          "pinned": dn2.get("pinned")}
            check("打开「拖动后固定」后，节点被钉在松手的位置",
                  dn2.get("pinned") is True
                  and abs((dn2.get("sx") or 0) - (hn2.get("sx") or 0) - 90) < 14
                  and abs((dn2.get("sy") or 0) - (hn2.get("sy") or 0) + 60) < 14,
                  str(out["pin"]))
            # 关掉，后面的用例按默认走
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.35)
            js("var f=document.querySelector('[data-gxflag=\"pin\"]'); f.checked=false;"
               "f.dispatchEvent(new Event('change',{bubbles:true}));")
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.4)
            js("window.__rwTest.openGraph('GW');")
            time.sleep(1.0)

            # ---- 单步按钮已按用户要求去掉 ----
            check("工具栏不再有「单步」", not js("!!document.getElementById('gx-step')"), "")

            # ---- 右键菜单：贴着节点、不出画面 ----
            time.sleep(1.6)      # 上一步刚放掉钉住，节点还在回弹，等它停稳再点
            cxm = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,"
               "clientX:r.left+%s,clientY:r.top+%s,button:2}));})()"
               % (cxm.get("sx", 0), cxm.get("sy", 0)))
            time.sleep(0.5)
            mb = loads(js(
                "JSON.stringify((function(){var m=document.getElementById('gx-menu');"
                "if(!m||m.hidden) return {open:false};"
                "var r=m.getBoundingClientRect(),s=document.getElementById('gx-stage').getBoundingClientRect();"
                "return {open:true,left:r.left-s.left,top:r.top-s.top,w:r.width,h:r.height,"
                "cw:s.width,ch:s.height};})())"
            )) or {}
            out["menu"] = {"node": [round(cxm.get("sx") or 0, 1), round(cxm.get("sy") or 0, 1)], "box": mb}
            side_ok = (mb.get("left", 0) > (cxm.get("sx") or 0)) or                       ((mb.get("left", 0) + (mb.get("w") or 0)) < (cxm.get("sx") or 0))
            check("右键菜单贴着节点、不跑到画面角上",
                  mb.get("open") and side_ok
                  and abs((mb.get("top") or 0) + (mb.get("h") or 0) / 2 - (cxm.get("sy") or 0)) < 26
                  and (mb.get("left") or 0) >= 0
                  and (mb.get("left") or 0) + (mb.get("w") or 0) <= (mb.get("cw") or 0) + 1,
                  str(out["menu"]))
            # 点菜单里的「设为起点」——以前只改 sel 不改 startIdx，等于没反应
            js("var b=document.querySelector('#gx-menu [data-gxmenu=\"start\"]'); if(b) b.click();")
            time.sleep(1.0)
            st0 = g()
            out["startSet"] = {"want": cxm.get("name"), "startRoom": st0.get("startRoom"),
                               "rooms": st0.get("rooms"), "staged": js("!!window.__rwTest.graph().playing")}
            check("右键「设为起点」真的改掉起点，且不会把图清空",
                  st0.get("startRoom") == cxm.get("name") and (st0.get("rooms") or 0) > 10,
                  str(out["startSet"]))
            grab(OUT5)
            js("var m=document.getElementById('gx-menu'); if(m) m.hidden=true;")

            # ---- 播放 ----
            js("document.getElementById('gx-restart').click();")
            time.sleep(0.3)
            js("document.getElementById('gx-gap').value=40;"
               "document.getElementById('gx-gap').dispatchEvent(new Event('input',{bubbles:true}));")
            js("window.__err=[]; window.addEventListener('error', function(e){"
               "window.__err.push((e.message||'?')+' @'+e.lineno); });")
            js("document.getElementById('gx-play').click();")
            time.sleep(1.0)
            pl = g()
            out["err"] = js("JSON.stringify(window.__err||[])")
            out["play"] = pl
            check("播放能自己往下走", pl.get("playing") and (pl.get("index") or 0) > 2,
                  f"i={pl.get('index')} lit={pl.get('lit')}")
            check("播放时出现光带", (pl.get("trail") or 0) >= 2, f"trail={pl.get('trail')}")
            grab(OUT2)
            apps = loads(js(
                "JSON.stringify([].slice.call(%d?[]:[]))" % 0
            )) if False else None
            vis = loads(js(
                "JSON.stringify((function(){var out={full:0,zero:0,mid:0};"
                "for(var i=0;i<window.__rwTest.graph().total;i++){"
                "var n=window.__rwTest.graphNode(i); if(!n) continue;"
                "if(n.appear>=0.99) out.full++; else if(n.appear<=0.01) out.zero++;"
                "else out.mid++;} return out;})())"
            )) or {}
            out["appear"] = vis
            check("播放中：已出现的节点不透明、未出现的完全没出现（不是先摆着再点亮）",
                  (vis.get("full") or 0) >= 2 and (vis.get("zero") or 0) >= 5,
                  f"full={vis.get('full')} zero={vis.get('zero')} mid={vis.get('mid')}")
            js("document.getElementById('gx-play').click();")
            time.sleep(0.3)
            check("暂停能停住", g().get("playing") is False, str(g().get("playing")))

            # ---- 播到底：停在"全部亮着"，2 秒后也不许自己清空（bug 复现点） ----
            js("document.getElementById('gx-gap').value=20;"
               "document.getElementById('gx-gap').dispatchEvent(new Event('input',{bubbles:true}));")
            js("document.getElementById('gx-play').click();")
            fin = {}
            for _ in range(80):
                time.sleep(0.2)
                fin = g()
                if not fin.get("playing") and (fin.get("lit") or 0) >= (fin.get("total") or 0):
                    break
            out["finish"] = {"lit": fin.get("lit"), "total": fin.get("total"), "playing": fin.get("playing")}
            grab(OUT6)
            check("播完所有节点都还在（不再是空的）",
                  (fin.get("lit") or 0) == (fin.get("total") or 0) and fin.get("playing") is False,
                  str(out["finish"]))
            vis_lit = loads(js(
                "JSON.stringify((function(){var a=0;"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "if(n&&n.appear>0.6)a++;} return a;})())"
            )) or 0
            time.sleep(2.8)
            fin2 = g()
            vis_lit2 = loads(js(
                "JSON.stringify((function(){var a=0;"
                "for(var i=0;i<window.__rwTest.graph().total;i++){var n=window.__rwTest.graphNode(i);"
                "if(n&&n.appear>0.6)a++;} return a;})())"
            )) or 0
            out["after"] = {"vis": vis_lit, "vis2": vis_lit2, "lit": fin2.get("lit")}
            check("播完静置 2.8s 后仍然全在（回归：以前会在 2s 后整体清空）",
                  vis_lit2 == (fin2.get("total") or 0) and vis_lit > 0,
                  str(out["after"]))

            # ---- 缩放缓动（目标立刻变、画面追上去） ----
            before = g().get("zoom")
            js("(function(){var cv=document.getElementById('gx-canvas');var r=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-240,bubbles:true,cancelable:true,"
               "clientX:r.left+r.width/2,clientY:r.top+r.height/2}));})()")
            z1 = g()
            time.sleep(0.6)
            z2 = g()
            out["zoom"] = [before, z1.get("zoom"), z1.get("zoomTarget"), z2.get("zoom")]
            check("滚轮缩放有缓动：目标先变、画面随后追上",
                  z1.get("zoomTarget") > (before or 0) and z1.get("zoom") <= z1.get("zoomTarget")
                  and z2.get("zoom") >= z1.get("zoom"),
                  str(out["zoom"]))

            # ---- 起点：庇护所 ----
            js("var s=document.getElementById('gx-start'); s.value='shelter';"
               "s.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(0.6)
            sh = g()
            out["shelter"] = sh.get("startRoom")
            check("起点切到庇护所后，第一个节点是庇护所",
                  sh.get("start") == "shelter" and (sh.get("startRoom") in gw_shelters),
                  f"start={sh.get('startRoom')} shelters={sorted(gw_shelters)[:4]}")

            # ---- 另一个区域：折叠无连接 ----
            js("window.__rwTest.openGraph('RF');")
            time.sleep(1.2)
            rf0 = g()
            out["rf0"] = rf0
            print("[布局 RF]", rf0.get("quality"))
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.5)
            js("var f=document.querySelector('[data-gxflag=\"orphan\"]'); f.checked=false;"
               "f.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(0.6)
            rf1 = g()
            out["rf1"] = rf1
            check("RF 折叠无连接后正好少了那些 0 度的房间",
                  rf1.get("rooms") == rf0.get("rooms") - (rf0.get("isolated") or 0),
                  f"{rf0.get('rooms')} → {rf1.get('rooms')}（孤立 {rf0.get('isolated')}）")

            # ---- 最大的区域：打开耗时（最坏情况） ----
            big = loads(js("JSON.stringify(window.__rwTest.biggestGraph())")) or {}
            t0 = time.time()
            js("window.__rwTest.openGraph('%s');" % big.get("code", ""))
            dt = time.time() - t0
            time.sleep(3.4)
            bf = g()
            out["big"] = {"code": big.get("code"), "want": big.get("rooms"), "ms": round(dt * 1000),
                          "rooms": bf.get("rooms"), "edges": bf.get("edges"), "q": bf.get("quality")}
            check("最大的区域打开不卡（房间数最多的那个）",
                  (bf.get("rooms") or 0) >= (big.get("rooms") or 0) * 0.95 and dt < 2.5,
                  str(out["big"]))

            # ---- 颜色（先重新打开设置面板；上一段换了区域，面板是关的） ----
            js("document.getElementById('gx-settings').click();")
            time.sleep(0.5)
            grab(OUT3)
            check("设置面板能打开且有颜色输入框",
                  js("!!document.querySelector('#gx-panel [data-gxcol=\"visited\"]')"), "")
            has_speed = js(
                "!!document.querySelector('#gx-panel [data-gxopt=\"settle\"]') && "
                "!!document.querySelector('#gx-panel [data-gxopt=\"dragPull\"]')")
            js("var r=document.querySelector('[data-gxopt=\"settle\"]'); r.value=1.5;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));"
               "r.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(1.0)
            cfg_now = {}
            try:
                with open(CFG, encoding="utf-8") as fh:
                    cfg_now = json.load(fh)
            except Exception:
                pass
            gopt = (cfg_now.get("ui") or {}).get("graph") or {}
            out["speedOpts"] = {"exist": has_speed, "saved": gopt.get("settle")}
            check("设置里有「布局速度 / 拖动拉力」，且会存进 config",
                  has_speed and gopt.get("settle") == 1.5, str(out["speedOpts"]))
            js("var r=document.querySelector('[data-gxopt=\"settle\"]'); r.value=1;"
               "r.dispatchEvent(new Event('input',{bubbles:true}));"
               "r.dispatchEvent(new Event('change',{bubbles:true}));")
            time.sleep(0.6)
            js("var c=document.querySelector('[data-gxcol=\"visited\"]'); c.value='#00ff88';"
               "c.dispatchEvent(new Event('input',{bubbles:true}));")
            time.sleep(0.5)
            js("var c=document.querySelector('[data-gxcol=\"visited\"]'); c.value='#ff0000';"
               "c.dispatchEvent(new Event('input',{bubbles:true}));")
            time.sleep(0.8)
            cols = (config_graph().get("dark") or {})
            out["colors"] = cols
            check("改「已探索」颜色写进 config.json",
                  cols.get("visited") == "#ff0000", str(cols.get("visited")))

            # ---- 点节点开卡 ----
            js("window.__rwTest.openGraph('GW');")
            time.sleep(3.4)
            node = loads(js("JSON.stringify(window.__rwTest.graphNode(0))")) or {}
            out["node0"] = node
            # 先单击：不应该开卡（这条是用户 11-04 明确要求的）
            js("(function(){var cv=document.getElementById('gx-canvas');"
               "var r=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new MouseEvent('click',{bubbles:true,"
               "clientX:r.left+%s, clientY:r.top+%s}));})()" % (node.get("sx", 0), node.get("sy", 0)))
            time.sleep(0.7)
            after_single = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            check("单击节点只选中，不打开房间卡", after_single.get("open") is False,
                  f"open={after_single.get('open')}")
            js("(function(){var cv=document.getElementById('gx-canvas');"
               "var r=cv.getBoundingClientRect();"
               "cv.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,"
               "clientX:r.left+%s, clientY:r.top+%s}));})()" % (node.get("sx", 0), node.get("sy", 0)))
            time.sleep(0.9)
            card = loads(js("JSON.stringify(window.__rwTest.roomCard())")) or {}
            out["card"] = card
            check("双击节点打开房间卡且房间号一致",
                  card.get("open") and card.get("room") == node.get("name"),
                  f"node={node.get('name')} card={card.get('room')} open={card.get('open')}")
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"worker: {exc}")
        finally:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass

    import threading
    threading.Thread(target=worker, daemon=True).start()
    webview.start()
    # 这个脚本会写 ui.graphColors / ui.graph，跑完把主人的配置原样放回去
    if cfg_backup is not None:
        with open(CFG, "wb") as fh:
            fh.write(cfg_backup)

    print("\n===== 结果 =====")
    bad = 0
    for ok, name, detail in results:
        print(("  ✅ " if ok else "  ❌ ") + name + (" — " + detail if detail else ""))
        if not ok:
            bad += 1
    if out["errors"]:
        print("\n--- 脚本告警 ---")
        for e in out["errors"][:6]:
            print(" ", e)
    print(f"\n合计 {len(results)} 项，失败 {bad} 项")
    with open(os.path.join(SHOTS, "graph_last.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0 if bad == 0 and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
