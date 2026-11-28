"""组装发布包的文本附件、校验清单与 zip。

用法： .venv/Scripts/python.exe build/make_release.py
前置：
    1. 已把 exe / _internal / region_data 放进 release/RwSaveTool-v<版本>-win64-<日期>/
    2. 仓库根有 VERSION 与 CHANGELOG.md

产物：
    release/<NAME>/README.txt        由 build/release_assets/README.txt 渲染（填版本与区域数）
    release/<NAME>/VERSION.txt       版本信息、兼容性、本包内容
    release/<NAME>/CHANGELOG.md      从仓库根复制
    release/<NAME>/CHECKSUMS.txt     关键文件 MD5/SHA256 + 完整清单
    release/<NAME>.zip               整个目录打包
    release/<NAME>.zip.md5.txt       zip 的 MD5 / SHA256 / 体积
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_meta() -> dict:
    meta: dict[str, str] = {}
    with io.open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            meta[key.strip()] = val.strip()
    return meta


META = _read_meta()
VERSION = META.get("version", "0.0.0")
VERSION_NAME = META.get("name", "")
RELEASE_DATE = META.get("date", "")
NAME = "RwSaveTool-v%s-win64-%s" % (VERSION, RELEASE_DATE.replace("-", ""))
PKG = os.path.join(ROOT, "release", NAME)
ZIP_PATH = os.path.join(ROOT, "release", NAME + ".zip")


def digest(path: str, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.1f %s" % (size, unit) if unit != "B" else "%d B" % size
        size /= 1024.0
    return str(size)


def walk_files(base: str) -> list[tuple[str, int]]:
    out = []
    for folder, _dirs, files in os.walk(base):
        for name in files:
            full = os.path.join(folder, name)
            out.append((os.path.relpath(full, base).replace("\\", "/"), os.path.getsize(full)))
    return sorted(out)


def write_docs() -> int:
    """把随包的三份文本刷新一遍，返回区域文件数。

    区域数从发布目录里的 region_data 数出来，README 里不再写死数字 ——
    上次就出现过「文档说 52 个、包里已经变了」的偏差。
    """
    region_dir = os.path.join(PKG, "region_data")
    regions = sorted(n for n in os.listdir(region_dir)
                     if n.endswith(".json") and not n.startswith("_")) if os.path.isdir(region_dir) else []

    tpl = os.path.join(ROOT, "build", "release_assets", "README.txt")
    with io.open(tpl, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("{version}", VERSION).replace("{regions}", str(len(regions)))
    with io.open(os.path.join(PKG, "README.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(text)

    ui = os.path.join(PKG, "_internal", "ui", "rw_gui.html")
    ui_md5 = digest(ui, "md5") if os.path.isfile(ui) else "（未打包）"
    ui_rel = "_internal/ui/rw_gui.html"
    core = os.path.join(ROOT, "core", "__init__.py")
    ver_name, rel_date = VERSION_NAME, RELEASE_DATE
    if os.path.isfile(core):
        with io.open(core, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("__version_name__"):
                    ver_name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("__release_date__"):
                    rel_date = line.split("=", 1)[1].strip().strip('"')

    py = "%d.%d.%d" % sys.version_info[:3]
    lines = [
        "RwSaveTool · 雨世界存档分析器",
        "=" * 60,
        "",
        "版本号        %s" % VERSION,
        "版本名称      %s" % ver_name,
        "发布日期      %s" % rel_date,
        "构建时间      %s (GMT+8)" % time.strftime("%Y-%m-%d %H:%M"),
        "构建环境      Windows x64 · Python %s · PyInstaller 6.22.3" % py,
        "程序形态      目录版（onedir）+ 单文件版（onefile），两者功能完全相同",
        "界面文件      %s" % ui_rel,
        "              md5 %s" % ui_md5,
        "",
        "【兼容性】",
        "配置版本      2（core/paths.py CONFIG_VERSION）",
        "区域数据      schema 4（layers + connections + exits + exitNumbering）",
        "存档读取      只读；不修改、不写入任何游戏文件",
        "",
        "【数据范围】",
        "内置区域      %d 个，来自游戏本体三个包：" % len(regions),
        "              游戏原版 / Downpour（倾盆大雨）/ The Watcher（观望者）",
        "模组数据      不含。使用者在程序里自行导入创意工坊模组后生成",
        "地图底图      不含（区域地图是几何图，靠房间数据现算，不需要 map_<reg>.png）",
        "个人数据      不含。无配置、无存档内容、无导入缓存、无本机路径",
        "              区域数据里记录的素材路径已统一抹除（换机器后按提示重新导入即可）",
        "",
        "【本包内容】",
        "RwSaveTool.exe              主程序 · 目录版（启动快，推荐日常用；必须与 _internal/ 一起）",
        "RwSaveTool-onefile.exe      同一程序的单文件版（双击即用，可单独拷到别处）",
        "_internal/                  目录版的运行库与内置只读资源（请勿删改）",
        "region_data/                官方区域数据；程序也把导入缓存写在这里",
        "VERSION.txt                 版本信息（本文件）",
        "README.txt                  面向使用者的操作说明",
        "CHANGELOG.md                本版相对上一版的改动清单",
        "CHECKSUMS.txt               关键文件的 MD5 / SHA256 与完整文件清单",
        "",
        "【首次运行】",
        "两个 exe 任选一个双击即可，功能完全一样，只是打包形态不同：",
        "  想启动快        → RwSaveTool.exe（整个文件夹别拆开）",
        "  想一个文件拷走  → RwSaveTool-onefile.exe（启动慢 1~3 秒）",
        "程序会在同目录生成 config.json，内容全部为默认值（不含任何个人信息）。",
        "若本目录不可写（例如放在 Program Files），配置会退到",
        "%APPDATA%\\RwSaveTool\\ 下，不影响使用。",
        "",
        "【本版要点】",
        "· 界面做减法：标签 7 → 4（概览 / 区域 / 统计 / 其他）；通行证、收集、已发现庇护所、",
        "  其他解锁、字段说明五页全部下线",
        "· 收集页改成「统计」：只留各战役统计一张表；代币 / 珍珠 / 广播 / 回响的数字与地图点位一并删除",
        "· 分数口径变更：不再乘「通行证数 + 1」，只按行为分算（White 8,463 → 2,821，详见 CHANGELOG 第一节）",
        "· 区域地图：页顶来源开关；Downpour / The Watcher 的等价模组层自动折叠；切来源不再闪白",
        "· 区域数据弹窗支持缩写 / 英文 / 中文搜索；译名补上模组角色",
        "",
    ]
    with io.open(os.path.join(PKG, "VERSION.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines))

    src = os.path.join(ROOT, "CHANGELOG.md")
    if os.path.isfile(src):
        shutil.copyfile(src, os.path.join(PKG, "CHANGELOG.md"))
    return len(regions)


def main() -> int:
    if not os.path.isdir(PKG):
        print("缺少发布目录:", PKG)
        return 1

    regions = write_docs()
    print("已刷新随包文本（区域 %d 个）" % regions)

    # 清单文件自己不算进去（否则第二次生成时会把上一次的 CHECKSUMS.txt 数进来，
    # 文件总数在 275/276 之间来回跳，校验的人会以为包变了）
    files = [item for item in walk_files(PKG) if item[0] != "CHECKSUMS.txt"]
    total = sum(size for _n, size in files)

    key_files = [
        "RwSaveTool.exe",
        "RwSaveTool-onefile.exe",
        "_internal/ui/rw_gui.html",
        "_internal/data/region_map.json",
        "_internal/data/region_reach.json",
        "_internal/data/region_access.json",
        "_internal/data/creature_score.json",
        "region_data/_sources.json",
    ]
    # 只数真正的区域文件：`_sources.json` / `_colors.json` 这类下划线开头的是元数据与缓存，
    # 数进来就会变成「118 个官方区域」，跟 README 里的 {regions} 对不上（v1.3.0 踩过）。
    region_files = sorted(n for n, _s in files
                          if n.startswith("region_data/") and n.endswith(".json")
                          and not n.split("/")[-1].startswith("_"))

    lines = []
    lines.append("RwSaveTool v%s · 校验清单" % VERSION)
    lines.append("=" * 62)
    lines.append("生成时间   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("文件总数   %d（不含本文件 CHECKSUMS.txt；zip 里的实际条目会多 1 个）" % len(files))
    lines.append("解压体积   %s（%d 字节）" % (human(total), total))
    lines.append("区域数据   %d 个官方区域 + _sources.json" % len(region_files))
    lines.append("")
    lines.append("【关键文件】")
    lines.append("%-34s %-34s %s" % ("文件", "MD5", "SHA256(前 32 位)"))
    lines.append("-" * 62)
    for rel in key_files:
        full = os.path.join(PKG, rel)
        if not os.path.isfile(full):
            lines.append("%-34s %s" % (rel, "缺失"))
            continue
        lines.append("%-34s %-34s %s" % (rel, digest(full, "md5"), digest(full, "sha256")[:32]))

    lines.append("")
    lines.append("【区域数据】（%d 个文件，逐个校验）" % len(region_files))
    lines.append("-" * 62)
    for rel in region_files:
        full = os.path.join(PKG, rel)
        lines.append("%-14s %10d B  %s" % (rel.split("/")[-1], os.path.getsize(full), digest(full, "md5")))

    lines.append("")
    lines.append("【完整文件清单】")
    lines.append("-" * 62)
    for rel, size in files:
        lines.append("%-56s %10d B" % (rel, size))

    text = "\n".join(lines) + "\n"
    manifest = os.path.join(PKG, "CHECKSUMS.txt")
    with io.open(manifest, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(text)
    print("已写校验清单:", manifest)

    # 打包：顶层保留版本目录，解压即得到一个干净的文件夹
    if os.path.isfile(ZIP_PATH):
        os.remove(ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for folder, _dirs, names in os.walk(PKG):
            for name in sorted(names):
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, os.path.dirname(PKG)).replace("\\", "/")
                zf.write(full, rel)

    zsize = os.path.getsize(ZIP_PATH)
    md5 = digest(ZIP_PATH, "md5")
    sha = digest(ZIP_PATH, "sha256")
    print("已打包:", ZIP_PATH)
    print("zip 体积: %s（%d 字节）" % (human(zsize), zsize))
    print("zip MD5 :", md5)
    print("zip SHA256:", sha)

    side = ZIP_PATH + ".md5.txt"
    with io.open(side, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("%s  %s\n" % (md5, os.path.basename(ZIP_PATH)))
        fh.write("SHA256  %s  %s\n" % (sha, os.path.basename(ZIP_PATH)))
        fh.write("size    %d bytes\n" % zsize)
        fh.write("version %s / %s\n" % (VERSION, RELEASE_DATE))
    print("已写:", side)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
