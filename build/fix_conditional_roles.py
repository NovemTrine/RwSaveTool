"""一次性数据修复（可重复跑，幂等）：条件链接里的角色名清洗。

`{!PostBathScene,!ToySending}Watcher` 这种写法，旧导入器先按 `,` 切、再剥花括号，
于是落盘成 `["{POSTBATHSCENE", "!TOYSENDING}WATCHER"]`——花括号里的剧情标记被当成
角色名。`mod_importer` 已改成「先剥 `{...}` 整块再切」（V1.24 №7），这个脚本把
**已经落盘**的旧数据按同一口径洗干净。

用法：
    .venv/Scripts/python.exe build/fix_conditional_roles.py          # 只报告
    .venv/Scripts/python.exe build/fix_conditional_roles.py --write  # 真写
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap.model import _clean_roles  # noqa: E402


def main(argv) -> int:
    write = "--write" in argv
    changed_files = 0
    changed_entries = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "region_data", "*.json"))):
        base = os.path.basename(path)
        if base.startswith("_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("跳过（读不了）：%s %s" % (base, exc))
            continue
        dirty = False
        for layer in data.get("layers") or []:
            for room in layer.get("rooms") or []:
                for key in ("exclusive", "hidden"):
                    old = room.get(key)
                    if not isinstance(old, list) or not old:
                        continue
                    new = _clean_roles(old)
                    if new != old:
                        print("%-10s %-12s %-12s %s: %r → %r"
                              % (base, layer.get("id"), room.get("name"), key, old, new))
                        room[key] = new
                        dirty = True
                        changed_entries += 1
        if dirty:
            changed_files += 1
            if write:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, path)
    print("\n%s：%d 个文件 / %d 条记录"
          % ("已写入" if write else "待修（加 --write 才写）", changed_files, changed_entries))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
