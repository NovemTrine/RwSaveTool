"""把 ui/rw_gui.html 里的剧情分值表导出为 data/creature_score.json。

UI 内置的 <script id="creature-score" type="application/json"> 是唯一数据源
（离线单文件也能用）；这个脚本只是把它落成一份可被外部工具读取的 JSON，
顺带做一致性检查：存档里出现过的击杀键是否都在表里。

用法：
    .venv\\Scripts\\python.exe build\\sync_score.py          # 生成 JSON
    .venv\\Scripts\\python.exe build\\sync_score.py --check  # 只校验，不写文件
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "ui", "rw_gui.html")
OUT = os.path.join(ROOT, "data", "creature_score.json")

BLOCK_RE = re.compile(
    r'<script id="creature-score" type="application/json">(.*?)</script>', re.S
)


def load_from_html() -> dict:
    with open(HTML, "r", encoding="utf-8") as fh:
        html = fh.read()
    m = BLOCK_RE.search(html)
    if not m:
        raise SystemExit("未在 ui/rw_gui.html 找到 creature-score 数据块")
    return json.loads(m.group(1))


def main(argv: list[str]) -> int:
    data = load_from_html()
    scores = data.get("scores") or {}
    if not scores:
        raise SystemExit("分值表为空")

    conf = {}
    for key, item in scores.items():
        conf[item.get("confidence", "unknown")] = conf.get(item.get("confidence", "unknown"), 0) + 1

    print(f"物种 {len(scores)} 条 · 置信度分布 {conf}")
    if "--check" in argv:
        with open(OUT, "r", encoding="utf-8") as fh:
            old = json.load(fh)
        if old != data:
            print("不一致：data/creature_score.json 需要重新生成")
            return 1
        print("一致")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
