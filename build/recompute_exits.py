"""重建区域缓存（设计文档 B1 + P1 的落地工具）· 一次性维护脚本。

背景：
    代码早已支持 `connections`（P0）与 `exits`（P1），但盘上的区域缓存还是 schema 2，
    两个字段都没有。而 P1 之前还必须先修一个真 bug：导入器原先**整个跳过** `modify/`
    目录，导致 Downpour 对原版区域的改动（SL 等）从来没被读进来。

它做什么：
    1. 备份整个 region_data（zip，含 _overrides.json / _sources.json）；
    2. 重导**官方包**（base / Downpour / Watcher / expedition）；
    3. 按已有层里记录的 `source.modRoot`，把**仍存在的模组**逐个重导；
    4. 打验收报告：每间房取「加载顺序最靠后」的那一层，列出出口数≠槽位数的房间。

安全：
    · 默认 --dry-run，只报告不写；
    · 官方包与模组都走正常导入链路，`_overrides.json`（用户改名）与
      `_sources.json`（来源开关）不会被覆盖；
    · 找不到目录的模组只跳过并报告，不删数据。

用法：
    .venv/Scripts/python.exe build/recompute_exits.py            # 只报告
    .venv/Scripts/python.exe build/recompute_exits.py --apply    # 真写
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import mod_importer, official_world, paths, region_store  # noqa: E402

BASE12 = {"SL", "GW", "SU", "HI", "CC", "DS", "SB", "LF", "SI", "SH", "SS", "UW"}
# 已由主人逐口核对过的房间（设计文档 §5.4）：它们必须仍然是 truncated
CONFIRMED = {"SL_D01", "SL_BRIDGE01", "SB_B04", "SI_SAINTINTRO", "SH_B02", "GATE_UW_LC"}
BACKUP_DIR = os.path.join(ROOT, "build", "_backup")


def _region_files(directory: str) -> list[str]:
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    return [
        os.path.join(directory, name)
        for name in names
        if name.lower().endswith(".json") and not name.startswith("_")
    ]


def _load(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _backup(directory: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    target = os.path.join(BACKUP_DIR, "region_data_%s.zip" % time.strftime("%Y%m%d-%H%M%S"))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _region_files(directory):
            zf.write(path, os.path.basename(path))
        for extra in ("_overrides.json", "_sources.json"):
            candidate = os.path.join(directory, extra)
            if os.path.isfile(candidate):
                zf.write(candidate, extra)
    return target


def _summary(regions: list[dict]) -> dict:
    rooms = sum(len(r.get("rooms") or []) for r in regions)
    return {"layers": len(regions), "rooms": rooms}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None, help="游戏根目录（默认自动探测）")
    parser.add_argument("--apply", action="store_true", help="真的写入（默认只报告）")
    parser.add_argument("--prune", action="store_true",
                        help="顺带删掉「本次没重导出来且 0 房间」的空壳层；有房间的旧层一律保留")
    args = parser.parse_args()

    directory = paths.data_dir()
    files = _region_files(directory)
    print("数据目录：%s" % directory)
    print("现有区域文件：%d 个" % len(files))
    if not files:
        print("没有可重建的数据，退出。")
        return 1

    # 先收集现有数据里的模组根（要在覆盖之前读）
    mod_roots: dict[str, str] = {}
    for path in files:
        data = _load(path) or {}
        for layer in data.get("layers") or []:
            source = layer.get("source") or {}
            root = source.get("modRoot")
            layer_id = layer.get("id")
            if root and str(layer_id or "").startswith("mod:") and layer_id not in mod_roots:
                mod_roots[layer_id] = root
    print("记录到的模组层：%d 个" % len(mod_roots))

    # ---- 1. 官方包 -----------------------------------------------------
    official = official_world.import_official(args.root)
    if not official.get("ok"):
        print("官方导入失败：%s" % official.get("error"))
        return 1
    print("\n官方包：%d 个，%d 个区域层，%s" % (
        len(official.get("packs") or []), len(official["regions"]), _summary(official["regions"])))
    print("   出口统计：%s" % (official.get("exitStats"),))
    for warning in (official.get("warnings") or [])[:5]:
        print("   提醒：%s" % warning)

    # ---- 2. 模组 -------------------------------------------------------
    mod_regions: list[dict] = []
    missing: list[tuple[str, str]] = []
    for layer_id, root in sorted(mod_roots.items()):
        if not os.path.isdir(root):
            missing.append((layer_id, root))
            continue
        try:
            result = mod_importer.import_mod(root)
        except Exception as exc:  # noqa: BLE001 - 单个模组失败不影响其它
            missing.append((layer_id, "%s（异常 %s）" % (root, exc)))
            continue
        if not result.get("ok"):
            missing.append((layer_id, "%s（%s）" % (root, result.get("error"))))
            continue
        mod_regions.extend(result.get("regions") or [])
    print("\n模组重导：%d 个成功 / %d 个跳过，%s" % (
        len(mod_roots) - len(missing), len(missing), _summary(mod_regions)))
    for layer_id, reason in missing:
        print("   跳过 %s → %s" % (layer_id, reason))

    # ---- 2.5 旧层清点（可选清理）---------------------------------------
    # 区域文件是按「层」合并保存的：本次没导出来的层会**原样留着**。
    # 但要区分两种：
    #   · 0 房间的层——纯壳（早期导入残留 / 只残留个 label），删了零损失；
    #   · 有房间的层——真实数据（Watcher 给原版区域加的房间、模组补丁层），
    #     删了就是丢数据，所以 --prune 只删前一种，这一种一律保留并报告。
    fresh: dict[str, set[str]] = {}
    for region in list(official["regions"]) + mod_regions:
        fresh.setdefault(region["code"], set()).add((region.get("layer") or {}).get("id"))
    stale: list[tuple[str, str, int]] = []
    for code, ids in sorted(fresh.items()):
        path = os.path.join(directory, code + ".json")
        data = _load(path)
        if not data:
            continue
        for layer in data.get("layers") or []:
            if layer.get("id") not in ids:
                stale.append((code, str(layer.get("id")), len(layer.get("rooms") or [])))
    empty_stale = [s for s in stale if not s[2]]
    busy_stale = [s for s in stale if s[2]]
    print("\n旧层（本次没有重导出来）：%d 个 = 空层 %d + 有房间 %d"
          % (len(stale), len(empty_stale), len(busy_stale)))
    for item in stale[:12]:
        print("   %-4s %-40s 房间 %d" % item)
    if len(stale) > 12:
        print("   …… 另有 %d 个" % (len(stale) - 12))

    # ---- 3. 写入 -------------------------------------------------------
    if args.apply:
        backup = _backup(directory)
        print("\n已备份：%s" % backup)
        if args.prune and empty_stale:
            dropped: dict[str, set[str]] = {}
            for code, layer_id, _rooms in empty_stale:
                dropped.setdefault(code, set()).add(layer_id)
            for code, ids in dropped.items():
                path = os.path.join(directory, code + ".json")
                data = _load(path) or {}
                layers = [l for l in (data.get("layers") or []) if l.get("id") not in ids]
                data["layers"] = layers
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=1)
            print("已清理空层：%d 个层 / %d 个区域（另有 %d 个有房间的旧层保留未删）"
                  % (len(empty_stale), len(dropped), len(busy_stale)))
        elif args.prune:
            print("没有可清理的空层；有房间的旧层 %d 个一律保留" % len(busy_stale))
        for label, regions in (("官方", official["regions"]), ("模组", mod_regions)):
            saved = region_store.save_regions(regions, force=True)
            print("%s层写入：成功 %d，失败 %d" % (
                label, len(saved.get("saved") or []), len(saved.get("failed") or [])))
            for item in (saved.get("failed") or [])[:10]:
                print("   失败：%s" % item)

    # ---- 4. 验收报告 ---------------------------------------------------
    effective: dict[tuple, dict] = {}
    for region in list(official["regions"]) + mod_regions:
        order = int((region.get("layer") or {}).get("order") or 0)
        code = region.get("code")
        for room in region.get("rooms") or []:
            conns = room.get("connections") or []
            exits = room.get("exits") or []
            if not conns or not exits:
                continue
            key = (code, room["name"])
            current = effective.get(key)
            if current is None or order > current["order"]:
                effective[key] = {
                    "exits": len(exits),
                    "slots": len(conns),
                    "order": order,
                    "layer": (region.get("layer") or {}).get("id"),
                }

    rows = sorted(
        (code, name, value["exits"], value["slots"], value["layer"])
        for (code, name), value in effective.items()
        if value["exits"] != value["slots"]
    )
    print("\n出口数 ≠ 槽位数（有效视图）：%d / %d 间" % (len(rows), len(effective)))
    for row in rows:
        print("   %-4s %-20s 出口%-2d/槽%-2d  [%s]" % row)

    base12 = [row for row in rows if row[0] in BASE12]
    print("\n其中 12 个基础区域 %d 间：" % len(base12))
    for row in base12:
        print("   %-3s %-18s 出口%d/槽%d" % row[:4])

    hit = {row[1] for row in rows}
    missing_confirmed = CONFIRMED - hit
    print("\n已确认的 6 间仍为 truncated：%s" % ("是" if not missing_confirmed else "缺 %s" % sorted(missing_confirmed)))
    if not args.apply:
        print("\n（dry-run，什么都没写。加 --apply 才落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
