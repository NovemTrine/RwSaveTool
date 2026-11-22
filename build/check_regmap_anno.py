"""W4 / №2 标注层回归：**只验子区域色与子区域名，验"该删的都删干净了"**。

    .venv/Scripts/python.exe build/check_regmap_anno.py            # 默认几个区
    .venv/Scripts/python.exe build/check_regmap_anno.py --all      # 全库（慢，约 2 分钟）
    .venv/Scripts/python.exe build/check_regmap_anno.py --shot     # 再开真实窗口点开关

验什么
------
数据层
  * `node["anno"]` **只有** `sub` / `sc` 两个键——`kind` / `marks` / `gates` 一律不许再挂；
  * 挂上的节点必须真的有子区域名，且子区域名不是区域自己的名字（否则整张图会被染一片）。
SVG 层（全是**反向**断言：删掉的东西不能再长回来）
  * 没有 `<defs>` / `<symbol id="rgi-…">` / `<use>`；
  * 没有 `.an-p` / `.an-i` 这些图标样式与元素；
  * 子区域名 `.an-lb` 与子区域色 `.an-sub` 仍照常出现，且 `labels=0` 时消失；
  * `anno=False` 时一个标注元素都不剩（载荷回到 W4 之前）。
页面层（`--shot`）
  * 打开几何图：`annos`（现在数的是 `.an-lb`）等于数据里的子区域数；
  * 关掉「子区域名」→ 归零；再打开 → 恢复。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, svg        # noqa: E402

# CC 排第一：`--shot` 用 `CODES[0]`，必须挑一个**真有子区域**的区（不然数不到名字）
CODES = ["CC", "MS", "HI", "SU", "GW"]
FAILS: list[str] = []
GONE = ('<use', "<defs", "<symbol", 'class="an-p"', 'class="an-i"', "rgi-")


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)
    return ok


def audit(code):
    lay = adapter.build(code)
    nodes = lay["nodes"]
    got = {"rooms": len(nodes), "sub": 0}
    for n in nodes:
        a = n.get("anno") or {}
        if not a:
            continue
        if a.get("sub"):
            got["sub"] += 1
        # 键必须只剩这两样：多出来的就是旧字段没删干净
        extra = sorted(set(a) - {"sub", "sc"})
        expect(not extra, "%s/%s 的 anno 还有旧字段 %s" % (code, n["name"], extra))
        expect(bool(a.get("sub")) and str(a.get("sc") or "").startswith("#"),
               "%s/%s 的 anno 缺 sub/sc（%r）" % (code, n["name"], a))

    body = svg.build_svg(lay, width=1400, anno=True)["svg"]
    for tok in GONE:
        expect(tok not in body, "%s 的 SVG 里还有 %s（图标那套没删干净）" % (code, tok))
    has_lb = 'class="an-lb"' in body
    expect(has_lb == (got["sub"] > 0), "%s 子区域名与子区域数据不一致（lb=%s, sub=%d）"
           % (code, has_lb, got["sub"]))

    # labels 关掉 → 名字必须消失（子区域色可以还在）
    no_lb = svg.build_svg(lay, width=1400, anno={"sub": 1, "labels": 0})["svg"]
    expect('class="an-lb"' not in no_lb, "%s 关掉「子区域名」后还有 .an-lb" % code)

    # 全关 = 一个标注元素都没有（载荷回到 W4 之前）
    none = svg.build_svg(lay, width=1400, anno=False)["svg"]
    expect('class="an-lb"' not in none and 'class="an-sub"' not in none,
           "%s 关掉标注后仍残留标注元素" % code)
    # 旧调用方传三个已删的开关：不许崩，也不许把图标带回来
    old = svg.build_svg(lay, width=1400, anno={"kind": 1, "marks": 1, "gates": 1})["svg"]
    for tok in GONE:
        expect(tok not in old, "%s 传旧开关 %s 时把图标带回来了" % (code, tok))
    return got


def webview_shots():
    """真实窗口：开几何图 → 数名字 → 关掉「子区域名」→ 归零 → 再开回来。"""
    import json
    import time

    import webview                                 # noqa: E402

    from core.bridge import Api                    # noqa: E402

    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = webview.create_window("RwSaveTool №2 标注检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out = {"errors": []}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:                   # noqa: BLE001
            out["errors"].append("%s: %s" % (code[:50], exc))
            return default

    def state():
        try:
            return json.loads(js("JSON.stringify(window.__rwTest.geoState())") or "{}")
        except ValueError:
            return {}

    def worker():
        time.sleep(2.5)
        js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
        for _ in range(60):
            time.sleep(0.5)
            if js("window.__rwTest.ready()"):
                break
        time.sleep(1.0)
        js("window.__rwTest.geo('%s')" % CODES[0])
        for _ in range(40):
            time.sleep(0.5)
            if state().get("svg"):
                break
        time.sleep(1.0)
        out["base"] = state()
        js("window.__rwTest.geoAnno('labels', 0)")
        time.sleep(1.5)
        out["off"] = state()
        js("window.__rwTest.geoAnno('labels', 1)")
        time.sleep(1.5)
        out["back"] = state()
        window.destroy()

    webview.start(worker)
    return out


def main():
    codes = CODES
    if "--all" in sys.argv:
        codes = sorted(os.path.splitext(f)[0].upper()
                       for f in os.listdir(os.path.join(ROOT, "region_data"))
                       if f.lower().endswith(".json") and not f.startswith("_"))
    print("区     房间  子区域房")
    total = {"rooms": 0, "sub": 0}
    per_code = {}
    for code in codes:
        try:
            got = audit(code)
        except ValueError as exc:
            if "空布局" in str(exc):                # 没有可排布房间的区（单间区等）
                print("%-6s 跳过（空布局）" % code)
                continue
            FAILS.append("%s 审计抛异常：%r" % (code, exc))
            continue
        except Exception as exc:                   # noqa: BLE001
            FAILS.append("%s 审计抛异常：%r" % (code, exc))
            continue
        per_code[code] = got
        for k in total:
            total[k] += got[k]
        print("%-6s %4d %8d" % (code, got["rooms"], got["sub"]))
    print("-" * 28)
    print("合计：房间 %d / 挂子区域的房间 %d" % (total["rooms"], total["sub"]))

    if "--shot" in sys.argv:
        # 页面里点开关会真写 config，先记一份、结束时还原
        from core import paths                       # noqa: E402
        before = (paths.load_config().get("ui") or {}).get("regmapAnno")
        out = webview_shots()
        base = out.get("base") or {}
        off = out.get("off") or {}
        back = out.get("back") or {}
        print("页面：base=%s off=%s back=%s" % (base.get("annos"), off.get("annos"),
                                              back.get("annos")))
        if out.get("errors"):
            print("  JS 异常：", out["errors"][:3])
        expect(base.get("rooms", 0) > 0, "几何图没开出来")
        expect(base.get("annos", 0) > 0, "页面里没数到子区域名")
        expect(off.get("annos") == 0, "关掉「子区域名」后还剩 %s 个" % off.get("annos"))
        expect(back.get("annos") == base.get("annos"), "再开回来没有恢复")
        try:
            paths.save_config({"ui": {"regmapAnno": before}})
        except Exception:                            # noqa: BLE001
            pass

    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for f in FAILS[:20]:
            print("  ·", f)
        return 1
    print("\nCHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
