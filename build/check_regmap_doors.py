"""W3 门位真值：把 map_*.txt 的 Connection 与房间出口格合成一张表，并报误差。

    .venv/Scripts/python.exe build/check_regmap_doors.py            # 全量（约几分钟）
    .venv/Scripts/python.exe build/check_regmap_doors.py SL HI UW   # 指定区域
    .venv/Scripts/python.exe build/check_regmap_doors.py SL --dump  # 打印每扇门
    .venv/Scripts/python.exe build/check_regmap_doors.py --json out.json

## 三个口径（都是实测标定，2026-11-21 夜）

1. **map Connection 的坐标是房间格坐标**（原点左下、y 向上），但它是**隧道内端**，
   不是墙上的开口：从开口沿隧道向内通常 4–12 格。所以它只能用来定**沿墙坐标**。
   实测：`SL_A02→SL_C01` 开口 (0,7)、map (10,28)[y 向下] → 换算 y 向上得 (10,6)，
   沿墙 y 差 1 格，内深 10 格。
2. **y 是向下**（屏幕口径）：换算 `y_up = h-1-y_map`。用 8 个已知门校验，
   不翻的话 100% 对不上，翻了 85% 完全相等。
3. **`dir` 字段不能当方位用**：`SL_A02` 三扇门分在左/右/上三种墙，dir 全是 3。
   所以方位改用「开口格 + map 点的内深方向」判定，只把 dir 记进表里当参考。

## 判定一条门端

对候选的每条边 S：`along_err = |开口沿墙坐标 - map 沿墙坐标|`，
`depth` = map 点在 S 方向上的内深（负数=跑到墙外了）。
取 `along_err` 最小、且 `depth` 落在 [0, 25] 的那条；都对不上就记 `unresolved`。
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import official_world                    # noqa: E402
from core.regmap import adapter                    # noqa: E402

SIDES = ("L", "R", "U", "D")
OPP = {"L": "R", "R": "L", "U": "D", "D": "U"}


def world_dirs() -> list[str]:
    out = []
    for inst in official_world.find_installations():
        for pack in inst.get("packs") or []:
            d = pack.get("worldDir")
            if d and d not in out:
                out.append(d)
    return out


WDIRS = world_dirs()


def map_file(code: str) -> str:
    for d in reversed(WDIRS):
        p = os.path.join(d, code.lower(), "map_%s.txt" % code.lower())
        if os.path.isfile(p):
            return p
    return ""


def parse_map(path: str):
    """→ (conns, ok)；conns = [(a, b, (xa,ya), (xb,yb), dir_a, dir_b)]（坐标 y 向下）"""
    conns = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("Connection:"):
                continue
            f = line[len("Connection:"):].strip().split(",")
            if len(f) < 8:
                continue
            try:
                conns.append((f[0].upper(), f[1].upper(),
                              (int(f[2]), int(f[3])), (int(f[4]), int(f[5])),
                              int(f[6]), int(f[7])))
            except ValueError:
                continue
    return conns


def _pick_side(mark, mp, w, h):
    """开口格 + map 内端点 → (side, along_err, depth)；判不出来返回 None。

    返回的 side 在**房间格坐标（y 向上）**里，比较前要翻成屏幕口径（见 `_to_screen`）。
    """
    mx, my = mp[0], (h - 1) - mp[1]          # map 的 y 翻成「向上」
    best = None
    for side in SIDES:
        if side in ("L", "R"):
            along = abs(mark[1] - my)
            depth = (mx - 0) if side == "L" else ((w - 1) - mx)
        else:
            along = abs(mark[0] - mx)
            depth = ((h - 1) - my) if side == "U" else (my - 0)
        if not (-1 <= depth <= 25):           # 跑到墙外或离得太远：这条边不像
            continue
        score = (along, abs(depth - 8))
        if best is None or score < best[0]:
            best = (score, side, along, depth)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _verdict(truth, tool):
    """真值边 vs 工具边 → 一致的三种结论。

    **不要**在比较前把真值翻一下：出口格的 y 是「向上」，工具给的是屏幕边名，
    但「上边」在两种口径里都叫 U —— 翻一下会把镜像错误抹平（2026-11-21 实测过）。
    """
    if truth == tool:
        return "同"
    if truth == OPP[tool]:
        return "镜像"
    return "异"


def audit(code: str) -> dict:
    mp = map_file(code)
    if not mp:
        return {"code": code, "skip": "no_map"}
    conns = parse_map(mp)
    if not conns:
        return {"code": code, "skip": "empty_map"}
    try:
        lay = adapter.build(code, prepare=False)
    except Exception as exc:                       # noqa: BLE001
        return {"code": code, "skip": "build_failed: %s" % exc}
    by = {n["name"].upper(): n for n in lay["nodes"]}
    tool = {}
    for e in lay["edges"]:
        tool[(e["a"].upper(), e["b"].upper())] = (e.get("side_a"), e.get("kind"))
        tool[(e["b"].upper(), e["a"].upper())] = (e.get("side_b"), e.get("kind"))

    rows = []
    st = Counter()
    for (a, b, pa, pb, da, db) in conns:
        for (nm, other, pos, dv) in ((a, b, pa, da), (b, a, pb, db)):
            st["map 端"] += 1
            n = by.get(nm)
            if not n:
                st["房间不在布局"] += 1
                continue
            r = n["room"]
            cands = [(x, y) for (x, y, to) in (r.exits or []) if str(to).upper() == other]
            if not cands:
                st["无出口到该邻居"] += 1
                continue
            # 有多个开口时取最贴近 map 点的那一个（内深+t 距离最小）
            mark = min(cands, key=lambda p: (p[0] - pos[0]) ** 2 + ((r.h - 1 - p[1]) - pos[1]) ** 2)
            got = _pick_side(mark, pos, r.w, r.h)
            t_side, kind = tool.get((nm, other), (None, None))
            if got is None:
                st["判不出边"] += 1
                rows.append({"region": code, "room": nm, "to": other, "mark": list(mark),
                             "map": list(pos), "truth": None, "tool": t_side,
                             "kind": kind, "along": None, "depth": None})
                continue
            side, along, depth = got
            st["有真值"] += 1
            if along == 0:
                st["沿墙完全吻合"] += 1
            st["沿墙误差_%d" % min(along, 9)] += 1
            if t_side is None:
                st["门房间/工具无此边"] += 1
            elif kind == "corner":
                st["转角边(不计)"] += 1
            else:
                v = _verdict(side, t_side)
                st["边" + v] += 1
                if v == "镜像":
                    st["镜像按轴_上下" if side in ("U", "D") else "镜像按轴_左右"] += 1
            # 对侧一致性：两端的边应该互为对面
            rows.append({"region": code, "room": nm, "to": other, "mark": list(mark),
                         "map": list(pos), "truth": side, "tool": t_side, "kind": kind,
                         "along": along, "depth": depth, "dir": dv})
    # 双向配对自检
    pair = {}
    for row in rows:
        pair.setdefault(frozenset((row["room"], row["to"])), []).append(row)
    for key, group in pair.items():
        if len(group) == 2 and group[0]["truth"] and group[1]["truth"]:
            if group[0]["truth"] == group[1]["truth"]:
                st["两端同侧(矛盾)"] += 1
            else:
                st["两端互对"] += 1
    return {"code": code, "stats": dict(st), "rows": rows}


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    dump = "--dump" in argv
    as_json = ""
    for i, a in enumerate(argv):
        if a == "--json" and i + 1 < len(argv):
            as_json = argv[i + 1]
    argv = [a for a in argv if not a.startswith("--") and a != as_json]

    if not WDIRS:
        print("找不到 world 目录")
        return 2
    found = []
    for d in WDIRS:
        found.extend(glob.glob(os.path.join(d, "*", "map_*.txt")))
    codes = [c.upper() for c in argv] or sorted(
        {os.path.basename(os.path.dirname(p)).upper() for p in found})
    print("world 包 %d | 待查区域 %d" % (len(WDIRS), len(codes)))

    total = Counter()
    per = []
    all_rows = []
    for code in codes:
        res = audit(code)
        if res.get("skip"):
            total["跳过:" + res["skip"]] += 1
            continue
        st = res["stats"]
        for k, v in st.items():
            total[k] += v
        per.append((code, st))
        all_rows.extend(res["rows"])

    print("\n== 汇总 ==")
    order = ["map 端", "有真值", "沿墙完全吻合", "边同", "边镜像", "边异", "转角边(不计)",
             "两端互对", "两端同侧(矛盾)", "判不出边", "无出口到该邻居", "房间不在布局"]
    for k in order:
        if k in total:
            print("  %-16s %d" % (k, total[k]))
    ok = total.get("边同", 0) + total.get("边镜像", 0) + total.get("边异", 0)
    if ok:
        print("  边：同 %.1f%%  上下镜像 %.1f%%  其它 %.1f%%（共 %d 端，转角边不计）"
              % (100.0 * total.get("边同", 0) / ok, 100.0 * total.get("边镜像", 0) / ok,
                 100.0 * total.get("边异", 0) / ok, ok))
    if total.get("有真值"):
        exact = total.get("沿墙完全吻合", 0)
        within2 = sum(total.get("沿墙误差_%d" % i, 0) for i in range(3))
        print("  沿墙坐标：完全吻合 %.1f%%，≤2 格 %.1f%%"
              % (100.0 * exact / total["有真值"], 100.0 * within2 / total["有真值"]))
        print("  沿墙误差分布 0..9+ :", [total.get("沿墙误差_%d" % i, 0) for i in range(10)])

    print("\n== 分区（只列有 map 的）==")
    bad = [(c, s) for (c, s) in per if s.get("边异", 0) + s.get("判不出边", 0)
           + s.get("两端同侧(矛盾)", 0)]
    for (c, s) in per[:14]:
        print("  %-4s 端 %3d  真值 %3d  同 %3d  镜像 %3d  异 %3d  矛盾 %2d  判不出 %2d"
              % (c, s.get("map 端", 0), s.get("有真值", 0), s.get("边同", 0),
                 s.get("边镜像", 0), s.get("边异", 0), s.get("两端同侧(矛盾)", 0),
                 s.get("判不出边", 0)))
    if len(per) > 14:
        print("  … 其余 %d 区，问题区 %d 个" % (len(per) - 14, len(bad)))

    if dump:
        print("\n== 明细（前 40 条，边不一致/判不出优先）==")
        rows = [r for r in all_rows if r["truth"] != r["tool"] or not r["truth"]]
        for r in rows[:40]:
            print("  %-4s %-14s → %-14s 开口%-9s map%-9s 真值%-4s 工具%-4s 沿墙%s 内深%s"
                  % (r["region"], r["room"], r["to"], r["mark"], r["map"],
                     r["truth"], r["tool"], r["along"], r["depth"]))

    if as_json:
        with open(as_json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"regions": len(per), "total": dict(total), "rows": all_rows},
                      fh, ensure_ascii=False, indent=1)
        print("\n表已写:", as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
