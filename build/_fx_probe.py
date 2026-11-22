"""W4-fx 只读探针：统计每个区域有多少房间带水 / 酸 / 沙 / 腐化。

    .venv/Scripts/python.exe build/_fx_probe.py SL GW MS SI WARA WORA
    .venv/Scripts/python.exe build/_fx_probe.py SL --dump SL_A03

不写任何数据，只打印。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.regmap import adapter, fx          # noqa: E402


def survey(code: str, dump: str = "") -> dict:
    t0 = time.perf_counter()
    rooms = adapter.load_rooms(code)["rooms"]
    load_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    got = {"rooms": len(rooms), "water": 0, "acid": 0, "sand": 0, "corrupt": 0,
           "both": 0, "settings": 0}
    samples = []
    for room in rooms:
        f = fx.room_fx(room)
        if not f:
            continue
        if f.get("settings"):
            got["settings"] += 1
        kinds = []
        if f.get("water"):
            got["water"] += 1
            kinds.append("水")
            if f["water"].get("acid"):
                got["acid"] += 1
                kinds[-1] = "酸"
        if f.get("sand"):
            got["sand"] += 1
            kinds.append("沙")
        if f.get("corrupt"):
            got["corrupt"] += 1
            kinds.append("腐化")
        if len(kinds) > 1:
            got["both"] += 1
        if len(samples) < 4:
            samples.append((room.name, kinds))
    got["ms"] = (time.perf_counter() - t0) * 1000
    got["load_ms"] = load_ms
    got["samples"] = samples

    if dump:
        for room in rooms:
            if room.name.upper() != dump.upper():
                continue
            f = fx.room_fx(room)
            print("==", room.name, room.w, "x", room.h, "path", room.path)
            if not f:
                print("   （无特效）")
                break
            print("   settings:", f.get("settings"))
            w = f.get("water")
            if w:
                print("   water full %s band %s holes %d acid %s inverted %s"
                      % (tuple(round(v, 1) for v in w["full"]),
                         tuple(round(v, 1) for v in w["band"]),
                         len(w["holes"]), w["acid"], w["inverted"]))
            if f.get("sand"):
                line = f["sand"]
                ys = [round(p[1], 1) for p in line]
                print("   sand 点 %d  x %.1f→%.1f  y %.1f..%.1f"
                      % (len(line), line[0][0], line[-1][0], min(ys), max(ys)))
            if f.get("corrupt"):
                print("   corrupt %d 个圆: %s"
                      % (len(f["corrupt"]),
                         [(round(c[0]), round(c[1]), round(c[2], 1)) for c in f["corrupt"][:4]]))
            break
    return got


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    dump = ""
    if "--dump" in argv:
        i = argv.index("--dump")
        dump = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
    codes = [c.upper() for c in argv] or ["SL", "GW", "MS", "SI", "RM"]

    print("%-5s %5s %5s %4s %4s %6s %6s %8s" %
          ("区", "房间", "水", "酸", "沙", "腐化", "多类", "耗时ms"))
    total = {"water": 0, "acid": 0, "sand": 0, "corrupt": 0, "rooms": 0}
    for code in codes:
        try:
            got = survey(code, dump if dump.upper().startswith(code) else "")
        except Exception as exc:               # noqa: BLE001
            print("%-5s  跳过：%s" % (code, exc))
            continue
        for k in total:
            total[k] += got.get(k, 0)
        print("%-5s %5d %5d %4d %4d %6d %6d %8.0f"
              % (code, got["rooms"], got["water"], got["acid"], got["sand"],
                 got["corrupt"], got["both"], got["ms"]))
        if got["samples"]:
            print("      样例 %s" % ", ".join("%s(%s)" % (n, "/".join(k))
                                              for n, k in got["samples"]))
    print("-" * 56)
    print("合计 %d 间：水 %d / 酸 %d / 沙 %d / 腐化 %d"
          % (total["rooms"], total["water"], total["acid"], total["sand"], total["corrupt"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
