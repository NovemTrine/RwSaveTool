"""房间卡「杆子」画法对比：同一间房、同一份地形，只换杆子的画法。

背景：区域地图的 SVG 走 S2（同列/同行连续格连成一条线，线宽 0.32 格），
而房间卡是 canvas，旧画法是同一套游程但线宽只有 0.11 格（屏幕下限 1px），
放大后明显比地图里细一大截。这个脚本把几种候选画法并排画出来对比。

    python build/check_room_beam.py                     # 自动挑杆子最多的房间
    python build/check_room_beam.py sl_c12 --scale 12   # 指定房间

产物：build/_shots/page/beam_<room>.html / .png
只用标准库 + core.room_geo（canvas 在无头 Chrome 里跑）。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import room_geo                          # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = os.path.join(HERE, "_shots", "page")
WORLD = r"d:/sortware/games/steam/steamapps/common/Rain World/RainWorld_Data/StreamingAssets/world"

# 与房间卡的房间配色一致（灰阶）
COL = {"air": "#535353", "solid": "#2f2f2f", "slope": "#2f2f2f",
       "climb": "#3c3c3c", "beam": "#f2c66d"}

MODES = [
    ("A 旧：0.11 格 / 连续", 0.11, 1.0, "butt"),
    ("B 新：1/3 格 / 连续", 1 / 3, 1.0, "round"),
    ("C 备选：1/3 格 / 逐格 1/3 段", 1 / 3, 1 / 3, "butt"),
    ("D 地图 S2：0.32 格 / 连续", 0.32, 1.0, "round"),
]


def pick_room(folder: str) -> str:
    """杆子最多、又装得进一张图的房间：按 type 1/2 的格子数排，避免挑到只有一两根的。"""
    best, best_n = None, -1
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                geo = room_geo.parse_text(fh.read())
        except Exception:
            continue
        if geo["w"] > 60 or geo["h"] > 44:      # 一屏放四块，太大的房间排不下
            continue
        n = sum(1 for o in geo["objects"] if o[2] in (1, 2))
        if n > best_n:
            best, best_n = path, n
    return best


def page(room: str, geo: dict, scale: int) -> str:
    w, h = geo["w"], geo["h"]
    data = {"w": w, "h": h, "cells": geo["cells"], "objects": geo["objects"]}
    panels = []
    for title, width, seg, cap in MODES:
        panels.append(
            '<div class="p"><h3>%s</h3><canvas data-w="%.4f" data-seg="%.4f" data-cap="%s"></canvas></div>'
            % (title, width, seg, cap))
    pw, ph = w * scale, h * scale
    return """<!doctype html><html><head><meta charset="utf-8"><title>杆子画法 · %s</title>
<style>
  body{margin:0;background:#16181c;color:#cfd6e0;font:13px/1.5 system-ui,-apple-system,sans-serif}
  header{padding:14px 18px 6px;font-size:15px;color:#e6ecf5}
  header b{color:#f2c66d}
  .row{display:flex;gap:16px;padding:10px 18px 18px;flex-wrap:wrap}
  .p h3{margin:0 0 6px;font-size:12px;font-weight:500;color:#93a0b3}
  canvas{display:block;width:%dpx;height:%dpx;border-radius:4px}
</style></head><body>
<header>房间卡杆子画法对比 · <b>%s</b> · %d×%d 格 · 1 格 = %d px</header>
<div class="row">%s</div>
<script>
var G = %s, S = %d;
var COL = %s;
var panels = document.querySelectorAll('canvas');

function runs(map){
  var out = [];
  Object.keys(map).forEach(function(k){
    var list = map[k].sort(function(a,b){ return a-b; });
    var from = list[0], prev = list[0];
    for (var i=1;i<list.length;i++){
      if (list[i] === prev + 1){ prev = list[i]; continue; }
      out.push({k:+k, from:from, len:prev-from+1}); from = prev = list[i];
    }
    out.push({k:+k, from:from, len:prev-from+1});
  });
  return out;
}

function draw(cv){
  var W = G.w, H = G.h, dpr = 2;
  cv.width = W*S*dpr; cv.height = H*S*dpr;
  cv.style.height = (H*S)+'px';
  var ctx = cv.getContext('2d');
  ctx.setTransform(dpr*S,0,0,dpr*S,0,0);
  ctx.fillStyle = COL.solid; ctx.fillRect(0,0,W,H);

  var clim = [], vert = {}, horz = {};
  for (var i=0;i<G.cells.length;i++){
    var ch = G.cells.charAt(i), x = i %% W, y = (i / W) | 0;
    if (ch === '0' || ch >= 'a'){ ctx.fillStyle = COL.air; ctx.fillRect(x,y,1.02,1.02); }
    else if (ch === '2' || ch === '3'){ /* 斜面按实心处理 */ }
  }
  G.objects.forEach(function(o){
    if (o[2] === 6) clim.push(o);
    else if (o[2] === 1) (vert[o[0]] = vert[o[0]] || []).push(o[1]);
    else if (o[2] === 2) (horz[o[1]] = horz[o[1]] || []).push(o[0]);
  });
  if (clim.length){
    ctx.fillStyle = COL.climb;
    clim.forEach(function(o){ ctx.fillRect(o[0],o[1],1.02,1.02); });
  }

  var bw = parseFloat(cv.getAttribute('data-w'));
  var seg = parseFloat(cv.getAttribute('data-seg'));
  ctx.strokeStyle = COL.beam;
  ctx.lineWidth = bw;
  ctx.lineCap = cv.getAttribute('data-cap');
  ctx.beginPath();
  runs(vert).forEach(function(r){
    if (seg >= 1){ ctx.moveTo(r.k+.5, r.from); ctx.lineTo(r.k+.5, r.from+r.len); }
    else for (var y=r.from; y<r.from+r.len; y++){
      var c = y + .5;
      ctx.moveTo(r.k+.5, c-(seg/2)); ctx.lineTo(r.k+.5, c+(seg/2));
    }
  });
  runs(horz).forEach(function(r){
    if (seg >= 1){ ctx.moveTo(r.from, r.k+.5); ctx.lineTo(r.from+r.len, r.k+.5); }
    else for (var x=r.from; x<r.from+r.len; x++){
      var c = x + .5;
      ctx.moveTo(c-(seg/2), r.k+.5); ctx.lineTo(c+(seg/2), r.k+.5);
    }
  });
  ctx.stroke();
}

Array.prototype.forEach.call(panels, draw);
</script></body></html>""" % (room, pw, ph, room.upper(), w, h, scale, "".join(panels),
                              json.dumps(data), scale, json.dumps(COL))


def main(argv=None):
    ap = argparse.ArgumentParser(description="房间卡杆子画法对比页")
    ap.add_argument("room", nargs="?", default="", help="房间名（sl_c12）或 .txt 路径")
    ap.add_argument("--folder", default=os.path.join(WORLD, "sl-rooms"))
    ap.add_argument("--scale", type=int, default=9, help="1 格多少 px")
    args = ap.parse_args(argv)

    path = args.room
    if not path:
        path = pick_room(args.folder)
    elif not path.lower().endswith(".txt"):
        path = os.path.join(args.folder, path.lower() + ".txt")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        geo = room_geo.parse_text(fh.read())
    room = os.path.splitext(os.path.basename(path))[0].lower()

    os.makedirs(OUT, exist_ok=True)
    html = os.path.join(OUT, "beam_%s.html" % room)
    with open(html, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page(room, geo, args.scale))
    print("%s  %d×%d  杆子 %d 格" % (html, geo["w"], geo["h"],
                                    sum(1 for o in geo["objects"] if o[2] in (1, 2))))

    if os.path.isfile(CHROME):
        png = os.path.join(OUT, "beam_%s.png" % room)
        size = "%d,%d" % (min(2600, geo["w"] * args.scale * 4 + 120),
                          min(1200, geo["h"] * args.scale + 110))
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=%s" % size,
                        "--screenshot=%s" % png, "file:///%s" % html.replace("\\", "/")],
                       check=False, timeout=180)
        print("        截图 %s" % png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
