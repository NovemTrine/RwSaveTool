"""P0 对拍：工具侧 `core.regmap`（走 room_geo）与 demo `region_map`（自带解析）逐位一致。

用法：
    .venv/Scripts/python.exe build/check_regmap_parity.py            # 全库
    .venv/Scripts/python.exe build/check_regmap_parity.py UW MS TL   # 指定区域

判定：
    · 房间名集合相同
    · 每间房 x/y/w/h 差 ≤ 1e-6
    · 边集合（a,b,kind,route）相同，条数相同
    · stats 里 rooms / edges / overlaps / route_unresolved 相同
任何一项不符 → 打印前 5 处差异并以退出码 1 结束。

DEP 说明：demo 只在本机存在（`../AI_Workspace/.../2026-11-19-23-55-46`），
这是开发期对拍脚本，不进打包产物。
"""

from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEMO = r"D:/Projects/AI_Workspace/WorkBuddy_Workspace/2026-11-19-23-55-46"
if os.path.isdir(DEMO):
    sys.path.insert(0, DEMO)

import region_map                                   # noqa: E402  demo
from core import paths                              # noqa: E402
from core.regmap import adapter                     # noqa: E402

TOL = 1e-6


def region_codes() -> list[str]:
    out = []
    for p in sorted(glob.glob(os.path.join(paths.data_dir(), "*.json"))):
        name = os.path.basename(p)[:-5]
        if not name.startswith("_"):
            out.append(name.upper())
    return out


def compare(code: str) -> list[str]:
    path = os.path.join(paths.data_dir(), code + ".json")
    tool = adapter.build(code)
    demo = region_map.build_region_layout(path, code=code)

    bad = []
    tn = {n["name"]: n for n in tool["nodes"]}
    dn = {n["name"]: n for n in demo["nodes"]}
    if set(tn) != set(dn):
        only_t = sorted(set(tn) - set(dn))[:5]
        only_d = sorted(set(dn) - set(tn))[:5]
        bad.append("房间集合不同：工具多 %s / demo 多 %s" % (only_t, only_d))
    for name in sorted(set(tn) & set(dn)):
        for f in ("x", "y", "w", "h"):
            if abs(tn[name][f] - dn[name][f]) > TOL:
                bad.append("%s.%s %.6f != %.6f" % (name, f, tn[name][f], dn[name][f]))
                break

    def ekey(e):
        # `kind` / `route` 可能是 None（门/绕行判不出来时），直接进元组排序会
        # `'<' not supported between NoneType and str` —— 统一转成字符串再比。
        return (str(e["a"]), str(e["b"]), str(e.get("kind") or ""), str(e.get("route") or ""))

    te = sorted(ekey(e) for e in tool["edges"])
    de = sorted(ekey(e) for e in demo["edges"])
    if te != de:
        bad.append("边集合不同：工具 %d 条 / demo %d 条" % (len(te), len(de)))
        for x in sorted(set(te) ^ set(de))[:5]:
            bad.append("  差异边 %s" % (x,))

    for k in ("rooms", "edges", "overlaps", "route_unresolved"):
        if tool["stats"].get(k) != demo["stats"].get(k):
            bad.append("stats[%s] %r != %r" % (k, tool["stats"].get(k), demo["stats"].get(k)))
    return bad


def main() -> int:
    if not os.path.isdir(DEMO):
        print("找不到 demo 目录：%s" % DEMO)
        return 2
    codes = [c.upper() for c in sys.argv[1:]] or region_codes()
    print("对拍 %d 个区域（容差 %g）…" % (len(codes), TOL))
    fails = 0
    rooms = edges = 0
    for code in codes:
        try:
            bad = compare(code)
        except Exception as exc:                    # noqa: BLE001
            print("%-6s 异常：%s" % (code, exc))
            fails += 1
            continue
        st = adapter.probe(code)
        rooms += st.get("rooms") or 0
        if bad:
            fails += 1
            print("%-6s 失败 %d 处" % (code, len(bad)))
            for line in bad[:5]:
                print("       " + line)
        else:
            print("%-6s ok（%d 间）" % (code, st.get("rooms") or 0))
    print("\n区域 %d 个，房间 %d 间，失败 %d 个" % (len(codes), rooms, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
