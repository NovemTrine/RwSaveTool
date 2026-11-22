"""W5b 手工探针：点「导出 SVG」，确认系统「另存为」真的弹出来。

为什么单独做一个脚本：真实对话框会**阻塞**那段 JS 调用，回归脚本没法定时点按钮，
只能人工或像这里一样"发现窗口 → 操作它"。

用法：
    .venv/Scripts/python.exe build/_export_probe.py            # 只验弹窗，然后 WM_CLOSE 取消
    .venv/Scripts/python.exe build/_export_probe.py GW C:\\Temp\\rw_probe.svg
                                                               # 真填路径回车，验落盘 + 提示卡

看到窗口标题里有「另存为」/「Save As」就算弹出来了；填路径那次还会报告
文件大小、提示卡里有没有把路径写全（这是主人 2026-11-22 要的那件事）。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core.bridge import Api  # noqa: E402

TITLE = "RwSaveTool 导出探针"
CODE = (sys.argv[1] if len(sys.argv) > 1 else "GW").upper()
SAVE_TO = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
MODE = (sys.argv[3] if len(sys.argv) > 3 else "map").strip().lower()   # map | graph
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def visible_titles() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        found.append((hwnd, buf.value.strip()))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found


def find_save_dialog(before: set[int]):
    for hwnd, title in visible_titles():
        if hwnd in before:
            continue
        low = title.lower()
        if "另存为" in title or "save as" in low or "save" in low:
            return hwnd, title
    return None, ""


def grab_window(title: str, path: str) -> bool:
    """把窗口原样截图存 BMP（PrintWindow），给"提示卡长什么样"留证据。"""
    hwnd = next((h for h, t in visible_titles() if t.strip() == title), None)
    if not hwnd:
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    gdi32 = ctypes.windll.gdi32
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    if not user32.PrintWindow(hwnd, mem, 0x2):
        user32.PrintWindow(hwnd, mem, 0)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    size = w * h * 4
    buf = ctypes.create_string_buffer(size)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    import struct
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"BM")
        fh.write(struct.pack("<IHHI", 14 + 40 + size, 0, 0, 14 + 40))
        fh.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, size, 0, 0, 0, 0))
        fh.write(buf.raw)
    return True


def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = webview.create_window(TITLE, html=html, js_api=api, width=1400, height=980,
                                   x=80, y=40)
    api.attach(window)
    result: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            print("JSERR", str(exc)[:100])
            return default

    def worker():
        time.sleep(2.6)
        js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
        for _ in range(60):
            time.sleep(0.5)
            if js("window.__rwTest.ready()"):
                break
        time.sleep(1.0)
        js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
           "function(e){return /White/.test(e.textContent);})[0]; if(s) s.click();")
        time.sleep(0.8)
        js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
        time.sleep(1.2)
        js("var b=document.querySelector('[data-map=\"%s\"]'); if(b) b.click();" % CODE)
        for _ in range(20):
            time.sleep(0.6)
            if js("document.querySelectorAll('#geo-stage svg.geo-svg').length"):
                break
        time.sleep(1.0)
        if not js("!!document.getElementById('geo-exp-svg')"):
            result["error"] = "地图没打开，导出按钮不存在"
            window.destroy()
            return

        before = {h for h, _t in visible_titles()}
        if SAVE_TO:
            # 用 stub 顶掉系统对话框，直接给出路径：这样能一次跑完"内容交给后端 →
            # 后端写盘 → 前端拿到真实路径 → 提示卡显示"。对话框本身在另一种模式下验。
            # `normpath` 是为了还原成 Windows 原生写法（`D:\a\b`），跟真对话框返回的一致。
            window.create_file_dialog = lambda *a, **k: [os.path.normpath(SAVE_TO)]

        if MODE == "graph":
            js("var b=document.getElementById('map-graph'); if(b) b.click();")
            for _ in range(24):
                time.sleep(0.5)
                if js("!!document.getElementById('gx-canvas')"):
                    break
            time.sleep(4.5)              # 等力导向站稳 + 出场动画跑完
            if not js("!!document.getElementById('gx-export')"):
                result["error"] = "拓扑图没打开，导出按钮不存在"
                window.destroy()
                return
            js("document.getElementById('gx-export').click();")
            if SAVE_TO:
                result["dialog"] = "stub"
                result["found"] = True
                for _ in range(80):        # 3× 拓扑图要编码 + 写盘，最多等 40 s
                    time.sleep(0.5)
                    if os.path.isfile(SAVE_TO) and os.path.getsize(SAVE_TO) > 1024:
                        time.sleep(0.8)    # 等提示卡渲染
                        break
            else:
                for _ in range(24):
                    time.sleep(0.25)
                    dlg, title = find_save_dialog(before)
                    if dlg:
                        break
                result["dialog"] = title
                result["found"] = bool(dlg)
                if dlg:
                    time.sleep(0.8)
                    user32.PostMessageW(dlg, 0x0010, 0, 0)
                    time.sleep(1.2)
        else:
            js("document.getElementById('geo-exp-svg').click();")
            dlg, title = None, ""
            if not SAVE_TO:
                for _ in range(24):          # 最多等 6 s
                    time.sleep(0.25)
                    dlg, title = find_save_dialog(before)
                    if dlg:
                        break
                result["dialog"] = title
                result["found"] = bool(dlg)
                if dlg:
                    time.sleep(0.8)          # 让它画完再关
                    user32.PostMessageW(dlg, 0x0010, 0, 0)     # WM_CLOSE = 取消
                    time.sleep(1.2)
            else:
                result["dialog"] = "stub"
                result["found"] = True
                time.sleep(2.5)              # 等前端把内容交过去、后端写盘、提示卡渲染
        if SAVE_TO:
            result["file"] = os.path.isfile(SAVE_TO)
            result["bytes"] = os.path.getsize(SAVE_TO) if result.get("file") else 0
            result["tip"] = js(
                "JSON.stringify((function(){var el=document.getElementById('export-tip');"
                "return {shown:!!(el&&el.classList.contains('on')),"
                "text:el?el.textContent:'',"
                "open:!!(el&&el.querySelector('[data-et=open]'))};})())")
            result["toast"] = js("(document.getElementById('toast')||{}).textContent||''")
            result["toastOn"] = js(
                "!!(document.getElementById('toast')||{className:''}).className.match(/\\bon\\b/)")
        else:
            # 取消之后：不应该弹错误 toast，也不应该有提示卡
            result["toast"] = js("(document.getElementById('toast')||{}).textContent||''")
            result["toastOn"] = js(
                "!!(document.getElementById('toast')||{className:''}).className.match(/\\bon\\b/)")
            result["tipHidden"] = js("window.__rwTest.exportTipHidden()")
        result["svgBtnDisabled"] = js(
            "(document.getElementById('geo-exp-svg')||{}).disabled")
        result["gxBtnDisabled"] = js(
            "(document.getElementById('gx-export')||{}).disabled")
        if SAVE_TO:
            shot = os.path.join(ROOT, "build", "_shots", "export", "export_tip.bmp")
            result["shot"] = grab_window(TITLE, shot)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        window.destroy()

    webview.start(worker)
    ok = bool(result.get("found")) and not result.get("error")
    if SAVE_TO:
        ok = ok and bool(result.get("file"))
        print("PROBE", "OK" if ok else "FAIL", "· 对话框：", result.get("dialog") or "未发现",
              "· 落盘：", result.get("bytes"), "字节")
    else:
        print("PROBE", "OK" if ok else "FAIL", "· 对话框标题：", result.get("dialog") or "未发现")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
