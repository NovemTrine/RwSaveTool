"""W1 · 单房间上色自检：把地形 + 覆盖层按 wiki 配色画成 PNG，肉眼对数。

为什么要有它：地图页还没接（P1），但"颜色对不对"必须现在就能看，否则接前端时
一次要调两处。这里直接用缩略数据（`runs` / `runsAir` / `over`）画，画法与前端一致：
先铺空气、再压实心、最后压覆盖层。

    python build/check_regmap_color.py UW UW_C07 HI HI_A04
    python build/check_regmap_color.py UW --top 6        # 随便挑 6 间大的
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, "D:/Projects/AI_Workspace/WorkBuddy_Workspace/2026-11-19-23-55-46"):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.regmap import adapter             # noqa: E402
from region_map.raster import Canvas, encode_png   # noqa: E402  冻结的 demo，只借 PNG

OUT = os.path.join(HERE, "_shots", "color")

# 配色取自主人给的游戏内地图截图（2026-11-21，`clipboard-2026-11-21T04-25-22`）：
#   室外纯黑 #000000 32.8% ｜ 可通行 #75ced5 12.3% ｜ 岩壁 #1a2031 5.9%+一票近邻色 ｜ 墙面 #589aa0 2.7%
# 墙面（可攀爬面）是压在岩壁上的一层中青，不是另一种独立地形——所以它要画在 solid **之后**。
PALETTE = {
    "outside": "#000000",   # 房间外
    "air": "#75ced5",       # 可通行
    "solid": "#1a2031",     # 岩壁
    "s": "#2b3444",         # 斜面 / 局部格（比岩壁略亮，能看出坡）
    "c": "#3f7f88",         # 背景结构（密集、压在空气上，只能当底纹，画亮就成条纹噪声）
    "b": "#d5f4f7",         # 竖杆 / 绳（截图里是一条条**亮**线）
    "B": "#d5f4f7",         # 横杆（同色，只差合并方向）
    "p": "#e8c65a",         # 管道
    "x": "#5ec46e",         # 出口
    "d": "#c07ae0",         # 巢穴
    "k": "#6f9bff",         # 生物通道
}
# 叠放顺序（下 → 上）：空气 → 岩壁 → 背景结构 → 斜面 → 杆子 → 管道 → 出口 → 巢穴 → 生物通道
DRAW_ORDER = ("c", "s", "b", "B", "p", "x", "d", "k")


def _blocks(tw, th, cw, ch):
    """显示格大小（逻辑像素）。"""
    return cw / max(1, tw), ch / max(1, th)


def draw_over(cv, node, px, py, cw, ch):
    """把覆盖层画上去：面铺满格，杆子/管道缩到格宽 1/3 的纯色矩形。

    与 `core/regmap/svg.py` 的 `_bar_path` 同一套几何（A+C）：
    竖杆纵向合并成条、横杆逐行成段（绝不纵向合并）、管道按块形状，全部缩到 1/3 格。
    改一处必须同时改另一处，否则 PNG 对照图与工具里的 SVG 会走形。
    """
    from core.regmap.svg import _merge_blocks

    for kind in DRAW_ORDER:
        segs = (node.get("over") or {}).get(kind) or []
        if not segs:
            continue
        if kind in ("b", "B", "p"):
            blocks = ([(y, y + 1, a, b) for (y, a, b) in segs] if kind == "B"
                      else _merge_blocks(segs))
            for (r0, r1, x0, x1) in blocks:
                ww = (x1 - x0) * cw
                hh = (r1 - r0) * ch
                if kind == "B" or ww >= hh * 1.2:      # 横条
                    cv.fill_rect(px + x0 * cw, py + (r0 + r1) * 0.5 * ch - ch / 6,
                                 ww, ch / 3, PALETTE[kind])
                elif hh >= ww * 1.2:                   # 竖条
                    cv.fill_rect(px + (x0 + x1) * 0.5 * cw - cw / 6, py + r0 * ch,
                                 cw / 3, hh, PALETTE[kind])
                else:                                  # 近方 → 中心 1/3 方块
                    cv.fill_rect(px + (x0 + x1) * 0.5 * cw - cw / 6,
                                 py + (r0 + r1) * 0.5 * ch - ch / 6,
                                 cw / 3, ch / 3, PALETTE[kind])
        else:
            for (ry, x0, x1) in segs:
                cv.fill_rect(px + x0 * cw, py + ry * ch, (x1 - x0) * cw, ch, PALETTE[kind])


def render_room(node, scale=4.0):
    """把一间房的缩略数据画成 (w, h, rgb)。画法即前端要照做的那一套。"""
    tw, th = node["thumbW"], node["thumbH"]
    w = max(8, int(round(tw * scale)))
    h = max(8, int(round(th * scale)))
    cv = Canvas(w, h, PALETTE["outside"], ss=1)
    bw, bh = _blocks(tw, th, w, h)

    # 1) 可通行：先铺空气，房间轮廓就是这一层的外沿
    for (y, x0, x1) in node.get("runsAir") or []:
        cv.fill_rect(x0 * bw, y * bh, (x1 - x0) * bw, bh, PALETTE["air"])
    # 2) 岩壁
    for (y, x0, x1) in node.get("runs") or []:
        cv.fill_rect(x0 * bw, y * bh, (x1 - x0) * bw, bh, PALETTE["solid"])
    # 3) 覆盖层（墙面要压在岩壁上，杆子/管道压在墙面上）
    draw_over(cv, node, 0, 0, bw, bh)
    return w, h, cv


def verify(node):
    """量三件真事（不再逐格比——缩略图是 1.3~3 倍降采样，逐格相等没有上限意义）：

    - `面积`：显示层的实心格占比 vs 源的实心格占比，相对误差；
    - `召回`：源里每一类覆盖物，有多少被画出来了（显示格被同类或更高优先类盖住都算）；
    - `精度`：显示层标成某类的格子，块里是否真有那一类（防无中生有）。
    """
    from core.regmap import thumbnail as th

    room = node["room"]
    tw, thn = node["thumbW"], node["thumbH"]
    w, h = room.w, room.h
    bbox = node.get("effBox")
    if bbox:
        bx0, by0, bx1, by1 = bbox
        bx0 = max(0, min(w - 1, bx0)); by0 = max(0, min(h - 1, by0))
        bx1 = max(bx0, min(w - 1, bx1)); by1 = max(by0, min(h - 1, by1))
    else:
        bx0 = by0 = 0; bx1, by1 = w - 1, h - 1
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1

    # `to_rows` / `to_over_rows` 的块起点：x0(ox) = min(bw-1, ox*bw//tw)
    # 反查必须按这张表来（用 ox = sx*tw//bw 是错的，两者不是互逆的整数划分）
    x0s = [min(bw - 1, ox * bw // tw) for ox in range(tw)]
    y0s = [min(bh - 1, oy * bh // thn) for oy in range(thn)]

    def disp_of(sx, sy):
        import bisect
        return (max(0, bisect.bisect_right(y0s, sy) - 1),
                max(0, bisect.bisect_right(x0s, sx) - 1))

    solid_d = set()
    for (y, x0, x1) in node.get("runs") or []:
        for x in range(x0, x1):
            solid_d.add((y, x))
    over_d = {}
    for k, segs in (node.get("over") or {}).items():
        s = set()
        for (y, x0, x1) in segs:
            for x in range(x0, x1):
                s.add((y, x))
        over_d[k] = s

    src = th.over_grid(room)
    rank = th._OVER_RANK
    # 显示格 → 它覆盖的源格类别集合（一次建好，召回/精度都查它）
    disp_src = {}
    for sy in range(bh):
        for sx in range(bw):
            disp_src.setdefault(disp_of(sx, sy), set()).add(
                src[(by0 + sy) * w + bx0 + sx])

    src_area = sum(1 for sy in range(bh) for sx in range(bw)
                   if room.cells[(by0 + sy) * w + bx0 + sx] != "0")
    disp_area = len(solid_d)
    src_frac = 100.0 * src_area / max(1, bw * bh)
    disp_frac = 100.0 * disp_area / max(1, tw * thn)
    rel = disp_frac - src_frac          # 占比之差（百分点）

    recall, prec = {}, {}
    for k in th.MAP_KINDS:
        cells = [(sx, sy) for sy in range(bh) for sx in range(bw)
                 if src[(by0 + sy) * w + bx0 + sx] == k]
        if not cells:
            continue
        got = 0
        for (sx, sy) in cells:
            dy, dx = disp_of(sx, sy)
            hit = [kk for kk, st in over_d.items() if (dy, dx) in st]
            if hit and rank.get(min(hit, key=lambda kk: rank.get(kk, 99)), 99) <= rank[k]:
                got += 1
        recall[k] = (got, len(cells))
        st = over_d.get(k, set())
        wrong = sum(1 for d in st if k not in disp_src.get(d, ()))
        prec[k] = (len(st) - wrong, len(st))

    return {"src_area": src_area, "disp_area": disp_area,
            "src_frac": src_frac, "disp_frac": disp_frac, "rel": rel,
            "recall": recall, "prec": prec}


def main(argv=None):
    ap = argparse.ArgumentParser(description="单房间上色自检")
    ap.add_argument("targets", nargs="+", help="区代码，或 区代码+房间名（如 UW_C07）")
    ap.add_argument("--top", type=int, default=0, help="每区挑最大的前 N 间")
    ap.add_argument("--scale", type=float, default=4.0, help="每显示格几像素")
    ap.add_argument("--verify", action="store_true", help="顺带做逐格对数")
    args = ap.parse_args(argv)

    os.makedirs(OUT, exist_ok=True)
    codes = sorted({t.split("_")[0].upper() for t in args.targets})
    wants = {t.upper() for t in args.targets if "_" in t}
    made = []
    for code in codes:
        layout = adapter.build(code)
        nodes = layout["nodes"]
        if wants:
            picked = [n for n in nodes if n["name"].upper() in wants]
        elif args.top:
            picked = sorted(nodes, key=lambda n: -(n["w"] * n["h"]))[:args.top]
        else:
            picked = nodes[:1]
        for n in picked:
            w, h, cv = render_room(n, args.scale)
            path = os.path.join(OUT, "%s.png" % n["name"])
            data = encode_png(w, h, cv.to_bytes())
            with open(path, "wb") as fh:
                fh.write(data)
            kinds = {k: len(v) for k, v in (n.get("over") or {}).items()}
            line = ("%-16s %dx%d  %.0f KB  runs %d  over %s"
                    % (n["name"], w, h, len(data) / 1024.0, len(n.get("runs") or []),
                       json.dumps(kinds, ensure_ascii=False)))
            if args.verify:
                v = verify(n)
                rec = "／".join("%s %d/%d" % (k, a, b) for k, (a, b) in sorted(v["recall"].items()))
                prc = "／".join("%s %d/%d" % (k, a, b) for k, (a, b) in sorted(v["prec"].items()))
                line += ("  ‖ 实心占比 %.1f%% / 源 %.1f%%（%+.1f 点）  召回 %s  精度 %s"
                         % (v["disp_frac"], v["src_frac"], v["rel"], rec, prc))
            made.append((n["name"], line))
    for name, info in made:
        print("%-16s %s" % (name, info))
    print("图在 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
