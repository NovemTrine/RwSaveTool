"""W4-fx 特效层回归：后端几何 + 房间卡像素，两头都验。

    .venv/Scripts/python.exe build/check_regmap_fx.py            # 只跑后端几何
    .venv/Scripts/python.exe build/check_regmap_fx.py --shot     # 再用真实 WebView 抽房间卡像素

后端部分（不需要窗口）：
    * 每个区域的房间数 / 带水 / 带酸 / 带沙 / 带腐化
    * 所有特效几何必须有限、落在房间范围内（y 不能超过 h、x 不能超过 w）
    * 沙面折线必须 x 递增（渲染端就是按 x 插值铺面的）

WebView 部分（`--shot`）：
    * 打开房间卡，读 canvas 像素，确认能看到水 / 沙的颜色（腐化 V1.24 №10 已下线）
    * 顺手把 canvas 导出成 PNG 存到 `build/_shots/page/room_fx_*.png`，方便人眼复核
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, fx, svg        # noqa: E402

OUT = os.path.join(ROOT, "build", "_shots", "page")

# 水 / 沙 / 腐化各挑一间有代表性的房（都在真实存档数据里）
# 腐化 2026-11-21 下线（V1.15 №5）：SVG 与房间卡都不再画，这里改成**反向断言**
# （`verify_no_corrupt`），像素检查只留水与沙两项。
ROOMS = [("SL", "SL_A03", "water"), ("WORA", "WORA_CITY10X", "sand")]
CORRUPT_ROOM = ("RM", "RM_E03")

CHECKS = {"water": 0, "acid": 0, "sand": 0, "corrupt": 0, "rooms": 0}
FAILS: list[str] = []


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)
    return ok


def audit_region(code: str) -> dict:
    lay = adapter.build(code)
    rooms = lay["nodes"]
    got = {"rooms": len(rooms), "water": 0, "acid": 0, "sand": 0, "corrupt": 0}
    for n in rooms:
        f = n.get("fx")
        if not f:
            continue
        w, h = f.get("w") or n["room"].w, f.get("h") or n["room"].h
        if f.get("water"):
            wt = f["water"]
            got["water"] += 1
            if wt.get("acid"):
                got["acid"] += 1
            for (y0, y1) in (wt.get("full") or (0, 0), wt.get("band") or (0, 0)):
                expect(math.isfinite(y0) and math.isfinite(y1), "%s 水位不是有限数" % n["name"])
                expect(-0.01 <= y0 <= h + 0.01 and -0.01 <= y1 <= h + 0.01,
                       "%s 水位越界 %.2f..%.2f (h=%d)" % (n["name"], y0, y1, h))
            for (x0, y0, x1, y1) in wt.get("holes") or []:
                expect(x0 < x1 and y0 < y1, "%s 水域洞退化" % n["name"])
                expect(0 <= x0 <= w + 0.01 and 0 <= x1 <= w + 0.01
                       and 0 <= y0 <= h + 0.01 and 0 <= y1 <= h + 0.01,
                       "%s 水域洞越界" % n["name"])
        if f.get("sand"):
            got["sand"] += 1
            line = f["sand"]
            expect(len(line) >= 2, "%s 沙面点太少" % n["name"])
            xs = [p[0] for p in line]
            expect(all(xs[i] <= xs[i + 1] + 1e-6 for i in range(len(xs) - 1)),
                   "%s 沙面 x 不是递增" % n["name"])
            expect(all(-0.01 <= y <= h + 0.01 for (_x, y) in line),
                   "%s 沙面越界 (h=%d)" % (n["name"], h))
        if f.get("corrupt"):
            got["corrupt"] += 1
            for (cx, cy, r) in f["corrupt"]:
                expect(r > 0 and math.isfinite(r), "%s 腐化半径异常" % n["name"])
                # 圆心允许贴边（圆本身可以探出墙外，游戏里也这样），但不能整个跑到房间外面
                expect(-1 <= cx <= w + 1 and -1 <= cy <= h + 1,
                       "%s 腐化圆心跑到房间外 (%.1f,%.1f) 房间 %dx%d" % (n["name"], cx, cy, w, h))
    for k in got:
        CHECKS[k] = CHECKS.get(k, 0) + got[k]
    return got


def verify_no_corrupt() -> None:
    """腐化必须彻底不上屏：色项、地图 SVG、房间卡回包、前端源码都不许再有。

    V1.24 №10 补了后两条——之前只守地图侧，房间卡那段画圆代码漏了整整两个版本，
    一直用兜底紫 `#9a4fc4` 往房间里糊大圆（截图采样：叠黑 = `#4C2961`）。
    """
    from core.regmap import svg as regmap_svg
    expect("corrupt" not in regmap_svg.PALETTE, "PALETTE 里还有 corrupt")
    from core.regmap import adapter
    for code in ("RM", "MS"):
        lay = adapter.build(code)
        has = sum(1 for n in lay["nodes"] if (n.get("fx") or {}).get("corrupt"))
        body = regmap_svg.build_svg(lay, width=1200, anno=True)["svg"]
        expect("fx-corr" not in body, "%s 的 SVG 里还有腐化圆" % code)
        expect("rg-corrupt" not in body, "%s 的 SVG 里还有 --rg-corrupt" % code)
        print("  %-4s 腐化数据仍有 %3d 间，SVG 里 0 个圆（预期）" % (code, has))

    # 房间卡侧：数据照旧生成，但 `bridge` 不许回传（回传了前端就会画）
    from core.bridge import Api
    api = Api()
    for code, room in (CORRUPT_ROOM, ("HI", "HI_W05")):
        geo = api.room_geometry(code, room)
        if not geo.get("ok"):
            print("  %-4s %s 跳过（%s）" % (code, room, geo.get("error")))
            continue
        got = geo.get("fx") or {}
        expect("corrupt" not in got,
               "%s/%s 的 room_geometry 回包里还有 fx.corrupt" % (code, room))
        print("  %-4s %-9s 房间卡回包 fx 键：%s（无 corrupt 预期）"
              % (code, room, sorted(got) or "空"))

    # 前端源码：画圆那段删干净（只查**调用点**，注释里提到名字不算——注释里确实写着
    # "配色项与 --rm-corrupt 早就删了"，所以这里查的是带冒号的 CSS 声明与 fxc 调用）
    try:
        html = open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8").read()
    except OSError:
        html = ""
    expect("fxc('corrupt'" not in html, "ui/rw_gui.html 里还有 fxc('corrupt') 取色")
    expect("--rm-corrupt:" not in html, "ui/rw_gui.html 的 CSS 里还有 --rm-corrupt 声明")


def verify_water_alpha() -> None:
    """水的两档透明度必须是「同一条真理」：后端常量 == 房间卡字面量 == 出图里的值。

    V1.24 №11 起，这个数就是**「水下结构有多深」的唯一杠杆**（水半透明盖在 `c` 上，
    `(1-α)` 才是结构的权重）。所以它不能是两处各写一遍的魔数——房间卡那份对不上，
    同一间房两个视图的水色就会不一样，而且改了一边看不出问题。
    """
    from core.regmap import svg as regmap_svg
    full, band = regmap_svg.WATER_OPACITY, regmap_svg.BAND_OPACITY
    print("  后端常量：满水 %.2f / 涨落带 %.2f" % (full, band))

    lay = adapter.build("SL")
    body = regmap_svg.build_svg(lay, width=1200)["svg"]
    expect(("fill-opacity:%.2f" % full) in body,
           "SVG 里找不到 fill-opacity:%.2f（水没按 WATER_OPACITY 画）" % full)
    expect("fill-opacity:0.88" not in body, "SVG 里还有旧的水透明度 0.88")

    try:
        html = open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8").read()
    except OSError:
        html = ""
    m_full = re.search(r"paint\(fw\.full\[0\], fw\.full\[1\], ([\d.]+)\)", html)
    m_band = re.search(r"paint\(fw\.band\[0\], fw\.band\[1\], ([\d.]+)\)", html)
    expect(m_full is not None, "房间卡里找不到 paint(fw.full…) 的透明度")
    expect(m_band is not None, "房间卡里找不到 paint(fw.band…) 的透明度")
    if m_full and m_band:
        got_full, got_band = float(m_full.group(1)), float(m_band.group(1))
        print("  房间卡字面量：满水 %.2f / 涨落带 %.2f" % (got_full, got_band))
        expect(abs(got_full - full) < 1e-6,
               "房间卡满水 %.2f ≠ 后端 WATER_OPACITY %.2f" % (got_full, full))
        expect(abs(got_band - band) < 1e-6,
               "房间卡涨落带 %.2f ≠ 后端 BAND_OPACITY %.2f" % (got_band, band))


def pixel_probe(window, code: str, room: str, kind: str) -> dict:
    """打开房间卡，数 canvas 里有多少像素落在那类特效的色相里。

    不能拿"颜色等于调色板值"来判：水/腐化是半透明叠上去的，实际像素是混合色。
    所以按**色相关系**判（蓝多、紫多、暖黄），阈值放宽，只求"这类颜色的面积明显存在"。
    """
    pred = {
        "water": "img[i+2] > img[i] + 40 && img[i+2] > img[i+1] + 15",
        "sand": "img[i] > 150 && img[i+1] > 120 && img[i+2] < img[i] - 35",
        "corrupt": "img[i+2] > img[i+1] + 18 && img[i] > img[i+1] + 18",
    }[kind]
    js = """
    (function(){
      var cv = document.getElementById('rm-canvas');
      if (!cv) return JSON.stringify({ok:false, why:'no canvas'});
      var c = cv.getContext('2d');
      var img = c.getImageData(0, 0, cv.width, cv.height).data;
      var n = 0, tot = cv.width * cv.height;
      for (var i = 0; i < img.length; i += 4){
        var r = img[i], g = img[i+1], b = img[i+2];
        if (%s) n++;
      }
      return JSON.stringify({ok:true, hit:n, total:tot, w:cv.width, h:cv.height});
    })()""" % pred
    raw = window.evaluate_js(js)
    try:
        return json.loads(raw) if raw else {"ok": False, "why": "empty"}
    except Exception:                          # noqa: BLE001
        return {"ok": False, "why": str(raw)[:80]}


def webview_shots() -> None:
    import webview                               # noqa: E402 - 只有 --shot 才需要

    from core.bridge import Api                  # noqa: E402

    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = webview.create_window("RwSaveTool W4-fx 检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    os.makedirs(OUT, exist_ok=True)
    result: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:                  # noqa: BLE001
            FAILS.append("JS 异常：%s → %s" % (code[:50], exc))
            return default

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
            time.sleep(0.8)
            for (code, room, kind) in ROOMS:
                js("window.__rwTest.openRoom('%s','%s')" % (code, room))
                time.sleep(1.6)
                png = js("document.getElementById('rm-canvas').toDataURL('image/png')")
                if isinstance(png, str) and png.startswith("data:image/png;base64,"):
                    raw = base64.b64decode(png.split(",", 1)[1])
                    path = os.path.join(OUT, "room_fx_%s_%s.png" % (kind, room.lower()))
                    with open(path, "wb") as fh:
                        fh.write(raw)
                    result[kind] = {"png": path, "bytes": len(raw)}
                result[kind + "_px"] = pixel_probe(window, code, room, kind)
            result["jsErr"] = js("JSON.stringify(window.__rwJsErr||[])")
        finally:
            try:
                window.destroy()
            except Exception:                     # noqa: BLE001
                pass

    webview.start(worker)

    for (code, room, kind) in ROOMS:
        px = result.get(kind + "_px") or {}
        expect(px.get("ok"), "%s 房间卡没读到画布" % room)
        expect((px.get("hit") or 0) > 60, "%s 画布上找不到 %s 颜色（hit=%s）"
               % (room, kind, px.get("hit")))
        got = result.get(kind) or {}
        print("  %-5s %-13s %-7s 像素命中 %5s / %s  截图 %s"
              % (code, room, kind, px.get("hit"), px.get("total"),
                 os.path.basename(got.get("png") or "-")))
    expect(result.get("jsErr") in ("[]", None), "房间卡里有 JS 异常：%s" % result.get("jsErr"))


def main() -> int:
    codes = [c for c in sys.argv[1:] if not c.startswith("-")] or ["SL", "GW", "WORA", "RM", "MS"]
    print("%-5s %5s %5s %4s %4s %6s" % ("区", "房间", "水", "酸", "沙", "腐化"))
    for code in codes:
        got = audit_region(code.upper())
        print("%-5s %5d %5d %4d %4d %6d"
              % (code.upper(), got["rooms"], got["water"], got["acid"], got["sand"], got["corrupt"]))
    print("-" * 40)
    print("合计：水 %d / 酸 %d / 沙 %d / 腐化 %d（房间 %d）"
          % (CHECKS["water"], CHECKS["acid"], CHECKS["sand"], CHECKS["corrupt"], CHECKS["rooms"]))

    print("\n腐化下线检查：")
    verify_no_corrupt()

    print("\n水透明度一致性：")
    verify_water_alpha()

    if "--shot" in sys.argv:
        print("\n房间卡像素：")
        webview_shots()

    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for f in FAILS[:20]:
            print("  ✗", f)
        return 1
    print("\nCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
