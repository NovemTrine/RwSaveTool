"""发版冒烟：把发布包跑起来一次，确认 exe 能启动、窗口能出来、界面不是空白。

为什么不能只跑 `verify_release.py`：那个脚本用的是**源码 + 包内资源**，
证明不了 `RwSaveTool.exe` 里的 PyInstaller 产物（尤其 `_internal` 里的 webview 桥接、
`ui/rw_gui.html`、新增的后端导出代码）真的能跑。

做法：把发布目录复制到 `build/_release_smoke/`（不在正式包里留 config.json），
启动 exe → 等窗口 → PrintWindow 截图 → 关进程。

用法： .venv/Scripts/python.exe build/_release_smoke.py [发布目录]
产物： build/_shots/release_smoke.bmp
"""
from __future__ import annotations

import ctypes
import os
import shutil
import struct
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))


def bmp_color_count(path: str, step: int = 7) -> int:
    """数截图中间区域的颜色种类（BMP 32 位，行序自上而下或自下而上）。"""
    data = open(path, "rb").read()
    off = struct.unpack_from("<I", data, 10)[0]
    w, h = struct.unpack_from("<ii", data, 18)
    bpp = struct.unpack_from("<H", data, 28)[0]
    top_down = h < 0
    h = abs(h)
    nch = bpp // 8
    stride = ((w * nch + 3) // 4) * 4
    colors = set()
    for y in range(h // 4, h * 3 // 4, step):
        sy = y if top_down else (h - 1 - y)
        base = off + sy * stride
        for x in range(w // 4, w * 3 // 4, step):
            i = base + x * nch
            colors.add(bytes(data[i:i + 3]))
    return len(colors)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()


def visible_windows() -> list[tuple[int, str]]:
    found = []

    def cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        if title:
            found.append((hwnd, title))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found


def grab(hwnd: int, path: str) -> tuple[int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"BM")
        fh.write(struct.pack("<IHHI", 14 + 40 + size, 0, 0, 14 + 40))
        fh.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, size, 0, 0, 0, 0))
        fh.write(buf.raw)
    return w, h


def main() -> int:
    dist = sys.argv[1] if len(sys.argv) > 1 else None
    if not dist:
        sys.path.insert(0, ROOT)
        from core import __version__   # noqa: PLC0415
        import io
        meta = {}
        with io.open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    meta[k.strip()] = v.strip()
        dist = os.path.join(ROOT, "release",
                            "RwSaveTool-v%s-win64-%s" % (meta["version"], meta["date"].replace("-", "")))
        assert __version__ == meta["version"], (__version__, meta["version"])

    exe_name = sys.argv[2] if len(sys.argv) > 2 else "RwSaveTool.exe"
    exe = os.path.join(dist, exe_name)
    if not os.path.isfile(exe):
        print("找不到 exe:", exe)
        return 1

    work = os.path.join(ROOT, "build", "_release_smoke")
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    print("复制发布目录到", work, "…")
    shutil.copytree(dist, work)
    # 文档与 zip 校验文件不用跟着跑
    for junk in ("README.txt", "VERSION.txt", "CHANGELOG.md", "CHECKSUMS.txt"):
        p = os.path.join(work, junk)
        if os.path.isfile(p):
            os.remove(p)

    before = {h for h, _t in visible_windows()}
    proc = subprocess.Popen([os.path.join(work, exe_name)], cwd=work)
    title, hwnd = "", None
    for _ in range(60):
        time.sleep(0.5)
        for h, t in visible_windows():
            if h in before:
                continue
            if "RwSaveTool" in t:
                hwnd, title = h, t
                break
        if hwnd:
            break

    ok = True
    print("进程存活    ", proc.poll() is None)
    print("窗口标题    ", title or "（未发现）")
    if proc.poll() is not None:
        ok = False
        print("exe 启动后立刻退出，返回码", proc.returncode)
    if not hwnd:
        ok = False
    else:
        time.sleep(2.5)          # 等 WebView2 把页面画出来
        shot = os.path.join(ROOT, "build", "_shots", "release_smoke.bmp")
        w, h = grab(hwnd, shot)
        print("截图        %s  %dx%d" % (shot, w, h))
        # 不是纯黑/纯白：看中间区域的颜色种类
        try:
            n = bmp_color_count(shot)
            print("画面颜色种类", n)
            if n < 6:
                ok = False
                print("画面几乎是纯色，界面可能没渲染出来")
        except Exception as exc:  # noqa: BLE001
            print("读取截图失败：", exc)

    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:  # noqa: BLE001
        proc.kill()
    print("SMOKE", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
