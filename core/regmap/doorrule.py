"""门属于哪条边：证据链 + 转角双记录 + 地图方位交叉验。

为什么需要这一层
----------------
旧规则是「贴边 ≤1 格 → 摄像机位移 → 房间中心」。用主人给的 8 扇标尺门一验，
只中 3 扇：

| 门 | 旧规则 | 主人 | 为什么旧规则错 |
|---|---|---|---|
| `UW_A01` (53,34) | 右 | 上 | 距上边 2 格，被 `tol=1` 卡掉，掉进摄像机分支 |
| `UW_D05` (215,1) | 下 | 右 | 声明宽 228，实心只到 215：门就在**有效右边界**上 |
| `UW_A06` (43,34) | 上 | 右 | 门在有效区右下角；两条边都≤容差，只记一条就丢了右 |
| `UW_A02` (55,34) | 上 | 上 | ✓ |

新规则（`door_side=auto`）按顺序取第一个成立的证据：

1. **通道**：门格上带对象 `3`（管道/通道口）。沿同一段通道走通，看门在这段通道的哪一端
   —— 段的走向就是出入口方向。这是最接近「玩家实际走的那个口」的证据。
2. **有效区**：用「实心格 ≥2 的行/列」包围盒代替声明尺寸。声明尺寸常含空白边距
   （D05 右边多 13 列），用声明尺寸算，最近边会永远是「下」。
3. **贴边**：`edge_tol`（默认 2）格以内直接取那条边。
4. **摄像机**：多台时取最近的一台，用「摄像机 → 门」的位移方向。
5. **房间中心**：兜底。

**转角双记录**：门到两条边都 ≤ `corner_tol`（默认 5）时，两条边都记下来
（`cands`，按距离排序）。布局优先用第一条，放不下时允许换第二条——A06 就是
「上」和「右」都成立，靠这一条才有机会落到右边。

**地图方位**：`map_side()` 用游戏内地图矩形算方位（y 向下）。它不直接决定布局，
只在候选边里挑：门说「上或右」、地图说「右」，就取右（A06 的结果）。
门与地图矛盾、且地图方位**不在**候选里时，标 `warn`（图上虚线、布局降权）。

拿地图当裁判的依据：把推断布局与地图矩形逐对比较，主轴方向 38/38 一致；
把地图 y 翻过来只剩 22/38。所以地图的朝向可信，翻轴反而错。

2026-11-21 补记（W3）：上面这套证据链本身没错，但**上下方向的极性全写反了**——
`_dists` / `classify` / `channel_side` / `exit_t` / `map_side` 五处一起反，
所以门一律落在镜像的那面墙上，而 `map_side` 也跟着反，两条错误证据互相"验证通过"。
拿主人标过的 `UW_A01 (53,34) = 上` 一验就露。修完：门边一致率 49.9% → 66.2%，
标尺门 4/4 命中，quad 中位 83.0 → 82.7。详见 `V1.10_W3_门位真值_落地记录.md`。
"""
from __future__ import annotations

from . import config
from .model import effective_bbox, room_objects

SIDES = ("L", "R", "U", "D")
OPP = {"L": "R", "R": "L", "U": "D", "D": "U"}

_OBJ = config.INTERNAL["channel_obj"]
_CH_MIN = config.INTERNAL["channel_min"]


def y_flip(opts=None):
    """门坐标是否需要"朝上"解释。**默认 False：房间格 y 与屏幕同向（向下）。**

    `y_axis` 的语义没变（1 = "y 小是上边"，也就是 y 向下），所以这里的返回值要取反：
    `y_axis=1` → 不翻；`y_axis=0` → 按"y 朝上"解释。

    2026-11-21 订正：原来默认按"y 朝上"解释，导致每扇门的上下边都判反——物件落点自洽性
    实测（珍珠/回响 97% 在对向才是空气、翻过来只剩 60%）证明坐标本来就与格子同向。
    """
    if not opts:
        return False
    try:
        return not bool(int(opts.get("y_axis", 1)))
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ 证据 1：通道

def channel_segment(room, x, y):
    """门所在的那段通道（四邻连通）；门格不是通道就返回 None。"""
    objs = room_objects(room)
    if not objs or _OBJ not in objs.get((x, y), ()):
        return None
    seg = set()
    stack = [(x, y)]
    while stack:
        cur = stack.pop()
        if cur in seg:
            continue
        seg.add(cur)
        cx, cy = cur
        for nxt in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if nxt in seg:
                continue
            if _OBJ in objs.get(nxt, ()):
                stack.append(nxt)
    return seg or None


_CLIMB = 6          # 可攀爬背景；「管道口」= 同格既有 3（管道）又有 6（背景）


def port_cell(room, x, y):
    """门格所在通道段的**管道口**格 `(x, y)`；不是通道 / 段太长找不到就 None。

    管道口 = 段里同时带 `3`（管道）与 `6`（可攀爬背景）的格——也就是管道从墙里伸出来、
    与空气/结构**接触**的那一格（房间卡里画成 T 形的就是它）。V1.25 №15：区域地图的
    门点从"框边界上的投影点"改到这一格，才是玩家实际走出去的位置。

    取**离门格最远**的那个口：一条通道偶尔有两头都带 6（穿墙两侧都是可攀爬面），
    远端那个才是房间里的口。段里没有 `3+6` 时退回段末端（管道尽头），仍然比框边界准。
    """
    seg = channel_segment(room, x, y)
    if not seg:
        return None
    objs = room_objects(room)
    ports = [q for q in seg if _OBJ in (objs.get(q) or ()) and _CLIMB in (objs.get(q) or ())]
    pool = ports or list(seg)
    return max(pool, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)


def channel_side(room, x, y, flip=True):
    """→ (side, conf) / None。方向 = 门相对这段通道质心的位移主轴。"""
    seg = channel_segment(room, x, y)
    if not seg or len(seg) < _CH_MIN:
        return None
    cx = sum(p[0] for p in seg) / float(len(seg))
    cy = sum(p[1] for p in seg) / float(len(seg))
    dx, dy = x - cx, y - cy
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return None
    if abs(dx) >= abs(dy):
        return ("R" if dx > 0 else "L"), 0.95
    if flip:
        return ("U" if dy > 0 else "D"), 0.95      # 格 y 朝上：dy>0 = 更靠上
    return ("D" if dy > 0 else "U"), 0.95


# ---------------------------------------------------------------- 证据 2：有效区

def effective_bounds(room):
    """有效区 = 「实心格 ≥2 的行/列」的包围盒，不是声明尺寸。

    声明尺寸常含空白边距：UW_D05 声明 228 宽，实心只到 215（右边 13 列是空的）。
    用声明尺寸算最近边，那扇门永远是「下」——主人说的「再怎么招也不会判下」。

    实现在 `model.effective_bbox()`（房间外框与缩略图裁切也用它），这里只做转发。
    """
    return effective_bbox(room)


def _dists(room, x, y, flip=True):
    """门到四条边的距离（格）。用有效区；没有有效区就退回声明尺寸。

    `flip=True`（默认）表示格 y 朝上：y 小的一侧是**下**边、y 大的一侧是上边。
    """
    bb = effective_bounds(room)
    if bb:
        x0, y0, x1, y1 = bb
    else:
        x0, y0, x1, y1 = 0, 0, room.w - 1, room.h - 1
    if flip:
        # y 朝上：y0 是底边、y1 是顶边
        return {"L": abs(x - x0), "R": abs(x1 - x), "U": abs(y1 - y), "D": abs(y - y0)}
    # y 向下（默认）：y0 是顶边、y1 是底边
    return {"L": abs(x - x0), "R": abs(x1 - x), "U": abs(y - y0), "D": abs(y1 - y)}


def _edge_from_dists(d):
    """按距离排序；平局按「先左右后上下」（雨世界水平出口比垂直多）。"""
    order = sorted(d.items(), key=lambda kv: (kv[1], "LRUD".index(kv[0])))
    return order[0][0], order


def effective_side(room, x, y, tol, flip=True):
    side, order = _edge_from_dists(_dists(room, x, y, flip))
    if order[0][1] > tol:
        return None
    return side, order[0][1]


def declared_side(room, x, y, tol, flip=True):
    """旧规则：贴声明尺寸的边。保留是为了 `door_side=edge` 时对照。"""
    if flip:
        d = {"L": x, "R": room.w - 1 - x, "U": y, "D": room.h - 1 - y}
    else:
        d = {"L": x, "R": room.w - 1 - x, "D": y, "U": room.h - 1 - y}
    side, order = _edge_from_dists(d)
    if order[0][1] > tol:
        return None
    return side, order[0][1]


# ---------------------------------------------------------------- 证据 3/4：摄像机

def _nearest_camera(room, x, y):
    best = None
    best_d = None
    for (cx, cy) in room.cameras:
        dx = (x + 0.5) - cx
        dy = (y + 0.5) - cy
        d2 = dx * dx + dy * dy
        if best_d is None or d2 < best_d:
            best_d, best = d2, (cx, cy)
    return best


def classify(dx, dy, flip=True):
    """斜向归类：主轴决定方向，归一化后的偏心率当置信度。"""
    adx, ady = abs(dx), abs(dy)
    if adx == 0 and ady == 0:
        return "R", 0.5
    if adx >= ady:
        side = "R" if dx > 0 else "L"
        conf = 0.5 + 0.5 * (1.0 - ady / adx) if adx else 0.5
    else:
        if flip:
            # 格 y 朝上：dy>0 = 门在参照物**上方**，屏幕上也还是上方（U）。
            # 2026-11-21 修：原来这里写反了，导致门一律落在上下镜像的那面墙上
            # （用主人标过的那扇 `UW_A01`「上」验出来的）。
            side = "U" if dy > 0 else "D"
        else:
            side = "D" if dy > 0 else "U"
        conf = 0.5 + 0.5 * (1.0 - adx / ady) if ady else 0.5
    return side, round(conf, 3)


def camera_side(room, x, y, flip=True):
    cam = _nearest_camera(room, x, y)
    if cam is None:
        return None
    side, conf = classify((x + 0.5) - cam[0], (y + 0.5) - cam[1], flip)
    return side, conf


def center_side(room, x, y, flip=True):
    side, conf = classify((x + 0.5) - room.w * 0.5, (y + 0.5) - room.h * 0.5, flip)
    return side, round(conf * 0.6, 3)


# ------------------------------------------------------------------ 组合

def exit_t(room, ex, side, flip=True):
    """门在那条边上的相对位置 0..1（屏幕坐标：0 = 左/上）。

    门常常贴角：投影到另一条边时会得到 0 或 1 附近的值——这正是「贴着那个角」的意思。
    归一化用**有效区**：房间外框既然按有效区画，门位也必须按同一个框算，否则门会跑偏。
    """
    x, y = ex[0], ex[1]
    bb = effective_bbox(room)
    x0, y0, x1, y1 = bb if bb else (0, 0, room.w - 1, room.h - 1)
    if side in ("L", "R"):
        t = (y - y0 + 0.5) / max(1.0, float(y1 - y0 + 1))   # 格 y 朝上：0 = 底
        # 屏幕 t 的 0 = 顶，所以要翻过来（2026-11-21 修，同 `_dists`）
        return min(1.0, max(0.0, 1.0 - t if flip else t))
    t = (x - x0 + 0.5) / max(1.0, float(x1 - x0 + 1))
    return min(1.0, max(0.0, t))


def candidates(room, x, y, corner_tol, flip=True):
    """门可以落在哪些边上（按距离升序）。转角门会有两条。"""
    _side, order = _edge_from_dists(_dists(room, x, y, flip))
    out = [s for (s, d) in order if d <= corner_tol]
    return out or [order[0][0]]


def evidence(room, ex, opts=None):
    """一条出口 → 完整判边证据（dict）。

    字段：`side`（首选边）、`cands`（候选边，含首选）、`dist`、`t`、`src`、
    `alt`（次选边，没有就是 None）、`detail`（各条证据各自的结论，调试用）。
    """
    o = opts or {}
    mode = o.get("door_side", "auto")
    tol = int(o.get("edge_tol", 2))
    ctol = int(o.get("corner_tol", 5))
    flip = y_flip(o)
    x, y = ex[0], ex[1]

    chain = {
        "channel": channel_side(room, x, y, flip),
        "effective": effective_side(room, x, y, tol, flip),
        "edge": declared_side(room, x, y, tol, flip),
        "camera": camera_side(room, x, y, flip),
    }
    orders = {
        "auto": ("channel", "effective", "edge", "camera"),
        "channel": ("channel", "effective", "edge", "camera"),
        "effective": ("effective", "edge", "camera"),
        "edge": ("edge", "camera"),
        "camera": ("camera",),
    }.get(mode, ("channel", "effective", "edge", "camera"))

    side = src = None
    conf = 0.0
    for name in orders:
        got = chain.get(name)
        if not got:
            continue
        side, conf = got
        src = name
        break
    if side is None:
        side, conf = center_side(room, x, y, flip)
        src = "center"

    cands = candidates(room, x, y, ctol, flip)
    if side not in cands:
        cands = [side] + cands
    d = _dists(room, x, y, flip)
    return {
        "side": side,
        "alt": cands[1] if len(cands) > 1 else None,
        "cands": cands,
        "dist": d.get(side, 0),
        "t": exit_t(room, ex, side, flip),
        "conf": conf,
        "src": src,
        "detail": {k: (v[0] if v else None) for k, v in chain.items()},
    }


def side_of(room, ex, opts=None):
    """只要方向（兼容旧调用）。"""
    return evidence(room, ex, opts)["side"]


# ------------------------------------------------------------------ 地图方位

def map_side(room, other, flip=True):
    """→ (side, ratio) / (None, None)。

    **仅供诊断/对照，不得用于布局决策**（2026-11-21 主人定案：`map_image` 的图标矩形
    不是给玩家看的那张图，每间房压成固定图标、整张再压进画布，长宽比失真）。
    布局侧的方位改由门位合成（`engine_zq._pair_dir`）。

    地图矩形 y **向下**（与屏幕同向，见 `model.Room` 的坐标约定）。
    """
    ra, rb = room.map_rect, other.map_rect
    if not ra or not rb:
        return None, None
    dx = (rb[0] + rb[2] * 0.5) - (ra[0] + ra[2] * 0.5)
    dy = (rb[1] + rb[3] * 0.5) - (ra[1] + ra[3] * 0.5)
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None, None
    mx, my = max(abs(dx), abs(dy)), min(abs(dx), abs(dy))
    ratio = round(my / mx, 2) if mx else 0.0
    if abs(dx) >= abs(dy):
        return ("R" if dx > 0 else "L"), ratio
    if flip:
        # `map_rect` 的 y **向下**（与屏幕一致，见 model.Room 的坐标约定）：
        # dy>0 表示对方在地图更下方 → 这边的门在底边（D）。
        # 2026-11-21 修：原来这里也写反了，和门那四条证据一起错，所以互相"验证通过"。
        return ("D" if dy > 0 else "U"), ratio
    return ("U" if dy > 0 else "D"), ratio
