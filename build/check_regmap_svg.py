"""把若干区域导出成 SVG + 一张画廊页，命令行就能看（不需要开桌面壳）。

    python build/check_regmap_svg.py UW HI CC MS FT
    python build/check_regmap_svg.py UW --width 4000 --labels
    python build/check_regmap_svg.py SL MS --engine zq     # W2：看 zq 引擎的排布

产物：`build/_shots/svg/<CODE>.svg`、`build/_shots/svg/index.html`（点区名切换）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.regmap import adapter, svg as regmap_svg      # noqa: E402

OUT = os.path.join(HERE, "_shots", "svg")

GALLERY = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>regmap SVG 画廊</title><style>
html,body{margin:0;height:100%;background:#05070a;color:#c9d6dd;
  font:13px/1.5 system-ui,"Segoe UI",sans-serif}
#bar{display:flex;gap:6px;align-items:center;padding:8px 12px;flex-wrap:wrap;
  border-bottom:1px solid #1b232b}
button{background:#141b22;color:#c9d6dd;border:1px solid #24313b;border-radius:6px;
  padding:5px 10px;cursor:pointer;font:inherit}
button.on{background:#1d3640;border-color:#3f6f7a;color:#cfeeff}
#meta{margin-left:auto;opacity:.7;font-variant-numeric:tabular-nums}
#stage{height:calc(100vh - 47px);overflow:auto;padding:10px}
#stage svg{display:block;width:100%;height:auto;background:#05070a}
</style></head><body>
<div id="bar"><span>区域</span><span id="btns"></span><span id="meta"></span></div>
<div id="stage"></div>
<script>
var META = __META__;
function show(code){
  fetch(code + '.svg').then(function(r){ return r.text(); }).then(function(t){
    document.getElementById('stage').innerHTML = t;
    var m = META[code] || {};
    document.getElementById('meta').textContent =
      m.w + '\\u00d7' + m.h + ' \\u00b7 ' + m.rooms + ' \\u95f4 \\u00b7 ' +
      m.links + ' \\u8fb9 \\u00b7 ' + m.kb + ' KB \\u00b7 \\u6784\\u5efa ' +
      m.ms + ' ms \\u00b7 \\u7f1d ' + m.gap;
    [].forEach.call(document.querySelectorAll('#btns button'), function(b){
      b.classList.toggle('on', b.dataset.c === code); });
  });
}
var btns = document.getElementById('btns');
Object.keys(META).forEach(function(code){
  var b = document.createElement('button');
  b.textContent = code; b.dataset.c = code;
  b.onclick = function(){ show(code); };
  btns.appendChild(b);
});
show(Object.keys(META)[0]);
</script></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="区域地图导出 SVG")
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--width", type=int, default=2400, help="SVG 目标宽度（默认 2400）")
    ap.add_argument("--labels", action="store_true", help="叠房间编号（调试）")
    ap.add_argument("--frames", action="store_true", help="画房间外框（调试）")
    ap.add_argument("--gallery", action="store_true", help="额外出一张 index.html")
    ap.add_argument("--engine", default="", help="排布引擎 legacy|zq（默认跟随 config）")
    args = ap.parse_args(argv)

    os.makedirs(OUT, exist_ok=True)
    made = []
    for code in args.codes:
        t0 = time.perf_counter()
        layout = adapter.build(code, opts={"engine": args.engine} if args.engine else None)
        r = regmap_svg.build_svg(layout, width=args.width, labels=args.labels,
                                 frames=args.frames)
        dt = (time.perf_counter() - t0) * 1000
        path = os.path.join(OUT, "%s.svg" % code.upper())
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(r["svg"])
        st = layout["stats"]
        made.append((code.upper(), r, dt, st))
        print("%-6s 间 %3d 边 %3d  %dx%d  %.0f KB  %.0f ms  缝 %.1f"
              % (code.upper(), r["rooms"], r["links"], r["w"], r["h"],
                 r["bytes"] / 1024.0, dt, st.get("gap", 0)))

    if args.gallery and made:
        meta = {}
        for (code, r, dt, st) in made:
            meta[code] = {"w": r["w"], "h": r["h"], "rooms": r["rooms"],
                          "links": r["links"], "kb": round(r["bytes"] / 1024.0, 1),
                          "ms": round(dt), "gap": st.get("gap", 0)}
        html = GALLERY.replace("__META__", json.dumps(meta, ensure_ascii=False))
        path = os.path.join(OUT, "index.html")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        print("画廊：%s" % path)
    print("SVG 在 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
