"""地形网格 → 房间缩略图。

每个显示格覆盖源图的一块，按「实心占比 ≥ threshold」判实心。阈值取 0.34 而不是
0.5，是因为压缩比大时（1418 格的房间压到 230 格，一格管 6×6 源格）1 格厚的墙只
占 1/6 面积，用 0.5 会把墙整条抹掉——那正是房间轮廓的来源。
"""
from __future__ import annotations


def grid_size(node, min_px=3, density=2):
    """显示尺寸 → 缩略图格数。

    `density=2` 表示「每显示单位铺 2 格」：房间在图上只有 20 单位宽时，1 单位约 3 px，
    铺 2 格就是每格 1.5 px——比「1 单位 1 格」细一倍，墙线才不至糊成一团。
    """
    tw = max(min_px, int(round(node["w"] * density)))
    th = max(min_px, int(round(node["h"] * density)))
    return tw, th


def to_rows(room, tw, th, threshold=0.34, y_flip=False, bbox=None):
    """把房间格缩成 `th` 行 × `tw` 列。

    **行序就是原图行序**（`y_flip=False`，默认）：房间格第 0 行 = 原图最上一行。
    2026-11-20 用实机渲染图逐格比对过：按「图顶 = 文件行 0」摆，亮度与实心格相关
    0.78 / 0.67；反过来只有 0.33 / 0.27。所以**不要再翻**——翻了就是每间房上下镜像。

    `y_flip=True` 只留给「和旧图对照」的场合（`y_render_flip` 那条路）。
    `bbox` = `(x0, y0, x1, y1)`（含端点）时只取这一块源格——房间外框既然按有效区画，
    缩略图也必须按同一个框裁，否则空白边距会被压进图里、地形整体偏移。
    """
    w, h, cells = room.w, room.h, room.cells
    if not cells or len(cells) < w * h:
        return ["0" * tw for _ in range(th)]
    if bbox:
        bx0, by0, bx1, by1 = bbox
        bx0 = max(0, min(w - 1, bx0))
        by0 = max(0, min(h - 1, by0))
        bx1 = max(bx0, min(w - 1, bx1))
        by1 = max(by0, min(h - 1, by1))
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    else:
        bx0 = by0 = 0
        bw, bh = w, h
    rows = []
    for oy in range(th):
        # 缩略图第 0 行是房间顶部；`cells` 的 y 从**底部**数（格 y 朝上），
        # 所以 y_flip 时要按 y 的高端往下走，否则直接顺序对应。
        # th > bh（放大）时天真的写法会把下标顶到 h*w 之外——必须夹住：
        if y_flip:
            ya = max(0, bh - ((oy + 1) * bh) // th)
            yb = min(bh, bh - (oy * bh) // th)
        else:
            ya = (oy * bh) // th
            yb = ((oy + 1) * bh) // th
        if yb <= ya:
            yb = min(bh, ya + 1)
        line = []
        for ox in range(tw):
            x0 = min(bw - 1, ox * bw // tw)
            x1 = min(bw, max(x0 + 1, (ox + 1) * bw // tw))
            solid = 0
            total = 0
            for y in range(ya, yb):
                base = (by0 + y) * w + bx0
                for x in range(x0, x1):
                    if cells[base + x] != "0":
                        solid += 1
                    total += 1
            line.append("1" if total and solid >= total * threshold else "0")
        rows.append("".join(line))
    return rows


def runs(rows, mark="1"):
    """每行合并成 (y, x0, x1) 游程 —— 画线/画 SVG 都用它，比逐格少一个量级。

    `mark` 默认合并实心格（'1'）；传 '0' 就合并**空气格**——游戏内地图是「可通行
    区域亮、岩壁暗」，画空气反而更像地图。
    """
    out = []
    for y, line in enumerate(rows):
        x = 0
        n = len(line)
        while x < n:
            if line[x] != mark:
                x += 1
                continue
            x0 = x
            while x < n and line[x] == mark:
                x += 1
            out.append((y, x0, x))
    return out


# ---- 覆盖层（W1）----------------------------------------------------------
# 地形只有「空/实心」两类，但一间房的性格全在**对象**上：管道从哪走、出口在哪、
# 哪里能爬。这些在原版里是**一格一格的编号**，压进二进制就没了。
# 这里把它们抽成一张独立的稀疏层，作息规则：
#   x 出口(4) > d 巢穴(5) > k 生物通道(9) > p 管道(3) > b 杆子(1/2) > c 可攀爬(6) > s 斜面(2..15)
# 一格挤多个时按上面这条取——**物体先于面**：x/d/k/p/b 是实体，c/s 是面，面让位于实体。
# 2026-11-21 修：原来 c 排在 b 前面，而杆子本来就贴在可攀爬墙面上，同格 `b+c` 极多
# （HI 2081 格、UW 3567 格），杆子被整根吞掉——比纯 b 格（2075）还多，等于一半以上从没画出来。

# 2026-11-21 夜（C）：type 1/2 拆成 `b`（竖杆）/ `B`（横杆）。
# 原来都并成 `b`，`_merge_blocks` 只做纵向合并，横杆会被上下粘成大矩形——
# 4000% 下就是"一根根横梁变成一整片"。拆开后横杆逐行成段、只做横向游程。
OVER_OF = {4: "x", 5: "d", 9: "k", 3: "p", 6: "c", 1: "b", 2: "B"}
OVER_PRIORITY = ("x", "d", "k", "p", "b", "B", "c", "s")
_OVER_RANK = {k: i for i, k in enumerate(OVER_PRIORITY)}

# 送进载荷的类：出口 / 巢穴 / 生物通道 / 管道 / 可攀爬背景 / 竖杆 / 横杆 / 斜面。
# 全部都要画（主人 2026-11-21 明确：杆子和背景也要）。代价是载荷比只画四类时大 2~3 倍，
# 换算见 `build/check_regmap_color.py`：绘图时按这个顺序叠——
#   空气 → 可攀爬背景(c) → 实心墙(solid) → 斜面(s) → 管道/出口/巢穴/生物通道/杆子
MAP_KINDS = ("x", "d", "k", "p", "c", "b", "B", "s")


def over_grid(room):
    """把 `room.objs` 与斜面摊成一格一个字符的覆盖网格（与 `cells` 同一个下标空间）。"""
    w, h, cells = room.w, room.h, room.cells
    grid = ["0"] * (w * h)
    # 先铺斜面：值 2..15 是斜面/局部，0 空气、1 满格实心
    for i in range(min(len(cells), len(grid))):
        c = cells[i]
        if c != "0" and c != "1":
            grid[i] = "s"
    objs = room.objs or {}
    for (x, y), codes in objs.items():
        idx = y * w + x
        if idx < 0 or idx >= len(grid):
            continue
        best = grid[idx]
        for code in codes:
            k = OVER_OF.get(code)
            if k is None:
                continue
            if best == "0" or _OVER_RANK[k] < _OVER_RANK.get(best, 99):
                best = k
        grid[idx] = best
    return grid


def crop_size(room, bbox=None):
    """覆盖层的**源格**尺寸 `(bx0, by0, bw, bh)`——`to_over_rows` 与 `prepare` 共用一套口径。

    为什么要单独拿出来：显示格比源格细时（高清层 density=4，见 `svg._copy_groups`），
    一根 1 格厚的管子会被复制成 2 个显示行，绘图那侧必须知道「源格有几行几列」
    才能把复制出来的假厚度折回去。
    """
    w, h = room.w, room.h
    if bbox:
        bx0, by0, bx1, by1 = bbox
        bx0 = max(0, min(w - 1, bx0))
        by0 = max(0, min(h - 1, by0))
        bx1 = max(bx0, min(w - 1, bx1))
        by1 = max(by0, min(h - 1, by1))
        return bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1
    return 0, 0, w, h


def to_over_rows(room, tw, th, y_flip=False, bbox=None):
    """覆盖层的缩略行。**块映射必须与 `to_rows` 完全一致**（改一处要同时改两处），
    否则覆盖层会和地形错位半格。

    与地形不同，这里不按占比阈值判：覆盖物本来就是一条线，取样块里只要出现就画，
    取块内**优先级最高**的那个字符。
    """
    w, h = room.w, room.h
    grid = over_grid(room)
    bx0, by0, bw, bh = crop_size(room, bbox)
    rows = []
    for oy in range(th):
        if y_flip:
            ya = max(0, bh - ((oy + 1) * bh) // th)
            yb = min(bh, bh - (oy * bh) // th)
        else:
            ya = (oy * bh) // th
            yb = ((oy + 1) * bh) // th
        if yb <= ya:
            yb = min(bh, ya + 1)
        line = []
        for ox in range(tw):
            x0 = min(bw - 1, ox * bw // tw)
            x1 = min(bw, max(x0 + 1, (ox + 1) * bw // tw))
            best = "0"
            for y in range(ya, yb):
                base = (by0 + y) * w + bx0
                for x in range(x0, x1):
                    c = grid[base + x]
                    if c != "0" and (best == "0" or _OVER_RANK.get(c, 99) < _OVER_RANK.get(best, 99)):
                        best = c
            line.append(best)
        rows.append("".join(line))
    return rows


def over_runs(room, tw, th, y_flip=False, bbox=None):
    """→ {"x": [[y,x0,x1],…], "p": [...], …}，只保留 `MAP_KINDS` 里真的出现过的类。"""
    rows = to_over_rows(room, tw, th, y_flip, bbox)
    out = {}
    for kind in MAP_KINDS:
        seg = runs(rows, kind)
        if seg:
            out[kind] = [list(s) for s in seg]
    return out


def prepare(nodes, threshold=0.34, density=2, y_flip=False):
    """给每个 node 补上缩略数据（`runs` 实心 / `runsAir` 空气 / `over` 覆盖层 / `thumbW/H`）。

    `overW/overH` 是覆盖层的**源格**尺寸（裁过 effBox）：高清层显示格比源格细，
    `over` 里同一根源格会被复制成两三行，绘图侧的 `_bar_path` 靠这两个数把假厚度折回去
    ——少了它，1 格厚的横管在 density=4 下会变成「一道横线 + 每格一根竖刺」（2026-11-21 夜）。
    """
    for node in nodes:
        tw, th = grid_size(node, density=density)
        room = node["room"]
        rows = to_rows(room, tw, th, threshold, y_flip, node.get("effBox"))
        node["thumbW"] = tw
        node["thumbH"] = th
        node["runs"] = runs(rows, "1")
        node["runsAir"] = runs(rows, "0")
        node["over"] = over_runs(room, tw, th, y_flip, node.get("effBox"))
        _bx0, _by0, bw, bh = crop_size(room, node.get("effBox"))
        node["overW"] = bw
        node["overH"] = bh
    return nodes
