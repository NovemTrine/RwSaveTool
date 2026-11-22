"""W1 · 整区观感图：房间按截图配色上色，房间之间用**三次贝塞尔**连线。

用途有两个：
1. 在碰前端之前，先把「上色 + 贝塞尔」这两件事的成品看到——M1 判的就是这个；
2. 每期改完重出同一批区，肉眼对比（配合 `check_regmap_shape.py` 的分数）。

    python build/check_regmap_look.py UW HI CC MS GW WARA
    python build/check_regmap_look.py UW --straight     # 对照组：折线/直线
    python build/check_regmap_look.py UW --labels       # 带房间编号，便于对点

画法与 `check_regmap_color.py` 完全一致（同一份 PALETTE / DRAW_ORDER），只是缩到整区。
连线的叠放顺序按决策 3：**线在房间下面**（先画线，再压房间），这样线只在缝里露出来。
"""

from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, "D:/Projects/AI_Workspace/WorkBuddy_Workspace/2026-11-19-23-55-46"):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.regmap import adapter                        # noqa: E402
from region_map.raster import Canvas, encode_png      # noqa: E402  冻结 demo，只借 PNG
from build.check_regmap_color import PALETTE, DRAW_ORDER, draw_over   # noqa: E402  同一份配色与画法

OUT = os.path.join(HERE, "_shots", "look")
LINK = "#3f6f7a"          # 缝里的连线：比墙面亮一档，但不抢房间
LINK_WARN = "#8a6a2a"     # 未解/冲突边
DOOR = "#9fe8ef"


def _normal(pt, rect):
    """门点相对房间中心的外法线（吸附到轴）。比按 side 字母推更稳——不依赖 y 朝向约定。"""
    cx = rect[0] + rect[2] * 0.5
    cy = rect[1] + rect[3] * 0.5
    dx = (pt[0] - cx) / max(1e-9, rect[2] * 0.5)
    dy = (pt[1] - cy) / max(1e-9, rect[3] * 0.5)
    if abs(dx) >= abs(dy):
        return (1.0 if dx >= 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy >= 0 else -1.0)


def _bezier(p0, p1, p2, p3, n=18):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
        y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
        pts.append((x, y))
    return pts


def link_points(edge, rect_a, rect_b, curve=True):
    """一条边的画法点列。曲线端点落在两扇门上，控制点沿门法线外推。"""
    p0 = (float(edge["pa"][0]), float(edge["pa"][1]))
    p3 = (float(edge["pb"][0]), float(edge["pb"][1]))
    if not curve:
        return [p0, p3]
    dist = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    if dist < 1e-6:
        return [p0, p3]
    na, nb = _normal(p0, rect_a), _normal(p3, rect_b)
    k = dist * 0.42
    p1 = (p0[0] + na[0] * k, p0[1] + na[1] * k)
    p2 = (p3[0] + nb[0] * k, p3[1] + nb[1] * k)
    return _bezier(p0, p1, p2, p3)


def _line(cv, pts, color, width):
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color, width)


def render_region(layout, target_w=2000, pad=16, curve=True, labels=False, ss=1):
    nodes = layout["nodes"]
    edges = layout["edges"]
    x0 = min(n["x"] for n in nodes)
    y0 = min(n["y"] for n in nodes)
    x1 = max(n["x"] + n["w"] for n in nodes)
    y1 = max(n["y"] + n["h"] for n in nodes)
    s = (target_w - pad * 2) / max(1e-9, (x1 - x0))
    w = target_w
    h = int((y1 - y0) * s + pad * 2)
    cv = Canvas(w, h, PALETTE["outside"], ss=ss)

    def mx(v):
        return pad + (v - x0) * s

    def my(v):
        return pad + (v - y0) * s

    rects = {n["name"].upper(): (n["x"], n["y"], n["w"], n["h"]) for n in nodes}

    # 1) 连线（在房间下面）
    lw = max(1, int(round(s * 0.10)))
    for e in edges:
        ra = rects.get(e["a"].upper())
        rb = rects.get(e["b"].upper())
        if not ra or not rb:
            continue
        pts = [(mx(px), my(py)) for px, py in link_points(e, ra, rb, curve)]
        warn = e.get("conflict") or e.get("route") == "unresolved"
        _line(cv, pts, LINK_WARN if warn else LINK, lw)

    # 2) 房间：空气 → 岩壁 → 覆盖层，与单房自检同一套顺序
    for n in nodes:
        px, py = mx(n["x"]), my(n["y"])
        pw, ph = n["w"] * s, n["h"] * s
        cw = pw / max(1, n["thumbW"])
        ch = ph / max(1, n["thumbH"])
        for (ry, c0, c1) in n.get("runsAir") or []:
            cv.fill_rect(px + c0 * cw, py + ry * ch, (c1 - c0) * cw, ch, PALETTE["air"])
        for (ry, c0, c1) in n.get("runs") or []:
            cv.fill_rect(px + c0 * cw, py + ry * ch, (c1 - c0) * cw, ch, PALETTE["solid"])
        draw_over(cv, n, px, py, cw, ch)          # 面 = 矩形，管道/杆子 = 等宽线

    # 3) 门点（画在房间之上，压住缝）
    dw = max(1.0, s * 0.5)
    for e in edges:
        for pt in (e["pa"], e["pb"]):
            cv.fill_rect(mx(pt[0]) - dw * 0.5, my(pt[1]) - dw * 0.5, dw, dw, DOOR)

    return w, h, cv, s


def main(argv=None):
    ap = argparse.ArgumentParser(description="整区观感图（上色 + 贝塞尔）")
    ap.add_argument("codes", nargs="+", help="区代码")
    ap.add_argument("--target", type=int, default=2000, help="目标宽度（像素）")
    ap.add_argument("--density", type=int, default=2,
                    help="每布局单位铺几格缩略（默认 2；整区看细节用 4）")
    ap.add_argument("--straight", action="store_true", help="对照组：连线画直线")
    ap.add_argument("--labels", action="store_true", help="叠房间编号（调试用，默认不画）")
    args = ap.parse_args(argv)

    os.makedirs(OUT, exist_ok=True)
    from core.regmap import thumbnail as th
    for code in args.codes:
        layout = adapter.build(code)
        if args.density != 2:
            th.prepare(layout["nodes"], density=args.density)
        w, h, cv, s = render_region(layout, args.target, curve=not args.straight,
                                    labels=args.labels)
        suffix = "" if not args.straight else "_straight"
        if args.density != 2:
            suffix += "d%d" % args.density
        path = os.path.join(OUT, "%s%s.png" % (code.upper(), suffix))
        data = encode_png(w, h, cv.to_bytes())
        with open(path, "wb") as fh:
            fh.write(data)
        st = layout["stats"]
        print("%-6s %dx%d  %.0f KB  间 %3d 边 %3d  直连 %d 绕行 %d 未解 %d  缝 %.1f"
              % (code.upper(), w, h, len(data) / 1024.0, len(layout["nodes"]),
                 len(layout["edges"]), st.get("route_straight", 0),
                 st.get("route_elbow", 0), st.get("route_unresolved", 0), st.get("gap", 0)))
    print("图在 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
