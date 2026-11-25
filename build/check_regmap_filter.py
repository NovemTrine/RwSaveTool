"""№6 来源筛选 + №7 条件房间的回归（无头，不画图，只看「装进来哪些房间」）。

用法：
    .venv/Scripts/python.exe build/check_regmap_filter.py

判据：
1. 变体键大小写：`Artificer` 与 `artificer` 装出同一批房间（修前 124 / 98）；
2. 角色差异：White 与 Artificer 的房间集合不同，且都 ⊆ 不筛时的全量；
3. 来源筛选：熄灭全部模组来源后房间仍是全量的子集且更少；
4. 取色稳定：`color_rooms` 恒等于「不筛时的房间数」，配色组与不筛时**逐字节相同**；
5. 严格口径：手工剔除只在 `strict=True` 时生效；
6. 脏数据：`{...}` 被切碎的角色名能洗干净（WAUA 的 `!TOYSENDING}WATCHER` → `WATCHER`）；
7. 缓存键：筛选口径进 `_regmap_key`（换角色必须换 key），未登记的来源 id 当启用。
"""
from __future__ import annotations

import json
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.bridge import _regmap_filters, _regmap_key  # noqa: E402
from core.regmap import adapter, colors               # noqa: E402
from core.regmap.model import _clean_roles           # noqa: E402

FAILS: list[str] = []
_CACHE: dict = {}


def expect(ok, msg):
    if not ok:
        FAILS.append(msg)


def load(code, role="", off=(), strict=True, ex=()):
    key = (code, role, tuple(off), bool(strict), tuple(ex))
    if key not in _CACHE:
        _CACHE[key] = adapter.load_rooms(code, role, {
            "off": list(off), "role": role, "strict": bool(strict), "ex": list(ex)})
    return _CACHE[key]


def raw(code, role=""):
    """**完全不筛**（`filters=None`）：demo / 形状评分那条路，用作对照基线。"""
    key = ("raw", code, role)
    if key not in _CACHE:
        _CACHE[key] = adapter.load_rooms(code, role)
    return _CACHE[key]


def names(region):
    return {r.name for r in region["rooms"]}


def mod_layers(code):
    path = adapter.region_path(code)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return sorted({str(L.get("id") or "") for L in data.get("layers") or []
                   if str(L.get("id") or "").startswith("mod:")})


def main() -> int:
    GW = "GW"
    full = raw(GW)                                    # 完全不筛：对照基线（124 间）
    full_names = names(full)

    # 1. 变体键大小写
    upper = load(GW, "Artificer")
    lower = load(GW, "artificer")
    print("GW 全量 %d 间（含门 %d 座）/ Artificer %d 间（战役表 %d）/ artificer %d 间"
          % (len(full_names), len([r for r in full["rooms"] if r.is_gate]),
             len(names(upper)), upper["rooms_total"], len(names(lower))))
    expect(names(upper) == names(lower), "大小写归一：Artificer 与 artificer 房间集合不一致")
    # V1.24 起大门也进 `keep`，`rooms_total` 会比战役表的 98 多出门的座数；
    # 把门扣掉再比，仍然是「战役表命中 98 间」这条老口径。
    gate_total = len([r for r in upper["rooms"] if r.is_gate]) + upper["dropped"]["gate"]
    expect(upper["rooms_total"] - gate_total == 98,
           "Artificer 战役表没命中（应为 98 间，实际 %d）" % (upper["rooms_total"] - gate_total))

    # 2. 角色差异
    white = load(GW, "White")
    expect(names(white) != names(upper), "White 与 Artificer 装出了同一批房间（角色筛选没起作用）")
    expect(names(white) <= full_names, "White 的房间不在全量里（不该凭空多出房间）")
    expect(len(names(white)) < len(full_names), "White 没有剔掉任何条件房间")
    print("GW White %d 间 · 剔除 %s" % (len(names(white)), white["dropped"]))

    # 3. 来源筛选
    off = mod_layers(GW)
    base = load(GW, "White", off=off)
    print("GW 熄灭 %d 个模组来源 → %d 间（剔除 %s）"
          % (len(off), len(names(base)), base["dropped"]))
    expect(names(base) <= names(white), "来源筛选后出现了不在原集合里的房间")
    expect(len(names(base)) < len(names(white)), "熄灭模组来源后房间数没减少（№6 没生效）")

    # 4. 取色稳定：对照同一个战役、**不筛**的那一版（门不参与取色，两边都扣掉）
    base_rooms = raw(GW, "Artificer")
    base_pick = [r for r in base_rooms["rooms"] if not r.is_gate]
    c0 = colors.for_region(GW, base_pick, base_rooms)
    c1 = colors.for_region(GW, upper.get("color_rooms") or [], upper)
    print("取色房间数：不筛 %d / 筛后 color_rooms %d"
          % (len(base_pick), len(upper.get("color_rooms") or [])))
    expect(len(upper.get("color_rooms") or []) == len(base_pick),
           "color_rooms 不等于筛选前的房间数（切来源/角色会让配色跳）")
    expect(c0["groups"] == c1["groups"], "筛选改变了区域配色（应当与筛选无关）")

    # 5. 严格口径 + 手工剔除：挑一间**有邻居**的房，手工剔掉
    # 挑普通房间（不挑 GATE_*）：门是叶子节点，剔掉它测不出「严格口径 vs 宽松口径」的差别
    connected = sorted(n for n in names(upper) if not n.startswith("GATE_")
                       and any(n == to for r in upper["rooms"] for _x, _y, to in r.exits))
    expect(bool(connected), "GW Artificer 里找不到有邻居的房间，无法测严格口径")
    if connected:
        victim = connected[0]
        tight = load(GW, "Artificer", ex=(victim,))
        loose = load(GW, "Artificer", ex=(victim,), strict=False)
        print("手工剔除 %s：严格口径 %d 间（manual %d）/ 宽松 %d 间"
              % (victim, len(names(tight)), tight["dropped"]["manual"], len(names(loose))))
        expect(victim not in names(tight), "严格口径没剔掉手工标记的房间")
        expect(victim in names(loose), "宽松口径不该剔除手工标记的房间")
        expect(tight["dropped"]["manual"] == 1, "manual 计数不是 1")

    # 6. 脏数据清洗
    expect(_clean_roles(["{POSTBATHSCENE", "!TOYSENDING}WATCHER"]) == ["WATCHER"],
           "_clean_roles 没把切碎的角色名洗成 WATCHER")
    expect(_clean_roles(["{ONLYSTORY}"]) == [], "_clean_roles 该丢掉纯剧情标记")
    if os.path.isfile(adapter.region_path("WAUA")):
        watcher = load("WAUA", "Watcher")
        expect("WAUA_A06B" not in names(watcher), "WAUA_A06B 没按 hidden 剔掉（脏数据没洗）")
        expect(watcher["dropped"]["hidden"] >= 2, "WAUA 的 hidden 计数不对")

    # 7. 数字自洽：rooms = rooms_total − Σdropped − missing（界面上的说明要能对上）
    for label, got in (("GW White", white), ("GW Artificer", upper), ("GW 熄模组", base)):
        lhs = len(got["rooms"])
        rhs = got["rooms_total"] - sum(got["dropped"].values()) - len(got["missing"])
        expect(lhs == rhs, "%s 房间数对不上：rooms=%d，total-Σdrop-missing=%d"
               % (label, lhs, rhs))

    # 8. 缓存键
    flt_a = _regmap_filters(GW, "White")
    flt_b = _regmap_filters(GW, "Artificer")
    print("筛选口径：%s" % json.dumps(flt_a, ensure_ascii=False, sort_keys=True)[:120])
    expect(flt_a != flt_b, "_regmap_filters 对两个角色给了同一份口径")
    ka = _regmap_key(GW, "White", {"flt": flt_a})
    kb = _regmap_key(GW, "Artificer", {"flt": flt_b})
    expect(ka != kb, "筛选口径没进缓存键（换角色会命中旧图）")
    same = load(GW, "White", off=("mod:并不存在",))
    expect(names(same) == names(white), "未登记的来源 id 不该被当成「已熄灭」")
    expect(load(GW, "")["dropped"]["exclusive"] > 0,
           "主线（无角色）应当把 exclusive 房间剔掉")

    if FAILS:
        print("\n失败 %d 项：" % len(FAILS))
        for f in FAILS:
            print("  ✗", f)
        return 1
    print("\nCHECK OK（%d 种筛选组合）" % len(_CACHE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
