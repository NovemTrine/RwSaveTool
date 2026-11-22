"""W4 探针：标注数据到底有多少、在哪。

统计一个区域里：房间标签（world 文件）、放置物（settings）、通往业力门的出口。
用法：python build/_anno_probe.py SU HI MS
"""
import os
import re
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regmap import adapter            # noqa: E402
from core.regmap import fx                 # noqa: E402

WANT = ("GhostSpot", "SpinningTopSpot", "WarpPoint", "DataPearl", "KarmaFlower",
        "ScavengerOutpost", "ScavengerTreasury", "BatflyNest")


def world_tags(world_dir):
    """world_*.txt 的 ROOMS 段 → {房间: 标签}。"""
    out = {}
    if not os.path.isdir(world_dir):
        return out
    for fn in os.listdir(world_dir):
        if not fn.lower().startswith("world_") or not fn.lower().endswith(".txt"):
            continue
        inrooms = False
        try:
            lines = open(os.path.join(world_dir, fn), encoding="utf-8",
                         errors="replace").read().split("\n")
        except OSError:
            continue
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if not inrooms:
                if s.upper() == "ROOMS":
                    inrooms = True
                continue
            if s.upper().startswith("END ROOMS"):
                break
            if s.startswith("//"):
                continue
            parts = [x.strip() for x in s.split(":")]
            if len(parts) < 2:
                continue
            name = parts[0].upper()
            tag = parts[2].upper() if len(parts) > 2 and parts[2] else ""
            if tag:
                out[name] = tag
    return out


def main():
    for code in sys.argv[1:] or ["SU"]:
        reg = adapter.load_rooms(code)
        rooms = reg["rooms"]
        tags = collections.Counter()
        objs = collections.Counter()
        gate_links = 0
        echoes = 0
        for r in rooms:
            for line in r.exits:
                if str(line[2]).upper().startswith("GATE_"):
                    gate_links += 1
            sp = fx._settings_path(r.path)
            if not sp:
                continue
            kv = fx._kv(sp)
            placed = fx._placed(kv.get("PlacedObjects", "") or "")
            for (name, x, y, props) in placed:
                if name in WANT:
                    objs[name] += 1
        print("%s: 房间 %d，通向门房的出口 %d" % (code, len(rooms), gate_links))
        print("   对象", dict(objs))
        # 每间房自己的 settings 命中率
        have = sum(1 for r in rooms if fx._settings_path(r.path))
        print("   有 settings 的房间 %d/%d" % (have, len(rooms)))


if __name__ == "__main__":
    main()
