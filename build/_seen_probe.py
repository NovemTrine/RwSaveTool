"""临时：探索高亮框（S3）的可视验证。

    .venv/Scripts/python.exe build/_seen_probe.py SL
    .venv/Scripts/python.exe build/_seen_probe.py SL 8 SL_C04    # 第二个参数是放大倍数，第三个是居中的房间

产物：build/_shots/page/seen_<code>.png（整图）与 seen_<code>_zoom.png
奇数序号的房间会被打上 `seen` 类，用来对照"有框 / 无框"。
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.regmap import adapter, svg as regmap_svg      # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = os.path.join(ROOT, "build", "_shots", "page")

code = (sys.argv[1] if len(sys.argv) > 1 else "SL").upper()
zoom = float(sys.argv[2]) if len(sys.argv) > 2 else 0
room = sys.argv[3] if len(sys.argv) > 3 else ""

lay = adapter.build(code)
r = regmap_svg.build_svg(lay, width=2400)
head, body = r["svg"].split('<g class="rooms">', 1)
body = body.rsplit("</svg>", 1)[0]
html = """<!doctype html><html><head><meta charset="utf-8"><title>seen %s</title>
<style>
 html,body{margin:0;background:%s;height:100%%}
 body{display:flex;align-items:center;justify-content:center}
 svg{width:100%%;height:100%%;display:block}
</style></head><body>%s<g class="rooms">%s
<script>
var q = new URLSearchParams(location.search);
var rooms = document.querySelectorAll('.rm');
for (var i = 0; i < rooms.length; i++){ if (i %% 2 === 0) rooms[i].classList.add('seen'); }
var z = parseFloat(q.get('zoom') || '0');
var nm = q.get('name') || '';
if (z > 1 && nm){
  var g = document.querySelector('.rm[data-room="' + nm + '"]');
  if (g){
    var b = g.getBBox(), pad = Math.max(b.width, b.height) * 0.12;
    var svg = document.querySelector('svg');
    svg.setAttribute('viewBox', (b.x - pad) + ' ' + (b.y - pad) + ' ' +
                                 (b.width + pad * 2) + ' ' + (b.height + pad * 2));
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  }
}
</script></body></html>""" % (code, regmap_svg.PALETTE["sheet"], head, body)

os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "seen_%s.html" % code.lower())
with open(path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(html)


def shot(url, png, size):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--window-size=%s" % size,
                    "--screenshot=%s" % png, url],
                   check=False, timeout=180)
    print("截图", png)


base = "file:///%s" % path.replace("\\", "/")
shot(base, os.path.join(OUT, "seen_%s.png" % code.lower()), "1680,760")
if zoom > 1 and room:
    shot(base + "?zoom=%s&name=%s" % (zoom, room),
         os.path.join(OUT, "seen_%s_zoom.png" % code.lower()), "1200,760")
