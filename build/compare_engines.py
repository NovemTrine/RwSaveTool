"""W2 · 两个引擎对拍：`legacy` vs `zq`。

    .venv/Scripts/python.exe build/compare_engines.py              # 全部有真值的区
    .venv/Scripts/python.exe build/compare_engines.py SL MS HI     # 指定区
    .venv/Scripts/python.exe build/compare_engines.py --all        # 连无真值的区一起（只比重叠/耗时）
    .venv/Scripts/python.exe build/compare_engines.py --md out.md  # 写报告

口径与 `check_regmap_shape.py` 完全一致（quad 取上下翻转后较高的那个，
只统计同一连通分量内），所以两边的分数可以直接和 W0/V1.10 的基线比。

另外记三个 zq 特有的量：
  · `overlaps`：残余重叠对数（W2 的硬指标，必须 0）
  · `ms`：布局耗时（目标 ≤ 2 s）
  · `gap_med`：相邻房间的缝中位数（太小会「粘成一片」，太大会散）
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "build"))

import check_regmap_shape as S            # noqa: E402
from core.regmap import adapter, build_rooms   # noqa: E402


def layout(code, engine):
    region = adapter.load_rooms(code)
    rooms = region["rooms"]
    t0 = time.perf_counter()
    res = build_rooms(rooms, region=region, code=code, prepare=False, opts={"engine": engine})
    return res, (time.perf_counter() - t0) * 1000.0


def quad_of(res, truth):
    nodes, edges = res["nodes"], res["edges"]
    if not nodes or not truth:
        return None
    pred = S._centers(nodes)
    adjacent = [(e["a"].upper(), e["b"].upper()) for e in edges]
    comp = S._components(nodes, edges)
    common = [k for k in pred if k in truth]
    if len(common) < 4:
        return None
    near = S._near_threshold([truth[k] for k in common], S.NEAR_FRAC)
    dn = S._compare(pred, truth, adjacent, near, False, comp)
    up = S._compare(pred, truth, adjacent, near, True, comp)
    return max(dn["quad"], up["quad"])


def gap_median(res):
    nodes = res["nodes"]
    rect = {n["name"]: [n["x"], n["y"], n["w"], n["h"]] for n in nodes}
    gaps = []
    for e in res["edges"]:
        a, b = rect.get(e["a"]), rect.get(e["b"])
        if not a or not b:
            continue
        dx = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
        dy = max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3])
        g = max(dx, dy)
        if 0 <= g < 200:
            gaps.append(g)
    return round(statistics.median(gaps), 1) if gaps else None


def main(argv=None):
    args = list(argv or sys.argv[1:])
    do_all = "--all" in args
    md = ""
    if "--md" in args:
        i = args.index("--md")
        md = args[i + 1]
        args = args[:i] + args[i + 2:]
    codes = [a.upper() for a in args if not a.startswith("--")] or S.all_codes()

    rows = []
    print("%-5s %6s %6s %6s | %5s %5s %7s %6s" %
          ("区", "房", "legacy", "zq", "重叠", "缝", "zq ms", "差"))
    for code in codes:
        try:
            truth = None
            data = json.load(open(adapter.region_path(code), encoding="utf-8"))
            src = ((data.get("layers") or [{}])[0].get("source") or {})
            truth, _ = S.truth_map(src, code)
        except Exception:                     # noqa: BLE001
            truth = None
        if not truth and not do_all:
            continue
        try:
            r1, ms1 = layout(code, "legacy")
            r2, ms2 = layout(code, "zq")
        except Exception as exc:              # noqa: BLE001
            print("%-5s 失败 %s" % (code, exc))
            continue
        q1 = quad_of(r1, truth) if truth else None
        q2 = quad_of(r2, truth) if truth else None
        rows.append({
            "code": code, "rooms": len(r1["nodes"]),
            "q_legacy": q1, "q_zq": q2,
            "ov_legacy": r1["stats"].get("overlaps"), "ov_zq": r2["stats"].get("overlaps"),
            "ms_legacy": round(ms1), "ms_zq": round(ms2),
            "gap_legacy": gap_median(r1), "gap_zq": gap_median(r2),
        })
        flag = ""
        if q1 is not None and q2 is not None:
            d = q2 - q1
            flag = "%+5.1f" % d
        print("%-5s %6d %6s %6s | %5s %5s %7d %6s" %
              (code, len(r1["nodes"]),
               "%.1f" % q1 if q1 is not None else "-",
               "%.1f" % q2 if q2 is not None else "-",
               r2["stats"].get("overlaps"), gap_median(r2), ms2, flag))

    both = [r for r in rows if r["q_legacy"] is not None and r["q_zq"] is not None]
    print("\n== 汇总 ==")
    print("  区域 %d（可比 quad %d）" % (len(rows), len(both)))
    if both:
        q1 = [r["q_legacy"] for r in both]
        q2 = [r["q_zq"] for r in both]
        win = sum(1 for r in both if r["q_zq"] > r["q_legacy"] + 0.05)
        lose = sum(1 for r in both if r["q_zq"] < r["q_legacy"] - 0.05)
        print("  quad 中位：legacy %.1f → zq %.1f（%+.1f）"
              % (statistics.median(q1), statistics.median(q2),
                 statistics.median(q2) - statistics.median(q1)))
        print("  quad 均值：legacy %.1f → zq %.1f（%+.1f）"
              % (statistics.mean(q1), statistics.mean(q2),
                 statistics.mean(q2) - statistics.mean(q1)))
        print("  zq 赢 %d 区 / 输 %d 区 / 平 %d 区" % (win, lose, len(both) - win - lose))
    print("  重叠：legacy %d 区非零 / zq %d 区非零"
          % (sum(1 for r in rows if r["ov_legacy"]), sum(1 for r in rows if r["ov_zq"])))
    if rows:
        ms = [r["ms_zq"] for r in rows]
        print("  耗时 zq：中位 %d ms，最慢 %d ms（%s）"
              % (statistics.median(ms), max(ms),
                 max(rows, key=lambda r: r["ms_zq"])["code"]))
        g = [r["gap_zq"] for r in rows if r["gap_zq"] is not None]
        if g:
            print("  缝（zq）中位 %.1f，最小 %.1f" % (statistics.median(g), min(g)))

    if md:
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("| 区 | 房间 | legacy quad | zq quad | 差 | zq 重叠 | zq 缝 | zq ms |\n")
            fh.write("|---|---|---|---|---|---|---|---|\n")
            for r in sorted(rows, key=lambda x: (x["q_zq"] or -1) - (x["q_legacy"] or -1)):
                d = ("%+.1f" % (r["q_zq"] - r["q_legacy"])
                     if r["q_zq"] is not None and r["q_legacy"] is not None else "-")
                fh.write("| %s | %d | %s | %s | %s | %s | %s | %d |\n" % (
                    r["code"], r["rooms"],
                    "%.1f" % r["q_legacy"] if r["q_legacy"] is not None else "-",
                    "%.1f" % r["q_zq"] if r["q_zq"] is not None else "-",
                    d, r["ov_zq"], r["gap_zq"], r["ms_zq"]))
        print("\n表已写:", md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
