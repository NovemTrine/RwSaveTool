"""W4 标注：截真实窗口（地图 + 设置浮层），给人眼复核。

    .venv/Scripts/python.exe build/shot_anno.py MS
    .venv/Scripts/python.exe build/shot_anno.py MS --pop     # 顺带把「设置」浮层展开截一张

产物：`build/_shots/geo_anno_<区>.bmp` / `..._pop.bmp`
（BMP 是因为抓窗口走 GDI，不引第三方库；文档里贴图再转 PNG。）
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import shot_theme as shot                            # noqa: E402  （复用窗口抓图）

from core.bridge import Api                          # noqa: E402

CODE = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MS").upper()
WANT_POP = "--pop" in sys.argv
ZOOM = 0
for _i, _a in enumerate(sys.argv):
    if _a == "--zoom" and _i + 1 < len(sys.argv):
        ZOOM = int(sys.argv[_i + 1])
ZOOM = 0
for _i, _a in enumerate(sys.argv):
    if _a == "--zoom" and _i + 1 < len(sys.argv):
        ZOOM = int(sys.argv[_i + 1])
TITLE = "RwSaveToolAnnoShot"


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = shot.webview.create_window(TITLE, html=html, js_api=api,
                                        width=1420, height=940, x=40, y=30)
    api.attach(window)

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception:                            # noqa: BLE001
            return default

    def worker():
        time.sleep(3.0)
        js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
        for _ in range(60):
            time.sleep(0.5)
            if js("window.__rwTest && window.__rwTest.ready && window.__rwTest.ready()"):
                break
        time.sleep(1.0)
        js("window.__rwTest.geo('%s')" % CODE)
        for _ in range(60):
            time.sleep(0.5)
            if js("(window.__rwTest.geoState()||{}).svg"):
                break
        time.sleep(2.0)
        for _ in range(ZOOM):
            js("var b=document.getElementById('geo-zoom').querySelector('[data-gz=in]');"
               "if(b) b.click();")
            time.sleep(0.35)
        if ZOOM:
            time.sleep(2.0)
        for _ in range(ZOOM):
            js("var b=document.getElementById('geo-zoom').querySelector('[data-gz=in]');"
               "if(b) b.click();")
            time.sleep(0.35)
        if ZOOM:
            time.sleep(2.0)
        shot.TITLE = TITLE
        shot.grab(os.path.join(shot.OUT_DIR, "geo_anno_%s.bmp" % CODE))
        if WANT_POP:
            js("document.getElementById('geo-pal').click();")
            time.sleep(1.2)
            js("var p=document.getElementById('geo-pal-pop');"
               "if(p) p.scrollTop = p.scrollHeight;")   # 让「标注」那一段进画面
            time.sleep(0.8)
            shot.grab(os.path.join(shot.OUT_DIR, "geo_anno_%s_pop.bmp" % CODE))
        window.destroy()

    shot.webview.start(worker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
