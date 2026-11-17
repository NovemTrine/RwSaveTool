"""把发布包里区域数据中的**本机绝对路径**抹掉。

为什么需要它
------------
`region_data/<CODE>.json` 是「在某台机器上导入后的结果」，每个 layer 的 `source`
里都记着当时的绝对路径：

    source.path / files[].dir / worldDirs / roomsDirs / modRoot / gameRoot
    map.imagePath / variants.*.imagePath / overridePaths / fallbackDir

这些路径有两个问题：

1. **对别人没用**——换台机器必然失效（程序自己会提示「底图路径不可用，重新导入」，
   房间清单与完成度照常）。所以抹掉不损失任何功能。
2. **属于本机信息**——Steam 库位置、创意工坊 `312520/<id>` 目录都在里面，
   不该随发布包发到公网。包内 `VERSION.txt` 明写「个人数据 不含 … 无本机路径」，
   不抹就是自相矛盾。

做法：结构不动，只把「看起来像绝对路径的字符串」换成空串，列表里则直接删掉该元素
（留下 `""` 会让 `os.path.join` 拼出相对路径，虽然也是 False，但不如空列表干净）。

用法
----
    # 先看会改什么（不写盘）
    .venv/Scripts/python.exe build/strip_local_paths.py --target release/<NAME>/region_data --dry-run

    # 就地改（只改 target 目录里的副本，不动仓库里那份）
    .venv/Scripts/python.exe build/strip_local_paths.py --target release/<NAME>/region_data

    # 改完复核（应输出 0）
    .venv/Scripts/python.exe build/strip_local_paths.py --target release/<NAME>/region_data --check
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys

# 盘符开头（D:\ / d:/）或 UNC（\\server\share）
WIN_ABS = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _looks_like_path(value: str) -> bool:
    return bool(value) and bool(WIN_ABS.match(value))


def _walk(node, key_path: str, hits: collections.Counter, samples: dict) -> int:
    """返回这一支里被抹掉的路径个数。"""
    removed = 0
    if isinstance(node, dict):
        for key, val in list(node.items()):
            child = "%s/%s" % (key_path, key)
            if isinstance(val, str) and _looks_like_path(val):
                hits[child] += 1
                samples.setdefault(child, val)
                node[key] = ""
                removed += 1
            elif isinstance(val, list):
                kept = []
                for item in val:
                    if isinstance(item, str) and _looks_like_path(item):
                        hits[child + "[]"] += 1
                        samples.setdefault(child + "[]", item)
                        removed += 1
                    elif isinstance(item, (dict, list)):
                        removed += _walk(item, child + "[]", hits, samples)
                        kept.append(item)
                    else:
                        kept.append(item)
                node[key] = kept
            elif isinstance(val, (dict, list)):
                removed += _walk(val, child, hits, samples)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                removed += _walk(item, key_path + "[]", hits, samples)
    return removed


def process(path: str, hits: collections.Counter, samples: dict, dry: bool) -> tuple[int, int]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(json.dumps(data, ensure_ascii=False))
    removed = _walk(data, "", hits, samples)
    if removed and not dry:
        text = json.dumps(data, ensure_ascii=False, indent=1)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    return removed, before


def count_remaining(target: str) -> tuple[int, int]:
    """还剩多少个文件带本机路径、总共几处。"""
    files = bad = 0
    for path in sorted(glob.glob(os.path.join(target, "*.json"))):
        raw = open(path, encoding="utf-8").read()
        if WIN_ABS.search(raw):
            files += 1
            bad += len(WIN_ABS.findall(raw))
    return files, bad


def main() -> int:
    ap = argparse.ArgumentParser(description="抹掉区域数据里的本机绝对路径")
    ap.add_argument("--target", required=True, help="region_data 目录（发布包里的那份副本）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写盘")
    ap.add_argument("--check", action="store_true", help="复核：应剩 0 个文件")
    args = ap.parse_args()

    if not os.path.isdir(args.target):
        print("目录不存在:", args.target)
        return 1

    if args.check:
        files, bad = count_remaining(args.target)
        print("仍含本机路径的文件 %d 个，共 %d 处" % (files, bad))
        return 0 if files == 0 else 2

    files = sorted(glob.glob(os.path.join(args.target, "*.json")))
    hits: collections.Counter = collections.Counter()
    samples: dict = {}
    total = touched = 0
    for path in files:
        n, _size = process(path, hits, samples, args.dry_run)
        total += n
        touched += 1 if n else 0

    print("扫描 %d 个区域文件，%s 抹掉 %d 处本机路径（涉及 %d 个文件）"
          % (len(files), "将" if args.dry_run else "已", total, touched))
    for key, count in hits.most_common(12):
        print("   %-38s %4d   例：%s" % (key, count, samples.get(key, "")[:56]))
    if args.dry_run:
        print("（--dry-run，未写盘）")
    else:
        left_files, left = count_remaining(args.target)
        print("复核：仍含本机路径的文件 %d 个（%d 处）" % (left_files, left))
        if left_files:
            print("⚠️ 还有残留，检查是否漏了某种字段形状")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
