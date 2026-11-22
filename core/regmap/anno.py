"""W4 标注层：**只剩子区域色与子区域名**。

2026-11-21 夜 №2 定案：房间类型图标（庇护所/哨站/蝠蝇巢/宝库）、物件（回响/传送点/珍珠）、
业力门徽标**全部下线**——`ICONS` / `TAG_KIND` / `OBJ_MARK` / `room_kind` / `room_marks` /
`room_gates` 连同 `svg.py` 那边 200 多行图标渲染一起删了，不是开关掉。

这里只给每个节点挂一个 `anno` 字典 `{"sub": 名字, "sc": 颜色}`，`svg.py` 按它划子区域名
的位置（颜色本身在 №4 之后已经当作"可通行底色"下发，见 `colors.py`）。

**被删掉的三类数据源解析代码留在别处，只是不再挂节点**（不可见 ≠ 删数据）：
· 房间标签 `Room.tags`（`model._layer_world_tags`）——将来按房间类型筛选还要用；
· 放置物 `_settings.txt` 的 `PlacedObjects:` 解析（`fx.placed_objects`）——同上；
· 业力门锁 `gates/locks.txt`（`model._gate_locks`）——房间卡的门信息仍在用。

**不要再往 `anno` 里加字段**：`svg.py` 已经没有任何图标渲染代码，加了只是白占载荷。
"""
from __future__ import annotations

# 子区域色：默认的饱和度 / 明度。缩略图只有 1–3 px 一格，色块要压得很淡，
# 所以真正的透明度在 `svg.py` 里给（`SUB_ALPHA`），这里只定色相。
SUB_SAT = 0.38
SUB_LIGHT = 0.52


def sub_color(name):
    """子区域名 → 稳定的十六进制色。同名永远同色（跨区域也一样）。"""
    h = 0
    for ch in str(name):
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    hue = (h * 47) % 360           # 乘一个大质数，让相邻名字的色相拉开
    return _hsl(hue / 360.0, SUB_SAT, SUB_LIGHT)


def _hsl(h, s, l):
    def k(n):
        return (n + h * 12.0) % 12.0
    a = s * min(l, 1.0 - l)

    def f(n):
        return l - a * max(-1.0, min(k(n) - 3.0, min(9.0 - k(n), 1.0)))
    return "#%02x%02x%02x" % (int(round(f(0) * 255)), int(round(f(8) * 255)),
                              int(round(f(4) * 255)))


def _sub_is_default(sub, region):
    """区域自己的名字（英文/中文）当子区域时不算「子区域」，不然整张图会被染成一片。"""
    if not sub:
        return True
    low = str(sub).strip().lower()
    for key in ("displayName", "nameZh", "name"):
        other = str(region.get(key) or "").strip().lower()
        if other and low == other:
            return True
    return False


def attach(nodes, region, opts=None) -> int:
    """给布局节点挂 `anno`（只挂 `sub` / `sc`）；返回挂上的节点数。

    `opts` 只认 `sub`（`0` = 关）。旧调用方传 `{"kind": …, "marks": …, "gates": …}`
    不会报错，但**什么也不会发生**——那三类已在 №2 删掉，`svg.py` 也没有渲染代码了。
    全关时一个 `anno` 也不挂，载荷与 W4 之前一样。
    """
    o = {"sub": 1}
    o.update(opts or {})
    if not o.get("sub"):
        return 0

    # 一个区只有一个子区域（或那个子区域就是区域名）时，上色没有意义，整层关掉
    subs = {n.get("sub") for n in nodes or [] if n.get("sub")}
    subs = {s for s in subs if not _sub_is_default(s, region or {})}
    if not subs:
        return 0

    got = 0
    for node in nodes or []:
        if node.get("room") is None:
            continue
        sub = node.get("sub")
        if not sub or sub not in subs:
            continue
        node["anno"] = {"sub": sub, "sc": node.get("subColor") or sub_color(sub)}
        got += 1
    return got
