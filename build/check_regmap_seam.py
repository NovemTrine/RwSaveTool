"""接缝审计：实心/面类块在量化之后，上下相邻的两块有没有对齐。

背景（2026-11-21 主人报）：4000% 放大下，灰色实心区里一条条**浅色横线**——
其实是相邻块各自四舍五入，边界差 0.1 单位，缝里露出了房间底（空气色）。
`_runs_path` 改成「先量化绝对边界、再相减求宽高」后，这里应该恒为 0。

    .venv/Scripts/python.exe build/check_regmap_seam.py RF SL MS HI UW CC
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter                 # noqa: E402
from core.regmap.svg import _merge_blocks       # noqa: E402

PAD = 14
WIDTH = 2400


def audit(code: str, legacy: bool = False) -> tuple[int, int, int]:
    """legacy=True 用旧算法（量化长度再相加），用来证明这条审计确实抓得到缝。"""
    lay = adapter.build(code)
    nodes = lay["nodes"]
    x0 = min(n["x"] for n in nodes)
    y0 = min(n["y"] for n in nodes)
    x1 = max(n["x"] + n["w"] for n in nodes)
    s = (WIDTH - PAD * 2) / max(1e-9, (x1 - x0))

    seams = 0
    blocks = 0
    rooms = 0
    for n in nodes:
        segs = n.get("runs") or []
        if not segs:
            continue
        rooms += 1
        cw = n["w"] * s / max(1, n["thumbW"])
        ch = n["h"] * s / max(1, n["thumbH"])
        ox = PAD + (n["x"] - x0) * s
        oy = PAD + (n["y"] - y0) * s
        boxes = []
        for (r0, r1, a0, a1) in _merge_blocks(segs):
            if legacy:                       # 旧：起点取整 + 长度取整，两段各自四舍五入
                ax = float("%.1f" % (ox + a0 * cw))
                ay = float("%.1f" % (oy + r0 * ch))
                bx = ax + float("%.1f" % ((a1 - a0) * cw))
                by = ay + float("%.1f" % ((r1 - r0) * ch))
            else:                            # 新：两端都用同一个绝对表达式取整
                ax = float("%.1f" % (ox + a0 * cw))
                ay = float("%.1f" % (oy + r0 * ch))
                bx = float("%.1f" % (ox + a1 * cw))
                by = float("%.1f" % (oy + r1 * ch))
            boxes.append((ax, ay, bx, by))
        blocks += len(boxes)
        # 任意两块：x 有重叠且 y 相接（顶 = 另一块的底）→ 边界必须完全相等
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if min(a[2], b[2]) - max(a[0], b[0]) <= 1e-6:
                    continue
                for lo, hi in ((a[3], b[1]), (b[3], a[1])):
                    if 0 < abs(lo - hi) < 0.2:      # 差一点点 = 缝
                        seams += 1
    return rooms, blocks, seams


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    legacy = "--legacy" in args
    codes = [a for a in args if not a.startswith("--")] or ["RF"]
    total = 0
    for code in codes:
        rooms, blocks, seams = audit(code.upper(), legacy=legacy)
        total += seams
        print("%-4s 房间 %3d  块 %5d  接缝 %d%s" %
              (code.upper(), rooms, blocks, seams, "（旧算法）" if legacy else ""))
    print("合计接缝 %d" % total)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
