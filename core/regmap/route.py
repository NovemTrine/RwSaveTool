"""正交折线绕行：从通道口出发，只走横竖，绝不穿过房间。

只做一件事：给两个门点找一条「离任何房间至少 margin」的折线。
找不到返回 None —— 上层必须把它记成 `unresolved`，不许静默画一条穿房的直线。

坐标就是布局坐标（与 `layout.rect` 同一套，单位≈1 格），所以 PNG 与 SVG 共用同一条路径。
"""
from __future__ import annotations

import heapq

# 4 邻域：右、左、下、上
_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def seg_rect_hit(p, q, rect, eps=0.02):
    """线段是否穿过矩形内部（Liang-Barsky 裁剪）。

    `eps` 是「贴边不算穿」的容差：房间壁上擦过去不该判成穿房，
    否则门点出发的第一段永远"穿"自己的房间。
    """
    x0 = rect[0] + eps
    y0 = rect[1] + eps
    x1 = rect[0] + rect[2] - eps
    y1 = rect[1] + rect[3] - eps
    if x1 <= x0 or y1 <= y0:
        return False
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if abs(pk) < 1e-12:
            if qk < 0:
                return False
        else:
            r = qk / pk
            if pk < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return (t1 - t0) > 1e-6


class _Grid(object):
    """局部占据栅格。

    只覆盖「两个门点的包围盒 + pad」这么大一块，不铺整张图——
    全库 153 次构建时，整图栅格会让 Python 慢到不可用。
    """

    def __init__(self, rects, own, box, step, margin):
        x0, y0, x1, y1 = box
        self.step = step
        self.x0 = x0
        self.y0 = y0
        self.w = max(1, int((x1 - x0) / step) + 1)
        self.h = max(1, int((y1 - y0) / step) + 1)
        n = self.w * self.h
        self.blocked = bytearray(n)     # 被「别的房间 + margin」占住
        self.own = bytearray(n)         # 落在两端自己的房间里（可以走）
        for i, r in enumerate(rects):
            if i in own:
                self._mark(r, self.own)
            else:
                self._mark((
                    r[0] - margin, r[1] - margin,
                    r[2] + 2 * margin, r[3] + 2 * margin,
                ), self.blocked)

    def _mark(self, r, arr):
        x0 = max(0, int((r[0] - self.x0) / self.step))
        x1 = min(self.w - 1, int((r[0] + r[2] - self.x0) / self.step))
        y0 = max(0, int((r[1] - self.y0) / self.step))
        y1 = min(self.h - 1, int((r[1] + r[3] - self.y0) / self.step))
        for gy in range(y0, y1 + 1):
            base = gy * self.w
            for gx in range(x0, x1 + 1):
                arr[base + gx] = 1

    def walkable(self, c):
        gx, gy = c
        if not (0 <= gx < self.w and 0 <= gy < self.h):
            return False
        i = gy * self.w + gx
        return (not self.blocked[i]) or bool(self.own[i])

    def cell(self, p):
        return (int(round((p[0] - self.x0) / self.step)),
                int(round((p[1] - self.y0) / self.step)))

    def near(self, c, radius=6):
        """门点格子被压住时，向外找最近的可走格子。"""
        if self.walkable(c):
            return c
        cx, cy = c
        for rad in range(1, radius + 1):
            best = None
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    if max(abs(dx), abs(dy)) != rad:
                        continue
                    q = (cx + dx, cy + dy)
                    if not self.walkable(q):
                        continue
                    d = dx * dx + dy * dy
                    if best is None or d < best[0]:
                        best = (d, q)
            if best:
                return best[1]
        return None

    def astar(self, s, e, turn_pen=0.7):
        """4 邻域 + 转弯罚。用 (格, 来向) 做状态，才能真的惩罚拐弯。"""
        s = self.near(s)
        e = self.near(e)
        if s is None or e is None:
            return None
        if s == e:
            return [s]
        openq = [(0.0, 0, s, -1)]
        best = {(s, -1): 0.0}
        prev = {}
        while openq:
            _f, g, cur, d = heapq.heappop(openq)
            if cur == e:
                path = [cur]
                key = (cur, d)
                while key in prev:
                    key = prev[key]
                    path.append(key[0])
                return path[::-1]
            if g > best.get((cur, d), 1e18) + 1e-9:
                continue
            for nd, (dx, dy) in enumerate(_DIRS):
                q = (cur[0] + dx, cur[1] + dy)
                if not self.walkable(q):
                    continue
                cost = 1.0 + (turn_pen if (d != -1 and d != nd) else 0.0)
                ng = g + cost
                k = (q, nd)
                if ng < best.get(k, 1e18) - 1e-9:
                    best[k] = ng
                    prev[k] = (cur, d)
                    h = abs(q[0] - e[0]) + abs(q[1] - e[1])
                    heapq.heappush(openq, (ng + h, ng, q, nd))
        return None


def _simplify(pts):
    """去掉共线的中间点，只留拐角。"""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-6:
            out.append((bx, by))
    out.append(pts[-1])
    return out


def length(path):
    tot = 0.0
    for i in range(len(path) - 1):
        tot += ((path[i + 1][0] - path[i][0]) ** 2 +
                (path[i + 1][1] - path[i][1]) ** 2) ** 0.5
    return tot


def route(pa, pb, rects, own, margin=0.3, step=1.0, pad=48.0):
    """两个门点之间的一条正交折线（含两端门点）；绕不出去返回 None。

    `own` = 两端房间在 `rects` 里的下标：它们只按**本体**阻挡（否则门点永远在障碍里）。
    """
    for extra in (0.0, 2.0):
        p = pad * (1.0 + extra)
        box = (min(pa[0], pb[0]) - p, min(pa[1], pb[1]) - p,
               max(pa[0], pb[0]) + p, max(pa[1], pb[1]) + p)
        g = _Grid(rects, own, box, step, margin)
        cells = g.astar(g.cell(pa), g.cell(pb))
        if not cells:
            continue
        pts = [(g.x0 + c[0] * step, g.y0 + c[1] * step) for c in cells]
        pts[0] = (pa[0], pa[1])
        pts[-1] = (pb[0], pb[1])
        pts = _simplify(pts)
        if any(seg_rect_hit(pts[i], pts[i + 1], rects[i2])
               for i in range(len(pts) - 1)
               for i2 in range(len(rects)) if i2 not in own):
            continue
        return [[round(x, 3), round(y, 3)] for (x, y) in pts]
    return None
