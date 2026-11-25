"""杆子/管道绘制回归（V1.15 №3 / V1.17 高清层修订）。

`_bar_path` 改成了"横向极大段 + 纵向极大段都画"（管道仍按块主方向），
这个脚本验的是**画出来的东西**，不是中间数据：直接解析 `_bar_path` 产出的 path `d`，
把矩形还原出来，再看每一格杆/管有没有被覆盖、拐角处横竖有没有真的连上。

判据：
1. **不丢格**：每个杆/管格的中心点，必须落在至少一个绘制矩形里（漏一格就是断线）；
2. **拐角连通**：横竖邻居都有的格子，必须同时被"偏横向的矩形"和"偏纵向的矩形"覆盖——
   这正是主人报的"只有横线与竖线、拐不过弯"；
3. **条目受控**：`b`/`B` 的矩形数不超过旧画法的 1.6 倍（管道 1.8）（早期按"长度为 1 的段"补方块，
   条目一度翻倍，字节涨 50%，见 §6 的坑）；
4. **管道不变胖**：`p` 的矩形数必须等于 `_merge_blocks` 的块数（管道已回旧画法）；
5. **高清层不出假竖刺（V1.17）**：`density=4` 时显示格比源格细，1 格厚的横杆会被复制成
   2 行；不折回源格就会在每一列都看到"上下都有邻居"→ 画成"横线上每格一根竖刺"（梯子）。
   判据：任何竖矩形的**高度必须 ≥ 2 个源格**（1 个源格高的竖条一定是假的）。

用法：
    python build/check_regmap_bars.py            # 默认 8 个区
    python build/check_regmap_bars.py --all      # 全库
    python build/check_regmap_bars.py --no-hd    # 跳过高清层那一步（快一倍）
"""
from __future__ import annotations

import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, svg, thumbnail      # noqa: E402

FAILS: list[str] = []
RECT = re.compile(r"M(-?\d+\.?\d*) (-?\d+\.?\d*)h(-?\d+\.?\d*)v(-?\d+\.?\d*)h-?\d+\.?\d*z")
CODES = ["SU", "CC", "HI", "GW", "MS", "SL", "LF", "UW"]


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)


def parse_rects(d: str):
    out = []
    for m in RECT.finditer(d):
        x, y, w, h = (float(m.group(i)) for i in range(1, 5))
        out.append((x, y, w, h))
    return out


def covers(rects, px, py, eps=0.35):
    for (x, y, w, h) in rects:
        if x - eps <= px <= x + w + eps and y - eps <= py <= y + h + eps:
            return True
    return False


def _merged(n, kinds):
    """把若干 kind 的游程拼成一份（与 `svg.build_svg` 的调用口径一致：`b`+`B` 一起画）。"""
    out = []
    for k in kinds:
        out.extend([list(s) for s in ((n.get("over") or {}).get(k) or [])])
    return out


def _hit(rects, px, py, eps=0.01):
    for (x, y, w, h) in rects:
        if x - eps <= px <= x + w + eps and y - eps <= py <= y + h + eps:
            return True
    return False


def audit_room(n, cw, ch, px, py):
    """一间房 → (缺格数, 拐角总数, 拐角连上的数, {组: (新条目, 旧条目)}, 外溢数, miss_by)。

    组只有两个：`b+B`（V1.24 №5 起合并绘制、同色）与 `p`。合并之后判据才和真实渲染一致
    ——按单个 kind 测会把"一格 b + 一格 B"的转角算成两个互不相连的段。
    """
    missing = corners = joined = spill = 0
    miss_by = {}
    stats = {}
    groups = (("b+B", ("b", "B"), "b"), ("p", ("p",), "p"))
    for gname, kinds, colour in groups:
        segs = _merged(n, kinds)
        if not segs:
            continue
        grid, w, h = svg._bar_grid(segs)
        if not w:
            continue
        # 管道的大片会先挖掉"内部格"（见 `_bar_path`）：那些格子本来就不该被画，
        # 统计"缺格"时要把它们排除，否则每一片实心都会报几十个假缺。
        hollowed = set()
        if colour == "p" and w > 2 and h > 2:
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if grid[y][x] and grid[y][x - 1] and grid[y][x + 1] \
                            and grid[y - 1][x] and grid[y + 1][x]:
                        hollowed.add((x, y))
        d = svg._bar_path(segs, cw, ch, px, py, colour, 1.0)
        rects = parse_rects(d)
        old = sum(len(svg._merge_blocks([list(s) for s in ((n.get("over") or {}).get(k) or [])]))
                  for k in kinds)
        stats[gname] = (len(rects), old)
        vs = svg._orient(grid, w, h, True)
        hs = svg._orient(grid, w, h, False)

        for y in range(h):
            for x in range(w):
                if not grid[y][x]:
                    continue
                cx = px + (x + 0.5) * cw
                cy = py + (y + 0.5) * ch
                hit = [r for r in rects
                       if r[0] - 0.35 <= cx <= r[0] + r[2] + 0.35
                       and r[1] - 0.35 <= cy <= r[1] + r[3] + 0.35]
                if not hit:
                    if (x, y) not in hollowed:
                        missing += 1
                        miss_by[gname] = miss_by.get(gname, 0) + 1
                    continue
                hz = (x > 0 and grid[y][x - 1]) or (x < w - 1 and grid[y][x + 1])
                vt = (y > 0 and grid[y - 1][x]) or (y < h - 1 and grid[y + 1][x])
                if hz and vt and colour != "p":      # 管道按块画，不参与"两向连上"这条
                    corners += 1
                    wide = any(r[2] > r[3] + 0.01 for r in hit)
                    tall = any(r[3] > r[2] + 0.01 for r in hit)
                    if wide and tall:
                        joined += 1
                    # №2：拐角格四个方向里"没有数据"的那半边不许被涂到 0.4 格外。
                    # 老画法两向都铺满整格，那半格就是主人看到的"＋"的两个多余臂。
                    if vs[y][x] and hs[y][x]:
                        for (dx, dy) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx]:
                                continue
                            if _hit(rects, cx + dx * cw * 0.4, cy + dy * ch * 0.4):
                                spill += 1
    return missing, corners, joined, stats, spill, miss_by


def audit_hd(nodes, code, s):
    """高清层（density=4）：折回源格之后，不许再出现"只有 1 个源格高"的竖矩形。

    1 格厚的横杆在 4 倍密度下会占 2 个显示行；老代码把"上下两行都有"当成竖向分叉，
    于是在**每一列**都画一根竖刺（主人 2026-11-21 夜报的"非十字的位置被打成十字"）。

    判据必须按**源格行**数，不能按像素高度算阈值：`th/bh` 是 1.3 时，两个源行各占 1 个
    显示行（合计 2 个），而 1 个源行被复制出来也可能占 2 个显示行——像素一样高，含义相反。
    所以这里拿 `svg._copy_groups` 的同一张分组表，把矩形的 y 区间翻回"覆盖了几个源行"。
    """
    ticks = drawn = 0
    for n in nodes:
        tw, th = n.get("thumbW"), n.get("thumbH")
        bw, bh = n.get("overW"), n.get("overH")
        if not (tw and th and bw and bh):
            continue
        cw, ch = (n["w"] * s) / max(1, tw), (n["h"] * s) / max(1, th)
        gy = svg._copy_groups(th, bh)
        for kinds, colour in ((("b", "B"), "b"), (("p",), "p")):
            segs = _merged(n, kinds)
            if not segs:
                continue
            d = svg._bar_path(segs, cw, ch, 0.0, 0.0, colour, 1.0, (bw, bh, tw, th))
            for (x, y, w, h) in parse_rects(d):
                drawn += 1
                # `h > w*1.5` 而不是 `h > w`：孤立格补的是 1/3 方块，宽高只差 0.1 的取整
                # （0.5 / 0.6）就会被误判成"竖条"。
                if h <= w * 1.5:
                    continue
                rows = sum(1 for (a, b) in gy
                           if b * ch > y + 0.01 and a * ch < y + h - 0.01)
                if rows < 2:
                    ticks += 1
    expect(ticks == 0, "%s 高清层有 %d 根假竖刺（每根都只有 1 个源格高，共 %d 个矩形）"
           % (code, ticks, drawn))
    return ticks


def main() -> int:
    codes = [c for c in sys.argv[1:] if not c.startswith("-")]
    hd = "--no-hd" not in sys.argv
    if "--all" in sys.argv or not codes:
        codes = sorted(os.path.splitext(f)[0].upper()
                       for f in os.listdir(os.path.join(ROOT, "region_data"))
                       if f.lower().endswith(".json") and not f.startswith("_")) \
            if "--all" in sys.argv else CODES

    print("%-6s %5s %-11s %-11s %-9s %s" % ("区", "房间", "杆(新/旧)", "管(新/旧)", "拐角(连上)", "外溢"))
    tot = {"rooms": 0, "b_new": 0, "b_old": 0, "p_new": 0, "p_old": 0,
           "corners": 0, "joined": 0, "missing": 0, "hd_ticks": 0, "spill": 0}
    t0 = time.time()
    for code in codes:
        try:
            lay = adapter.build(code)
        except Exception as exc:                   # noqa: BLE001
            print("%-6s 跳过（%s）" % (code, str(exc)[:30]))
            continue
        s = (2400 - 28) / max(1e-9, max(n["x"] + n["w"] for n in lay["nodes"])
                              - min(n["x"] for n in lay["nodes"]))
        got = {"b+B": [0, 0], "p": [0, 0]}
        missing = corners = joined = spill = 0
        miss_by = {}
        for n in lay["nodes"]:
            cw = (n["w"] * s) / max(1, n["thumbW"])
            ch = (n["h"] * s) / max(1, n["thumbH"])
            m, c, j, st, sp, mb = audit_room(n, cw, ch, 0.0, 0.0)
            missing += m
            corners += c
            joined += j
            spill += sp
            for k, v in mb.items():
                miss_by[k] = miss_by.get(k, 0) + v
            for k, (new, old) in st.items():
                got[k][0] += new
                got[k][1] += old
        expect(missing == 0, "%s 有 %d 个杆/管格没被任何矩形覆盖（会断线）%s"
               % (code, missing, miss_by))
        expect(corners == 0 or joined >= corners,
               "%s 拐角 %d 个，只有 %d 个横竖都画到" % (code, corners, joined))
        expect(spill == 0, "%s 有 %d 处拐角往\"没有数据\"的方向多涂了半格（就是那个＋）"
               % (code, spill))
        for k in ("b+B", "p"):
            if got[k][1]:
                ratio = got[k][0] / float(got[k][1])
                cap = 1.6 if k == "b+B" else 1.8
                expect(ratio <= cap, "%s 的 %s 条目是旧画法的 %.2f 倍（上限 %.1f，字节会涨）"
                       % (code, k, ratio, cap))
        print("%-6s %5d %5d/%-5d %5d/%-5d %5d/%-5d %d %.1fs"
              % (code, len(lay["nodes"]), got["b+B"][0], got["b+B"][1],
                 got["p"][0], got["p"][1], joined, corners, spill, time.time() - t0))
        if hd:
            # 高清层要重新铺一遍缩略图（density=4 的显示格比源格细，假厚度就在那一层）
            nodes = [dict(x) for x in lay["nodes"]]
            thumbnail.prepare(nodes, density=4)
            ticks = audit_hd(nodes, code, s)
            tot["hd_ticks"] += ticks
            print("%-6s 高清层 4x：假竖刺 %d 根" % ("", ticks))
        tot["rooms"] += len(lay["nodes"])
        tot["b_new"] += got["b+B"][0]; tot["b_old"] += got["b+B"][1]
        tot["p_new"] += got["p"][0]; tot["p_old"] += got["p"][1]
        tot["corners"] += corners; tot["joined"] += joined
        tot["missing"] += missing; tot["spill"] += spill

    print("-" * 60)
    print("合计：%d 间房；杆 %d→%d（×%.2f）、管 %d→%d（×%.2f）；"
          "拐角 %d 个、连通 %d 个；缺格 %d；外溢 %d；高清层假竖刺 %d"
          % (tot["rooms"], tot["b_old"], tot["b_new"], tot["b_new"] / max(1, tot["b_old"]),
             tot["p_old"], tot["p_new"], tot["p_new"] / max(1, tot["p_old"]),
             tot["corners"], tot["joined"], tot["missing"], tot["spill"], tot["hd_ticks"]))
    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for f in FAILS:
            print("  ✗", f)
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
