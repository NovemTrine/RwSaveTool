"""临时：把区域地图放大到 N 倍，截某个房间的局部（查 4000% 下的观感）。

    .venv/Scripts/python.exe build/_zoom_probe.py RF            # 自动挑杆子最多的房间
    .venv/Scripts/python.exe build/_zoom_probe.py RF RF_A01 40
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
OUT = os.path.join(ROOT, "build", "_shots", "page")

code = (sys.argv[1] if len(sys.argv) > 1 else "RF").upper()
want = sys.argv[2] if len(sys.argv) > 2 else ""
zoom = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

lay = adapter.build(code)
gray = len(sys.argv) > 4 and sys.argv[4] == "gray"
colors = {"air": "#535353", "solid": "#2f2f2f", "s": "#2f2f2f", "c": "#3c3c3c"} if gray else None
r = regmap_svg.build_svg(lay, width=2400, colors=colors)
nodes = lay["nodes"]
s = r["scale"]

pick = None
best = -1
for n in nodes:
    cnt = len((n.get("over") or {}).get("b") or []) + len((n.get("over") or {}).get("p") or [])
    if want and n["name"].upper() == want.upper():
        pick, best = n, cnt
        break
    if cnt > best:
        pick, best = n, cnt
print("房间 %s  杆子/管道游程 %d  格 %.2f px" % (pick["name"], best, s))

# 只留目标房间的 <g class="rm" data-room=…>：切到下一个房间 / 门点组之前
pat = r'<g class="rm[^"]*" data-room="%s".*?(?=<g class="rm[ "]<|<g class="doors">|</svg>)' % (
    re.escape(pick["name"]))
body = re.search(pat, r["svg"], re.S)
frag = body.group(0) if body else ""
if not frag:
    frag = re.search(r'<g class="rm[^"]*" data-room="[^"]*".*?(?=<g class="rm[ "]<)', r["svg"], re.S).group(0)
    print("!! 没精确命中，退回第一间")
# 连线在 rooms 之后单独成组：一并带上，否则放大后只看得到房间、看不到线
links = re.search(r'<g class="links">.*?</g>', r["svg"], re.S)
if links:
    frag = frag + links.group(0)          # 房间先、线后，与原图同一层序
print("片段 %.0f KB" % (len(frag) / 1024.0))

head = ""
style = re.search(r"<style>.*?</style>", r["svg"], re.S)
if style:
    head = style.group(0)

PAD = 14
x0 = min(n["x"] for n in nodes)
y0 = min(n["y"] for n in nodes)
px = (pick["x"] - x0) * s + PAD
py = (pick["y"] - y0) * s + PAD
pw = pick["w"] * s
ph = pick["h"] * s
# 用 viewBox 直接框住房间中心的一小块：矢量放大没有纹理上限，比 transform 稳
vw = 900.0 / zoom                                 # 屏幕上 1 单位 = zoom px
vh = vw * 500.0 / 860.0
cx = px + pw * 0.5
cy = py + ph * 0.5
vb = "%.2f %.2f %.2f %.2f" % (cx - vw / 2, cy - vh / 2, vw, vh)

WIN_W, WIN_H = 860, 500
html = """<!doctype html><html><head><meta charset="utf-8"><title>zoom %s</title>
<style>html,body{margin:0;background:%s}svg{display:block}</style>
</head><body><svg xmlns="http://www.w3.org/2000/svg" viewBox="%s" width="%d" height="%d"
class="regmap-svg">%s<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f"
style="fill:var(--rg-sheet,%s)"/>%s</svg></body></html>""" % (
    zoom, regmap_svg.PALETTE["sheet"], vb, WIN_W, WIN_H, head,
    cx - vw, cy - vh, vw, vh, regmap_svg.PALETTE["sheet"], frag)

os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "zoom_%s.html" % code.lower())
with open(path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(html)
png = os.path.join(OUT, "zoom_%s.png" % code.lower())
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--window-size=%d,%d" % (WIN_W, WIN_H),
                "--screenshot=%s" % png, "file:///%s" % path.replace("\\", "/")],
               check=False, timeout=180)
print("截图", png)
