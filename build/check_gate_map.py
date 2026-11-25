"""全库扫一遍：每个区域在「白猫 + 默认筛选」下能不能把大门贴上去。

判据：
  1. 布局不抛异常；
  2. 图上的门节点数 = 装进来的门数（`gates_off` 之外的门都挂上了）；
  3. 门节点的 `isolated` 全是 False（孤岛会被摆到停车场，这就是不能上图的那种）；
  4. `rooms = rooms_total − Σdropped − missing` 恒等式成立。

    python build/check_gate_map.py            # 全库
"""
from __future__ import annotations

import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import bridge                        # noqa: E402
from core.regmap import adapter                # noqa: E402

FAILS = []


def check(ok, msg):
    if not ok:
        FAILS.append(msg)
        print("  ✗ " + msg)


def main() -> int:
    rows = []
    t0 = time.time()
    for path in sorted(glob.glob(os.path.join(ROOT, "region_data", "*.json"))):
        code = os.path.splitext(os.path.basename(path))[0]
        if code.startswith("_"):
            continue
        flt = bridge._regmap_filters(code, "White")
        try:
            reg = adapter.load_rooms(code, "White", flt)
        except Exception as exc:               # noqa: BLE001
            check(False, "%s 装配失败：%s" % (code, exc))
            continue
        gates = [r for r in reg["rooms"] if r.is_gate]
        lhs = len(reg["rooms"])
        rhs = reg["rooms_total"] - sum(reg["dropped"].values()) - len(reg["missing"])
        check(lhs == rhs, "%s 房间数不自洽：rooms=%d，total-Σdrop-missing=%d"
              % (code, lhs, rhs))
        if not reg["rooms"]:
            rows.append((code, 0, len(gates), 0, 0, 0.0))
            continue
        try:
            res = adapter.build(code, "White", {"flt": flt}, prepare=False)
        except Exception as exc:               # noqa: BLE001
            check(False, "%s 布局失败：%s" % (code, exc))
            continue
        nodes = res["nodes"]
        gn = [n for n in nodes if n.get("gate")]
        check(len(gn) == len(gates),
              "%s 图上门数 %d ≠ 装进来的 %d（gates_off=%r）"
              % (code, len(gn), len(gates), reg["gates_off"]))
        stray = [n["name"] for n in gn if n.get("isolated")]
        check(not stray, "%s 有门被当孤岛摆到停车场：%s" % (code, stray[:4]))
        rows.append((code, len(nodes) - len(gn), len(gn),
                     len(reg["gates_off"]), reg["dropped"].get("gate", 0),
                     res["stats"].get("isolated", 0)))
    print("-" * 72)
    for r in rows:
        # r[3] = 本区没有连线被剔的门；r[4] = `dropped["gate"]`（= 无连线 + 缺 txt），别再相加
        print("%-6s 房间 %3d + 门 %2d = %3d｜没上图的门 %d（无连线 %d / 缺 txt %d）｜孤岛 %d"
              % (r[0], r[1], r[2], r[1] + r[2], r[4], r[3], r[4] - r[3], r[5]))
    tot_room = sum(r[1] for r in rows)
    tot_gate = sum(r[2] for r in rows)
    print("-" * 72)
    print("区域 %d｜房间 %d｜图中门 %d｜没上图的门 %d（无连线 %d / 缺 txt %d）｜耗时 %.1fs"
          % (len(rows), tot_room, tot_gate, sum(r[4] for r in rows),
             sum(r[3] for r in rows), sum(r[4] - r[3] for r in rows),
             time.time() - t0))
    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for m in FAILS:
            print("  - " + m)
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
