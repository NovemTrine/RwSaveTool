"""W0 · 尺子：现有 regmap 布局 vs 游戏自己的房间位置。

为什么要有它：后面每一期（W1 上色 / W2 换引擎 / W4 标注）都要回答"是不是更像了"，
靠眼睛答不了。这里给 117 个区各打一个分，作为后续所有改动的对照基线。

## 真值用哪个：`map_*.txt`，不是 region_data 的 `map`

两个候选都试过，差别是决定性的（见 `build/_regmap_shape.md` 附录 A）：

| 来源 | HI 跨度 | 长宽比 | 是什么 |
|---|---|---|---|
| `region_data/*.json` 的 `map` | 900 × 1048 | 0.86 | `map_image_<reg>.txt`：**每间房画成固定 48×35 图标**、整张压进 `map_hi.png`(1081×1206) 那块画布，比例被压扁 |
| `map_<reg>.txt` 的房间行 | 2444 × 1138 | 2.15 | 房间在**世界坐标**里的真实位置（y 向上，20 px/格），按真实尺寸画 |

wiki 图是按真实尺寸画的横带，参考实现 `rainworld_zhiqiong` 的成品长宽比 4.45 也在这条线上，
所以真值取 `map_<reg>.txt`。demo 的 `region_map/evaluate.py` 用的是前者——那是**错的尺子**，
它的分数越低不代表越不像 wiki。想复现旧口径就 `--truth rect`。

## 口径（沿用 `evaluate.py` 的定义，只换真值）

| 口径 | 含义 |
|---|---|
| `quad` | 主轴四向一致（`|dx| >= |dy|` 归左右，否则上下） |
| `oct8` | 8 向一致（45° 扇区） |
| `near_quad` | 只比真值距离 <= `near`（默认云团对角线 20%，与尺度无关）的对 |
| `nb_quad` | 只比有连线的邻居对（最严的一档） |

四个口径都只统计**同一连通分量内**的房间对：跨分量的相对位置是自由选择，没有真值。

layout 的 y 与世界 y 朝向相反，所以逐区投票（`_detect_flip`）后两种朝向都算一遍：
`quad` 取高的那个，`quad_vote` 记投票所选朝向。两者差很多说明该区上下关系本来就乱。

用法：

    python build/check_regmap_shape.py                  # 全库 → build/_regmap_shape.md
    python build/check_regmap_shape.py UW HI CC         # 只看几个区
    python build/check_regmap_shape.py --shots          # 顺带出 6 区基线图
    python build/check_regmap_shape.py --truth rect     # 复现 demo 旧口径（仅供对照）
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import paths                      # noqa: E402
from core.regmap import adapter             # noqa: E402
from core.regmap import build_rooms         # noqa: E402

WS = "D:/Projects/AI_Workspace/WorkBuddy_Workspace/2026-11-19-23-55-46"
NEAR_FRAC = 0.20                            # near 阈值 = 真值云团对角线 × 这个比例
SHOT_CODES = ("UW", "HI", "CC", "MS", "GW", "WARA")
SHOT_DIR = os.path.join(HERE, "_shots", "baseline")
REPORT = os.path.join(HERE, "_regmap_shape.md")
REPORT_RECT = os.path.join(HERE, "_regmap_shape_rect.md")
PX_PER_CELL = 20.0                          # 世界像素 / 格（房间 txt 的约定）


# ---------- 真值 ----------

def map_file(src, code):
    """`map_<reg>.txt`：只有它有真实世界位置（96/117 个区有）。"""
    low = code.lower()
    for d in (src or {}).get("worldDirs") or []:
        p = os.path.join(d, low, "map_%s.txt" % low)
        if os.path.isfile(p):
            return p
    return None


def truth_map(src, code):
    """→ {房间: (x, y)}，世界像素、y 向上，取房间行的四角中点。

    行格式：`名字: x1><y1><x2><y2><层><子区域?><`，四数是**两个对角**（宽高可正可负），
    所以取中点才稳。`Connection:` 行是另一张表（两端门位 + 方向码），这里跳过。
    """
    p = map_file(src, code)
    if not p:
        return {}, ""
    out = {}
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if ": " not in line or line.startswith("Connection:"):
                    continue
                name, _, payload = line.partition(": ")
                f = payload.split("><")
                if len(f) < 4:
                    continue
                try:
                    x1, y1, x2, y2 = (float(v) for v in f[:4])
                except ValueError:
                    continue
                out[name.strip().upper()] = ((x1 + x2) * 0.5, (y1 + y2) * 0.5)
    except OSError:
        return {}, ""
    return out, os.path.basename(p)


def truth_rect(rooms):
    """demo 旧口径：`map_rect` 中心（固定图标 + 压扁画布，仅作对照）。"""
    out = {}
    for r in rooms:
        if not r.map_rect:
            continue
        x, y, w, h = r.map_rect
        out[r.name.upper()] = (x + w * 0.5, y + h * 0.5)
    return out


# ---------- 口径 ----------

def _octant(dx, dy):
    if dx == 0.0 and dy == 0.0:
        return -1
    return int(round(math.atan2(dy, dx) / (math.pi / 4.0))) % 8


def _quad(dx, dy):
    if dx == 0.0 and dy == 0.0:
        return -1
    if abs(dx) >= abs(dy):
        return 0 if dx > 0 else 2          # 0=右 2=左
    return 1 if dy > 0 else 3              # 1=下 3=上


def _centers(nodes):
    return {n["name"].upper(): (n["x"] + n["w"] * 0.5, n["y"] + n["h"] * 0.5)
            for n in nodes if not n.get("isolated")}


def _detect_flip(pred, truth, adjacent):
    """layout 的 y 与世界 y 朝向是否相反：用相邻房间的竖向关系投票。"""
    pos = neg = 0
    for (a, b) in adjacent:
        if a not in pred or b not in pred or a not in truth or b not in truth:
            continue
        dy_pred = pred[b][1] - pred[a][1]
        dy_true = truth[b][1] - truth[a][1]
        if abs(dy_pred) < 0.5 or abs(dy_true) < 0.5:
            continue
        if dy_pred * dy_true > 0:
            pos += 1
        else:
            neg += 1
    return (neg > pos), pos, neg


def _near_threshold(truth_pts, frac=NEAR_FRAC):
    xs = [p[0] for p in truth_pts]
    ys = [p[1] for p in truth_pts]
    if not truth_pts:
        return 0.0
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys)) * frac


def _components(nodes, edges):
    """连通分量（按连线）。跨分量的相对位置是**自由选择**（我们摆停车场、
    参考实现往主块上挤），没有真值可比，打分时排除。"""
    par = {n["name"].upper(): n["name"].upper() for n in nodes}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for e in edges:
        a, b = find(e["a"].upper()), find(e["b"].upper())
        if a != b:
            par[a] = b
    return {k: find(k) for k in par}


def _compare(pred, truth, adjacent, near, flip_y, comp=None):
    names = [n for n in pred if n in truth]
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    total_pairs = len(pairs)
    if comp:
        pairs = [(a, b) for (a, b) in pairs if comp.get(a) == comp.get(b)]
    adj = set(adjacent)
    n = oct8 = quad = 0
    near_n = near_quad = 0
    nb_n = nb_oct8 = nb_quad = 0
    sign = -1.0 if flip_y else 1.0
    for (a, b) in pairs:
        pa, pb = pred[a], pred[b]
        ra, rb = truth[a], truth[b]
        dpx, dpy = pb[0] - pa[0], pb[1] - pa[1]
        drx, dry = rb[0] - ra[0], (rb[1] - ra[1]) * sign
        if abs(dpx) < 0.3 and abs(dpy) < 0.3:
            continue
        if abs(drx) < 0.3 and abs(dry) < 0.3:
            continue
        n += 1
        same_oct = _octant(dpx, dpy) == _octant(drx, dry)
        same_quad = _quad(dpx, dpy) == _quad(drx, dry)
        oct8 += 1 if same_oct else 0
        quad += 1 if same_quad else 0
        if math.hypot(drx, dry) <= near:
            near_n += 1
            near_quad += 1 if same_quad else 0
        if (a, b) in adj or (b, a) in adj:
            nb_n += 1
            nb_oct8 += 1 if same_oct else 0
            nb_quad += 1 if same_quad else 0

    def pct(k, base):
        return round(100.0 * k / base, 1) if base else 0.0

    return {
        "pairs": n,
        "cross": total_pairs - len(pairs),
        "oct8": pct(oct8, n),
        "quad": pct(quad, n),
        "near_pairs": near_n,
        "near_quad": pct(near_quad, near_n),
        "nb_pairs": nb_n,
        "nb_oct8": pct(nb_oct8, nb_n),
        "nb_quad": pct(nb_quad, nb_n),
    }


def _gap_median(nodes, edges):
    """相邻房间的矩形间隙中位（与 layout._gap_stats 同一几何，换成中位）。"""
    rect = {n["name"]: (n["x"], n["y"], n["w"], n["h"]) for n in nodes}
    gaps = []
    for e in edges:
        a, b = rect.get(e["a"]), rect.get(e["b"])
        if not a or not b:
            continue
        dx = max(0.0, max(a[0] - (b[0] + b[2]), b[0] - (a[0] + a[2])))
        dy = max(0.0, max(a[1] - (b[1] + b[3]), b[1] - (a[1] + a[3])))
        gaps.append(math.hypot(dx, dy))
    return round(statistics.median(gaps), 2) if gaps else 0.0


# ---------- 单区打分 ----------

def score(code, truth_mode="map", near_frac=NEAR_FRAC):
    t0 = time.time()
    with open(adapter.region_path(code), encoding="utf-8") as fh:
        data = json.load(fh)
    src = ((data.get("layers") or [{}])[0].get("source") or {})

    region = adapter.load_rooms(code)
    rooms = region["rooms"]
    # 直接走 `build_rooms`：`adapter.build` 会再 `load_rooms` 一次，房间数超过解析缓存
    # （LRU 48）的区（MS/GW/CL 这些）会整区重解析一遍，白等几秒。缩略图也不用做。
    res = build_rooms(rooms, region=region, code=code, prepare=False)
    nodes, edges, st = res["nodes"], res["edges"], res["stats"]

    pred = _centers(nodes)
    adjacent = [(e["a"].upper(), e["b"].upper()) for e in edges]
    comp = _components(nodes, edges)

    if truth_mode == "rect":
        truth, tname = truth_rect(rooms), "map_rect"
    else:
        truth, tname = truth_map(src, code)
    if not truth:
        raise LookupError("没有真值（%s）" % (tname or "map_<reg>.txt 缺失"))

    common = [k for k in pred if k in truth]
    near = _near_threshold([truth[k] for k in common], near_frac)

    vote_flip, pos, neg = _detect_flip(pred, truth, adjacent)
    dn = _compare(pred, truth, adjacent, near, False, comp)
    up = _compare(pred, truth, adjacent, near, True, comp)
    best, pick_flip = (up, True) if up["quad"] >= dn["quad"] else (dn, False)
    vote_row = up if vote_flip else dn
    if best["pairs"] == 0:
        # 单房间区域 / 全被过滤掉：没有可配对，0.0 会污染均值与最低值，直接算跳过
        raise LookupError("无可配对（%d 间 / %d 边）" % (len(nodes), len(edges)))

    # 真值房间太少（地图文件只覆盖一部分房间）或可配对太少时，分数不可当结论用
    weak = len(common) < max(10.0, 0.30 * len(nodes)) or best["pairs"] < 100

    return {
        "code": code,
        "rooms": len(nodes),
        "edges": len(edges),
        "truth_rooms": len(common),
        "weak": weak,
        "truth": tname,
        "near": round(near, 1),
        "near_cells": round(near / PX_PER_CELL, 1) if truth_mode != "rect" else 0.0,
        "pairs": best["pairs"],
        "cross": best["cross"],
        "quad": best["quad"],
        "quad_vote": vote_row["quad"],
        "oct8": best["oct8"],
        "near_quad": best["near_quad"],
        "near_pairs": best["near_pairs"],
        "nb_quad": best["nb_quad"],
        "nb_pairs": best["nb_pairs"],
        "gap": _gap_median(nodes, edges),
        "flip": "U" if pick_flip else "D",
        "vote": "%d/%d" % (pos, neg),
        "overlaps": st.get("overlaps", 0),
        "unresolved": st.get("route_unresolved", 0),
        "ms": int((time.time() - t0) * 1000),
    }


def all_codes():
    out = []
    for p in sorted(glob.glob(os.path.join(paths.data_dir(), "*.json"))):
        name = os.path.basename(p)[:-5]
        if name.startswith("_"):
            continue
        out.append(name.upper())
    return out


# ---------- 基线图 ----------

def render_shots(codes=SHOT_CODES, target_w=1600):
    if WS not in sys.path:
        sys.path.insert(0, WS)
    from region_map import render as demo_render   # 冻结的 demo，只借画法

    os.makedirs(SHOT_DIR, exist_ok=True)
    made = []
    for code in codes:
        try:
            layout = adapter.build(code)
            path = os.path.join(SHOT_DIR, "%s.png" % code)
            info = demo_render.render_png(layout, path, target_w=target_w, ss=1,
                                          invert=True, link_mode=2)
        except Exception as exc:                   # noqa: BLE001 - 出图失败不该拦住评分
            made.append((code, "失败 %s: %s" % (type(exc).__name__, exc)))
            continue
        made.append((code, "%dx%d  %.0f KB  scale %.2f"
                     % (info["w"], info["h"], info["bytes"] / 1024.0, info["scale"])))
    return made


# ---------- 报表 ----------

def _summary(rows):
    quads = [r["quad"] for r in rows if r["pairs"]]
    strong = [r["quad"] for r in rows if r["pairs"] and not r["weak"]]
    return {
        "regions": len(rows),
        "weak": sum(1 for r in rows if r["weak"]),
        "rooms": sum(r["rooms"] for r in rows),
        "edges": sum(r["edges"] for r in rows),
        "pairs": sum(r["pairs"] for r in rows),
        "quad_med": round(statistics.median(quads), 1) if quads else 0.0,
        "quad_mean": round(statistics.mean(quads), 1) if quads else 0.0,
        "quad_min": min(quads) if quads else 0.0,
        "quad_max": max(quads) if quads else 0.0,
        "strong_med": round(statistics.median(strong), 1) if strong else 0.0,
        "ge95": sum(1 for q in quads if q >= 95.0),
        "ge90": sum(1 for q in quads if q >= 90.0),
        "lt80": sum(1 for q in quads if q < 80.0),
        "ms": sum(r["ms"] for r in rows),
    }


def _write_report(rows, summ, shots, fails, truth_mode, near_frac, path=None):
    if path is None:
        path = REPORT if truth_mode == "map" else REPORT_RECT
    lines = []
    add = lines.append
    add("# regmap 布局基线（W0 尺子）")
    add("")
    if truth_mode == "map":
        add("> 生成：`build/check_regmap_shape.py`　真值：**`map_<reg>.txt` 的房间世界位置**")
        add("> 口径：`quad` 主轴 / `oct8` 八向 / `near_quad` 局部（云团对角线 %.0f%%）/ "
            "`nb_quad` 邻居（最严）" % (near_frac * 100))
        add("> 对照：`region_data/*.json` 只用来拿房间与连线，**不用它的 `map`**（理由见附录 A）。")
    else:
        add("> **旧口径对照页**：真值取 `region_data` 的 `map`（`map_image_*.txt`）。")
        add("> 这张表只为证明\"旧尺子量错了\"，**不要拿它验收**——理由见附录 A。")
    add("")
    add("## 汇总")
    add("")
    add("| 区 | 房间 | 边 | 可配对 | quad 中位 | quad 均值 | 最低 | 最高 "
        "| 强区中位 | ≥95% 区 | ≥90% 区 | <80% 区 | 总耗时 |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    add("| %d（弱 %d） | %d | %d | %d | **%.1f** | %.1f | %.1f | %.1f | %.1f | %d | %d | %d | %.1f s |"
        % (summ["regions"], summ["weak"], summ["rooms"], summ["edges"], summ["pairs"],
           summ["quad_med"], summ["quad_mean"], summ["quad_min"], summ["quad_max"],
           summ["strong_med"], summ["ge95"], summ["ge90"], summ["lt80"],
           summ["ms"] / 1000.0))
    add("")
    add("所有口径只统计**同一连通分量内**的房间对；`跨分量` 列是因此排除的对数——"
        "两块互不相连的房间摆在哪边是自由的（我们摆停车场、参考实现往主块上挤），"
        "没有真值可比，算进去只会量到运气。")
    add("")
    add("`gap` = 相邻房间矩形间隙中位（布局单位）；`flip` 是**取高那侧**的 y 朝向，"
        "`投票侧` 是**投票所选朝向**的 quad，`vote` 是投票正/负。")
    add("`flip` 与投票不一致、或 `quad` 与 `投票侧` 差得多的区，上下关系本身就含糊，"
        "别把它的分数当结论。")
    add("")
    add("带 `*` 的是**弱区**：地图文件只覆盖不到三成房间，或可配对 < 100，"
        "分数不能当结论用（`强区中位` 已排除它们）。")
    add("")
    if shots:
        add("## 基线图")
        add("")
        add("`build/_shots/baseline/`：")
        add("")
        add("| 区 | 结果 |")
        add("|---|---|")
        for code, info in shots:
            add("| %s | %s |" % (code, info))
        add("")
    add("## 全表（按 quad 升序）")
    add("")
    add("| 区 | 房间 | 真值房间 | 边 | 可配对 | 跨分量 | **quad** | 投票侧 | oct8 "
        "| near_quad | nb_quad | 缝中位 | flip | vote | 重叠 | 未解 | ms |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["quad"], x["code"])):
        add("| %s%s | %d | %d | %d | %d | %d | **%.1f** | %.1f | %.1f | %.1f | %.1f "
            "| %.2f | %s | %s | %d | %d | %d |"
            % (r["code"], "\\*" if r["weak"] else "", r["rooms"], r["truth_rooms"],
               r["edges"], r["pairs"], r["cross"], r["quad"], r["quad_vote"],
               r["oct8"], r["near_quad"], r["nb_quad"], r["gap"], r["flip"],
               r["vote"], r["overlaps"], r["unresolved"], r["ms"]))
    add("")
    if fails:
        add("## 没有真值 / 失败的区（%d）" % len(fails))
        add("")
        add("| 区 | 原因 |")
        add("|---|---|")
        for code, msg in fails:
            add("| %s | %s |" % (code, msg))
        add("")
    add("## 附录 A · 为什么不用 `region_data` 的 `map`")
    add("")
    add("| 来源 | HI 跨度 | 长宽比 | 是什么 |")
    add("|---|---|---|---|")
    add("| `region_data/HI.json` 的 `map` | 900 × 1048 | 0.86 | "
        "`map_image_hi.txt`：每间房画成固定 48×35 图标、整体压进 `map_hi.png`(1081×1206)，比例被压扁 |")
    add("| `map_hi.txt` 房间行 | 2444 × 1138 | 2.15 | 房间真实世界位置（y 向上，20 px/格） |")
    add("| `rainworld_zhiqiong` 成品 | 1888 × 424 | 4.45 | 参考实现的 HI 排布 |")
    add("")
    add("两张同源数据的形状对不上，只能留一个当真值。wiki 图按房间真实尺寸画，"
        "参考实现的成品也在这条线上，所以取 `map_*.txt`。")
    add("")
    add("`--truth rect` 复现 demo 旧口径（写本文件的姊妹页），同一批区会低 30~40 个百分点，"
        "旧口径下的分数与\"像不像 wiki\"无关。")
    add("")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="regmap 布局基线打分")
    ap.add_argument("codes", nargs="*", help="区域代码；不填则全库")
    ap.add_argument("--truth", choices=("map", "rect"), default="map",
                    help="真值来源：map=map_*.txt（默认），rect=region_data 的 map（旧口径）")
    ap.add_argument("--near", type=float, default=NEAR_FRAC,
                    help="局部口径的阈值，按云团对角线比例（默认 %.2f）" % NEAR_FRAC)
    ap.add_argument("--shots", action="store_true", help="顺带出 6 区基线图")
    ap.add_argument("--quiet", action="store_true", help="只打汇总")
    args = ap.parse_args(argv)

    codes = [c.upper() for c in args.codes] or all_codes()
    rows, fails = [], []
    print("打分 %d 个区（真值 %s，near %.0f%%）……"
          % (len(codes), args.truth, args.near * 100), flush=True)
    for i, code in enumerate(codes, 1):
        try:
            r = score(code, args.truth, args.near)
        except Exception as exc:                   # noqa: BLE001
            fails.append((code, "%s: %s" % (type(exc).__name__, exc)))
            if not args.quiet:
                print("  %-6s 跳过 %s: %s" % (code, type(exc).__name__, exc), flush=True)
            continue
        rows.append(r)
        if not args.quiet:
            print("  %3d/%d %-6s 间 %3d/%3d  quad %5.1f  oct8 %5.1f  near %5.1f(%3.0f格)  "
                  "nb %5.1f  缝 %5.2f  %s  %dms"
                  % (i, len(codes), code, r["rooms"], r["truth_rooms"], r["quad"],
                     r["oct8"], r["near_quad"], r["near_cells"], r["nb_quad"],
                     r["gap"], r["flip"], r["ms"]), flush=True)

    summ = _summary(rows)
    shots = render_shots() if args.shots else None
    # 只跑几个区时不要覆盖全库基线报表（本喵踩过一次：冒烟把基线冲掉了）
    out = None
    if args.codes:
        out = os.path.join(HERE, "_regmap_shape_subset.md")
    path = _write_report(rows, summ, shots, fails, args.truth, args.near, out)

    print("")
    print("区 %d（弱区 %d，无真值/失败 %d）｜房间 %d｜边 %d｜可配对 %d"
          % (summ["regions"], summ["weak"], len(fails), summ["rooms"],
             summ["edges"], summ["pairs"]))
    print("quad  中位 %.1f  均值 %.1f  最低 %.1f  最高 %.1f（强区中位 %.1f）"
          % (summ["quad_med"], summ["quad_mean"], summ["quad_min"], summ["quad_max"],
             summ["strong_med"]))
    print("≥95%% %d 区｜≥90%% %d 区｜<80%% %d 区｜总耗时 %.1f s"
          % (summ["ge95"], summ["ge90"], summ["lt80"], summ["ms"] / 1000.0))
    print("报表 %s" % path)
    if shots:
        for code, info in shots:
            print("图 %-5s %s" % (code, info))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
