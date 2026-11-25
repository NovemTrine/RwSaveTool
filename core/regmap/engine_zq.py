"""zq 引擎：四段式排布（对齐 → 力松弛 → 去重叠 → 分量拼装）。

为什么另起一个引擎
------------------
`layout.py`（legacy）是「出口方向约束 → BFS 硬贴合 → 力松弛」，房间位置由**门属于哪条边**
决定；这套在 UW 这类规整区域很好（quad 93），但在门数据杂乱的大区（MS 70、HI 81）会把
整块拉歪。

参考实现 `rainworld_zhiqiong` 走的是另一条路（照算法自己写，不复用其代码）：

1. **对齐**：按度数 BFS 展开，把新框摆到「两扇门重合」的位置，再推开与已放置框的重叠，
   并把被压住的邻居也一并推开（传递）；
2. **力松弛**：沿边把两扇门往一起拉（pull 从大到小），同时重叠相斥（repel 从小到大）；
3. **去重叠**：残余重叠按**最小穿透轴**推，步长每 5000 轮 ×1.1；
4. **分量拼装**：互不相连的几片按包围盒面积从大到小，往已占区域的角上垒。

和 `layout.py` 共用：尺寸换算（有效区 + `scale_exp` + `min_side`）、门位推断
（`doorrule`，2026-11-21 修完上下极性后两侧门位都是准的）、`thumbnail.prepare`。

对外契约与 `layout.build` 一致：`build(rooms, opts) -> {nodes, edges, stats}`，
所以 `core/regmap/__init__.build_rooms` 与所有下游（SVG、导出、审计脚本）不用改。
"""
from __future__ import annotations

import math

from . import config, doorrule
from .direction import OPP
from .model import effective_bbox, effective_size, is_gate

SIDES = ("L", "R", "U", "D")
NORMAL = {"L": (-1.0, 0.0), "R": (1.0, 0.0), "U": (0.0, -1.0), "D": (0.0, 1.0)}


def _disp(w, h, exp, floor):
    return max(floor, float(w) ** exp), max(floor, float(h) ** exp)


class Box(object):
    """一个房间的显示框（布局单位，y 向下）。"""

    __slots__ = ("name", "x", "y", "w", "h", "ends", "room")

    def __init__(self, name, w, h, room=None):
        self.name = name
        self.x = self.y = 0.0
        self.w, self.h = float(w), float(h)
        self.ends = []          # 这条框上的门端：[{to, side, t, other}]
        self.room = room

    @property
    def cx(self):
        return self.x + self.w * 0.5

    @property
    def cy(self):
        return self.y + self.h * 0.5

    @property
    def area(self):
        return self.w * self.h

    def door(self, end):
        """门点在**当前**坐标下的位置。"""
        _side, t = end["side"], end["t"]
        if _side == "L":
            return (self.x, self.y + t * self.h)
        if _side == "R":
            return (self.x + self.w, self.y + t * self.h)
        if _side == "U":
            return (self.x + t * self.w, self.y)
        return (self.x + t * self.w, self.y + self.h)

    def off(self, end):
        """门点相对框原点的偏移。"""
        _side, t = end["side"], end["t"]
        if _side == "L":
            return (0.0, t * self.h)
        if _side == "R":
            return (self.w, t * self.h)
        if _side == "U":
            return (t * self.w, 0.0)
        return (t * self.w, self.h)

    def hit(self, o):
        return not (self.x >= o.x + o.w - 1e-9 or self.x + self.w <= o.x + 1e-9
                    or self.y >= o.y + o.h - 1e-9 or self.y + self.h <= o.y + 1e-9)

    def pen(self, o):
        dx = min(self.x + self.w, o.x + o.w) - max(self.x, o.x)
        dy = min(self.y + self.h, o.y + o.h) - max(self.y, o.y)
        if dx <= 1e-9 or dy <= 1e-9:
            return None
        return dx, dy


# ------------------------------------------------------------------ 网格加速

class Grid(object):
    """均匀网格：把「两两检查」降到「邻域检查」。

    用**下标**存桶、用 generation 去重（`id()` + set 在 7 万次查询下是主要开销）。
    """

    __slots__ = ("cell", "buckets", "stamp", "gen")

    def __init__(self, cell, n):
        self.cell = max(1.0, float(cell))
        self.buckets = {}
        self.stamp = [-1] * n
        self.gen = 0

    def _span(self, a0, a1):
        return int(math.floor(a0 / self.cell)), int(math.floor((a1 - 1e-6) / self.cell))

    def insert(self, i, box):
        ix0, ix1 = self._span(box.x, box.x + box.w)
        iy0, iy1 = self._span(box.y, box.y + box.h)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                self.buckets.setdefault((ix, iy), []).append(i)

    def near(self, i, box):
        """返回与 box 同格或相邻格里可能相交的框下标（去重，不含自己）。"""
        self.gen += 1
        gen = self.gen
        out = []
        ix0, ix1 = self._span(box.x, box.x + box.w)
        iy0, iy1 = self._span(box.y, box.y + box.h)
        for ix in range(ix0 - 1, ix1 + 2):
            for iy in range(iy0 - 1, iy1 + 2):
                bucket = self.buckets.get((ix, iy))
                if not bucket:
                    continue
                for k in bucket:
                    if k == i or self.stamp[k] == gen:
                        continue
                    self.stamp[k] = gen
                    out.append(k)
        return out


def _grid(boxes):
    """格长取中位尺寸：太大等于没分格（一次查询命中几十个），太小则长条框要跨很多格。"""
    dims = sorted(max(b.w, b.h) for b in boxes)
    cell = max(6.0, dims[len(dims) // 2] * 0.75 if dims else 8.0)
    g = Grid(cell, len(boxes))
    for i, b in enumerate(boxes):
        g.insert(i, b)
    return g


# ------------------------------------------------------------------ ① 对齐

def _order_bfs(boxes, pair_area):
    """度数高的先开路，BFS 展开；同层的边按「两端面积和」升序（先摆小房间）。

    `end` 是**从已放置那一侧看出去**的门端：`{box, side, t, mate}`，`mate` 是对面那端。
    """
    # 用**按名字**的 dict 而不是 set：`set` 的迭代顺序随对象地址/字符串 hash 变，
    # 同一个区每跑一次排出来的图都略有不同（SI 实测 68 间全都不一样）。
    # 布局是要反复比对与回归的，必须可重复，所以这里把顺序钉死在名字上。
    todo = {b.name: b for b in boxes}
    seen = set()
    order = []
    while todo:
        start = max(todo.values(), key=lambda b: (len(b.ends), b.area, b.name))
        todo.pop(start.name, None)
        order.append((None, start))
        queue = list(start.ends)
        while queue:
            queue.sort(key=lambda e: pair_area.get(
                tuple(sorted((e["box"].name, e["mate"]["box"].name))), 1e18))
            end = queue.pop(0)
            key = tuple(sorted((end["box"].name, end["mate"]["box"].name)))
            if key in seen:
                continue
            seen.add(key)
            target = end["mate"]["box"]
            if target.name not in todo:
                # 对面已经放好了：换个方向，从对面看回来再试
                rev = end["mate"]
                if rev["box"].name in todo:
                    end, target = rev, rev["box"]
                else:
                    continue
            order.append((end, target))
            todo.pop(target.name, None)
            queue.extend(target.ends)
            queue = [e for e in queue
                     if e["mate"]["box"].name in todo]
    return order


def _push_out(box, others, gap, skip, limit=120):
    """把 box 推到不与 others 相交；被它压住的「已放置」框也一起推（传递一层）。"""
    pool = [o for o in others if id(o) not in skip] + [box]
    me = len(pool) - 1
    grid = _grid(pool)
    for _ in range(limit):
        moved = False
        for k in grid.near(me, box):
            o = pool[k]
            if o is box or id(o) in skip:
                continue
            got = box.pen(o)
            if not got:
                continue
            dx, dy = got
            moved = True
            if dx < dy:
                s = dx + gap
                box.x += s if box.cx >= o.cx else -s
            else:
                s = dy + gap
                box.y += s if box.cy >= o.cy else -s
        if not moved:
            return True
    return False


def align_pass(boxes, pairs, gap, order):
    """① 对齐：把新框摆到「两扇门相距 gap」的位置，再顶开已放置的框。

    ⚠️ `done` **必须是 list，不能是 set**（V1.24 修）：`Box` 没有 `__hash__`，
    集合的迭代顺序按对象 `id()`（内存地址）排，每次重算地址都不同 → `_push_out()`
    顶开「已放置框」的顺序跟着变 → 同一份数据两次布局差 10~80 单位。
    实测（SL 96 间）：set 版连续三次 96/96 间坐标不同；list 版三次**逐位相同**。
    顺序语义没变（还是放置先后），只是把它固定下来。
    """
    done = []
    for (end, box) in order:
        if end is None:
            box.x = box.y = 0.0
            done.append(box)
            continue
        pa = end["box"].door(end)
        n = NORMAL[end["side"]]
        off = box.off(end["mate"])
        box.x = pa[0] + n[0] * gap - off[0]
        box.y = pa[1] + n[1] * gap - off[1]
        _push_out(box, list(done), gap, skip=set())
        done.append(box)
    return


# ------------------------------------------------------------------ ② 力松弛

def force_pass(boxes, pairs, gap, iters, seed=42):
    """② 力松弛：沿边把两扇门往一起拉（pull 由强到弱）+ 重叠相斥（repel 由弱到强）。

    2026-11-21 修过一次发散：原来目标点跟着自己动、又没限幅，链条会越拉越远
    （UW 从 ±300 跑到 ±96000）。现在改成**相对修正**：按方向走 `min(误差, 6)` 的一小步，
    两边各承担一半，单帧位移再夹一道。
    """
    n = len(boxes)
    if n < 2:
        return
    idx = {id(b): k for k, b in enumerate(boxes)}
    avg = sum(b.w + b.h for b in boxes) / (4.0 * n)
    cap = max(2.0, gap * 0.5)
    gcache = {"it": -99, "grid": None}

    def _grid_now(it):
        # 网格每 6 轮重建一次：一轮里位移只有几格，邻居集合几乎不变，重建是纯浪费
        if gcache["grid"] is None or it - gcache["it"] >= 6:
            gcache["grid"] = _grid(boxes)
            gcache["it"] = it
        return gcache["grid"]

    for it in range(iters):
        t = it / float(max(1, iters))
        pull = 0.5 * (math.cos(t * math.pi) + 1.0) * 0.5
        # 相斥只在前半段「不发力」：一上来就推会把刚对好的门又推开
        rep = 0.0 if t < 0.35 else (1.0 - math.cos((t - 0.35) / 0.65 * math.pi)) * 0.5 * (avg / 7.0)
        dx = [0.0] * n
        dy = [0.0] * n
        for (ea, eb) in pairs:
            a, b = ea["box"], eb["box"]
            # 方位弱约束：房间相对位置摆到了门所指的另一侧时，往回拉。
            # W2 原本读的是地图矩形；V1.15 改成读**两端门位**（`_pair_dir`），
            # 理由：地图源已作废，而门位在冲突时也需要一个折中的拉力。权重小，不跟主项抢。
            ms = ea.get("map_side")
            if ms and pull > 0:
                nx, ny = NORMAL[ms]
                proj = (b.cx - a.cx) * nx + (b.cy - a.cy) * ny
                if proj < 0:
                    fix = min(-proj, 12.0) * pull * 0.12
                    ia0, ib0 = idx[id(a)], idx[id(b)]
                    dx[ib0] += nx * fix
                    dy[ib0] += ny * fix
                    dx[ia0] -= nx * fix * 0.5
                    dy[ia0] -= ny * fix * 0.5
            pa, pb = a.door(ea), b.door(eb)
            nrm = NORMAL[ea["side"]]
            ex = (pa[0] + nrm[0] * gap) - pb[0]
            ey = (pa[1] + nrm[1] * gap) - pb[1]
            dist = math.hypot(ex, ey)
            if dist < 1e-9:
                continue
            step = min(dist, 6.0) * pull * 0.5
            ux, uy = ex / dist * step, ey / dist * step
            ia, ib = idx[id(a)], idx[id(b)]
            dx[ib] += ux
            dy[ib] += uy
            dx[ia] -= ux * 0.5
            dy[ia] -= uy * 0.5
        if rep > 1e-9:
            grid = _grid_now(it)
            for i, b in enumerate(boxes):
                bx0, by0 = b.x, b.y
                bw, bh = b.w, b.h
                for j in grid.near(i, b):
                    o = boxes[j]
                    px = min(bx0 + bw, o.x + o.w) - max(bx0, o.x)
                    if px <= 1e-9:
                        continue
                    py = min(by0 + bh, o.y + o.h) - max(by0, o.y)
                    if py <= 1e-9:
                        continue
                    k = rep * 0.5
                    if px < py:
                        sgn = 1.0 if b.cx >= o.cx else -1.0
                        dx[i] += sgn * k
                        dx[j] -= sgn * k
                    else:
                        sgn = 1.0 if b.cy >= o.cy else -1.0
                        dy[i] += sgn * k
                        dy[j] -= sgn * k
        big = 0.0
        for k, b in enumerate(boxes):
            mx = max(-cap, min(cap, dx[k]))
            my = max(-cap, min(cap, dy[k]))
            big = max(big, abs(mx), abs(my))
            b.x += mx
            b.y += my
        if big < 0.02:                 # 已经收敛，剩下的轮次没意义
            break


# ------------------------------------------------------------------ ③ 去重叠

def overlap_pass(boxes, gap, limit=240):
    """③ 去重叠：按**最小穿透轴**把相交的两框对推，每轮建一次网格。

    原来是「每轮重建网格 + 最多 6000 轮」，MS 那种 142 间的大区光这一项就 2 s。
    实际上门对齐之后残余重叠很少，几十轮就清干净，所以轮数上限压到 240，
    并且**重叠对数降到 0 立刻退出**。
    """
    for it in range(limit):
        grid = _grid(boxes)
        step = gap * 0.5 * (1.1 ** (it / 40.0))
        pairs = 0
        for i, b in enumerate(boxes):
            for j in grid.near(i, b):
                o = boxes[j]
                if j <= i:
                    continue
                got = b.pen(o)
                if not got:
                    continue
                pairs += 1
                px, py = got
                if px < py:
                    sh = (px + step) * 0.5
                    sgn = 1.0 if b.cx >= o.cx else -1.0
                    b.x += sgn * sh
                    o.x -= sgn * sh
                else:
                    sh = (py + step) * 0.5
                    sgn = 1.0 if b.cy >= o.cy else -1.0
                    b.y += sgn * sh
                    o.y -= sgn * sh
        if not pairs:
            return it
    return -1


# ------------------------------------------------------------------ ④ 分量拼装

def pack_components(comps, gap):
    """互不相连的几片：大的先放，其余往**已占区域的角**上垒。"""
    def bbox(group):
        x0 = min(b.x for b in group)
        y0 = min(b.y for b in group)
        x1 = max(b.x + b.w for b in group)
        y1 = max(b.y + b.h for b in group)
        return [x0, y0, x1, y1]

    comps = sorted(comps, key=lambda g: (bbox(g)[2] - bbox(g)[0]) * (bbox(g)[3] - bbox(g)[1]),
                   reverse=True)
    if not comps:
        return 0
    big = comps[0]
    x0, y0, _, _ = bbox(big)
    for b in big:
        b.x -= x0
        b.y -= y0
    placed = [bbox(big)]
    for g in comps[1:]:
        x0, y0, x1, y1 = bbox(g)
        spots = []
        for (px0, py0, px1, py1) in placed:
            spots.append((px1 + gap, py0))          # 右侧
            spots.append((px0, py1 + gap))          # 下方
            spots.append((px1 + gap, py1 + gap))    # 右下
        spots.sort(key=lambda c: (max(c), c[1]))
        sx, sy = spots[0]
        for b in g:
            b.x += sx - x0
            b.y += sy - y0
        placed.append(bbox(g))
    return len(comps)


# ------------------------------------------------------------------ 主入口

def _pair_dir(ev_a, ev_b):
    """一条边两端 → 「b 相对 a 的方位」（`U/D/L/R`）。

    **只依赖房间自己的数据**（两端各自的出口落在哪面墙上），不碰 `map_image`、不碰世界坐标——
    那两个源 2026-11-21 被明确否掉（不是给玩家看的那张图）。

    两端互证（`OPP[sb] == sa`）时直接采信 `sa`；冲突时取更贴边的一侧：
    `t` 是出口到那面墙的距离比（0 = 紧贴），越小说明证据越硬。
    """
    sa, sb = ev_a["side"], ev_b["side"]
    if sa and sb and OPP.get(sb) == sa:
        return sa
    if not sa:
        return OPP.get(sb)
    if not sb:
        return sa
    return sa if float(ev_a.get("t", 1.0)) <= float(ev_b.get("t", 1.0)) else OPP.get(sb)


def build(rooms, opts=None):
    o = dict(config.defaults())
    o.update(opts or {})
    if not rooms:
        return {"nodes": [], "edges": [], "stats": {"rooms": 0, "engine": "zq"}}

    gap = float(o.get("gap", 6.0)) / 2.0          # 两侧各让一半，和 legacy 的观感对齐
    exp = float(o.get("scale_exp", 0.75))
    floor = float(o.get("min_side", 2.0))

    boxes = {}
    for r in rooms:
        ew, eh = effective_size(r)
        w, h = _disp(ew, eh, exp, floor)
        boxes[r.name.upper()] = Box(r.name, w, h, r)

    # ---- 门端：两侧各一条 ----
    ends = {}
    pairs = []
    one_side = 0
    by_name = {r.name.upper(): r for r in rooms}
    for r in rooms:
        a = boxes[r.name.upper()]
        for ex in (r.exits or []):
            to = str(ex[2]).upper() if ex[2] else ""
            if not to or to == r.name.upper() or to not in boxes:
                continue
            key = tuple(sorted((r.name.upper(), to)))
            if key in ends:
                continue
            b = boxes[to]
            ev_a = doorrule.evidence(r, (ex[0], ex[1]), o)
            rb = by_name[to]
            back = [e for e in (rb.exits or []) if str(e[2]).upper() == r.name.upper()]
            if back:
                ev_b = doorrule.evidence(rb, (back[0][0], back[0][1]), o)
            else:
                one_side += 1
                ev_b = {"side": OPP[ev_a["side"]], "t": 1.0 - ev_a["t"]}
            ea = {"box": a, "side": ev_a["side"], "t": ev_a["t"],
                  "cell": (ex[0], ex[1]),
                  "port": doorrule.port_cell(r, ex[0], ex[1])}
            eb = {"box": b, "side": ev_b["side"], "t": ev_b["t"],
                  "cell": None, "port": None}
            if back:
                eb["cell"] = (back[0][0], back[0][1])
                eb["port"] = doorrule.port_cell(rb, back[0][0], back[0][1])
            # 方位弱约束（V1.15）：**只用两端门位合成**，不再读 map_image / 世界坐标。
            # `ea["side"]` 就是"a 的门开在哪面墙"，也就等于"b 在 a 的哪一侧"；
            # 两端不一致时取更贴边（`t` 更小）的那一侧。见 force_pass 里那一项。
            ea["map_side"] = _pair_dir(ev_a, ev_b)
            ea["mate"], eb["mate"] = eb, ea
            pairs.append((ea, eb))
            a.ends.append(ea)
            b.ends.append(eb)
            ends[key] = (ea, eb)

    pair_area = {}
    for (ea, eb) in pairs:
        pair_area[tuple(sorted((ea["box"].name, eb["box"].name)))] = ea["box"].area + eb["box"].area

    dbg = bool(o.get("zq_debug"))
    def _bounds():
        bs = list(boxes.values())
        return [round(min(b.x for b in bs), 1), round(min(b.y for b in bs), 1),
                round(max(b.x + b.w for b in bs), 1), round(max(b.y + b.h for b in bs), 1)]

    order = _order_bfs(list(boxes.values()), pair_area)
    align_pass(boxes, pairs, gap, order)
    if dbg:
        print("   对齐后", _bounds())

    # ---- 分量 ----
    adj = {n: set() for n in boxes}
    for (ea, eb) in pairs:
        adj[ea["box"].name].add(eb["box"].name)
        adj[eb["box"].name].add(ea["box"].name)
    seen, comps = set(), []
    for n in boxes:
        if n in seen:
            continue
        stack, comp = [n], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(boxes[cur])
            stack.extend(sorted(adj[cur] - seen))      # 排序：set 的迭代顺序不可重复
        comps.append(comp)

    force_pass(list(boxes.values()), pairs, gap,
               iters=int(o.get("zq_iters") or max(40, len(boxes) * 6)))
    if dbg:
        print("   力松弛后", _bounds())
    overlap_pass(list(boxes.values()), gap)
    if dbg:
        print("   去重叠后", _bounds())
    comp_gap = float(o.get("component_gap", 6.0)) * float(o.get("gap", 6.0))
    pack_components(comps, comp_gap)
    overlap_pass(list(boxes.values()), gap)

    # ---- 归一化 + 输出 ----
    xs = [b.x for b in boxes.values()]
    ys = [b.y for b in boxes.values()]
    x0, y0 = min(xs), min(ys)
    for b in boxes.values():
        b.x -= x0
        b.y -= y0

    nodes = []
    for r in rooms:
        b = boxes[r.name.upper()]
        ew, eh = effective_size(r)
        nodes.append({
            "name": r.name,
            "x": b.x, "y": b.y, "w": b.w, "h": b.h,
            "srcW": r.w, "srcH": r.h,
            "effW": ew, "effH": eh,
            "effBox": effective_bbox(r),
            "room": r,
            "isolated": not b.ends,
            "sub": r.sub,
            "gate": is_gate(r.name),      # 大门（V1.24）：渲染样式与房间不同
        })

    edges = []
    conflict = warn = corner = 0
    for (ea, eb) in pairs:
        a, b = ea["box"], eb["box"]
        cross = eb["side"] != OPP[ea["side"]]
        if cross:
            conflict += 1
        pa = a.door(ea)
        pb = b.door(eb)
        edges.append({
            "a": a.name, "b": b.name,
            "tree": True,
            "pa": [pa[0], pa[1]], "pb": [pb[0], pb[1]],
            "kind": "corner" if cross else "solid",
            "elbow": False,
            "conflict": cross,
            "disagree": False,
            "side_a": ea["side"], "side_b": eb["side"],
            "ta": ea["t"], "tb": eb["t"],
            # V1.25 №15：门端自己的出口格与「管道口」格（源格坐标，不是布局单位）。
            # 渲染侧拿它把门点画在 E 上；缺一个就退回 `pa/pb`（框边界）。
            "e_a": list(ea["port"]) if ea.get("port") else None,
            "e_b": list(eb["port"]) if eb.get("port") else None,
            "door_a": ea["side"], "door_b": eb["side"],
            "map_a": None, "map_b": None,
            "src_a": "door", "src_b": "door",
        })

    x1 = max(n["x"] + n["w"] for n in nodes)
    y1 = max(n["y"] + n["h"] for n in nodes)
    bad = _overlaps(nodes)
    stats = {
        "rooms": len(nodes),
        "isolated": sum(1 for n in nodes if n["isolated"]),
        "edges": len(edges),
        "conflicts": conflict,
        "warn": warn,
        "corner": corner,
        "disagree": 0,
        "overlaps": len(bad),
        "bounds": [0.0, 0.0, x1, y1],
        "dir_sources": {"door": 2 * len(edges)},
        "dir_map": 0,
        "dir_door": 2 * len(edges),
        "root": nodes[0]["name"] if nodes else "",
        "components": len(comps),
        "order": [],
        "scale_exp": exp,
        "gap": o.get("gap", 6.0),
        "campaign": o.get("campaign") or "",
        "engine": "zq",
        "mirror_doors": one_side,
        "iters": int(o.get("zq_iters") or max(40, len(boxes) * 6)),
    }
    return {"nodes": nodes, "edges": edges, "stats": stats}


def _overlaps(nodes, eps=0.5):
    bad = []
    for i in range(len(nodes)):
        a = nodes[i]
        for j in range(i + 1, len(nodes)):
            b = nodes[j]
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox > eps and oy > eps:
                bad.append((a["name"], b["name"], round(ox, 2), round(oy, 2)))
    return bad
