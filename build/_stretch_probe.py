"""只读分析：放大后「杆子被拉伸」到底来自哪里。

不碰 core，只读布局数据：
  · 每个缩略格对应多少原格（cw/ch 换算）
  · 杆子/管道块按**原格**计的宽高分布
  · 最粗/最长的几块，回溯房间名

    .venv/Scripts/python.exe build/_stretch_probe.py RF SL
"""

from __future__ import annotations

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter                 # noqa: E402
from core.regmap.svg import _merge_blocks       # noqa: E402


def probe(code: str):
    lay = adapter.build(code)
    nodes = lay["nodes"]
    print("\n=== %s · %d 间房 ===" % (code, len(nodes)))
    ratio = nodes[0]["thumbW"] / max(1e-9, nodes[0]["w"])
    print("缩略密度：1 原格 = %.2f 缩略格（density=%.1f）" % (ratio, ratio))

    wdist = Counter()      # 块宽（原格）
    hdist = Counter()
    widest = []
    longest = []
    total = 0
    for n in nodes:
        if not n["thumbW"] or not n["w"]:
            continue
        kx = n["w"] / float(n["thumbW"])          # 1 缩略格 = kx 原格
        ky = n["h"] / float(n["thumbH"])
        for kind in ("b", "p"):
            segs = (n.get("over") or {}).get(kind) or []
            for (r0, r1, a0, a1) in _merge_blocks(segs):
                total += 1
                w = (a1 - a0) * kx
                h = (r1 - r0) * ky
                wdist[round(w, 1)] += 1
                hdist[round(h, 1)] += 1
                widest.append((w, h, n["name"], kind))
                longest.append((h, w, n["name"], kind))
    print("杆子/管道块 %d 个" % total)
    print("原格宽度分布（宽 → 块数）：", dict(sorted(wdist.items())[:8]))
    print("原格长度分布（长 → 块数）：", dict(sorted(hdist.items())[:8]))
    widest.sort(reverse=True)
    longest.sort(reverse=True)
    print("最宽的 6 块（宽×长 原格，房间，类）：")
    for w, h, name, kind in widest[:6]:
        print("   %4.1f × %4.1f   %-12s %s" % (w, h, name, kind))
    print("最长的 6 块（长×宽）：")
    for h, w, name, kind in longest[:6]:
        print("   %4.1f × %4.1f   %-12s %s" % (h, w, name, kind))


for c in (sys.argv[1:] or ["RF"]):
    probe(c.upper())
