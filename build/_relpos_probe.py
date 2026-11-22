"""临时探针：门边证据 vs 游戏内地图矩形，谁说的相对位置对？

对每条边取两端出口判出的边（L/R/U/D），推出"谁在谁上面/左边"，
再和 `map_<reg>.txt` 的地图矩形比。两种 y 极性各跑一遍。

用法：python build/_relpos_probe.py [区代码…]
"""
from __future__ import annotations

import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regmap import adapter, doorrule          # noqa: E402

UP = {"U", "D"}


def implied(side_a):
    """a 的门在 side_a 那面墙上 → b 在 a 的哪边。返回 'a_above_b' / 'a_left_b' / None。"""
    if side_a == "D":      # 门在下墙 → 出去往下 → b 在 a 下面
        return "a_above_b"
    if side_a == "U":
        return "a_below_b"
    if side_a == "R":
        return "a_left_b"
    if side_a == "L":
        return "a_right_b"
    return None


def actual(ra, rb, axis):
    """地图口径（y 向下）：返回 a 相对 b 的位置。"""
    if not ra.map_rect or not rb.map_rect:
        return None
    ay = ra.map_rect[1] + ra.map_rect[3] * 0.5
    by = rb.map_rect[1] + rb.map_rect[3] * 0.5
    ax = ra.map_rect[0] + ra.map_rect[2] * 0.5
    bx = rb.map_rect[0] + rb.map_rect[2] * 0.5
    if axis == "v":
        if abs(ay - by) < 1e-6:
            return None
        return "a_above_b" if ay < by else "a_below_b"
    if abs(ax - bx) < 1e-6:
        return None
    return "a_left_b" if ax < bx else "a_right_b"


def run(code, y_axis):
    reg = adapter.load_rooms(code)
    by = {r.name.upper(): r for r in reg["rooms"]}
    opts = {"y_axis": y_axis}
    stat = collections.Counter()
    for a in reg["rooms"]:
        for (x, y, to) in a.exits:
            b = by.get(str(to or "").upper())
            if b is None or b is a:
                continue
            if a.name.upper() > b.name.upper():        # 每条边只算一次
                continue
            ev = doorrule.evidence(a, (x, y), opts)
            side = ev.get("side")
            rel = implied(side)
            if not rel:
                stat["no_side"] += 1
                continue
            axis = "v" if side in UP else "h"
            act = actual(a, b, axis)
            if act is None:
                stat["no_map"] += 1
                continue
            stat["edges"] += 1
            stat[axis] += 1
            if act == rel:
                stat["ok_" + axis] += 1
            elif {act, rel} == {"a_above_b", "a_below_b"} or \
                    {act, rel} == {"a_left_b", "a_right_b"}:
                stat["flip_" + axis] += 1        # 正好相反（镜像）
            else:
                stat["cross_" + axis] += 1       # 方向都不同（对角）
    return stat


def main():
    codes = sys.argv[1:] or ["CC", "SU", "HI", "GW", "MS", "SL", "LF", "UW"]
    print("%-5s %6s %6s | %-22s | %-22s" % ("区", "边", "", "y_axis=1（当前）", "y_axis=0（反转）"))
    print("%-5s %6s %6s | %6s %6s %6s | %6s %6s %6s" %
          ("", "", "", "竖一致", "竖镜像", "横一致", "竖一致", "竖镜像", "横一致"))
    tot = collections.Counter()
    for code in codes:
        s1 = run(code, 1)
        s0 = run(code, 0)
        for k, v in s1.items():
            tot["1_" + k] += v
        for k, v in s0.items():
            tot["0_" + k] += v
        print("%-5s %6d %6s | %6d %6d %6d | %6d %6d %6d" % (
            code, s1["edges"], "",
            s1["ok_v"], s1["flip_v"], s1["ok_h"],
            s0["ok_v"], s0["flip_v"], s0["ok_h"]))
    print("-" * 70)
    print("合计 y_axis=1: 竖 %d 一致 / %d 镜像 / %d 对角；横 %d 一致 / %d 镜像 / %d 对角（边 %d）" % (
        tot["1_ok_v"], tot["1_flip_v"], tot["1_cross_v"],
        tot["1_ok_h"], tot["1_flip_h"], tot["1_cross_h"], tot["1_edges"]))
    print("合计 y_axis=0: 竖 %d 一致 / %d 镜像 / %d 对角；横 %d 一致 / %d 镜像 / %d 对角（边 %d）" % (
        tot["0_ok_v"], tot["0_flip_v"], tot["0_cross_v"],
        tot["0_ok_h"], tot["0_flip_h"], tot["0_cross_h"], tot["0_edges"]))


if __name__ == "__main__":
    main()
