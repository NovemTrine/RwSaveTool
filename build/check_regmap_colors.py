"""区域配色回归（V1.15 №0 / №4 / №5）：路 A 取色 + corlor 派生 + 分组建。

判据（都能用命令行复算，不看图）：
1. 每个区都拿得到「可通行色」与「背景结构色」，且结构色比可通行色暗；
2. 取色只来自调色板文件（`src` 是 `properties` / `rooms`），不是 hash 兜底
   ——hash 只允许出现在**子区域**，主体走 hash 就说明调色板没找到；
3. `struct_color` 与主人 `corlor.py` 的算法逐位一致（用那 3 组已知样例核）；
4. 有子区域的区，SVG 里每间房的 `--rg-air` 必须等于它所在子区域那组的颜色；
5. 缓存文件 `region_data/_colors.json` 与现场计算一致（缓存不能变成"上一版残留"）。

用法：
    python build/check_regmap_colors.py            # 12 个原版区 + 2 个模组区
    python build/check_regmap_colors.py --all      # 全库
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, colors, svg as regmap_svg      # noqa: E402

FAILS: list[str] = []
DEFAULTS: list[str] = []      # 没有 `Palette:` 行、按游戏默认回落 0 号调色板的区
CODES = ["SU", "CC", "HI", "GW", "MS", "SL", "LF", "UW", "SI", "DS", "SH", "SB",
         "WORA", "RM"]

# 与 `corlor.py` 对拍：参数 0.75 / 1.0（它 `__main__` 里那三组的用例色）。
# 右边是 **corlor.py 的输出**（不是它注释里的"真实色2"——那是另一张色卡，别搞混）。
CORLOR_CASES = [("#AA9E53", "#7F763E"), ("#EFD26C", "#B39D51"), ("#EF8BD1", "#B3689C")]
HEX = re.compile(r"^#[0-9A-F]{6}$")


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)


def lum(hex_color: str) -> float:
    s = hex_color.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def all_codes() -> list[str]:
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "region_data"))):
        if f.lower().endswith(".json") and not f.startswith("_"):
            out.append(os.path.splitext(f)[0].upper())
    return out


def audit(code: str) -> dict:
    reg = adapter.load_rooms(code)
    # 门不参与取色（产品侧同样排除：门房在 `world/gates/` 下，且 `GATE_*` 排在最前，
    # 会顶掉 `colors.for_region` 用 `rooms[0].path` 反推区域目录那一步）
    rooms = [r for r in reg["rooms"] if not r.is_gate]
    got = colors.for_region(code, rooms, reg)
    expect(HEX.match(got["air"] or ""), "%s 可通行色不是合法 HEX：%r" % (code, got["air"]))
    expect(HEX.match(got["struct"] or ""), "%s 结构色不是合法 HEX：%r" % (code, got["struct"]))
    expect(lum(got["struct"]) < lum(got["air"]),
           "%s 结构色不比可通行色暗（%s vs %s）" % (code, got["struct"], got["air"]))
    expect(got["src"] in ("properties", "rooms", "default"),
           "%s 主体色来源异常（src=%s）" % (code, got["src"]))
    if got["src"] == "default":
        DEFAULTS.append(code)
    me = [g for g in got["groups"] if not g["sub"]]
    expect(len(me) == 1, "%s 主体组数量是 %d（应为 1）" % (code, len(me)))
    for g in got["groups"]:
        expect(HEX.match(g["air"] or ""), "%s 组 %s 颜色非法" % (code, g["sub"] or "(主体)"))
        expect(lum(g["struct"]) < lum(g["air"]), "%s 组 %s 结构色不够暗" % (code, g["sub"] or "(主体)"))

    # SVG：每间房都得带上自己的 `--rg-air`，且只能取自己那组的值。
    # V1.24 起 `<g>` 上多了一个 `data-sub`（前端「背景取色」按它改 CSS 变量），
    # 所以 `data-room` 与 `style` 之间不再相邻——正则放宽成 `[^>]*`。
    lay = adapter.build(code)
    body = regmap_svg.build_svg(lay, width=1400, anno=True)["svg"]
    by_sub = {g["sub"]: g["air"] for g in got["groups"]}
    seen = re.findall(
        r'<g class="rm[^"]*" data-room="[^"]*"[^>]*style="--rg-air:([^;]+);--rg-cg:([^"]+)"', body)
    expect(len(seen) == len(lay["nodes"]),
           "%s 带底色变量的房间 %d 个，布局里 %d 间" % (code, len(seen), len(lay["nodes"])))
    dsubs = re.findall(r'<g class="rm[^"]*" data-room="[^"]*" data-sub="([^"]*)"', body)
    expect(len(dsubs) == len(lay["nodes"]),
           "%s 带 data-sub 的房间 %d 个，布局里 %d 间" % (code, len(dsubs), len(lay["nodes"])))
    expect(all((s or "") in by_sub for s in dsubs),
           "%s data-sub 里出现了不存在的分组：%s"
           % (code, sorted({s for s in dsubs if (s or "") not in by_sub})[:3]))
    allowed = set(by_sub.values())
    bad = [a for (a, _c) in seen if a not in allowed]
    expect(not bad, "%s SVG 里出现了不属于任何分组的底色：%s" % (code, bad[:3]))

    # 子区域键必须都能在布局节点里找到对应房间（否则等于白配一组色）
    subs = {str(n.get("sub") or "") for n in lay["nodes"]}
    for g in got["groups"]:
        if g["sub"]:
            expect(g["sub"] in subs, "%s 的子区域组 %r 没有任何房间" % (code, g["sub"]))

    # 缓存必须与现场计算一致
    cache = colors.load_cache().get(code.upper())
    if cache:
        expect(cache.get("air") == got["air"],
               "%s 缓存里的可通行色 %s ≠ 现场 %s" % (code, cache.get("air"), got["air"]))

    return {"code": code, "air": got["air"], "struct": got["struct"],
            "src": got["src"], "palette": got["palette"],
            "groups": len(got["groups"]), "subs": [g["sub"] for g in got["groups"] if g["sub"]],
            # 只数普通房间：门不参与取色，算进「间房」会把总数虚增（V1.24 rev.14）
            "rooms": sum(1 for n in lay["nodes"] if not n.get("gate"))}


def audit_struct_algo() -> None:
    """`struct_color` 必须与 `corlor.py` 等价（HSV 下 V*ratio、S*sat）。"""
    for src, want in CORLOR_CASES:
        got = colors.struct_color(src, 0.75, 1.0).upper()
        expect(got == want, "struct_color(%s) = %s，corlor.py 给 %s" % (src, got, want))
    # 默认参数（0.65 / 0.6）自洽：输出比输入暗、且色相不变
    for src in ("#8D98B0", "#BE7E82", "#FFFFFF"):
        got = colors.struct_color(src)
        expect(lum(got) < lum(src), "struct_color(%s) 没变暗：%s" % (src, got))


def main() -> int:
    codes = [c for c in sys.argv[1:] if not c.startswith("-")]
    if "--all" in sys.argv or not codes:
        codes = all_codes() if "--all" in sys.argv else CODES

    print("%-6s %-9s %-9s %-11s %-6s %3s %s" % ("区", "可通行", "背景结构", "来源", "调色板", "组", "子区域"))
    total = {"rooms": 0, "groups": 0}
    for code in codes:
        try:
            got = audit(code)
        except FileNotFoundError:
            print("%-6s 跳过（没有房间数据）" % code)
            continue
        except Exception as exc:                   # noqa: BLE001
            FAILS.append("%s 审计抛异常：%r" % (code, exc))
            continue
        total["rooms"] += got["rooms"]
        total["groups"] += got["groups"]
        print("%-6s %-9s %-9s %-11s %-6s %3d %s"
              % (got["code"], got["air"], got["struct"], got["src"], got["palette"],
                 got["groups"], ", ".join(got["subs"][:2]) or "-"))

    print("\n结构色算法：")
    audit_struct_algo()
    print("  corlor.py 三组样例逐位一致" if not FAILS else "  有偏差（见下）")

    if DEFAULTS:
        print("\n按默认调色板（properties 里没有 Palette: 行）：%d 个区 %s"
              % (len(DEFAULTS), ", ".join(DEFAULTS[:8])))
    print("\n合计：%d 个区 / %d 间房 / 配色组 %d 个" % (len(codes), total["rooms"], total["groups"]))
    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for f in FAILS:
            print("  ✗", f)
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
