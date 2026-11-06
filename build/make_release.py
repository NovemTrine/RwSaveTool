"""组装发布包的校验清单与 zip（一次性脚本）。

用法： .venv/Scripts/python.exe build/_make_release.py
产物：
    release/RwSaveTool-v1.0.0-win64-20261106/校验清单.txt
    release/RwSaveTool-v1.0.0-win64-20261106.zip
    release/RwSaveTool-v1.0.0-win64-20261106.zip.md5.txt
"""

from __future__ import annotations

import hashlib
import io
import os
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


def main() -> int:
    if not os.path.isdir(PKG):
        print("缺少发布目录:", PKG)
        return 1

    files = walk_files(PKG)
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
    region_files = sorted(n for n, _s in files if n.startswith("region_data/") and n.endswith(".json")
                          and not n.endswith("_sources.json"))

    lines = []
    lines.append("RwSaveTool v%s · 校验清单" % VERSION)
    lines.append("=" * 62)
    lines.append("生成时间   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("文件总数   %d" % len(files))
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
    lines.append("【区域数据】（52 个文件，逐个校验）")
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
