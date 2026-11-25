"""区域布局 → 自包含 SVG。

为什么放在后端而不是前端画：
1. 前端 `rw_gui.html` 里画一遍、导出再画一遍，两套代码必然走形；这里出一次，页面直接塞进去就是**所见即所导**；
2. 没有浏览器也能验：`build/check_regmap_svg.py` 落盘 + 出画廊页，命令行就能看；
3. 房间是一堆游程（`runs`），拼成 `<path>` 比逐格 `<rect>` 小一个量级。

坐标：布局单位 → 像素（`scale`），外边距 `pad`。房间自己的缩略格再按 `w/thumbW`、`h/thumbH` 铺开，
与 `thumbnail.prepare` 的块映射一致——**改一处要同时改两处**（那边是渲染的依据，这边是它的像素化）。

配色见 `PALETTE`，来源是主人 2026-11-21 给的游戏内地图截图（像素统计），
与 `build/check_regmap_color.py` / `check_regmap_look.py` 是同一份口径。三层之外不再加装饰。
"""

from __future__ import annotations

import math

from . import anno as anno_mod

# 16 项色卡（V1.15 №5，主人 2026-11-21 给的颜色集 / `颜色集代码.txt`）。
#
# 两条口径：
#   · **`air`（可通行）与 `c`（背景结构）不在表里**——它们由区域调色板提取
#     （`core/regmap/colors.py`，路 A）后按房间/子区域分组下发，见 `_region_vars`。
#     `PALETTE` 里这两个值只是"拿不到提取结果时"的兜底。
#   · **腐化（corrupt）已删**：色项、圆斑渲染、房间卡 arc 一起下线（№5 附加要求）。
PALETTE = {
    "sheet": "#3D4448",     # 区域背景（房间外 / 画布；`outside` 并入此项）
    "air": "#8C97AF",       # 可通行（兜底；正常由 colors.py 提取）
    "solid": "#000000",     # 岩壁
    "s": "#2F2F2F",         # 斜面
    "c": "#637178",         # 背景结构（兜底；正常由 corlor 派生）
    "b": "#374D5D",         # 竖杆
    "B": "#374D5D",         # 横杆（同色，仅合并不一样）
    "p": "#FFFFFF",         # 管道
    "x": "#2FED2F",         # 通道入口
    "d": "#ED2F2F",         # 巢穴
    "k": "#2F2FED",         # 生物通道
    "door": "#9FE8EF",      # 门点
    "seen": "#FFF700",      # 已探索房间的框
    "link": "#3F6F7A",      # 缝里的连线
    "warn": "#8A6A2A",      # 未解 / 冲突边（内部诊断色，不入面板）
    "water": "#5089D9",     # 水体
    "acid": "#8FC63D",      # 酸液 / 毒卤水（覆盖 water 的颜色）
    "sand": "#E5A462",      # 沙 / 雪（TerrainHandle 堆出来的面）
    "anno": "#FFFFFF",      # 标注前景色（№2 之后只剩「子区域名」在用）
}

# 标注层默认开关（№2 之后只剩两项）：`labels`（子区域名）默认**开**——主人定案：标注只留
# 子区域色与子区域名，名字是唯一的文字信息，不给个默认开就等于没有。
ANNO_DEFAULTS = {"sub": 1, "labels": 1}

# 子区域淡色的不透明度：只用来「分块」，不能盖住地形。
SUB_ALPHA = 0.18

# 区域地图的杆子色：**固定** `PALETTE["b"] = #374D5D`，与房间卡那条深色细线同一个颜色。
# V1.24 №13 曾改成「该子区域结构色再压一档」，V1.25 №14 已回滚——主人 2026-11-25 定案：
# 杆子本身颜色没问题，出问题的是杆子格的**底色**（`thumbnail._settle` 把 `c` 剥掉了）。
# 底色修好后，固定深色压在结构色上反而更清楚，两视图也才一致。

# 水的两档不透明度（V1.24 №11）。**这是「水下结构有多深」的唯一杠杆**，不是随手调的：
#   水半透明盖在 `c` 上，水下「空气 vs 结构」的差别 = (1-α)·(air − c)。
#   α=0.88 → 结构只剩 12% 权重，ΔE76 1.3–2.7（水下一片平，所以当初才会误以为要压暗 `c`）；
#   α=0.62 → 38% 权重，ΔE76 4.3–8.2（结构块在水下能看出形状），水本身只从 `#5489D3` 变 `#5E89C5`。
# 房间卡 `drawRoom` 的 `paint(..., alpha)` 必须跟这两个数**完全一致**（同一个房间两个视图）。
WATER_OPACITY = 0.62
BAND_OPACITY = 0.32        # 涨落带淡一档；原比例 0.45/0.88 ≈ 51%，这里 0.32/0.62 ≈ 52%

# 叠放顺序（下 → 上）；连线单独在最底，门点在最上。
# **面在前、实体在后**：`c`（可攀爬背景）/`s`（斜面）是面，`b`/`p`/`x`/`d`/`k` 是实体，
# 实体必须压在面上面，否则细杆子会被背景块吞掉（与 `thumbnail.OVER_PRIORITY` 同一个道理）。
# ⚠️ `c` 虽然还留在这里（外部若按元组遍历能拿到它），但**实际不参与这个循环**：
# V1.24 №1 起它在水之前单独画（见 `build_svg` 的 ①②③ 三段），否则结构色会把水切断。
# V1.24 №5：`p`（白管）挪到 `b`/`B` **之前** —— 杆子是玩家真正抓的那根，得压在白管上面，
# 否则拐角处杆子被管道截断一截，看着像"没接上"。
DRAW_ORDER = ("c", "s", "p", "b", "B", "x", "d", "k")

# 轴对齐矩形的 path 走这条 CSS：关掉抗锯齿，消掉子路径共边时透下层色的细缝。
# 2026-11-21：放大十几倍后实心块里每块一条亮横线，就是共边抗锯齿造成的。
# **只给矩形用，绝不能挂到 `<svg>` 上**——曲线需要抗锯齿，挂了就变锯齿。
RECT_CSS = ".regmap-svg .rc{shape-rendering:crispEdges}"


def _wire_css(wire):
    """（已停用）管道/杆子的线宽 CSS。留着是因为旧版页面可能还引用 `--rg-wire`。"""
    return (".regmap-svg .wl{fill:none;stroke-linecap:round;stroke-linejoin:round;"
            "stroke-width:var(--rg-wire,%.2f)}" % wire)

# 杆子/管道走「格内缩窄矩形」（2026-11-21 夜 A 方案）：按整格填会把 1 格宽的杆子
# 画粗 3–4 倍（游戏里只有约 1/4 格）；缩到 1/3 格既能保持纯色直角，又不膨胀。
BAR_KINDS = ("b", "B", "p")


def _merge_blocks(segs):
    """[(row, x0, x1), …] → [(r0, r1, x0, x1), …]，按 x 范围做纵向合并。

    **不能只跟"上一块"比**：游程是行优先的（同一行的多个游程挨着排），
    一行里有几根杆子时，上一行同 x 的那块早就被同行的其它游程顶掉了，永远合不上。
    2026-11-21 踩过：杆子按行切成 1×1 块，改画线之后整排变成点状虚线。

    同一 `(x0, x1)` 的游程按 y 递增出现（行优先保证），所以用一张 `(x0,x1) → 当前块`
    的表就能把整列接起来。岩壁那种一行多段的形状也因此能正确合并。
    """
    open_: "dict[tuple[int, int], list[int]]" = {}
    done = []
    for (ry, x0, x1) in segs:
        if x1 <= x0:
            continue
        cur = open_.get((x0, x1))
        if cur is not None:
            if cur[1] == ry:                 # 紧挨着上一行 → 继续往下接
                cur[1] = ry + 1
                continue
            done.append((cur[0], cur[1], x0, x1))   # 断了，收掉旧块
        open_[(x0, x1)] = [ry, ry + 1]
    for (x0, x1), cur in open_.items():
        done.append((cur[0], cur[1], x0, x1))
    done.sort(key=lambda b: (b[0], b[2]))    # 输出顺序稳定，便于逐版对比
    return done


def _runs_path(segs, cw, ch, ox, oy):
    """[(row, x0, x1), …] → path 的 d 串（矩形，给实心/面类覆盖物用）。

    **先量化绝对边界、再相减求宽高**。直接量化 `(x1-x0)*cw` 这类长度时，
    相邻两块各自四舍五入能差 0.1 单位——缩略下看不出来，放大到 40 倍就是一条
    贯穿整行的横缝（露底色，2026-11-21 主人报的"空气里有虚线"就是这个）。
    改成两边都从同一个表达式取整，接缝字符串逐字相同，缝就没了。
    """
    out = []
    for (r0, r1, x0, x1) in _merge_blocks(segs):
        ax = "%.1f" % (ox + x0 * cw)
        ay = "%.1f" % (oy + r0 * ch)
        bx = "%.1f" % (ox + x1 * cw)
        by = "%.1f" % (oy + r1 * ch)
        w = "%.1f" % (float(bx) - float(ax))
        h = "%.1f" % (float(by) - float(ay))
        out.append("M%s %sh%sv%sh-%sz" % (ax, ay, w, h, w))
    return "".join(out)


def _bar_blocks(segs, cw, ch, ox, oy, scale=1.0):
    """旧的"按块主方向"画法，只留给**管道**用（见 `_bar_path` 里那段说明）。"""
    tw3 = cw * scale / 3.0
    th3 = ch * scale / 3.0
    out = []
    for (r0, r1, x0, x1) in _merge_blocks(segs):
        w = (x1 - x0) * cw
        h = (r1 - r0) * ch
        if w >= h * 1.2:                                    # 横条
            ax, ay, ww, hh = ox + x0 * cw, oy + (r0 + r1) * 0.5 * ch - th3 * 0.5, w, th3
        elif h >= w * 1.2:                                  # 竖条
            ax, ay = ox + (x0 + x1) * 0.5 * cw - tw3 * 0.5, oy + r0 * ch
            ww, hh = tw3, h
        else:                                               # 近方 → 中心 1/3 方块
            ax = ox + (x0 + x1) * 0.5 * cw - tw3 * 0.5
            ay = oy + (r0 + r1) * 0.5 * ch - th3 * 0.5
            ww, hh = tw3, th3
        out.append(_rect_d(ax, ay, ww, hh))
    return "".join(out)


def _bar_grid(segs):
    """`[(row, x0, x1), …]` → `(grid, w, h)`，`grid[y][x] = 1` 表示这一格有杆/管。

    用**位图**而不是 `set[(x, y)]`：MS 有 142 间房、1.4 万个杆管格，元组集合的
    建集合 + 排序在 2.9 s 的基线上一口气推到 13.9 s（实测），位图是纯数组扫描。
    """
    w = h = 0
    for seg in segs:
        ry, x0, x1 = int(seg[0]), int(seg[1]), int(seg[2])
        if x1 <= x0 or ry < 0:
            continue
        w = max(w, x1)
        h = max(h, ry + 1)
    if w <= 0 or h <= 0:
        return [], 0, 0
    grid = [bytearray(w) for _ in range(h)]
    for seg in segs:
        ry, x0, x1 = int(seg[0]), int(seg[1]), int(seg[2])
        if x1 <= x0 or not (0 <= ry < h):
            continue
        row = grid[ry]
        for x in range(max(0, x0), min(w, x1)):
            row[x] = 1
    return grid, w, h


def _copy_groups(disp, src):
    """显示格 → 源格 的「复制分组」：`[(disp_起, disp_止), …]`（止不含）。

    口径与 `thumbnail.to_over_rows` 的 `ya = (i * src) // disp` **逐字一致**——
    两边一旦不一致，折回去的位置就会整体错半格。

    · `disp <= src`（默认层 density=2，显示比源粗）：每个显示格自成一组，等于恒等；
    · `disp > src`（高清层 density=4）：连续几个显示格落在同一个源格上，就是这么来的
      **假厚度**（1 格厚的管子在 45 行里占 2 行）。
    """
    out = []
    i = 0
    while i < disp:
        s = (i * src) // disp
        j = i + 1
        while j < disp and (j * src) // disp == s:
            j += 1
        out.append((i, j))
        i = j
    return out


def _collapse(grid, w, h, gx, gy):
    """按复制分组把显示位图折回**源格粒度**（组内取或）。

    折完再判方向，才不会把"同一根源格被复制成两行"当成"这里有个竖向分叉"。
    """
    nw, nh = len(gx), len(gy)
    out = [bytearray(nw) for _ in range(nh)]
    for ny, (y0, y1) in enumerate(gy):
        dst = out[ny]
        for nx, (x0, x1) in enumerate(gx):
            hit = 0
            for y in range(y0, min(y1, h)):
                row = grid[y]
                for x in range(x0, min(x1, w)):
                    if row[x]:
                        hit = 1
                        break
                if hit:
                    break
            dst[nx] = hit
    return out, nw, nh


def _orient(grid, w, h, vertical):
    """标记「属于长度 ≥2 的竖向/横向段」的格子。

    绘制那侧的极大段判定与这里**逐字一致**（同一套 `while` 扫描），否则"这一格是
    横条成员还是竖条成员"会对不上，端点缩进就会缩错地方。
    """
    flag = [bytearray(w) for _ in range(h)]
    if vertical:
        for x in range(w):
            y = 0
            while y < h:
                if not grid[y][x]:
                    y += 1
                    continue
                y0 = y
                while y < h and grid[y][x]:
                    y += 1
                if y - y0 >= 2:
                    for yy in range(y0, y):
                        flag[yy][x] = 1
    else:
        for y in range(h):
            row = grid[y]
            x = 0
            while x < w:
                if not row[x]:
                    x += 1
                    continue
                x0 = x
                while x < w and row[x]:
                    x += 1
                if x - x0 >= 2:
                    for xx in range(x0, x):
                        flag[y][xx] = 1
    return flag


def _bar_path(segs, cw, ch, ox, oy, kind="b", scale=1.0, cells=None):
    """杆子/管道 → **格内缩窄的纯色矩形**（宽/高取 1/3 格，直角，不描边）。

    五条口径（2026-11-21 三次修订 + 2026-11-24 V1.24 №2/№5）：

    · **A**：按整格铺会把 1 格宽的杆子画粗 3–4 倍（源数据逐格标注，游戏里约 1/4 格），
      所以每条缩到 1/3 格 —— 还是纯色矩形、直角，只是不再铺满整格。
    · **两向段**：把游程展开成格子，**横向极大段与纵向极大段都画**（都以格中心线为准）。
      只画"这一块的主方向"会导致拐角处断开——一格宽的 L 形，竖块只画竖条、横块只画横条，
      转角上那半格是空的，放大看就是"只有横线和竖线、拐不过弯"（主人 2026-11-21 报的现象）。
    · **端点缩进（№2，2026-11-24）**：两向都铺满整格时，拐角格会被横竖各铺一次，并集就是
      "＋"——而且往外多出**两个半格**（那半格并没有数据，是转角格剩下的部分）。
      现在：一段的**端点格**如果同时属于另一方向的段，就只画到**格中心**。
      拐角于是变成真正的 L（两条带在格心相交），直线杆子的端点仍铺到格边（长度不变）。
    · **先折回源格再判方向（`cells`）**：高清层显示格比源格细，一根 1 格厚的横管会被
      复制成 2–3 个显示行；照显示格判两向，就等于在**每一列**都看到一个"上下都有邻居"的
      十字，画出来是"横线上每隔一格一根竖刺"的梯子（主人 2026-11-21 夜报的现象）。
      `cells=(源宽, 源高, 显示宽, 显示高)` 给出来时先 `_collapse` 成源格粒度判方向，
      出矩形时再把坐标摊回显示格（厚度仍是 1/3 **显示**格，看起来还是一根细条）。
    · **不再纵向合并**：以前 `b` 会按 `(x0,x1)` 把整竖列粘成一块，粘完就丢掉"这一列中途
      有过横向分叉"的信息，两向段必须在格级判断。

    孤立格（横竖都只有 1 格）不再一律画中心小方块（№5）：只要四邻里有线格，就朝那个方向
    伸出**半格臂**——单格的杆子才接得上邻居，也不会在"邻居段长度不足 2 被跳过"的地方留缝。

    调用侧把 `b` 与 `B` 的游程**合并**后传进来（两者同色）：一格多 kind 之后，转角常常是
    "一格 b + 一格 B"，拆开各自扫段就谁也连不上谁。
    """
    grid, w, h = _bar_grid(segs)
    if not w:
        return ""
    gx = gy = None
    if cells:
        bw, bh, tw_, th_ = (int(v or 0) for v in cells)
        if bw > 0 and bh > 0 and (tw_ > bw or th_ > bh):
            gx, gy = _copy_groups(tw_, bw), _copy_groups(th_, bh)
            grid, w, h = _collapse(grid, w, h, gx, gy)
    if gx is None:
        gx = [(i, i + 1) for i in range(w)]
        gy = [(i, i + 1) for i in range(h)]
    if kind == "p" and w > 2 and h > 2:
        # 管道是墙内走线，缩略后经常成整片（一间房几十格连一起）。直接两向段会画成网格墙，
        # 退回"按块主方向"又会把多行块压成一条横线（SU_A02 的 3×2 块只画中间那一行，
        # 上下两行整排漏掉）。所以：**先挖掉"内部格"再两向段**——
        # 四邻都有同类邻居的格子不画，大片就只剩外轮廓一圈，细线一格都不受影响。
        for y in range(1, h - 1):
            row, up, dn = grid[y], grid[y - 1], grid[y + 1]
            for x in range(1, w - 1):
                if row[x] and up[x] and dn[x] and row[x - 1] and row[x + 1]:
                    row[x] = 0
    if not w:
        return ""
    tw3 = cw * scale / 3.0
    th3 = ch * scale / 3.0
    out = []
    cov = [bytearray(w) for _ in range(h)]

    # 压缩格 → 显示格的像素区间（恒等分组时就是老公式 `i*cw`，一个字都不差）
    xs = [g[0] * cw for g in gx] + [gx[-1][1] * cw]
    ys = [g[0] * ch for g in gy] + [gy[-1][1] * ch]

    # 「这一格是横条成员 / 竖条成员」——端点缩进靠它判断，绝不靠"四邻都有"（那会把
    # 高清层的假厚度也算进来，正好踩回 V1.17 的梯子坑）。
    vs = _orient(grid, w, h, True)
    hs = _orient(grid, w, h, False)

    # 横向极大段
    for y in range(h):
        row = grid[y]
        x = 0
        while x < w:
            if not row[x]:
                x += 1
                continue
            x0 = x
            while x < w and row[x]:
                x += 1
            if x - x0 < 2:
                continue
            # 端点在竖条上 → 是拐角/丁字，止于格心；否则铺到格边（直线杆保持原长）
            lx = (xs[x0] + xs[x0 + 1]) * 0.5 if vs[y][x0] else xs[x0]
            rx = (xs[x - 1] + xs[x]) * 0.5 if vs[y][x - 1] else xs[x]
            if rx - lx <= 0:
                lx, rx = xs[x0], xs[x]
            ay = oy + (ys[y] + ys[y + 1]) * 0.5 - th3 * 0.5
            out.append(_rect_d(ox + lx, ay, rx - lx, th3))
            c = cov[y]
            for i in range(x0, x):
                c[i] = 1

    # 纵向极大段
    for x in range(w):
        y = 0
        while y < h:
            if not grid[y][x]:
                y += 1
                continue
            y0 = y
            while y < h and grid[y][x]:
                y += 1
            if y - y0 < 2:
                continue
            ty = (ys[y0] + ys[y0 + 1]) * 0.5 if hs[y0][x] else ys[y0]
            by = (ys[y - 1] + ys[y]) * 0.5 if hs[y - 1][x] else ys[y]
            if by - ty <= 0:
                ty, by = ys[y0], ys[y]
            ax = ox + (xs[x] + xs[x + 1]) * 0.5 - tw3 * 0.5
            out.append(_rect_d(ax, oy + ty, tw3, by - ty))
            for i in range(y0, y):
                cov[i][x] = 1

    # 孤立格：朝有邻居的方向伸半格臂（四邻全空才画中心方块）
    for y in range(h):
        row, c = grid[y], cov[y]
        for x in range(w):
            if not row[x] or c[x]:
                continue
            cx0, cx1 = xs[x], xs[x + 1]
            cy0, cy1 = ys[y], ys[y + 1]
            mx, my = (cx0 + cx1) * 0.5, (cy0 + cy1) * 0.5
            arm = False
            if x > 0 and row[x - 1]:
                out.append(_rect_d(ox + cx0, oy + my - th3 * 0.5, mx - cx0, th3))
                arm = True
            if x < w - 1 and row[x + 1]:
                out.append(_rect_d(ox + mx, oy + my - th3 * 0.5, cx1 - mx, th3))
                arm = True
            if y > 0 and grid[y - 1][x]:
                out.append(_rect_d(ox + mx - tw3 * 0.5, oy + cy0, tw3, my - cy0))
                arm = True
            if y < h - 1 and grid[y + 1][x]:
                out.append(_rect_d(ox + mx - tw3 * 0.5, oy + my, tw3, cy1 - my))
                arm = True
            if not arm:
                out.append(_rect_d(ox + mx - tw3 * 0.5, oy + my - th3 * 0.5, tw3, th3))
    return "".join(out)


def _rect_d(ax, ay, ww, hh):
    """像素矩形 → path 片段；**两端都从同一个绝对表达式取整再相减**，避免 0.1 单位的接缝。

    （接缝的来龙去脉见 `_runs_path` 的注释——同一个坑，别在这里重新踩一次。）
    """
    ax_s, ay_s = "%.1f" % ax, "%.1f" % ay
    ww_s = "%.1f" % (float("%.1f" % (ax + ww)) - float(ax_s))
    hh_s = "%.1f" % (float("%.1f" % (ay + hh)) - float(ay_s))
    if float(ww_s) <= 0 or float(hh_s) <= 0:
        return ""
    return "M%s %sh%sv%sh-%sz" % (ax_s, ay_s, ww_s, hh_s, ww_s)


def _normal(pt, rect):
    """门点相对房间中心的外法线（吸附到轴）。不依赖 x/y 朝向约定。"""
    cx = rect[0] + rect[2] * 0.5
    cy = rect[1] + rect[3] * 0.5
    dx = (pt[0] - cx) / max(1e-9, rect[2] * 0.5)
    dy = (pt[1] - cy) / max(1e-9, rect[3] * 0.5)
    if abs(dx) >= abs(dy):
        return (1.0 if dx >= 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy >= 0 else -1.0)


def _cubic_at(p0, p1, p2, p3, t):
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _split_cubic(p0, p1, p2, p3, t):
    """de Casteljau：在参数 t 处把一条三次贝塞尔切成两段（都是三次贝塞尔，形状不变）。"""
    def lp(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    q0, q1, q2 = lp(p0, p1), lp(p1, p2), lp(p2, p3)
    r0, r1 = lp(q0, q1), lp(q1, q2)
    s = lp(r0, r1)
    return (p0, q0, r0, s), (s, r1, q2, p3)


def _cubic_d(p):
    return "M%.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1f" % (
        p[0][0], p[0][1], p[1][0], p[1][1], p[2][0], p[2][1], p[3][0], p[3][1])


def _hit_room(pt, rects):
    """点在不在任一房间矩形内。`rects` 必须按 x0 升序——碰到 `rx > x` 就停，省一大半。"""
    x, y = pt
    for (rx, ry, rw, rh) in rects:
        if rx > x:
            break
        if x <= rx + rw and ry <= y <= ry + rh:
            return True
    return False


def _ctrl_points(pa, pb, rect_a, rect_b, curve, s):
    """端点 + 两个控制点。`curve` 见 `build_svg` 的文档；`s` 是布局单位→像素的比。"""
    p0 = (float(pa[0]), float(pa[1]))
    p3 = (float(pb[0]), float(pb[1]))
    cfg = curve or {}
    if (cfg.get("mode") or "normal") == "straight":
        return p0, p0, p3, p3
    dist = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    if dist < 1e-6:
        return p0, p0, p3, p3
    k = dist * float(cfg.get("k", 0.42))
    kmin = float(cfg.get("min", 1.5) or 0) * s
    kmax = float(cfg.get("max", 0) or 0) * s
    if kmin > 0:
        k = max(k, kmin)
    if kmax > 0:
        k = min(k, kmax)
    if (cfg.get("mode") or "normal") == "center":
        ca = (rect_a[0] + rect_a[2] * 0.5, rect_a[1] + rect_a[3] * 0.5)
        cb = (rect_b[0] + rect_b[2] * 0.5, rect_b[1] + rect_b[3] * 0.5)
        vx, vy = cb[0] - ca[0], cb[1] - ca[1]
        n = math.hypot(vx, vy) or 1.0
        ux, uy = vx / n, vy / n
        return p0, (p0[0] + ux * k, p0[1] + uy * k), (p3[0] - ux * k, p3[1] - uy * k), p3
    na, nb = _normal(p0, rect_a), _normal(p3, rect_b)
    return p0, (p0[0] + na[0] * k, p0[1] + na[1] * k), (p3[0] + nb[0] * k, p3[1] + nb[1] * k), p3


def link_segments(pa, pb, rect_a, rect_b, rects, curve=None, scale=1.0,
                  inner=0.5, samples=24):
    """一条边 → [(d, 是否室内段), …]。

    `inner` 为 None 或 ≥1 时不切段（整条一段）。切点用采样 + 5 次二分细化，
    切分走 de Casteljau，所以每一段仍是**三次贝塞尔**，不是折线。
    """
    p0, p1, p2, p3 = _ctrl_points(pa, pb, rect_a, rect_b, curve, scale)
    whole = ((p0, p1, p2, p3), False)
    if inner is None or inner >= 1 or not rects or (p0 == p1 and p2 == p3):
        return [(_cubic_d((p0, p1, p2, p3)), False)]

    flags = [_hit_room(_cubic_at(p0, p1, p2, p3, i / samples), rects)
             for i in range(samples + 1)]
    if all(flags) or not any(flags):
        return [(_cubic_d((p0, p1, p2, p3)), flags[0])]

    cuts = []
    for i in range(1, samples + 1):
        if flags[i] == flags[i - 1]:
            continue
        lo, hi = (i - 1) / samples, i / samples
        for _ in range(5):
            mid = (lo + hi) * 0.5
            if _hit_room(_cubic_at(p0, p1, p2, p3, mid), rects) == flags[i - 1]:
                lo = mid
            else:
                hi = mid
        cuts.append(((lo + hi) * 0.5, flags[i]))

    out = []
    cur, t0, flag = (p0, p1, p2, p3), 0.0, flags[0]
    for (t, f) in cuts:
        if t <= t0 + 1e-6 or t >= 1.0 - 1e-6:
            continue
        left, right = _split_cubic(*cur, (t - t0) / (1.0 - t0))
        out.append((_cubic_d(left), flag))
        cur, t0, flag = right, t, f
    out.append((_cubic_d(cur), flag))
    return out or [whole]


def bezier_d(pa, pb, rect_a, rect_b, k_frac=0.42, samples=None):
    """三次贝塞尔：端点 = 两扇门，控制点沿门法线外推（老接口，保留给单独调试）。"""
    p0, p1, p2, p3 = _ctrl_points(pa, pb, rect_a, rect_b, {"k": k_frac}, 0.0)
    if samples:
        return [_cubic_at(p0, p1, p2, p3, i / samples) for i in range(samples + 1)]
    return _cubic_d((p0, p1, p2, p3))


def _eff_box(n):
    """节点在缩略图里实际画出来的源格范围 `(x0, y0, x1, y1)`（含端点）。

    `thumbnail.prepare` 按 `effBox` 裁切，而节点矩形只是把这块**拉伸**到 `w×h`
    （`_disp` 还会非等比压缩）。所以房间格 → 像素必须走这个框，不能直接拿 `w/h` 缩放。
    """
    sw = int(n.get("srcW") or n.get("w") or 1)
    sh = int(n.get("srcH") or n.get("h") or 1)
    box = n.get("effBox")
    if not box:
        return (0, 0, sw - 1, sh - 1)
    bx0, by0, bx1, by1 = [int(v) for v in box]
    return (bx0, by0, max(bx0, bx1), max(by0, by1))


def _scaler(box, px, py, pw, ph):
    """`(X, Y)`：源格 → 像素。X 收格 x（自左），Y 收**屏幕口径 y**（0 = 房间顶，向下增）。"""
    bx0, by0, bx1, by1 = box
    bw = max(1, bx1 - bx0 + 1)
    bh = max(1, by1 - by0 + 1)

    def X(v):
        return px + (v - bx0) / float(bw) * pw

    def Y(v):
        return py + (v - by0) / float(bh) * ph

    return X, Y


def _fx_water(fx, px, py, pw, ph, th, box=None):
    """水 / 酸液：**画在背景结构之上、岩壁之下**（W4-fx；V1.24 №1 调层序）。

    一开始是画在地形之上的（wiki 那样把墙也蒙一层），但地图缩略只有 1–3 px 一格，
    蒙上之后整间房下半截糊成一块蓝、地形形状全丢。改成"水在墙下、底色之上"：
    空的地方是干净的蓝、岩壁仍是清晰的深色，缩略视图里一眼就能分出水位。

    层级链（§2.4b，与房间卡 `drawRoom` 同构）：`air → c → water → solid → s`。
    调用点因此**挪到了 `c` 之后**——原来水先画、`c` 后画，结构色把水切成一截一截。

    洞（`AirPocket` / `WaterCutoff`）用 `evenodd` 挖，不能拿底色盖——
    盖了会把洞里的地形一起抹掉。

    **透明度就是「水下结构有多深」的唯一杠杆**（V1.24 №11）。水是半透明盖在 `c` 上的，
    水下的「空气 vs 结构」差别 = `(1-α)·(air - c)`：
      · α=0.88 → 结构只剩 12% 权重，ΔE76 只有 1.3–2.7（视觉上"水下一片平"）；
      · α=0.62 → 38% 权重，ΔE76 4.3–8.2（结构块在水下能看出形状）。
    再往下压水会发白（叠在空气上从 `#5489D3` 变 `#5E89C5`），所以停在 0.62。
    涨落带（`band`）按同比例调淡：0.45 → 0.32（原比例 ≈51%）。

    `box`（W4）：节点矩形只覆盖有效区时，水位要按有效区换算，否则会整体偏移。
    """
    if not fx:
        return []
    rw, rh = fx.get("w") or 0, fx.get("h") or 0
    water = fx.get("water")
    if not water or rw <= 0 or rh <= 0:
        return []
    X, Y = _scaler(box or (0, 0, rw - 1, rh - 1), px, py, pw, ph)
    key = "acid" if water.get("acid") else "water"
    holes = water.get("holes") or []
    out = []

    def _rect(y0, y1, op):
        d = ["M%.1f %.1fH%.1fV%.1fH%.1fZ" % (px, Y(y0), px + pw, Y(y1), px)]
        for (hx0, hy0, hx1, hy1) in holes:
            d.append("M%.1f %.1fH%.1fV%.1fH%.1fZ"
                     % (X(hx0), Y(hy0), X(hx1), Y(hy1), X(hx0)))
        rule = ';fill-rule:evenodd' if holes else ''
        out.append('<path class="fx-%s" style="fill:var(--rg-%s,%s);fill-opacity:%.2f%s" d="%s"/>'
                   % (key, key, th[key], op, rule, "".join(d)))

    (b0, b1) = water["band"]
    if b1 - b0 > 0.35:                     # 涨落带淡一档（不足 1/3 格看不见，省掉）
        _rect(b0, b1, BAND_OPACITY)
    (f0, f1) = water["full"]
    if f1 - f0 > 0.02:
        _rect(f0, f1, WATER_OPACITY)
    return out


def _fx_above(fx, px, py, pw, ph, th, box=None):
    """沙：画在岩壁**上面**（沙把地面埋住）。

    `box` 同 `_fx_water`。沙面铺满整宽，所以只夹 y、x 直接用地块两端。
    """
    if not fx:
        return []
    rw, rh = fx.get("w") or 0, fx.get("h") or 0
    if rw <= 0 or rh <= 0:
        return []
    X, Y = _scaler(box or (0, 0, rw - 1, rh - 1), px, py, pw, ph)
    out = []

    sand = fx.get("sand")
    if sand and len(sand) >= 2:
        # 沙面折线本身按 x 递增铺满整宽，所以 x 照常换算再夹到节点矩形里；
        # 两端补到底边，闭合成一块面（铺满整宽＝连岩壁一起埋住，与房间卡一致）。
        def _sx(v):
            return max(px, min(px + pw, X(v)))

        d = ["M%.1f %.1f" % (_sx(sand[0][0]), Y(sand[0][1]))]
        for (x, y) in sand[1:]:
            d.append("L%.1f %.1f" % (_sx(x), Y(y)))
        d.append("L%.1f %.1f" % (_sx(sand[-1][0]), py + ph))
        d.append("L%.1f %.1f" % (_sx(sand[0][0]), py + ph))
        d.append("Z")
        out.append('<path class="fx-sand" style="fill:var(--rg-sand,%s);fill-opacity:.92" d="%s"/>'
                   % (th["sand"], "".join(d)))

    # 腐化圆斑 2026-11-21 下线（№5 附加要求）：色项、渲染、房间卡 arc 一起删。
    return out


def _anno_tint(n, px, py, pw, ph, opts):
    """一间房的**子区域淡色底**（只在不走提取色时才有：`use_region` 为真时会被 `tint=""` 抹掉）。

    №2 之后这里不再有图标：房间类型 / 物件 / 业力门三类标注连同 `anno.ICONS` 一起删了。
    子区域名的定位在 `build_svg` 里按包围盒算，不走这个函数。
    """
    a = n.get("anno") or {}
    if not (a.get("sc") and opts.get("sub")):
        return ""
    return ('<rect class="an-sub" x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
            'style="fill:%s;fill-opacity:%.2f"/>'
            % (px, py, pw, ph, a["sc"], SUB_ALPHA))


def build_svg(layout, width=2400, pad=14, colors=None, labels=False, frames=False,
              link_width=None, door=True, css=True, wire=None, seen_frames=True,
              curve=None, link_inner=None, bar_scale=1.0, anno=None):
    """返回 {svg, w, h, bytes, rooms, links, scale}。

    `layout` 就是 `adapter.build()` 的结果（含 `nodes[].runs / runsAir / over`）。
    `labels` 只为调试：房间名画在左上角，正式图不要。

    `curve`（S4）是连线参数，全局一套：
    `{"mode": "normal"|"center"|"straight", "k": 0.42, "min": 1.5, "max": 0}`
    —— `k` 是控制点外推 = 弦长 × k，`min`/`max` 是外推长度的上下限（布局单位，0 = 不限）。
    `link_inner`：曲线落在房间内那一段的不透明度（0.5 = 半透明；0 ≈ 看不见；≥1 = 不分段）。
    `bar_scale`：杆子/管道粗细倍数（1 = 1/3 格）。
    `anno`（W4）：标注开关，键见 `ANNO_DEFAULTS`——`sub` 子区域淡色、
    `kind` 房间类型图标、`marks` 物件、`gates` 业力门徽标、`labels` 子区域名。
    传 `None` 或全 `0` 时一个标注元素也不出。
    `wire` 只为旧调用方兼容，已不参与渲染。
    """
    th = dict(PALETTE)
    th.update(colors or {})
    # ---- 区域提取色（V1.15 №0/№4）----
    # `layout["colors"]` 是 `colors.for_region()` 的结果：主体一组 + 每个子区域一组。
    # 规则：`colors` 参数（面板/命令行）里**显式给了 `air`** 就整张图用那个值（覆盖），
    # 否则按房间所在子区域下发，一个子区域一套 `--rg-air` / `--rg-c`。
    rc = layout.get("colors") or {}
    rgroups = {str(g.get("sub") or ""): g for g in (rc.get("groups") or [])}
    use_region = bool(rgroups) and not (colors and "air" in colors)
    if use_region:
        head = rgroups.get("") or next(iter(rgroups.values()))
        th["air"] = head.get("air") or th["air"]
        th["c"] = head.get("struct") or th["c"]
    ao = dict(ANNO_DEFAULTS)
    if isinstance(anno, dict):
        for k in ao:
            if k in anno:
                ao[k] = int(bool(anno[k]))
    elif anno is False:
        ao = {k: 0 for k in ao}
    anno_on = any(ao.values())
    nodes = layout["nodes"]
    edges = layout["edges"]
    if not nodes:
        raise ValueError("空布局")

    x0 = min(n["x"] for n in nodes)
    y0 = min(n["y"] for n in nodes)
    x1 = max(n["x"] + n["w"] for n in nodes)
    y1 = max(n["y"] + n["h"] for n in nodes)
    s = (width - pad * 2) / max(1e-9, (x1 - x0))
    w = int(round(width))
    h = int(round((y1 - y0) * s + pad * 2))

    def mx(v):
        return pad + (v - x0) * s

    def my(v):
        return pad + (v - y0) * s

    rects = {n["name"].upper(): (n["x"], n["y"], n["w"], n["h"]) for n in nodes}
    node_by = {n["name"].upper(): n for n in nodes}

    def _e_px(name, cell):
        """门端 E（管道口格）→ 像素中心；没有数据/坐标越界就 None（调用方退回 `pa/pb`）。

        **必须走 `_scaler(_eff_box(n))`**：房间矩形只覆盖有效区、还被非等比拉伸过，
        直接按 `w/h` 缩放会偏半格到几格（缩略图是按 effBox 裁切后拉伸的）。
        """
        n = node_by.get(str(name).upper())
        if not n or not cell:
            return None
        a, b = mx(n["x"]), my(n["y"])
        try:
            cx, cy = float(cell[0]), float(cell[1])
        except (TypeError, ValueError, IndexError):
            return None
        box = _eff_box(n)
        bx0, by0, bx1, by1 = box
        # 格必须落在有效区里：越界说明这份缓存的 effBox 与数据不是同一代，别硬画
        if not (bx0 - 0.5 <= cx <= bx1 + 1.5 and by0 - 0.5 <= cy <= by1 + 1.5):
            return None
        X, Y = _scaler(box, a, b, n["w"] * s, n["h"] * s)
        return (X(cx + 0.5), Y(cy + 0.5))
    lw = link_width if link_width else max(1.2, s * 0.09)
    # `wire` 只留给旧调用方兼容（现在杆子走 `_bar_path`，宽高直接按格算，不再有 stroke-width）
    wire = float(wire) if wire else s / 3.0

    out = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'viewBox="0 0 %d %d" '
           'width="100%%" height="100%%" preserveAspectRatio="xMidYMid meet" '
           'class="regmap-svg" data-w="%d" data-h="%d">' % (w, h, w, h)]
    if css:
        # 颜色一律走 CSS 变量 `--rg-*`，默认值写在 var() 的兜底里：
        #   · 页面改色 = 在容器上 setProperty，不用重新算/重新传 SVG（0.4–1.4 MB 不是小数）；
        #   · 单独打开这个 .svg 文件 = 没有变量，落到兜底色，照样能看。
        out.append(
            "<style>"
            ".regmap-svg{background:var(--rg-sheet,%s);font:10px/1.2 system-ui,sans-serif}"
            ".regmap-svg .ln{fill:none;stroke:var(--rg-link,%s);stroke-width:%.2f;"
            "stroke-linecap:round}"
            ".regmap-svg .ln.warn{stroke:var(--rg-warn,%s);stroke-dasharray:6 4}"
            # 室内段（S4）：只有落进房间里的那一截用这个不透明度，兜底值可被行内 style 覆盖
            ".regmap-svg .ln.in{stroke-opacity:.5}"
            ".regmap-svg .hit{fill:transparent;stroke:none}"
            ".regmap-svg .rm:hover .hit{stroke:var(--rg-door,%s);stroke-width:1.2;"
            "stroke-opacity:.55}"
            ".regmap-svg .rb{fill:none;stroke:var(--rg-door,%s);stroke-width:1;stroke-opacity:.35}"
            # 已探索框（S3）：常态 display:none，前端给 `<g class="rm">` 加 `seen` 才显示。
            # `non-scaling-stroke` 保证放大 20 倍时框线还是 1.4 px，不跟着房间一起变粗。
            # 探索框：色卡给的 `#FFF700` 很亮，整片已探索区会被框成一张黄网，
            # 所以呈现上压到 0.5 不透明度、1.2 px（**色卡值不变**，只降强度）。
            ".regmap-svg .fr{display:none;fill:none;stroke:var(--rg-seen,%s);stroke-width:1.2;"
            "stroke-opacity:.5;vector-effect:non-scaling-stroke}"
            ".regmap-svg .rm.seen .fr{display:block}"
            # 大门（V1.24）：虚线框。颜色跟着「门点」走（`--rg-door`），不新开一个面板色，
            # 这样换配色方案时门框与门点始终是一套。
            ".regmap-svg .rm.gate .gt{fill:none;stroke:var(--rg-door,%s);stroke-width:1.3;"
            "stroke-dasharray:3 2;stroke-opacity:.9;vector-effect:non-scaling-stroke}"
            ".regmap-svg .lb{fill:#93a4ad;paint-order:stroke;stroke:var(--rg-sheet,%s);"
            "stroke-width:2.5px}"
            # 标注（W4 / №2）：只剩子区域淡色底与子区域名。图标那套 `.an-p`/`.an-i`
            # 随图标一起删了——没有 `<use>` 也就没有底板要垫。
            ".regmap-svg .an-sub{stroke:none}"
            ".regmap-svg .an-lb{fill:var(--rg-anno,%s);fill-opacity:.6;font-size:15px;"
            "paint-order:stroke;stroke:var(--rg-sheet,%s);stroke-width:3px;"
            "stroke-opacity:.6;letter-spacing:.5px}"
            "%s"
            "</style>" % (th["sheet"], th["link"], lw, th["warn"], th["door"],
                          th["door"], th["seen"], th["door"],
                          th["sheet"], th["anno"], th["sheet"], RECT_CSS))

    out.append('<rect x="0" y="0" width="%d" height="%d" style="fill:var(--rg-sheet,%s)"/>'
               % (w, h, th["sheet"]))

    # ---- 连线：先算，等房间画完再输出 ----
    # S4：线改到房间**上面**。留在底层的话，室内段再怎么调不透明度都看不见——
    # 因为整段被房间矩形盖住了。现在室内段压在地形上、按 `link_inner` 半透明，
    # 室外段仍是实线，两头都看得见。
    # 像素坐标的房间矩形（切段判定与曲线控制点都要用像素，不能拿布局单位混）
    rect_px = {n["name"].upper(): (mx(n["x"]), my(n["y"]), n["w"] * s, n["h"] * s)
               for n in nodes}
    rect_list = sorted(rect_px.values(), key=lambda r: r[0])
    inner = 0.5 if link_inner is None else float(link_inner)
    link_parts = []
    n_links = 0
    # 门端的两处落点：门点与连线**共用**同一对像素（V1.25 №15），否则线头会留在框上、
    # 与移到管道口的门点脱开 1–5 格。没有 E 的一端仍用 `pa/pb`（框边界），与改前一致。
    ends_px = [(_e_px(e["a"], e.get("e_a")) or (mx(e["pa"][0]), my(e["pa"][1])),
                _e_px(e["b"], e.get("e_b")) or (mx(e["pb"][0]), my(e["pb"][1])))
               for e in edges]
    for e, (pa_px, pb_px) in zip(edges, ends_px):
        ra, rb = rect_px.get(e["a"].upper()), rect_px.get(e["b"].upper())
        if not ra or not rb:
            continue
        segs = link_segments(pa_px, pb_px, ra, rb, rect_list, curve, s, inner)
        warn = e.get("conflict") or e.get("route") == "unresolved"
        for (d, is_in) in segs:
            cls = "ln" + (" warn" if warn else "") + (" in" if is_in else "")
            op = ' style="stroke-opacity:%.2f"' % inner if is_in else ""
            link_parts.append('<path class="%s"%s d="%s"/>' % (cls, op, d))
        n_links += 1

    # ---- 房间 ----
    sub_boxes = {}           # 子区域名 → 该子区域所有房间的像素矩形（算标签位置用）
    out.append('<g class="rooms">')
    for n in nodes:
        px, py = mx(n["x"]), my(n["y"])
        pw, ph = n["w"] * s, n["h"] * s
        cw = pw / max(1, n["thumbW"])
        ch = ph / max(1, n["thumbH"])
        name = n["name"]
        gate = bool(n.get("gate"))
        cls = "rm" + (" iso" if n.get("isolated") else "") + (" gate" if gate else "")
        # 底色按**这间房所在的子区域**下发：CSS 变量写在 `<g>` 的行内 style 上，
        # 下面的 `fill:var(--rg-air,…)` / `var(--rg-c,var(--rg-cg,…))` 自然继承，不用包层。
        # 取不到分组就用主体那组（`""`）；都没有就不写，落到 CSS 兜底。
        vs = ""
        dsub = ""
        if use_region:
            g = rgroups.get(str(n.get("sub") or "")) or rgroups.get("")
            if g:
                vs = ' style="--rg-air:%s;--rg-cg:%s"' % (
                    g.get("air"), g.get("struct"))
                # `data-sub` = **生效的分组名**（找不到子区域时是 `""`，即主体）。
                # 前端「背景取色」改色时按它直接改这些 `<g>` 的 CSS 变量（V1.24）：
                # 不重取 SVG、不重算布局，改一个子区域的色只动它自己那几间房。
                dsub = ' data-sub="%s"' % _attr(g.get("sub") or "")
        out.append('<g class="%s" data-room="%s"%s%s><title>%s</title>'
                   % (cls, _attr(name), dsub, vs,
                      _text(name + (" · 大门" if gate else ""))))
        # 命中区：整块房间矩形。悬停/双击都认它（前端按 [data-room] 找）。
        # 顺便当**可通行底色**：每个缩略格非"实心"即"空气"，所以「矩形铺空气色 +
        # 实心游程压上去」与「逐行画空气游程」像素等价，但少一整层 path（省四到五成字节）。
        out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                   'style="fill:var(--rg-air,%s)"/>'
                   % (px, py, pw, ph, th["air"]))
        # 标注的淡色底（W4）：比水还靠下——它只是"这块属于哪个子区域"，不能盖地形
        box = _eff_box(n) if (anno_on or n.get("fx")) else None
        tint = _anno_tint(n, px, py, pw, ph, ao) if anno_on else ""
        if use_region:
            # №4 定案：子区域色**直接当可通行底色**，不再叠一层 0.18 的淡色
            # （叠上去会变成"提取色 × 淡色"两重混合，颜色就不准了）。
            # 但子区域名仍要能定位，所以这里补记包围盒。
            if ao.get("labels") and ao.get("sub") and n.get("anno", {}).get("sub"):
                sub_boxes.setdefault(n["anno"]["sub"], []).append((px, py, pw, ph))
            tint = ""
        if tint:
            out.append(tint)
        # 子区域名要按**所有**带子区域色的房间算位置（№2 之后这里不再有图标可挂）
        if tint and ao.get("labels"):
            sub_boxes.setdefault(n["anno"]["sub"], []).append((px, py, pw, ph))
        out.append('<rect class="hit" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                   % (px, py, pw, ph))
        # ---- ① 背景结构（c）：**必须画在水之前**（V1.24 №1）----
        # 房间卡那边（`drawRoom`）的顺序是「空气 → 斜面对… → 可攀爬背景墙 → 水」，
        # 水是**盖在背景结构上**的；地图这边原来把 `c` 留在 `DRAW_ORDER` 里（水之后），
        # 于是水被结构色切成一截一截。把 `c` 提上来、水紧跟其后，两个视图就同构了。
        # 层级链（§2.4b）：air → c → water → solid → s。
        segs_c = (n.get("over") or {}).get("c") or []
        if segs_c:
            # 背景结构有**两级**：`--rg-c` 是"用户/全局"意图，`--rg-cg` 是"这间房所在
            # 子区域"的派生值。CSS 变量不能"取消"，所以外面那层优先、里面兜底：
            # 用户没改 → `--rg-c` 不存在 → 落到分组值；用户改了 → 直接盖掉分组值。
            out.append('<g class="rc"><path style="fill:var(--rg-c,var(--rg-cg,%s))" d="%s"/></g>'
                       % (th["c"], _runs_path(segs_c, cw, ch, px, py)))
        # ---- ② 水/酸：压在 空气 / 背景结构 之上、岩壁之下（见 `_fx_water`）----
        water_parts = _fx_water(n.get("fx"), px, py, pw, ph, th, box)
        if water_parts:
            out.extend(water_parts)
        # ---- ③ 实心 / 沙 / 斜面 / 杆管 ----
        # 按 `DRAW_ORDER` 保序，但要分两种画法：
        #   · 面（solid / c / s / x / d / k）→ 矩形 path，进 `.rc` 组吃 `crispEdges`；
        #   · 线（p / b）→ 等宽 stroke，进 `.wl`；`crispEdges` 只该作用于矩形，
        #     描边线沾上会让线宽按像素对齐、又变回"时粗时细"。
        parts = []
        buf = []

        def flush_rc():
            if buf:
                parts.append('<g class="rc">' + "".join(buf) + "</g>")
                del buf[:]

        d_solid = _runs_path(n.get("runs") or [], cw, ch, px, py)
        if d_solid:
            buf.append('<path style="fill:var(--rg-solid,%s)" d="%s"/>'
                       % (th["solid"], d_solid))
        # 沙 / 腐化（W4-fx）：压在岩壁之上、杆子与入口之下
        flush_rc()
        fx_parts = _fx_above(n.get("fx"), px, py, pw, ph, th, box)
        if fx_parts:
            parts.extend(fx_parts)
        for kind in DRAW_ORDER:
            if kind == "c":
                continue                       # 已在 ① 画过（它必须在水之前）
            segs = (n.get("over") or {}).get(kind) or []
            if not segs:
                continue
            if kind in BAR_KINDS:
                if kind == "B":
                    continue                   # 与 `b` 合并绘制（同色，且合并后拐角才连得上）
                flush_rc()                     # 收掉上面的面，细条才不会被半截组盖住
                if kind == "b":
                    # 竖杆 + 横杆并成一张网：一格多 kind 之后，转角常是"一格 b + 一格 B"，
                    # 拆开各自扫段就谁也连不上谁（V1.24 №5 的关键一步）。
                    segs = list(segs) + list((n.get("over") or {}).get("B") or [])
                # `cells` 只给杆/管：高清层显示格比源格细，1 格厚的杆会被复制成 2–3 个
                # 显示行，不折回源格就会画成"每格一根竖刺"（见 `_bar_path`）。
                cells = None
                if n.get("overW") and n.get("overH"):
                    cells = (n["overW"], n["overH"], n["thumbW"], n["thumbH"])
                d = _bar_path(segs, cw, ch, px, py, kind, bar_scale, cells)
                if d:
                    ck = "b" if kind == "B" else kind   # 横杆与竖杆同色，配色面板只认 --rg-b
                    parts.append('<path style="fill:var(--rg-%s,%s)" d="%s"/>'
                                 % (ck, th[ck], d))
            else:
                buf.append('<path style="fill:var(--rg-%s,%s)" d="%s"/>'
                           % (kind, th[kind], _runs_path(segs, cw, ch, px, py)))
        flush_rc()
        if parts:
            out.append("".join(parts))
        # 大门（V1.24）：虚线圈一下。门房也是真房间（有地形、能开卡），但尺寸小、
        # 又贴在区域边界，不圈出来会被当成"图上掉了一格"。
        if gate:
            out.append('<rect class="gt" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                       % (px, py, pw, ph))
        # 已探索框：常驻但默认隐藏（CSS `display:none`），前端给房间加 `seen` 类才显形。
        # 画在内容之后，悬停的 `.hit` 描边仍压在它上面（hover 更亮更粗）。
        if seen_frames:
            out.append('<rect class="fr" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                       % (px, py, pw, ph))
        if frames:
            out.append('<rect class="rb" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                       % (px, py, pw, ph))
        if labels:
            out.append('<text class="lb" x="%.2f" y="%.2f">%s</text>'
                       % (px + 2, py + 9, _text(name)))
        out.append("</g>")
    out.append("</g>")

    # ---- 连线（S4：压在房间上面；室内段已经切出来并调过半透明）----
    if link_parts:
        out.append('<g class="links">' + "".join(link_parts) + "</g>")

    # ---- 标注（W4）：压在连线与房间之上，别被任何东西盖住 ----
    # №2 之后这里只剩「子区域名」一层；图标三类已删，`<g class="annos">` 只在有名字时出现。
    if ao.get("labels") and sub_boxes:
        out.append('<g class="annos">')
        for sub, boxes in sorted(sub_boxes.items()):
            # 位置取**房间中心的平均**而不是包围盒中心：子区域常常是 L 形或分成两片，
            # 包围盒中心会落在两片之间的空白里（MS 实测「Bitter Aerie」标在墙上）。
            cx = sum(b[0] + b[2] * 0.5 for b in boxes) / len(boxes)
            cy = sum(b[1] + b[3] * 0.5 for b in boxes) / len(boxes)
            # 夹在画布里：子区域常常贴着图的边缘（MS 的 Struts 在左上角），
            # 不夹的话标签有一半会被裁掉。宽度按字数估（15px 中文约 15 px 一个）。
            half = len(str(sub)) * 7.5
            cx = max(half + 4, min(w - half - 4, cx))
            cy = max(14.0, min(h - 6.0, cy))
            out.append('<text class="an-lb" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                       % (cx, cy, _text(sub)))
        out.append("</g>")

    # ---- 门点（在最上，正好压住缝）----
    if door:
        out.append('<g class="doors" style="fill:var(--rg-door,%s)">' % th["door"])
        dw = max(1.6, s * 0.45)
        for (pa_px, pb_px) in ends_px:
            for (x, y) in (pa_px, pb_px):
                out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                           % (x - dw * 0.5, y - dw * 0.5, dw, dw))
        out.append("</g>")

    out.append("</svg>")
    text = "".join(out)
    n_gate = sum(1 for n in nodes if n.get("gate"))
    return {"svg": text, "w": w, "h": h, "bytes": len(text.encode("utf-8")),
            "rooms": len(nodes), "gates": n_gate, "links": n_links, "annos": len(sub_boxes),
            # `region` = 是否按子区域给每间房下发了 `--rg-air/--rg-cg`（前端改色的前提）。
            # 关掉时（色卡显式给了 `air`）房间上不会有内联变量，前端就别去改它们。
            "region": bool(use_region),
            "scale": s}


def _attr(v):
    return (str(v).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _text(v):
    return _attr(v)


def build_html(layout, title="区域地图", **kw):
    """把 SVG 包成一张可单独打开的 HTML（预览、验收、给设计看都用它）。"""
    r = build_svg(layout, **kw)
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>%s</title><style>html,body{margin:0;height:100%%;background:#05070a}"
            "#wrap{width:100%%;height:100%%;display:flex;align-items:center;"
            "justify-content:center}</style></head><body><div id=\"wrap\">%s</div>"
            "</body></html>" % (_attr(title), r["svg"])), r
