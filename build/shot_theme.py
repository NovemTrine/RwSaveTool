"""截取真实窗口：暗色区域页 + 亮色击杀页（用于人工核对配色）。

用法： .venv/Scripts/python.exe build/shot_theme.py
产物： docs/theme_dark.bmp / docs/theme_light.bmp
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 回归产物统一放 build/_shots，不污染 docs（docs 只放被文档引用的图）
SHOTS = os.path.join(ROOT, "build", "_shots")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402

TITLE = "RwSaveToolShot"
OUT_DIR = SHOTS

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()


def find_hwnd(title: str):
    found = []

    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip() == title:
            found.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found[0] if found else None


def grab(path: str) -> bool:
    hwnd = find_hwnd(TITLE)
    if not hwnd:
        print("未找到窗口")
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 0x2)  # PW_RENDERFULLCONTENT
    if not ok:
        ok = user32.PrintWindow(hwnd, mem, 0)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    size = w * h * 4
    buf = ctypes.create_string_buffer(size)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    row = w * 4
    with open(path, "wb") as fh:
        fh.write(b"BM")
        fh.write(struct.pack("<IHHI", 14 + 40 + size, 0, 0, 14 + 40))
        fh.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, size, 0, 0, 0, 0))
        fh.write(buf.raw)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print("saved", path, w, h)
    return bool(ok)


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = webview.create_window(TITLE, html=html, js_api=api, width=1360, height=900,
                                   x=60, y=40)
    api.attach(window)
    os.makedirs(OUT_DIR, exist_ok=True)

    def worker():
        time.sleep(3.0)
        try:
            window.evaluate_js("try{localStorage.removeItem('rwTheme')}catch(e){}")
            window.evaluate_js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(60):
                time.sleep(0.5)
                if window.evaluate_js("window.__rwTest && window.__rwTest.ready && window.__rwTest.ready()"):
                    break
            time.sleep(1.0)
            window.evaluate_js(
                "var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
                "function(e){return /White/.test(e.textContent);})[0]; if(s) s.click();"
            )
            time.sleep(0.8)
            window.evaluate_js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.5)
            grab(os.path.join(OUT_DIR, "theme_dark.bmp"))

            # 亮色 + 青瓷
            window.evaluate_js("document.getElementById('theme-fab').click();")
            time.sleep(0.6)
            window.evaluate_js("var b=document.querySelector('[data-theme-opt=\"light\"]'); if(b) b.click();")
            time.sleep(0.5)
            window.evaluate_js("var b=document.querySelector('[data-accent-opt=\"teal\"]'); if(b) b.click();")
            time.sleep(0.5)
            window.evaluate_js("document.getElementById('modal-close').click();")
            time.sleep(0.6)
            window.evaluate_js("var tb=document.querySelector('[data-tab=\"kills\"]'); if(tb) tb.click();")
            time.sleep(1.6)
            grab(os.path.join(OUT_DIR, "theme_light.bmp"))

            # 还原成暗色 + 琥珀，避免影响日常使用
            window.evaluate_js("document.getElementById('theme-fab').click();")
            time.sleep(0.5)
            window.evaluate_js("var b=document.querySelector('[data-theme-opt=\"dark\"]'); if(b) b.click();")
            time.sleep(0.4)
            window.evaluate_js("var b=document.querySelector('[data-accent-opt=\"amber\"]'); if(b) b.click();")
            time.sleep(0.4)
            window.evaluate_js("document.getElementById('modal-close').click();")
            time.sleep(0.3)
        finally:
            window.destroy()

    webview.start(worker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
