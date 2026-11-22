"""临时探针：布局结果 vs 门边证据，相对位置对不对得上？

对每条边：
  · 期望 = 两端出口判出的边（D→a 在 b 上面，R→a 在 b 左边…）；两端冲突就当"无期望"；
  · 实际 = 布局矩形（y 向下）。
分竖/横、分区统计，并列出不一致的边（给主人看的那些）。

用法：python build/_layout_rel_probe.py CC SU HI
"""
from __future__ import annotations

import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regmap import adapter, doorrule          # noqa: E402


def side_rel(side):
    """a 的门在哪面墙 → 邻居在 a 的哪边。"""
    return {"D": ("v", "a_above_b"), "U": ("v", "a_below_b"),
            "R": ("h", "a_left_b"), "L": ("h", "a_right_b")}.get(side)


def run(code):
    lay = adapter.build(code)
    rect = {n["name"].upper(): (n["x"], n["y"], n["w"], n["h"]) for n in lay["nodes"]}
    by = {n["name"].upper(): n["room"] for n in lay["nodes"]}
    stat = collections.Counter()
    bad = []
    for e in lay["edges"]:
        an, bn = e["a"].upper(), e["b"].upper()
        if an not in rect or bn not in rect:
            continue
        ra, rb = rect[an], rect[bn]
        # 门边证据（两端都用同一份出口数据里各自的出口）
        sa = e.get("door_a") or e.get("side_a")
        sb = e.get("door_b") or e.get("side_b")
        ga = side_rel(sa)
        gb = side_rel(sb)
        if not ga or not gb or ga[0] != gb[0]:
            stat["no_expect"] += 1
            continue
        axis = ga[0]
        # 两端必须互相印证：a 认为邻居在下/右，b 就要认为邻居在上/左
        opp = {"a_above_b": "a_below_b", "a_below_b": "a_above_b",
               "a_left_b": "a_right_b", "a_right_b": "a_left_b"}[ga[1]]
        if gb[1] != opp:
            stat["conflict"] += 1
            continue
        ax = ra[0] + ra[2] * 0.5
        ay = ra[1] + ra[3] * 0.5
        bx = rb[0] + rb[2] * 0.5
        by_ = rb[1] + rb[3] * 0.5
        if axis == "v":
            act = "a_above_b" if ay < by_ else "a_below_b"
        else:
            act = "a_left_b" if ax < bx else "a_right_b"
        stat["edges"] += 1
        stat[axis] += 1
        key = "ok" if act == ga[1] else "bad"
        stat[key + "_" + axis] += 1
        if key == "bad":
            bad.append((an, bn, sa, sb, axis))
    return stat, bad


def main():
    codes = sys.argv[1:] or ["CC", "SU", "HI", "GW", "MS"]
    tot = collections.Counter()
    print("%-5s %5s | %8s %8s | %8s %8s | 举例" % ("区", "边", "竖对", "竖错", "横对", "横错"))
    for code in codes:
        st, bad = run(code)
        for k, v in st.items():
            tot[k] += v
        print("%-5s %5d | %8d %8d | %8d %8d | %s" % (
            code, st["edges"], st["ok_v"], st["bad_v"], st["ok_h"], st["bad_h"],
            ", ".join("%s→%s(%s/%s)" % (b[0], b[1], b[2], b[3]) for b in bad[:2])))
    print("-" * 78)
    ev = tot["ok_v"] + tot["bad_v"] + tot["ok_h"] + tot["bad_h"]
    print("合计：%d 边有期望，其中 %d 对 %d 错（%.1f%% 对）；竖 %d/%d，横 %d/%d；"
          "两端冲突 %d，无期望 %d" % (
              ev, tot["ok_v"] + tot["ok_h"], tot["bad_v"] + tot["bad_h"],
              (tot["ok_v"] + tot["ok_h"]) * 100.0 / max(1, ev),
              tot["ok_v"], tot["ok_v"] + tot["bad_v"],
              tot["ok_h"], tot["ok_h"] + tot["bad_h"],
              tot["conflict"], tot["no_expect"]))


if __name__ == "__main__":
    main()
