"""№8 等价来源折叠的回归。

用法：
    .venv/Scripts/python.exe build/check_dup_sources.py

判据（这条改动只有一个硬指标，其余都是护栏）：
1. **并集恒等**：117 个区域在「折叠」与「强制全开」两种口径下，
   `activeRooms` 必须完全相同 —— 折叠只减噪，绝不能少房间；
2. 判定命中：`moreslugcats` 与 `watcher` 两对都在，且都指向 official 侧；
3. 默认熄灭：等价层的生效 `enabled` 是 False，官方侧是 True；
4. 用户优先：显式点亮后不再被折叠覆盖（测完还原）；
5. 注册表干净：`_sources.json` 里不能出现 `dupOf` / `folded` 这类派生字段；
6. 名字：`official:watcher` 显示成「The Watcher（观望者）」，`official:moreslugcats` 带 MSE 别名。
"""
from __future__ import annotations

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import paths, region_store, sources  # noqa: E402

FAILS: list[str] = []
PASS = 0


def check(ok, msg: str, detail: str = "") -> None:
    global PASS
    if ok:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAILS.append(msg)
        print(f"  ❌ {msg}" + (f"  ← {detail}" if detail else ""))


def main() -> int:
    regions = region_store.all_regions()
    if not regions:
        print("没有 region_data，跳过。")
        return 0

    print("\n[1] 判定命中")
    pairs = sources.duplicate_pairs()
    print(f"  · 命中 {len(pairs)} 对：{pairs}")
    check(pairs.get("mod:moreslugcats") == "official:moreslugcats",
          "MSE 模组层指向 Downpour 官方层", str(pairs.get("mod:moreslugcats")))
    check(pairs.get("mod:watcher") == "official:watcher",
          "The Watcher 模组层指向 Watcher 官方层", str(pairs.get("mod:watcher")))
    check("official:base" not in pairs.values(), "官方原版层不参与折叠")

    print("\n[2] 并集恒等（唯一的硬指标）")
    # 只有「这一区所有来源都亮着」时才有 activeRooms == unionRooms。
    # 用户关掉某个来源（`enabled=False`）后两者本来就不等——那不是 bug，是开关在起作用。
    # （2026-11-27：`mod:harvie.thedronemaster` 被关，DMD / FW / NLA 三个只有它一层的区
    #   activeRooms=0，原断言误报。这里改成跳过这些区，仍然盯「全亮时恒等」。）
    offenders, skipped = [], []
    for code, region in regions.items():
        layers = region.get("layers") or []
        if any(not l.get("enabled") for l in layers):
            skipped.append(code)
            continue
        if region.get("activeRooms") != region.get("unionRooms"):
            offenders.append((code, region.get("activeRooms"), region.get("unionRooms")))
    if skipped:
        print(f"  · 跳过 {len(skipped)} 个有来源被关的区：{sorted(skipped)[:8]}")
    check(not offenders, f"{len(regions) - len(skipped)} 区（来源全亮）activeRooms == unionRooms",
          str(offenders[:5]))

    # 强制「不折叠」再算一遍：两种口径的结果必须逐区相同
    saved = sources._dup_cache
    try:
        sources._dup_cache = {}
        diff = []
        for code, region in regions.items():
            fresh = region_store.get_region(code) or {}
            if fresh.get("activeRooms") != region.get("activeRooms"):
                diff.append((code, region.get("activeRooms"), fresh.get("activeRooms")))
        check(not diff, "折叠态与全开态的 activeRooms 逐区一致", str(diff[:5]))
    finally:
        sources._dup_cache = saved

    print("\n[3] 默认熄灭")
    enabled = sources.enabled_map()
    check(enabled.get("mod:moreslugcats") is False, "MSE 模组层默认熄灭")
    check(enabled.get("mod:watcher") is False, "The Watcher 模组层默认熄灭")
    check(enabled.get("official:moreslugcats") is True, "Downpour 官方层默认点亮")
    check(enabled.get("official:watcher") is True, "The Watcher 官方层默认点亮")

    sample = "CC" if "CC" in regions else sorted(regions)[0]
    reg = regions[sample]
    folded_layers = [l for l in reg.get("layers") or [] if l.get("dupOf")]
    check(bool(folded_layers), f"{sample} 的层带上了 dupOf 标记",
          str([l["id"] for l in folded_layers]))
    check(all(not l.get("enabled") for l in folded_layers),
          "带 dupOf 的层在装配后是熄灭态")

    print("\n[4] 用户优先（测完还原）")
    cfg_file = os.path.join(paths.data_dir(), sources.REGISTRY_FILE)
    backup = cfg_file + ".bak_test"
    existed = os.path.isfile(cfg_file)
    if existed:
        shutil.copy2(cfg_file, backup)
    try:
        sources.set_enabled("mod:moreslugcats", True)
        after = sources.enabled_map()
        check(after.get("mod:moreslugcats") is True, "显式点亮后不再被折叠覆盖")
        check(sources.duplicate_pairs().get("mod:moreslugcats") == "official:moreslugcats",
              "但判定本身还在（结构上是重复的）")

        print("\n[5] 注册表干净")
        with open(cfg_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        keys = set()
        for item in raw.get("sources") or []:
            keys |= set(item.keys())
        check(not ({"dupOf", "folded"} & keys),
              "派生字段没有写进 _sources.json", str(sorted(keys)))
        check("userSet" in keys, "userSet 有落盘（用户意图要持久）", str(sorted(keys)))
    finally:
        if existed and os.path.isfile(backup):
            os.replace(backup, cfg_file)
        elif os.path.isfile(backup):
            os.remove(backup)
        sources.invalidate_duplicates()

    print("\n[6] 显示名")
    reg2 = sources.registry_enabled()
    check(reg2.get("official:watcher", {}).get("name") == "The Watcher（观望者）",
          "official:watcher 显示为「The Watcher（观望者）」",
          str(reg2.get("official:watcher", {}).get("name")))
    check(sources.aka_of("official:moreslugcats") == "More Slugcats Expansion",
          "Downpour 带「亦称 More Slugcats Expansion」别名",
          sources.aka_of("official:moreslugcats"))

    print()
    if FAILS:
        print(f"FAIL：{len(FAILS)} 项")
        for item in FAILS:
            print(f"  - {item}")
        return 1
    print(f"CHECK DUP SOURCES OK（{PASS} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
