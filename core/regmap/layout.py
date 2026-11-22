"""布局：出口方向约束 → BFS 生成树 + 门对齐 → 力松弛。

三段式（对应主人给的判据）：

1. **方向**：每条出口给一组候选边（`doorrule`），再由 `dir_source` 决定用哪条：
   - `auto`：门给候选（通道 → 有效区 → 贴边 → 摄像机），**游戏地图的方位落在候选里就用它**
     ——A06⇄E04 靠这一条从「上」纠正成「右」；
   - `door`：只用门的物理位置；
   - `map`：尽量用地图方位。
2. **拼接**：从根开始 BFS，把子房间贴到父房间那条边上，并让两边的**门落在同一条
   线上**——贴着的房间因此不需要连线，也不会留线头。房间之间留 `gap` 的细缝。
   转角门（两条候选边）在放不下时允许换另一条边。
3. **力松弛**：生成树以外的关系会互相撞车，所以约束只用来定初始位置，最终是否整齐
   由「不重叠」决定：
   - 有门相通的对：只留 `gap` 细缝，并有弹簧拉回「贴边 + 门对齐」的理想偏移；
   - 没有门相通的对：更用力地隔开（`gap * repel`）。

**不允许斜放**：真斜向的对子（地图上 `min(|dx|,|dy|)/max ≥ diag_ratio`）不参与
生成树的硬贴合，只给一个**弱弹簧**（`corner_k`，默认 0.1）把两者拉得别太远，
图上仍用**拐角虚线**连接。

显示尺寸按**有效区**（实心包围盒）的格数 `w ** scale_exp` 压缩：声明尺寸里的空白
边距不进图（UW_D05 右边 13 列空白），缩略图也按同一个框裁切。指数相同意味着
**长宽比不变**，缩略图不会变形；0.75 把最大房间（1418 格）相对中位房间的倍数从 29.5 压到 12.7。
"""
from __future__ import annotations

import math
import random
from collections import deque

from . import config, doorrule, route as routing
from .direction import OPP
from .model import effective_bbox, effective_size, is_gate

# 布局吃这些参数；其余（缩略阈值、密度、反色、连线、镜像）属于画法，在渲染阶段生效。
_LAYOUT_KEYS = ("scale_exp", "min_side", "gap", "repel", "spring_k", "corner_k",
                "sep_alpha", "sep_iters", "fit_rounds",
                "component_gap", "parking_gap",
                "door_side", "edge_tol", "corner_tol", "dir_source",
                "map_check", "diag_ratio",
                "align_tol", "slide_max", "slide_rounds", "loose_tol", "route_margin",
                "door_clear", "door_half")
DEFAULTS = {k: config.defaults()[k] for k in _LAYOUT_KEYS}
DEFAULTS["seed"] = config.INTERNAL["seed"]


def _disp(w, h, exp, floor):
    W = max(floor, float(w) ** exp)
    H = max(floor, float(h) ** exp)
    return W, H


# ------------------------------------------------------------------ 边：方向结算

def _own_best(view, name):
    """该房间自己那条出口里最可信的一条（同分取更贴边的）。"""
    own = [e for e in view if e["frm"] == name]
    if not own:
        return None
    own.sort(key=lambda e: (-e["conf"], e["dist"], e["t"]))
    return own[0]


def _resolve_edge(key, view, by, opts):
    """一条无向边 → 两侧的方向、门位、类型（solid / warn / corner）。"""
    a, b = key
    ds = opts.get("dir_source", "auto")
    check = bool(int(opts.get("map_check", 1)))
    diag_lim = float(opts.get("diag_ratio", 0.6))
    flip = doorrule.y_flip(opts)

    rec = {"a": a, "b": b, "sides": {}, "ts": {}, "src": {}, "conf": {},
           "alt": {}, "door": {}, "map": {}, "diag": 0.0, "warn": False,
           "disagree": False}

    for name, other in ((a, b), (b, a)):
        own = _own_best(view, name)
        # `map_image` 的图标矩形**不可作方向依据**（2026-11-21 定案：那张图不是给玩家看的）。
        # 这里只留 `ratio` 做"斜向"诊断，方向一律按门走。
        _ms, ratio = doorrule.map_side(by[name], by[other], flip)
        map_s = None
        rec["diag"] = max(rec["diag"], ratio or 0.0)
        if own is None:
            rev = _own_best(view, other)
            if rev is None:
                rec["sides"][name] = None
                continue
            rec["sides"][name] = OPP[rev["side"]]
            rec["ts"][name] = min(1.0, max(0.0, 1.0 - rev["t"]))
            rec["src"][name] = "rev"
            rec["conf"][name] = rev["conf"] * 0.9
            rec["alt"][name] = None
            continue

        side = own["side"]
        pref = side
        if map_s:
            if ds == "map":
                # map 模式：地图说了算，map_check 只管「要不要额外标 warn」，不拦它
                pref = map_s
            elif ds == "auto" and check and map_s in own["cands"]:
                pref = map_s
        if map_s and map_s != side:
            # 门说一条边、地图说另一条：地图优先（dir_source=map），但这条不一致要留档，
            # 只作诊断计数，不降权、不画虚线——否则 UW 会有 7 条「其实是按地图摆好的」虚线。
            rec["disagree"] = True
        if check and map_s and map_s != pref:
            rec["warn"] = True
        rec["sides"][name] = pref
        rec["ts"][name] = doorrule.exit_t(by[name], own["ex"], pref, flip)
        rec["src"][name] = own["src"]
        rec["conf"][name] = own["conf"]
        rec["door"][name] = side
        rec["map"][name] = map_s
        alt = own["alt"]
        if alt == pref:
            alt = side if side != pref else None
        rec["alt"][name] = alt

    if check and rec["diag"] >= diag_lim:
        rec["kind"] = "corner"
    elif rec["warn"]:
        rec["kind"] = "warn"
    else:
        rec["kind"] = "solid"
    return rec


def _collect_edges(rooms, opts):
    """把所有区域内出口按无向对聚合，再逐条结算方向。"""
    by = {r.name: r for r in rooms}
    views = {}
    src_counter = dict.fromkeys(("channel", "effective", "edge", "camera", "center"), 0)
    for room in rooms:
        for ex in room.exits:
            to = ex[2]
            if to == room.name or to not in by:
                continue
            ev = doorrule.evidence(room, ex, opts)
            src_counter[ev["src"]] = src_counter.get(ev["src"], 0) + 1
            key = (room.name, to) if room.name < to else (to, room.name)
            views.setdefault(key, []).append({
                "frm": room.name, "to": to, "ex": ex,
                "side": ev["side"], "cands": ev["cands"], "alt": ev["alt"],
                "t": ev["t"], "conf": ev["conf"], "src": ev["src"],
                "dist": ev["dist"],
            })
    edges = {key: _resolve_edge(key, view, by, opts) for key, view in views.items()}
    return by, edges, src_counter


# ------------------------------------------------------------------ 摆放

def _place(parent_rect, side, pt, child_w, child_h, ct, gap):
    px, py, pw, ph = parent_rect
    if side == "R":
        x = px + pw + gap
        y = py + pt * ph - ct * child_h
    elif side == "L":
        x = px - gap - child_w
        y = py + pt * ph - ct * child_h
    elif side == "D":
        y = py + ph + gap
        x = px + pt * pw - ct * child_w
    else:  # U
        y = py - gap - child_h
        x = px + pt * pw - ct * child_w
    return [x, y, child_w, child_h]


def _overlap_cost(placed, cand, gap):
    """候选位置与已放下房间的「挤占代价」——用来在两条候选边里挑一条。"""
    cost = 0.0
    for r in placed.values():
        ox = min(r[0] + r[2], cand[0] + cand[2]) - max(r[0], cand[0])
        oy = min(r[1] + r[3], cand[1] + cand[3]) - max(r[1], cand[1])
        if ox > -gap and oy > -gap:
            cost += (max(0.0, ox) + gap) * (max(0.0, oy) + gap)
    return cost


def _door_zone(rect, side, t, depth, half):
    """门圈：门外侧那块「人要站得住」的空地（贴着墙、向外 depth 深、沿墙 ±half 宽）。

    贴在墙角上的门会被墙的端点截短——它的空地本来就只有那么点，不该虚构出一块伸出墙外的地。
    """
    x, y, w, h = rect
    if side in ("L", "R"):
        py = y + t * h
        y0, y1 = max(y, py - half), min(y + h, py + half)
        if y1 <= y0:
            return None
        if side == "R":
            return (x + w, y0, depth, y1 - y0)
        return (x - depth, y0, depth, y1 - y0)
    if side in ("U", "D"):
        px = x + t * w
        x0, x1 = max(x, px - half), min(x + w, px + half)
        if x1 <= x0:
            return None
        if side == "D":
            return (x0, y + h, x1 - x0, depth)
        return (x0, y - depth, x1 - x0, depth)
    return None


def _relax(names, rect, springs, adjacent, opts, root, extra=None, rounds=None, doors=None):
    n = len(names)
    idx = {nm: i for i, nm in enumerate(names)}
    rl = [rect[nm] for nm in names]
    area = [max(1.0, rl[i][2] * rl[i][3]) for i in range(n)]
    ri = idx.get(root, 0)
    gap = opts["gap"]
    repel = gap * opts["repel"]
    rnd = random.Random(opts["seed"])
    jitter = [(rnd.random() - 0.5) * 1e-3 for _ in range(n)]

    depth = float(opts.get("door_clear", 0.0) or 0.0)
    half = float(opts.get("door_half", 0.0) or 0.0)
    zones = []
    if doors and depth > 0.0 and half > 0.0:
        for (owner, partner, side, t) in doors:
            if owner in idx:
                zones.append((idx[owner], owner, partner, side, t))

    def clear_doors(alpha=0.6):
        """门圈禁区：谁压住了别人的门口，就把它推出门圈。

        优先级**低于「真重叠」**（`separate` 负责），**高于贴合弹簧**。
        只在布局定型后跑（见 `_relax` 末尾），以免和弹簧互推、把对齐磨掉。
        返回推动次数：0 表示这一轮已经没有门口被压住了。
        """
        moved = 0
        for (oi, owner, partner, side, t) in zones:
            z = _door_zone(rl[oi], side, t, depth, half)
            if z is None:
                continue
            zx, zy, zw, zh = z
            for k in range(n):
                if names[k] == owner or names[k] == partner:
                    continue
                ox = min(zx + zw, rl[k][0] + rl[k][2]) - max(zx, rl[k][0])
                oy = min(zy + zh, rl[k][1] + rl[k][3]) - max(zy, rl[k][1])
                if ox <= 1e-6 or oy <= 1e-6:
                    continue
                # 优先沿**门法线**方向推（side=R/L 就推 x，U/D 就推 y）：
                # 只沿最小穿透轴推的话，转角上的邻房会被横着推走，门就再也对不齐了。
                perp_x = side in ("L", "R")
                if perp_x:
                    use_x = ox <= oy * 3.0
                else:
                    use_x = ox * 3.0 < oy
                if use_x:
                    sign = -1.0 if (rl[k][0] + rl[k][2] * 0.5) < (zx + zw * 0.5) else 1.0
                    rl[k][0] += sign * (ox + 0.02) * alpha
                else:
                    sign = -1.0 if (rl[k][1] + rl[k][3] * 0.5) < (zy + zh * 0.5) else 1.0
                    rl[k][1] += sign * (oy + 0.02) * alpha
                moved += 1
        return moved

    def separate(rounds, alpha=None, push_extra=None):
        """`push_extra=None` 用默认余量（相邻 gap / 非相邻 repel）；给 0 就只推掉重叠，
        不再额外撑开——收尾阶段用它，避免把整张图越推越大。"""
        if alpha is None:
            alpha = opts["sep_alpha"]
        for _ in range(rounds):
            for i in range(n):
                axi, ayi, awi, ahi = rl[i]
                for j in range(i + 1, n):
                    bxj, byj, bwj, bhj = rl[j]
                    ox = min(axi + awi, bxj + bwj) - max(axi, bxj)
                    oy = min(ayi + ahi, byj + bhj) - max(ayi, byj)
                    if ox <= 0.0 or oy <= 0.0:
                        continue
                    sep = gap if (names[i], names[j]) in adjacent else repel
                    if push_extra is not None:
                        sep = push_extra       # 只解决真重叠，不额外推开
                    elif extra is not None:
                        sep = extra
                    nx = ox + sep
                    ny = oy + sep
                    mi = area[j] / (area[i] + area[j])
                    mj = 1.0 - mi
                    if i == ri:
                        mi, mj = 0.0, 1.0
                    elif j == ri:
                        mj, mi = 1.0, 0.0
                    if nx <= ny:
                        sign = 1.0 if (axi + awi * 0.5) <= (bxj + bwj * 0.5) else -1.0
                        if abs(ox - oy) < 1e-6:
                            sign += jitter[i] * 1000.0
                        push = nx * alpha
                        rl[i][0] -= sign * push * mi
                        rl[j][0] += sign * push * mj
                        axi = rl[i][0]
                    else:
                        sign = 1.0 if (ayi + ahi * 0.5) <= (byj + bhj * 0.5) else -1.0
                        push = ny * alpha
                        rl[i][1] -= sign * push * mi
                        rl[j][1] += sign * push * mj
                        ayi = rl[i][1]

    def fit():
        k = opts["spring_k"]
        for (a, b, tx, ty, kk) in springs:
            i, j = idx[a], idx[b]
            ex = (rl[j][0] - rl[i][0]) - tx
            ey = (rl[j][1] - rl[i][1]) - ty
            if abs(ex) < 1e-4 and abs(ey) < 1e-4:
                continue
            s = k * kk * 0.5
            if i == ri:
                si, sj = 0.0, 1.0
            elif j == ri:
                sj, si = 0.0, 1.0
            else:
                si = sj = 1.0
            rl[i][0] += ex * s * si
            rl[i][1] += ey * s * si
            rl[j][0] -= ex * s * sj
            rl[j][1] -= ey * s * sj

    if rounds is not None:          # 只做分离的收尾调用
        separate(rounds, push_extra=extra)
        for _ in range(8):
            if not _overlaps(names, rect):
                break
            separate(80, alpha=0.9, push_extra=extra)
        return {names[i]: rl[i] for i in range(n)}

    separate(opts["sep_iters"])
    for _ in range(opts["fit_rounds"]):
        fit()
        separate(2)
    separate(60)          # 终局：保证零重叠，弹簧不许把房间再压到一起

    # 门口清场：放在弹簧**定型之后**再做。每轮都插进去会和弹簧互推，
    # 房间被反复挪动、门反而更对不齐（实测直连边会少 5 条）。
    if zones:
        for _ in range(6):
            if not clear_doors(alpha=0.9):
                break
            separate(10)
    # 密集区域（TM 112 间）60 轮 Gauss-Seidel 不一定收敛：一间房被几间夹住时推力互抵消。
    # 实测「大步长 + 多轮」才收敛（α=0.9 需 ~400 轮；α≤0.5 会停在 6~20 对不动），
    # 所以这里按需追加，正常区域第一轮就 break，不花时间。
    for _ in range(8):
        if not _overlaps(names, rect):
            break
        separate(80, alpha=0.9)

    return {names[i]: rl[i] for i in range(n)}


def _rect_gap(a, b):
    """两个矩形的欧氏间隙（相交时为 0）。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(0.0, max(ax - (bx + bw), bx - (ax + aw)))
    dy = max(0.0, max(ay - (by + bh), by - (ay + ah)))
    return math.hypot(dx, dy)


def _gap_stats(rect, pairs, tight_tol=3.0):
    """相邻房间的间隙统计 —— 用来判断 gap / spring_k 到底有没有生效。

    `tight_tol` 是「贴住」的门槛。它**必须跟着 gap 走**（调用方传 `gap + loose_tol`）：
    gap 放大到 6 之后，还用写死的 3 去数，全库都会变成「一条也没贴住」。
    """
    gaps = []
    for (a, b) in pairs:
        if a in rect and b in rect:
            gaps.append(_rect_gap(rect[a], rect[b]))
    if not gaps:
        return {"mean_gap": 0.0, "max_gap": 0.0, "tight": 0, "adj_total": 0,
                "tight_tol": round(tight_tol, 2)}
    gaps.sort()
    tight = sum(1 for g in gaps if g <= tight_tol)
    return {"mean_gap": round(sum(gaps) / len(gaps), 2),
            "max_gap": round(gaps[-1], 2),
            "tight": tight, "adj_total": len(gaps),
            "tight_tol": round(tight_tol, 2)}


def _overlaps(names, rect, eps=0.02):
    n = len(names)
    rl = [rect[nm] for nm in names]
    bad = []
    for i in range(n):
        for j in range(i + 1, n):
            ox = min(rl[i][0] + rl[i][2], rl[j][0] + rl[j][2]) - max(rl[i][0], rl[j][0])
            oy = min(rl[i][1] + rl[i][3], rl[j][1] + rl[j][3]) - max(rl[i][1], rl[j][1])
            if ox > eps and oy > eps:
                bad.append((names[i], names[j], round(ox, 2), round(oy, 2)))
    return bad


def _components(names, adjacent):
    """把房间按「有门相通」切成连通分量，按大小降序。"""
    adj = {n: set() for n in names}
    for (a, b) in adjacent:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen = set()
    comps = []
    for n in names:
        if n in seen:
            continue
        stack = [n]
        comp = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(adj[cur] - seen)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps, adj


def build(rooms, opts=None):
    """主入口。`rooms` 是 `model.Room` 列表，返回布局 dict（可直接渲染）。"""
    o = dict(DEFAULTS)
    o.update(config.defaults())
    o.update(opts or {})

    rooms = [r for r in rooms if not is_gate(r.name)]
    if not rooms:
        return {"nodes": [], "edges": [], "stats": {"rooms": 0}}

    by, edge_info, src_counter = _collect_edges(rooms, o)
    adjacent = set(edge_info.keys())
    # 真斜向的对子不算「贴合邻接」——它们不参与弹簧，只占细缝
    fit_pairs = set(k for k, e in edge_info.items() if e["kind"] != "corner")

    # 每扇门一条「门圈」的元数据：(房主, 对面那间, 该房这条门所在的边, 门在边上的位置)
    # 只记边长与 t，不记坐标——门圈要跟着房间动，坐标每次现算。
    door_meta = []
    for (a, b), e in edge_info.items():
        sa, sb = e["sides"].get(a), e["sides"].get(b)
        if sa:
            door_meta.append((a, b, sa, e["ts"].get(a, 0.5)))
        if sb:
            door_meta.append((b, a, sb, e["ts"].get(b, 0.5)))

    size = {}
    area = {}
    for r in rooms:
        # 外框用**有效区**（实心包围盒）：声明尺寸里的空白边距不进图，
        # 否则 D05 右边 13 列空白会让房间看着比实际大一圈。
        ew, eh = effective_size(r)
        size[r.name] = _disp(ew, eh, o["scale_exp"], o["min_side"])
        area[r.name] = float(ew * eh)

    deg = {}
    for (a, b) in adjacent:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1

    comps, adj = _components([r.name for r in rooms], adjacent)

    def edge_of(cur, other):
        return edge_info[(cur, other) if (cur, other) in edge_info else (other, cur)]

    def view_for(cur, other):
        """从 cur 看 other 的方向、门位、次选边。"""
        e = edge_of(cur, other)
        side = e["sides"].get(cur)
        if side is None:
            side = OPP[e["sides"].get(other)] if e["sides"].get(other) else None
        if side is None:
            return None
        return {
            "side": side,
            "t": e["ts"].get(cur, 0.5),
            "conf": e["conf"].get(cur, 0.5),
            "alt": e["alt"].get(cur),
            "kind": e["kind"],
            "disagree": e["disagree"],
        }

    def grow(comp):
        """在一个连通分量里 BFS 长出布局：门对齐放置 + 力松弛。"""
        comp_set = set(comp)
        root = max(comp, key=lambda n: (deg.get(n, 0), area[n]))
        rect = {root: [0.0, 0.0, size[root][0], size[root][1]]}
        tree = []
        springs = []
        order = [root]
        queue = deque([root])
        while queue:
            cur = queue.popleft()
            nbrs = []
            for other in adj[cur]:
                if other in rect or other not in comp_set:
                    continue
                info = view_for(cur, other)
                if info is None:
                    continue
                # 排序（越小越先用）：门与地图一致的边优先走树——它们是「两边都认」的关系，
                # 拿它们搭骨架不容易把房间摆到自己的门背后（map 模式下矛盾边很多，
                # 全按地图硬摆会绕成几何环，力松弛只能靠把整块推开解环 → 缝变大）。
                rank = (1 if info["disagree"] else 0,
                        {"solid": 0, "warn": 1, "corner": 2}.get(info["kind"], 1))
                nbrs.append((rank, -info["conf"], other))
            nbrs.sort()
            for (_rank, _neg, other) in nbrs:
                if other in rect:
                    continue
                info = view_for(cur, other)
                if info is None:
                    continue
                w, h = size[other]
                cand = _place(rect[cur], info["side"], info["t"], w, h, 0.5, o["gap"])
                if info["alt"]:
                    alt = _place(rect[cur], info["alt"], info["t"], w, h, 0.5, o["gap"])
                    if _overlap_cost(rect, alt, o["gap"]) < _overlap_cost(rect, cand, o["gap"]):
                        cand = alt
                rect[other] = cand
                tree.append((cur, other))
                kk = 1.0
                if info["kind"] == "warn":
                    kk = config.INTERNAL["warn_k"]
                elif info["kind"] == "corner":
                    # 斜向对子也拉一把，权重很轻（默认 0.1）：只让拐角虚线别飘太远，
                    # 不足以把整块拉歪。设 0 = 旧行为（完全不拉）。
                    kk = float(o.get("corner_k", 0.1))
                springs.append((cur, other, cand[0] - rect[cur][0],
                                cand[1] - rect[cur][1], kk))
                order.append(other)
                queue.append(other)

        # 非树边也给一个较弱的弹簧，让强相关但没被 BFS 选中的房间靠回去
        tree_set = set(tree) | set((b, a) for (a, b) in tree)
        for (a, b), e in edge_info.items():
            if (a, b) in tree_set or a not in rect or b not in rect:
                continue
            ideal = _ideal_offset(rect, size, e, a, b, o["gap"])
            if ideal is not None:
                if e["kind"] == "corner":
                    kk = float(o.get("corner_k", 0.1))   # 斜向非树边：同样只给弱弹簧
                elif e["kind"] == "solid":
                    kk = 0.45
                else:
                    kk = config.INTERNAL["warn_k"]
                springs.append((a, b, ideal[0], ideal[1], kk))

        names = [nm for nm in order if nm in rect]
        rect = _relax(names, rect, springs, adjacent, o, root,
                      doors=[d for d in door_meta if d[0] in comp_set])
        return rect, tree, root, names

    # ---- 主连通分量 ----
    rect, tree_edges, root, growth = grow(comps[0])
    all_tree = set(tree_edges) | set((b, a) for (a, b) in tree_edges)
    top_y = min(r[1] for r in rect.values())
    main_height = max(r[1] + r[3] for r in rect.values()) - top_y

    # ---- 其余分量：各自长成一块，排在主块右侧（不重叠，块内关系保留）----
    def bbox(rr):
        xs = [v[0] for v in rr.values()]
        ys = [v[1] for v in rr.values()]
        xe = [v[0] + v[2] for v in rr.values()]
        ye = [v[1] + v[3] for v in rr.values()]
        return min(xs), min(ys), max(xe), max(ye)

    cursor_x = bbox(rect)[2] + o["gap"] * o["component_gap"]
    cursor_y = top_y
    col_w = 0.0
    for comp in comps[1:]:
        rr, te, _r, sub_order = grow(comp)
        all_tree |= set(te) | set((b, a) for (a, b) in te)
        growth.extend(sub_order)
        x0, y0, x1, y1 = bbox(rr)
        bw, bh = x1 - x0, y1 - y0
        if cursor_y + bh > top_y + main_height and cursor_y > top_y + 1e-6:
            cursor_x += col_w + o["gap"] * o["component_gap"]
            cursor_y = top_y
            col_w = 0.0
        dx, dy = cursor_x - x0, cursor_y - y0
        for nm in rr:
            rr[nm][0] += dx
            rr[nm][1] += dy
        rect.update(rr)
        cursor_y += bh + o["gap"] * 4
        col_w = max(col_w, bw)

    isolated = [r.name for r in rooms if r.name not in rect]
    all_names = [r.name for r in rooms if r.name in rect]

    # 跨分量之间只解决真重叠（extra=0），不能用 repel 余量——那会把同一簇里
    # 已经贴好的相邻房间又推开一圈，缝隙会从 1.2 变成 3 以上。
    if len(comps) > 1 and all_names:
        _relax(all_names, rect, [], adjacent, o, root, extra=0.0, rounds=90)

    # ---- 情形②：门对不齐的先挪房间（挪不动才留给绕行）----
    # 放在力学收敛之后、停车场之前：此时相对方位已经定型，只需要把最后几格补齐。
    slide = _slide_align(rect, edge_info, all_names, o, doors=door_meta)

    # ---- 孤立房间：主块右侧的停车场 ----
    if isolated:
        xs = [rect[nm][0] for nm in all_names]
        xe = [rect[nm][0] + rect[nm][2] for nm in all_names]
        ys = [rect[nm][1] for nm in all_names]
        parking_x = max(xe) + o["gap"] * o["parking_gap"]
        cols = max(1, int(math.ceil(math.sqrt(len(isolated)))))
        cell_w = max(size[nm][0] for nm in isolated) + o["gap"] * 3
        cell_h = max(size[nm][1] for nm in isolated) + o["gap"] * 3
        for k, nm in enumerate(isolated):
            c, r = divmod(k, cols)
            w, h = size[nm]
            rect[nm] = [parking_x + c * cell_w, min(ys) + r * cell_h, w, h]

    all_names = all_names + isolated
    bad = _overlaps(all_names, rect)

    nodes = []
    for nm in all_names:
        x, y, w, h = rect[nm]
        r = by[nm]
        ew, eh = effective_size(r)
        nodes.append({
            "name": nm,
            "x": x, "y": y, "w": w, "h": h,
            "srcW": r.w, "srcH": r.h,
            "effW": ew, "effH": eh,
            "effBox": effective_bbox(r),      # 缩略图按这个框裁切源格
            "room": r,
            "isolated": nm in isolated,
            "sub": r.sub,
        })

    # ---- 连线端点：先算（用最终坐标），再做平移 ----
    edges = []
    for (a, b), e in edge_info.items():
        if a not in rect or b not in rect:
            continue
        sa, sb = e["sides"].get(a), e["sides"].get(b)
        if e["kind"] == "corner":
            # 端点一律用**通道口**（§6 R1）；只有两间房都没记录边时才退回最近角点
            if sa and sb:
                pa = _door_point(rect[a], sa, e["ts"].get(a, 0.5))
                pb = _door_point(rect[b], sb, e["ts"].get(b, 0.5))
            else:
                pa, pb = _corner_pair(rect[a], rect[b])
        else:
            pa = _door_point(rect[a], sa, e["ts"].get(a, 0.5))
            pb = _door_point(rect[b], sb, e["ts"].get(b, 0.5))
        edges.append({
            "a": a, "b": b,
            "tree": (a, b) in all_tree,
            "pa": pa, "pb": pb,
            "kind": e["kind"],
            "elbow": e["kind"] == "corner",
            "conflict": bool(sa and sb and sb != OPP[sa]),
            "disagree": e["disagree"],
            "side_a": sa, "side_b": sb,
            "ta": e["ts"].get(a, 0.5), "tb": e["ts"].get(b, 0.5),
            "door_a": e["door"].get(a), "door_b": e["door"].get(b),
            "map_a": e["map"].get(a), "map_b": e["map"].get(b),
            "src_a": e["src"].get(a), "src_b": e["src"].get(b),
        })

    x0 = min(n["x"] for n in nodes)
    y0 = min(n["y"] for n in nodes)
    x1 = max(n["x"] + n["w"] for n in nodes)
    y1 = max(n["y"] + n["h"] for n in nodes)
    for n in nodes:
        n["x"] -= x0
        n["y"] -= y0
    for e in edges:
        e["pa"] = [e["pa"][0] - x0, e["pa"][1] - y0]
        e["pb"] = [e["pb"][0] - x0, e["pb"][1] - y0]

    # ---- 情形①③④：直连 / 绕行 / 未解（必须在归一化之后，折线才不会跟着偏移）----
    rect_n = {n["name"]: [n["x"], n["y"], n["w"], n["h"]] for n in nodes}
    routed = _route_edges(edges, rect_n, o)
    blocked = _door_blocked(edges, rect_n, o)

    warn = [e for e in edges if e["kind"] == "warn"]
    corner = [e for e in edges if e["kind"] == "corner"]
    dir_map = sum(1 for e in edges for k in ("a", "b")
                  if e["map_" + k] and e["side_" + k] == e["map_" + k])
    stats = {
        "rooms": len(nodes),
        "isolated": len(isolated),
        "edges": len(edges),
        "conflicts": sum(1 for e in edges if e["conflict"]),
        "warn": len(warn),
        "corner": len(corner),
        "disagree": sum(1 for e in edges if e["disagree"]),
        "overlaps": len(bad),
        "bounds": [0.0, 0.0, x1 - x0, y1 - y0],
        "dir_sources": src_counter,
        "dir_map": dir_map,
        "dir_door": 2 * len(edges) - dir_map,
        "root": root,
        "components": len(comps),
        "order": growth + isolated,
        "scale_exp": o["scale_exp"],
        "gap": o["gap"],
        "campaign": o.get("campaign") or "",
    }
    stats.update(slide)
    stats.update(routed)
    stats.update(blocked)
    stats.update(_gap_stats(rect, list(fit_pairs),
                            o["gap"] + float(o.get("loose_tol", 2.4))))
    return {"nodes": nodes, "edges": edges, "stats": stats}


def _door_off(rect, sa, ta, rb, sb, tb):
    """两个通道口沿共享边方向的**错位**（有符号）。只有正对的边算得出来。"""
    if sa in ("U", "D") and sb in ("U", "D"):
        return (rect[0] + ta * rect[2]) - (rb[0] + tb * rb[2])
    if sa in ("L", "R") and sb in ("L", "R"):
        return (rect[1] + ta * rect[3]) - (rb[1] + tb * rb[3])
    return None


def _sweep_clear(rect, axis, delta, others, eps=0.02):
    """沿轴滑 `delta` 的**全程**是否不碰任何别的房间。

    把「扫过的整段」并成一个矩形再求交——一次就算完，不用按步长切。
    """
    x, y, w, h = rect
    if axis == "x":
        box = (min(x, x + delta), y, w + abs(delta), h)
    else:
        box = (x, min(y, y + delta), w, h + abs(delta))
    bx, by, bw, bh = box
    for (ox, oy, ow, oh) in others:
        if (min(bx + bw, ox + ow) - max(bx, ox) > eps and
                min(by + bh, oy + oh) - max(by, oy) > eps):
            return False
    return True


def _slide_align(rect, edge_info, names, opts, doors=None):
    """情形②：门错位的房间，沿共享边**挪一下**，挪得动才挪。

    只沿共享边滑（上下相邻就左右滑、左右相邻就上下滑），垂直方向一步不动——
    垂直一挪就改了相对方位，把 §3.3 用地图定下来的方位弄坏。

    `slide_max` 保证两间房仍有一半边长对着，所以`_rect_gap` 不会因为滑动变大。
    滑动也**不许压住别人的门口**：门圈一起算进障碍里，否则刚清完的门圈又被自己挤了。
    """
    rounds = int(opts.get("slide_rounds", 3) or 0)
    max_frac = float(opts.get("slide_max", 0.5) or 0.0)
    align = float(opts.get("align_tol", 2.0) or 0.0)
    depth = float(opts.get("door_clear", 0.0) or 0.0)
    half = float(opts.get("door_half", 0.0) or 0.0)
    out = {"slide": 0, "slide_blocked": 0, "slide_shift": 0.0,
           "slide_off0": 0.0, "slide_off1": 0.0}
    if rounds <= 0 or max_frac <= 0:
        return out

    def obstacles_for(mover):
        """别人的房间 + **别人的**门圈；自己的门圈跟着自己动，不算障碍。"""
        res = [rect[nm] for nm in names if nm != mover]
        if doors and depth > 0 and half > 0:
            for (owner, _partner, side, t) in doors:
                if owner == mover or owner not in rect:
                    continue
                z = _door_zone(rect[owner], side, t, depth, half)
                if z:
                    res.append(z)
        return res

    pairs = []
    for (a, b), e in edge_info.items():
        if a not in rect or b not in rect or e["kind"] == "corner":
            continue
        sa, sb = e["sides"].get(a), e["sides"].get(b)
        if not sa or not sb or sb != OPP[sa]:
            continue
        pairs.append((a, b, sa, sb, e["ts"].get(a, 0.5), e["ts"].get(b, 0.5)))

    def off_of(x, y, sx, sy, tx, ty):
        return _door_off(rect[x], sx, tx, rect[y], sy, ty)

    def total_off():
        tot = 0.0
        for (a, b, sa, sb, ta, tb) in pairs:
            d = off_of(a, b, sa, sb, ta, tb)
            if d is not None:
                tot += abs(d)
        return round(tot, 1)

    # 一个房间可能挂着好几条边；滑动前要算「挪了它，别的边会不会更歪」
    near = {}
    for (a, b, sa, sb, ta, tb) in pairs:
        near.setdefault(a, []).append((b, sa, sb, ta, tb))
        near.setdefault(b, []).append((a, sb, sa, tb, ta))

    out["slide_off0"] = total_off()

    for _ in range(rounds):
        plan = []
        for (a, b, sa, sb, ta, tb) in pairs:
            d = off_of(a, b, sa, sb, ta, tb)
            if d is None or abs(d) <= align:
                continue
            ext = min(rect[a][2], rect[a][3], rect[b][2], rect[b][3])
            plan.append((-abs(d) / max(1e-6, ext), a, b, sa, sb, ta, tb, d))
        plan.sort()
        for (_rel, a, b, sa, sb, ta, tb, d) in plan:
            small = a if rect[a][2] * rect[a][3] <= rect[b][2] * rect[b][3] else b
            axis = "x" if sa in ("U", "D") else "y"
            extent = rect[small][2] if axis == "x" else rect[small][3]
            cap = max_frac * extent
            want = -d if small == a else d          # 朝对齐方向
            step = max(-cap, min(cap, want))
            if abs(step) < 1e-9:
                continue
            others = obstacles_for(small)
            if not _sweep_clear(rect[small], axis, step, others):
                step *= 0.5                          # 密集区常见：退一半再试
                if abs(step) < 1e-9 or not _sweep_clear(rect[small], axis, step, others):
                    out["slide_blocked"] += 1
                    continue

            def moved(o2, x, y):
                return o2 + (step if small == x else -step)

            gain = abs(d) - abs(moved(d, a, b))
            cost = 0.0
            for (other, s1, s2, t1, t2) in near.get(small, ()):
                if other in (a, b):
                    continue
                d2 = off_of(small, other, s1, s2, t1, t2)
                if d2 is None:
                    continue
                cost += max(0.0, abs(moved(d2, small, other)) - abs(d2))
            if gain - 0.5 * cost <= 1e-6:
                continue
            rect[small][0 if axis == "x" else 1] += step
            out["slide"] += 1
            out["slide_shift"] = round(out["slide_shift"] + abs(step), 2)

    out["slide_off1"] = total_off()
    return out


_NORMAL = {"U": (0.0, -1.0), "D": (0.0, 1.0), "L": (-1.0, 0.0), "R": (1.0, 0.0)}


def _safe_stub(pa, direction, rects, skip, want=3.0):
    """未解边的短头能画多长：沿这个方向走不了几步就被别的房间挡住，就别硬画。

    「门被对面的房间堵死」时（§7 门圈禁区还没做），短头会直接插进别人屋里——
    那等于用一条短线承认了一条并不存在的通路。所以这里按实际空隙裁剪。
    """
    dx, dy = direction
    for keep in (want, want * 0.6, want * 0.35, want * 0.2):
        q = (pa[0] + dx * keep, pa[1] + dy * keep)
        if not any(routing.seg_rect_hit(pa, q, rects[i]) for i in skip):
            return round(keep, 2)
    return 0.0


def _stub_path(pa, pb, sa, sb, rects, skip, want=3.0):
    """未解边：两端各沿**门的法线**向外画一小段（不是沿着直线斜着戳）。

    沿着 pa→pb 画会得到一小截斜线，看着像箭头；沿法线才是「这条通道出去就没路了」的意思。
    """
    out = []
    for pt, side in ((pa, sa), (pb, sb)):
        n = _NORMAL.get(side)
        if not n:
            continue
        keep = _safe_stub(pt, n, rects, skip, want)
        if keep > 1e-6:
            out.append([[round(pt[0], 2), round(pt[1], 2)],
                        [round(pt[0] + n[0] * keep, 2), round(pt[1] + n[1] * keep, 2)]])
    return out


def _door_blocked(edges, rect_n, opts):
    """「门被堵死」的判定（§7 L3）：只看门点正前方那一小块（1.0 深 × 1.0 宽）。

    这里刻意**不**用布局用的那个 2.5×0.8 门圈：那是约束区，被擦一下很正常；
    真正值得报的是「门正对着别人家墙」——线出不去、房间也挪不动。用宽门圈去报，
    数字会虚高十倍，报表就没人看了。
    """
    depth = min(0.6, float(opts.get("door_clear", 0.0) or 0.0))
    half = min(0.35, float(opts.get("door_half", 0.0) or 0.0))
    if depth <= 0.0 or half <= 0.0:
        for e in edges:
            e["door_blocked"] = False
        return {"door_blocked": 0, "door_blocked_list": []}
    names = list(rect_n)
    cnt = 0
    lst = []
    for e in edges:
        hit_any = False
        for (owner, partner, side, t) in (
                (e["a"], e["b"], e.get("side_a"), e.get("ta", 0.5)),
                (e["b"], e["a"], e.get("side_b"), e.get("tb", 0.5))):
            if not side:
                continue
            z = _door_zone(rect_n[owner], side, t, depth, half)
            if z is None:
                continue
            zx, zy, zw, zh = z
            for nm in names:
                if nm == owner or nm == partner:
                    continue
                r = rect_n[nm]
                if (min(zx + zw, r[0] + r[2]) - max(zx, r[0]) > 1e-6 and
                        min(zy + zh, r[1] + r[3]) - max(zy, r[1]) > 1e-6):
                    hit_any = True
                    break
            if hit_any:
                break
        e["door_blocked"] = hit_any
        if hit_any:
            cnt += 1
            lst.append("%s ⇄ %s" % (e["a"], e["b"]))
    return {"door_blocked": cnt, "door_blocked_list": lst}


def _route_edges(edges, rect_n, opts):
    """情形①③④：直连 / 绕行 / 未解 —— 给每条边算出要画的折线。

    顺序判：贴住且门对齐且直连不穿房 → 实线；否则从通道口出发绕；
    绕不过就记 `unresolved`，**绝不静默画一条穿房的直线**。
    """
    gap = float(opts["gap"])
    align = float(opts.get("align_tol", 2.0))
    loose = gap + float(opts.get("loose_tol", 2.4))
    margin = float(opts.get("route_margin", 0.3))
    names = list(rect_n)
    idx = {nm: i for i, nm in enumerate(names)}
    rects = [rect_n[nm] for nm in names]
    cnt = {"route_straight": 0, "route_elbow": 0, "route_unresolved": 0}
    unresolved = []
    for e in edges:
        a, b = e["a"], e["b"]
        pa, pb = e["pa"], e["pb"]
        straight = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        off = _door_off(rect_n[a], e.get("side_a"), e.get("ta", 0.5),
                        rect_n[b], e.get("side_b"), e.get("tb", 0.5))
        g = _rect_gap(rect_n[a], rect_n[b])
        hit = any(routing.seg_rect_hit(pa, pb, rects[i])
                  for i in range(len(rects)) if i not in (idx[a], idx[b]))
        # 斜得不超过 45° 就直连：缝只有 6 时，错开 5 格画成斜线比画成小 Z 更像「通着」。
        # 离得远（缝大）时才用 align_tol 卡住斜度，避免拉出一条长斜线。
        limit = max(align, g)
        if (e["kind"] != "corner" and g <= loose and
                (off is None or abs(off) <= limit) and not hit):
            e["path"] = [list(pa), list(pb)]
            e["route"] = "straight"
            e["elbow"] = False
            e["detour"] = 1.0
            e["door_off"] = round(abs(off), 2) if off is not None else None
            cnt["route_straight"] += 1
            continue
        path = routing.route(pa, pb, rects, {idx[a], idx[b]},
                             margin=margin, step=1.0)
        det = 0.0
        if path:
            det = routing.length(path) / max(1e-6, straight)
        if path and det <= 6.0:
            e["path"] = path
            e["route"] = "elbow"
            e["elbow"] = True
            e["detour"] = round(det, 2)
            e["door_off"] = round(abs(off), 2) if off is not None else None
            cnt["route_elbow"] += 1
            continue
        # 绕不过去：只留最后一点兜底（渲染时画成「断口」短虚线）
        e["path"] = [list(pa), list(pb)]
        e["route"] = "unresolved"
        e["elbow"] = False
        e["detour"] = round(det, 2) if det else None
        e["door_off"] = round(abs(off), 2) if off is not None else None
        others = {i for i in range(len(rects)) if i not in (idx[a], idx[b])}
        e["stub_path"] = _stub_path(pa, pb, e.get("side_a"), e.get("side_b"), rects, others)
        cnt["route_unresolved"] += 1
        unresolved.append("%s ⇄ %s" % (a, b))
    cnt["unresolved_list"] = unresolved
    return cnt


def _ideal_offset(rect, size, edge, a, b, gap):
    """非树边：按方向给一个理想偏移（只用于弱弹簧）。"""
    side = edge["sides"].get(a)
    if side is None:
        return None
    if a not in rect or b not in rect:
        return None
    w, h = size[b]
    r = _place(rect[a], side, edge["ts"].get(a, 0.5), w, h, 0.5, gap)
    return (r[0] - rect[a][0], r[1] - rect[a][1])


def _door_point(rect, side, t):
    """门点在布局坐标里的位置。"""
    x, y, w, h = rect
    if side == "L":
        return [x, y + t * h]
    if side == "R":
        return [x + w, y + t * h]
    if side == "U":
        return [x + t * w, y]
    return [x + t * w, y + h]


def _corner_pair(ra, rb):
    """两个矩形最近的一对角点——真斜向的对子用拐角虚线连。"""
    ca = [(ra[0], ra[1]), (ra[0] + ra[2], ra[1]),
          (ra[0], ra[1] + ra[3]), (ra[0] + ra[2], ra[1] + ra[3])]
    cb = [(rb[0], rb[1]), (rb[0] + rb[2], rb[1]),
          (rb[0], rb[1] + rb[3]), (rb[0] + rb[2], rb[1] + rb[3])]
    best = None
    for pa in ca:
        for pb in cb:
            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if best is None or d < best[0]:
                best = (d, pa, pb)
    return [best[1][0], best[1][1]], [best[2][0], best[2][1]]
