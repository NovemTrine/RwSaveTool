"""№1 验收：门位 y 方向（2026-11-21）。

守的是这条**内部事实**，不依赖任何地图图片或世界坐标：

- 物件坐标的 y 与地形格**同向（y 向下，row 0 = 图顶）**；
- 所以出口应落在实心格里（门开在墙里），珍珠/回响/传送点应落在空气里；
- 一旦有人再给它翻一次，上面两条会立刻掉下去（实测翻一次：出口 97%→88%、物件 97%→60%）；
- 并且 `CC_B01` 必须在 `CC_B06` 上方（主人点名的那一对）。

跑法：

    python build/check_regmap_doorpolarity.py            # 抽样 8 区，几秒
    python build/check_regmap_doorpolarity.py --all      # 全库
    python build/check_regmap_doorpolarity.py CC SU      # 指定区
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.regmap import adapter                    # noqa: E402

FAILS = []
SAMPLE = ["CC", "SU", "HI", "GW", "MS", "SL", "LF", "UW"]
OPP = {"U": "D", "D": "U", "L": "R", "R": "L"}
# 「应该落在空气里」的物件编号：7 / 8 / 11 实测 100% / 89% / 99.7% 在空气格上，
# 是珍珠 / 回响 / 传送点这一类。5 / 9 / 10 / 12 是**挂在墙上**的（实测 90%+ 在实心格），
# 不能拿它们判方向——那不是翻转，是语义如此。
AIR_CODES = {7, 8, 11}


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)
    print(("  OK  " if ok else "  FAIL") + " " + msg)


def scan(code):
    """→ (出口落墙率, 物件落空气率, 两端互逆率, 房间数)"""
    reg = adapter.load_rooms(code)
    rooms = reg["rooms"]
    by = {r.name.upper(): r for r in rooms}
    ex_solid = ex_n = mk_air = mk_n = 0
    both = ok = 0
    for r in rooms:
        w, h = r.w, r.h
        if not r.objs:
            continue
        for (x, y), codes in r.objs.items():
            if not (0 <= x < w and 0 <= y < h):
                continue
            solid = r.cells[y * w + x] != "0"
            s = set(codes)
            if 4 in s:                          # 出口：门开在墙里
                ex_n += 1
                ex_solid += 1 if solid else 0
            elif s & AIR_CODES:                 # 珍珠/回响/传送点：摆在能走的地方
                mk_n += 1
                mk_air += 0 if solid else 1
        for (x, y, to) in (r.exits or []):
            b = by.get(str(to or "").upper())
            if not b or b is r:
                continue
            back = [(bx, byy) for (bx, byy, t) in (b.exits or [])
                    if str(t).upper() == r.name.upper()]
            if not back:
                continue
            sa = _side(r, x, y)
            sb = _side(b, back[0][0], back[0][1])
            both += 1
            ok += 1 if OPP[sa] == sb else 0
    return (ex_solid, ex_n, mk_air, mk_n, ok, both, len(rooms))


def _side(r, x, y):
    """按"y 向下"算门在哪条边（与 `doorrule._dists` 的默认口径一致）。"""
    w, h = r.w, r.h
    d = {"L": x, "R": w - 1 - x, "U": y, "D": h - 1 - y}
    return min(d.items(), key=lambda kv: (kv[1], "LRUD".index(kv[0])))[0]


def main(argv=None):
    args = [a for a in (argv if argv is not None else sys.argv[1:]) if not a.startswith("-")]
    if "--all" in (argv if argv is not None else sys.argv[1:]):
        codes = sorted(os.path.splitext(f)[0].upper()
                       for f in os.listdir(os.path.join(ROOT, "region_data"))
                       if f.lower().endswith(".json") and not f.startswith("_"))
    else:
        codes = [c.upper() for c in args] or SAMPLE

    print("区     房间  出口落墙   物件落空气   两端互逆")
    tot = [0] * 6 + [0]
    for code in codes:
        try:
            got = scan(code)
        except Exception as exc:                   # noqa: BLE001
            FAILS.append("%s 扫描抛异常：%r" % (code, exc))
            continue
        for i, v in enumerate(got):
            tot[i] += v
        print("%-5s %4d  %5.1f%%     %5.1f%%      %5.1f%%" % (
            code, got[6], 100.0 * got[0] / max(1, got[1]), 100.0 * got[2] / max(1, got[3]),
            100.0 * got[4] / max(1, got[5])))

    ex = 100.0 * tot[0] / max(1, tot[1])
    mk = 100.0 * tot[2] / max(1, tot[3])
    bi = 100.0 * tot[4] / max(1, tot[5])
    print("-" * 62)
    print("合计：出口 %d/%d=%.1f%%  物件 %d/%d=%.1f%%  互逆 %d/%d=%.1f%%"
          % (tot[0], tot[1], ex, tot[2], tot[3], mk, tot[4], tot[5], bi))

    expect(ex >= 95.0, "出口落在实心格的比例 %.1f%%（应 ≥95，低了说明 y 又被翻了一次）" % ex)
    expect(mk >= 92.0, "珍珠/回响/传送点落在空气格的比例 %.1f%%（应 ≥92；翻一次只剩 60%%）" % mk)
    expect(bi >= 75.0, "两端门互逆率 %.1f%%（应 ≥75；它对这个镜像免疫，只作健康度）" % bi)

    # 点名验收
    if "CC" in codes:
        lay = adapter.build("CC")
        n = {x["name"]: x for x in lay["nodes"]}
        a, b = n.get("CC_B01"), n.get("CC_B06")
        expect(a is not None and b is not None, "CC 里能找到 CC_B01 / CC_B06")
        if a and b:
            expect(a["y"] < b["y"], "CC_B01 必须在 CC_B06 上方（y %.1f vs %.1f）"
                   % (a["y"], b["y"]))
            expect(lay["stats"].get("overlaps") == 0,
                   "CC 布局出现重叠：%s" % (lay["stats"].get("overlaps"),))

    if FAILS:
        print("\nFAIL %d 条：" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("\nCHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
