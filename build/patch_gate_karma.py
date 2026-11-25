"""把业力门槛烘焙进 `region_data/*.json`（V1.24 №8，一次性增量补丁，幂等）。

数据来源：`<游戏目录>/RainWorld_Data/StreamingAssets/world/gates/locks.txt`
（原版 18 门；第 4 段 `SWAPMAPSYMBOL` 只表示两端在图上对调，本轮不使用）。
只写 `rooms[].karma = [左, 右]`，**不动** `source.files` 指纹 / `stats` / `variants`，
所以发布前不需要再跑 `strip_local_paths.py`，也不会触发「来源已过期」。

用法：
    python build/patch_gate_karma.py                 # 只报告
    python build/patch_gate_karma.py --write         # 真写
    python build/patch_gate_karma.py --root "D:/.../Rain World"   # 指定游戏目录
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import official_world, paths          # noqa: E402
from core import mod_importer                   # noqa: E402


def game_world_dir(root: str | None) -> str:
    if root:
        root = os.path.normpath(root)
        cand = os.path.join(root, "RainWorld_Data", "StreamingAssets", "world")
        if os.path.isdir(cand):
            return cand
        # 允许直接给 StreamingAssets 或 world
        for alt in (os.path.join(root, "world"), root):
            if os.path.isdir(os.path.join(alt, "gates")) or os.path.isfile(
                    os.path.join(alt, "gates", "locks.txt")):
                return alt
        return ""
    inst = official_world.find_installations()
    if not inst:
        return ""
    return os.path.join(inst[0]["root"], "RainWorld_Data", "StreamingAssets", "world")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="真写（默认只报告）")
    ap.add_argument("--root", default=None, help="雨世界安装目录（默认自动探测）")
    args = ap.parse_args(argv)

    world = game_world_dir(args.root)
    locks = mod_importer.read_gate_locks(world) if world else {}
    print("游戏 world 目录：%s" % (world or "（没找到）"))
    if not locks:
        print("读不到 locks.txt，什么也不做。可用 --root 指定游戏目录。")
        return 1
    print("locks.txt：%d 门（含 SWAPMAPSYMBOL 的门也收，左右数字照抄）" % len(locks))

    files, gates_hit, rooms_touched, missing = 0, set(), 0, []
    for path in sorted(glob.glob(os.path.join(paths.data_dir(), "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("跳过（读不了）：%s %s" % (base, exc))
            continue
        gate_names = {str(r.get("name") or "").strip().upper()
                      for L in data.get("layers") or []
                      for r in L.get("rooms") or []
                      if str(r.get("name") or "").startswith("GATE_")}
        if not gate_names:
            continue
        # 该区有门房，但 locks.txt 里一个都没有 → 模组区，记一笔（不是错）
        for name in sorted(gate_names):
            if name in locks:
                gates_hit.add(name)
            elif name not in missing:
                missing.append(name)
        before = rooms_touched
        rooms_touched += mod_importer.bake_gate_karma([data], locks)
        if rooms_touched > before:
            files += 1
            if args.write:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, path)

    print("\n门：locks.txt 里 %d 个，命中数据 %d 个；没门槛的门房 %d 个（模组门，留空）"
          % (len(locks), len(gates_hit), len(missing)))
    print("%s：%d 个区域 / %d 条房间记录"
          % ("已写入" if args.write else "待写（加 --write 才写）", files, rooms_touched))
    if missing:
        print("（没门槛的示例：%s）" % ", ".join(sorted(missing)[:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
