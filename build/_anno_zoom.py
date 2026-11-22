"""W4 标注：局部放大截图（№2 之后只剩子区域名，看它落在哪、糊不糊）。

    .venv/Scripts/python.exe build/_anno_zoom.py CC                  # 自动挑标注最多的房间
    .venv/Scripts/python.exe build/_anno_zoom.py CC CC_A01 6        # 指定房间与倍率

输出 `build/_shots/anno_<区>_<房>.png`，看不了就再调倍率。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, svg as regmap_svg      # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = os.path.join(ROOT, "build", "_shots")

code = (sys.argv[1] if len(sys.argv) > 1 else "CC").upper()
want = sys.argv[2] if len(sys.argv) > 2 else ""
zoom = float(sys.argv[3] if len(sys.argv) > 3 else 6.0)
labels = "--labels" in sys.argv

# 应用里默认是「房间卡那套灰阶」配色（不是 PALETTE 的青色），看观感要对齐它
# V1.15 起默认色就是 `PALETTE` 那 16 项 + 区域提取色，不用再手动塞一份；
# 想看用户自定义的样子时用 `--colors` 传，日常直接吃默认。
APP_COLORS = None
lay = adapter.build(code)
r = regmap_svg.build_svg(lay, width=2400, colors=APP_COLORS, anno=True)
s = r["scale"]

pick = None
best = -1
for n in lay["nodes"]:
    score = 0
    a = n.get("anno") or {}
    score += 1 if a.get("sub") else 0          # №2 之后 anno 只剩 sub/sc
    if want and n["name"].upper() == want.upper():
        pick = n
        break
    if score > best:
        pick, best = n, score
if pick is None:
    pick = lay["nodes"][0]

pad = 14
px = pad + (pick["x"] - min(m["x"] for m in lay["nodes"])) * s
py = pad + (pick["y"] - min(m["y"] for m in lay["nodes"])) * s
pw, ph = pick["w"] * s, pick["h"] * s
cx, cy = px + pw * 0.5, py + ph * 0.5
vw, vh = pw / zoom, ph / zoom     # zoom 越大视野越小 = 放大

body = r["svg"]
body = re.sub(r'viewBox="[^"]*"', 'viewBox="%.1f %.1f %.1f %.1f"'
              % (cx - vw * 0.5, cy - vh * 0.5, vw, vh), body, count=1)
body = re.sub(r'width="100%" height="100%"', 'width="1200" height="900"', body, count=1)

html = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>html,body{margin:0;height:100%;background:#05070a;overflow:hidden}'
        'svg{display:block}</style></head><body>' + body + '</body></html>')
name = "anno_%s_%s" % (code, pick["name"].replace("/", "_"))
p = os.path.join(OUT, name + ".html")
with open(p, "w", encoding="utf-8") as fh:
    fh.write(html)
png = os.path.join(OUT, name + ".png")
print("房间 %s  倍率 %.1f  标注 %s" % (pick["name"], zoom, pick.get("anno")))
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--window-size=1200,900", "--screenshot=" + png,
                "file:///" + p.replace("\\", "/")], check=False,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(png)
