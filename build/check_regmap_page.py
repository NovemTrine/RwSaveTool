"""把「几何图」那一页拼成静态 HTML 并截图：不动桌面壳也能看真实观感。

做法：借 `ui/rw_gui.html` 的样式表 + `regmap_svg` 出的 SVG，按弹窗结构拼一页。
所以它跟工具里看到的是**同一份 CSS、同一份 SVG、同一套配色变量**。

默认用 `density=4`（工具里放大 2 倍后自动换的那一层），所以预览的清晰度 = 工具放大后的清晰度。

    python build/check_regmap_page.py HI UW CC --shot
    python build/check_regmap_page.py HI --density 2            # 看默认层（粗一档）
    python build/check_regmap_page.py HI --colors "air=#7fe3ff" # 试色

产物：`build/_shots/page/<CODE>.html`；加 `--shot` 用无头 Chrome 截一张 PNG。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import bridge                        # noqa: E402
from core.regmap.svg import PALETTE            # noqa: E402

# 与 `ui/rw_gui.html` 的 `ROOM_PALETTE_DEFAULT.dark` 同步：工具里的默认配色取房间卡那套
ROOM_DARK = {"air": "#535353", "solid": "#2f2f2f", "slope": "#2f2f2f", "climb": "#3c3c3c",
             "pipe": "#777777", "beam": "#f2c66d", "exit": "#2fed2f", "den": "#ed2f2f",
             "creature": "#2f2fed"}


def default_colors():
    return {"sheet": "#0b0d11", "air": ROOM_DARK["air"], "solid": ROOM_DARK["solid"],
            "s": ROOM_DARK["slope"], "c": ROOM_DARK["climb"], "p": ROOM_DARK["pipe"],
            "b": ROOM_DARK["beam"], "x": ROOM_DARK["exit"], "d": ROOM_DARK["den"],
            "k": ROOM_DARK["creature"], "link": PALETTE["link"], "door": PALETTE["door"]}

OUT = os.path.join(HERE, "_shots", "page")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 与前端 `RG_ITEMS` 同一份清单；颜色默认值取 svg.PALETTE 的兜底
ITEMS = [("sheet", "区域背景"), ("air", "可通行"), ("solid", "岩壁"), ("c", "背景结构"),
         ("b", "杆子"), ("p", "管道"), ("x", "通道入口"), ("d", "巢穴"),
         ("k", "生物通道"), ("s", "斜面"), ("link", "连线"), ("door", "门点")]

SCRIPT = r"""
var ITEMS = __ITEMS__;
var PAL = __PAL__;
var MAP = __MAP__;
var DEF = JSON.parse(JSON.stringify(PAL));
var stage = document.getElementById('geo-stage');
var wrap = document.getElementById('geo-wrap');
var svg = stage.querySelector('svg');
if (svg) svg.classList.add('geo-svg');
function paint(){ ITEMS.forEach(function(it){
  wrap.style.setProperty('--rg-' + it[0], PAL[it[0]]); }); }
paint();

var pop = document.getElementById('geo-pal-pop');
if (location.hash === '#pal') pop.hidden = false;   /* 截图用：直接展开配色面板 */
var grid = document.getElementById('geo-pal-grid');
grid.innerHTML = ITEMS.map(function(it){
  return '<label class="rp-item"><input type="color" data-k="' + it[0] + '" value="' + PAL[it[0]] +
    '"><span>' + it[1] + '</span></label>'; }).join('');
[].forEach.call(grid.querySelectorAll('[data-k]'), function(inp){
  inp.addEventListener('input', function(){ PAL[inp.dataset.k] = inp.value; paint(); });
});
document.getElementById('geo-pal').addEventListener('click', function(e){
  e.stopPropagation(); pop.hidden = !pop.hidden; });
pop.addEventListener('click', function(e){ e.stopPropagation(); });
document.body.addEventListener('click', function(){ pop.hidden = true; });
[].forEach.call(pop.querySelectorAll('[data-rgpreset]'), function(btn){
  btn.addEventListener('click', function(e){ e.stopPropagation();
    var src = btn.dataset.rgpreset === 'map' ? MAP : DEF;
    ITEMS.forEach(function(it){ PAL[it[0]] = src[it[0]] || DEF[it[0]];
      var i = grid.querySelector('[data-k="' + it[0] + '"]'); if (i) i.value = PAL[it[0]]; });
    paint(); });
});

var W = +svg.dataset.w, H = +svg.dataset.h, baseW = 0;
var vb = {x:0,y:0,w:1,h:1};
function size(){ var b = stage.getBoundingClientRect();
  return {w:Math.max(1,b.width), h:Math.max(1,b.height)}; }
function apply(){ svg.setAttribute('viewBox', vb.x.toFixed(1)+' '+vb.y.toFixed(1)+' '+
  vb.w.toFixed(1)+' '+vb.h.toFixed(1));
  document.getElementById('geo-pct').textContent = Math.round(baseW/vb.w*100)+'%'; }
function fit(){ var s = size(); var k = Math.min(s.w/W, s.h/H);
  var w = s.w/k, h = s.h/k; baseW = w;
  vb = {x:(W-w)/2, y:(H-h)/2, w:w, h:h}; apply(); }
fit();
stage.addEventListener('wheel', function(e){ if(!e.deltaY) return; e.preventDefault();
  var s = size(), b = stage.getBoundingClientRect();
  var px = e.clientX-b.left, py = e.clientY-b.top;
  var ux = vb.x + px/s.w*vb.w, uy = vb.y + py/s.h*vb.h;
  var w2 = Math.max(W/40, Math.min(W*1.8, vb.w/Math.pow(1.0022,-e.deltaY)));
  var h2 = w2*(s.h/s.w);
  vb = {x: ux - px/s.w*w2, y: uy - py/s.h*h2, w: w2, h: h2}; apply();
}, {passive:false});
var drag=null;
stage.addEventListener('mousedown', function(e){ if(e.button!==0) return;
  drag={sx:e.clientX, sy:e.clientY};
  window.addEventListener('mousemove', mv); window.addEventListener('mouseup', up); });
function mv(e){ if(!drag) return; var s = size();
  vb.x -= (e.clientX-drag.sx)/s.w*vb.w; vb.y -= (e.clientY-drag.sy)/s.h*vb.h;
  drag.sx=e.clientX; drag.sy=e.clientY; apply(); }
function up(){ drag=null; window.removeEventListener('mousemove',mv);
  window.removeEventListener('mouseup',up); }
stage.addEventListener('dblclick', fit);
[].forEach.call(document.querySelectorAll('#geo-zoom [data-gz]'), function(b){
  b.addEventListener('click', function(){
    var act = b.dataset.gz;
    if (act === 'fit'){ fit(); return; }
    var s = size();
    var w2 = vb.w / (act === 'in' ? 1.45 : 1/1.45);
    var cx = vb.x + vb.w/2, cy = vb.y + vb.h/2, h2 = w2*(s.h/s.w);
    vb = {x: cx - w2/2, y: cy - h2/2, w: w2, h: h2}; apply();
  });
});
"""


def page(code: str, svg: str, rooms: int, links: int, sub: str, density: int,
         colors: dict | None = None) -> str:
    html = open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8").read()
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    m = re.search(r"<body([^>]*)>", html)
    battr = m.group(1) if m else ""
    base = default_colors()
    pal = {k: (colors or {}).get(k, base.get(k, PALETTE[k])) for k, _ in ITEMS}
    legend = "".join(
        '<span><i style="background:var(--rg-%s)"></i>%s</span>' % (k, n)
        for k, n in ITEMS[1:10])
    head = ('<!DOCTYPE html><html lang="zh-CN" data-theme="dark"><head><meta charset="utf-8">'
            '<title>几何图预览 · ' + code + '</title><style>' + css +
            '\nhtml,body{height:100%;overflow:hidden}\n#modal{display:block}\n</style></head>')
    body = [
        '<body' + battr + '>',
        '<div id="modal" class="modal"><div class="modal-card full" id="modal-card">',
        '<div class="modal-head"><div><h3 id="modal-title">区域地图 · ' + code + ' · 几何</h3>',
        '<div class="sub" id="modal-sub">' + sub + '</div></div><span class="grow"></span>',
        '<button class="modal-close" type="button">×</button></div>',
        '<div class="modal-body" id="modal-body">',
        '<div class="map-wrap" id="geo-wrap"><div class="map-main">',
        '<div class="map-tools"><span class="mlabel">几何排布</span>',
        '<button class="btn ghost" type="button">← 方块图</button>',
        '<button class="btn ghost" id="geo-pal" type="button">设置</button>',
        '<span class="map-hint" id="geo-meta">%d 间 · %d 边 · 密度 %d</span></div>'
        % (rooms, links, density),
        '<div class="geo-stage" id="geo-stage">',
        '<div class="map-zoom" id="geo-zoom">',
        '<button type="button" data-gz="out">−</button><span id="geo-pct">100%</span>',
        '<button type="button" data-gz="in">+</button>',
        '<button type="button" data-gz="fit">适应</button></div>',
        '<div class="geo-pal-pop" id="geo-pal-pop" hidden>',
        '<div class="geo-pal-head"><span>本区设置</span>',
        '<button class="btn ghost" data-rgpreset="room" type="button">房间卡</button>',
        '<button class="btn ghost" data-rgpreset="map" type="button">地图</button></div>',
        '<div class="rp-grid" id="geo-pal-grid"></div></div>',
        svg,
        '</div></div>',
        '<aside class="map-side"><div class="geo-legend">' + legend + '</div>',
        '<div class="geo-note"><b>这张图是算出来的</b>：房间按真实尺寸画地形，',
        '房间之间用三次贝塞尔连线，线压在房间下面，只在缝里露出来。<br>',
        '<b>缩放改的是 viewBox</b>，放到十几倍边缘还是锐的。<br>',
        '<b>配色按钮</b>按区域保存，默认跟随房间卡配色。</div>',
        '</aside></div></div></div></div>',
        '<script>' + SCRIPT.replace("__ITEMS__", json.dumps(ITEMS, ensure_ascii=False))
        .replace("__PAL__", json.dumps(pal))
        .replace("__MAP__", json.dumps({k: PALETTE[k] for k, _ in ITEMS})) + '</script>',
        '</body></html>',
    ]
    return head + "\n".join(body)


def main(argv=None):
    ap = argparse.ArgumentParser(description="几何图静态预览（同一份 CSS + 同一份 SVG）")
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--shot", action="store_true", help="用无头 Chrome 截图")
    ap.add_argument("--size", default="1680,950", help="截图尺寸 宽,高")
    ap.add_argument("--density", type=int, default=4, help="缩略密度（默认 4 = 高清层）")
    ap.add_argument("--colors", default="", help='临时试色，如 "air=#7fe3ff,sheet=#04070b"')
    args = ap.parse_args(argv)

    colors = {}
    for part in (args.colors or "").split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            colors[k.strip()] = v.strip()

    os.makedirs(OUT, exist_ok=True)
    api = bridge.Api()
    for code in args.codes:
        r = api.regmap_svg(code, density=args.density)
        if not r.get("ok"):
            print("%-6s 失败 %s" % (code, r.get("error")))
            continue
        path = os.path.join(OUT, "%s.html" % code.upper())
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page(code.upper(), r["svg"], r["rooms"], r["links"],
                          "World / 几何排布 · 预览页（同一份 CSS + SVG）",
                          args.density, colors))
        print("%-6s %s  %.0f KB（密度 %d）" % (code.upper(), path,
                                              os.path.getsize(path) / 1024.0, args.density))
        if args.shot and os.path.isfile(CHROME):
            png = os.path.join(OUT, "%s.png" % code.upper())
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=1",
                            "--window-size=%s" % args.size,
                            "--screenshot=%s" % png,
                            "file:///%s" % path.replace("\\", "/")],
                           check=False, timeout=180)
            print("        截图 %s" % png)
    print("预览在 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
