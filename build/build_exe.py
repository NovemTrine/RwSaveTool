"""PyInstaller 打包脚本。

用法：
    .venv/Scripts/python.exe build/build_exe.py              # 目录版（onedir，启动快）
    .venv/Scripts/python.exe build/build_exe.py --onefile    # 单文件版（一个 exe 拷走）
    .venv/Scripts/python.exe build/build_exe.py --console    # 保留控制台（排错用）
    .venv/Scripts/python.exe build/build_exe.py --out=发布目录 # 打到指定目录（发版用，互不干扰）

产物：
    dist/RwSaveTool/RwSaveTool.exe            （onedir，推荐分发）
    dist_onefile/RwSaveTool单文件.exe          （onefile，省事分发）
    带 --out 时： <发布目录>/RwSaveTool/... 或 <发布目录>/RwSaveTool单文件.exe
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "_work")


def main() -> int:
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("缺少 pyinstaller：pip install --index-url https://pypi.org/simple pyinstaller")
        return 1

    console = "--console" in sys.argv
    onefile = "--onefile" in sys.argv
    name = "RwSaveTool单文件" if onefile else "RwSaveTool"
    out = None
    for a in sys.argv[1:]:
        if a.startswith("--out="):
            out = os.path.abspath(a[len("--out="):])
    distpath = out or os.path.join(ROOT, "dist_onefile" if onefile else "dist")
    if out:
        os.makedirs(out, exist_ok=True)

    # PyInstaller --clean 会整个删掉输出目录，而用户的导入缓存就在里面（dist/RwSaveTool/region_data）。
    # 打包前先搬到临时目录，打完再搬回来，用户数据优先。
    saved = None
    saved_target = None
    for candidate in (
        os.path.join(distpath, "region_data") if onefile else None,
        os.path.join(distpath, "RwSaveTool", "region_data") if not onefile else None,
    ):
        if candidate and os.path.isdir(candidate):
            saved = tempfile.mkdtemp(prefix="rw_region_")
            shutil.copytree(candidate, os.path.join(saved, "region_data"))
            saved_target = candidate
            print("已暂存用户导入缓存：", candidate)
            break

    args = [
        os.path.join(ROOT, "main.py"),
        "--name", name,
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        "--console" if console else "--windowed",
        "--add-data", os.path.join(ROOT, "ui") + os.pathsep + "ui",
        "--add-data", os.path.join(ROOT, "data") + os.pathsep + "data",
        "--distpath", distpath,
        "--workpath", BUILD,
        "--specpath", BUILD,
        "--hidden-import", "webview.platforms.edgechromium",
        # WebView2 的 loader / .NET 桥接 DLL 必须一起打包，否则冻结后无法创建窗口
        "--collect-all", "webview",
    ]
    icon = os.path.join(ROOT, "build", "app.ico")
    if os.path.isfile(icon):
        args += ["--icon", icon]

    print("PyInstaller 参数：", " ".join(args))
    pyi.run(args)

    if onefile:
        exe = os.path.join(distpath, name + ".exe")
        print("产物：", exe, "存在" if os.path.isfile(exe) else "缺失")
        if saved and saved_target:
            os.makedirs(saved_target, exist_ok=True)
            for fn in os.listdir(os.path.join(saved, "region_data")):
                shutil.copy(os.path.join(saved, "region_data", fn), saved_target)
            shutil.rmtree(saved, ignore_errors=True)
            print("已恢复用户导入缓存：", saved_target)
        return 0 if os.path.isfile(exe) else 1

    # 目录版：把一份已导入的区域数据放到 exe 旁边，方便直接复用
    dist = os.path.join(distpath, "RwSaveTool")
    target = os.path.join(dist, "region_data")
    if os.path.isdir(dist):
        os.makedirs(target, exist_ok=True)
        if saved:
            restored = 0
            for fn in os.listdir(os.path.join(saved, "region_data")):
                shutil.copy(os.path.join(saved, "region_data", fn), target)
                restored += 1
            shutil.rmtree(saved, ignore_errors=True)
            print("已恢复用户导入缓存（%d 个文件，优先于仓库里那份）" % restored)
        else:
            for fn in os.listdir(os.path.join(ROOT, "region_data")):
                if fn.lower().endswith(".json"):
                    shutil.copy(os.path.join(ROOT, "region_data", fn), target)
            print("已复制导入缓存到", target)
    else:
        print("未找到 dist 目录，打包可能失败")
        return 1

    exe = os.path.join(dist, "RwSaveTool.exe")
    print("产物：", exe, "存在" if os.path.isfile(exe) else "缺失")
    return 0 if os.path.isfile(exe) else 1


if __name__ == "__main__":
    raise SystemExit(main())
