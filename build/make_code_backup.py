r"""源码分版本备份。

用法：
    .venv\Scripts\python.exe build\make_code_backup.py            # 打当前 VERSION 指定的版本
    .venv\Scripts\python.exe build\make_code_backup.py --list     # 只看已有哪些备份

产物：
    code_backups/code-v<版本>.zip        源码包（可解压，顶层为 RwSaveTool-v<版本>/）
    code_backups/code-v<版本>.md5.txt    校验值 + 逐文件清单
    code_backups/README.md               索引（自动重建，按版本倒序）

规则：
- 只收源码与构建脚本，不收 .venv / dist / release / docs / region_data（用户数据）/ config.json。
- 版本号以 VERSION 为准，并与 core/__init__.py 的 __version__ 交叉校验，不一致直接失败。
- 同一版本重复执行会覆盖该版本的文件，但不会动其他版本的备份。
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(ROOT, "code_backups")

INCLUDE_DIRS = ("core", "ui", "data", "build")
INCLUDE_FILES = (
    "main.py",
    "requirements.txt",
    "README.md",
    "VERSION",
    "启动.bat",
    "调试启动.bat",
)
SKIP_DIRS = {"__pycache__", "_work", "_pre_release_bak", "_stage", ".venv"}


# ----------------------------------------------------------------------
# 版本信息
# ----------------------------------------------------------------------
def read_meta() -> dict:
    path = os.path.join(ROOT, "VERSION")
    meta: dict[str, str] = {}
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            meta[key.strip()] = val.strip()
    return meta


def code_version() -> str:
    path = os.path.join(ROOT, "core", "__init__.py")
    with io.open(path, encoding="utf-8") as fh:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', fh.read())
    return match.group(1) if match else ""


# ----------------------------------------------------------------------
# 文件收集
# ----------------------------------------------------------------------
def keep(name: str, folder: str) -> bool:
    if name.endswith((".pyc", ".pyo", ".bak")):
        return False
    if name.startswith("rw_gui.html.bak"):
        return False
    # build/ 只收正式脚本；一次性脚本（_probe_* / _sim_tune / _make_*）不入档
    if folder == "build" and not (name.endswith(".py") and not name.startswith("_")):
        return False
    return True


def collect() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for name in INCLUDE_FILES:
        full = os.path.join(ROOT, name)
        if os.path.isfile(full):
            items.append((full, name))
    for folder in INCLUDE_DIRS:
        base = os.path.join(ROOT, folder)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in sorted(files):
                if not keep(fname, folder):
                    continue
                full = os.path.join(root, fname)
                items.append((full, os.path.relpath(full, ROOT).replace("\\", "/")))
    items.sort(key=lambda pair: pair[1])
    return items


# ----------------------------------------------------------------------
# 哈希
# ----------------------------------------------------------------------
def digest(path: str, algo: str = "md5") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(size: int) -> str:
    if size < 1024:
        return "%d B" % size
    if size < 1024 * 1024:
        return "%.1f KB" % (size / 1024.0)
    return "%.2f MB" % (size / 1048576.0)


# ----------------------------------------------------------------------
# 索引
# ----------------------------------------------------------------------
def read_sidecar(path: str) -> dict:
    info: dict[str, str] = {}
    if not os.path.isfile(path):
        return info
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("【"):
                break
            if " " in line:
                key, val = line.rstrip("\n").split(" ", 1)
                info[key.strip()] = val.strip()
    return info


def rebuild_index() -> str:
    rows = []
    for name in sorted(os.listdir(BACKUP_DIR)):
        if not (name.startswith("code-v") and name.endswith(".zip")):
            continue
        full = os.path.join(BACKUP_DIR, name)
        info = read_sidecar(full[:-4] + ".md5.txt")
        rows.append(
            {
                "file": name,
                "version": info.get("version") or name[6:-4],
                "name": info.get("name", "—"),
                "date": info.get("date", "—"),
                "files": info.get("files", "—"),
                "size": human(int(info.get("zip_size", os.path.getsize(full)))),
                "md5": info.get("zip_md5") or digest(full),
            }
        )
    # 版本号倒序（1.10.0 > 1.9.0，按数字段比较）
    def sort_key(row: dict) -> list:
        parts = []
        for seg in row["version"].split("."):
            parts.append(int(seg) if seg.isdigit() else 0)
        return parts

    rows.sort(key=sort_key, reverse=True)

    lines = [
        "# 源码备份索引",
        "",
        "每个发布版本对应一个 `code-v<版本>.zip`，**不覆盖历史版本**。",
        "包内只含源码与构建脚本，不含 `.venv` / `dist` / `release` / `docs` / `region_data`（用户数据）/ `config.json`。",
        "",
        "| 版本 | 名称 | 日期 | 文件数 | zip 大小 | zip MD5 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| [%s](%s) | %s | %s | %s | %s | `%s` |"
            % (row["version"], row["file"], row["name"], row["date"],
               row["files"], row["size"], row["md5"])
        )
    if not rows:
        lines.append("| — | 还没有备份 | — | — | — | — |")

    lines += [
        "",
        "## 怎么恢复某个版本",
        "",
        "```bash",
        "unzip code-v<版本>.zip          # 得到 RwSaveTool-v<版本>/",
        "cd RwSaveTool-v<版本>",
        "python -m venv .venv",
        ".venv/Scripts/pip install -r requirements.txt",
        ".venv/Scripts/python.exe build/smoke.py    # 期望 SMOKE OK",
        "```",
        "",
        "区域数据不在源码包里。要跑完整界面，把对应发布包的 `region_data/`",
        "复制到源码根，或在程序里重新导入游戏本体。",
        "",
        "## 怎么新增一个版本",
        "",
        "1. 改 `VERSION` 与 `core/__init__.py` 的 `__version__`（两处必须一致）；",
        "2. 跑 `.venv/Scripts/python.exe build/make_code_backup.py`；",
        "3. 本索引会自动重建。",
        "",
    ]
    text = "\n".join(lines)
    with io.open(os.path.join(BACKUP_DIR, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def list_only() -> int:
    if not os.path.isdir(BACKUP_DIR):
        print("还没有 code_backups/ 目录")
        return 0
    for name in sorted(os.listdir(BACKUP_DIR)):
        if name.endswith(".zip"):
            print("%-28s %s" % (name, human(os.path.getsize(os.path.join(BACKUP_DIR, name)))))
    return 0


def main() -> int:
    if "--list" in sys.argv:
        return list_only()

    meta = read_meta()
    version = meta.get("version", "")
    if not version:
        print("VERSION 里没有 version 字段")
        return 1
    in_code = code_version()
    if in_code != version:
        print("版本号不一致：VERSION=%s，core/__init__.py=%s" % (version, in_code))
        print("两处必须一致，先改齐再备份。")
        return 1

    items = collect()
    if not items:
        print("没收集到任何文件")
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    top = "RwSaveTool-v%s" % version
    zip_path = os.path.join(BACKUP_DIR, "code-v%s.zip" % version)
    if os.path.isfile(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for full, rel in items:
            zf.write(full, top + "/" + rel)

    ui_path = os.path.join(ROOT, "ui", "rw_gui.html")
    ui_md5 = digest(ui_path)
    ui_bytes = os.path.getsize(ui_path)
    with io.open(ui_path, encoding="utf-8") as fh:
        ui_lines = sum(1 for _ in fh)

    zip_size = os.path.getsize(zip_path)
    zip_md5 = digest(zip_path)
    zip_sha = digest(zip_path, "sha256")

    side_lines = [
        "version %s" % version,
        "name %s" % meta.get("name", ""),
        "date %s" % meta.get("date", ""),
        "built %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "files %d" % len(items),
        "zip_size %d" % zip_size,
        "zip_md5 %s" % zip_md5,
        "zip_sha256 %s" % zip_sha,
        "ui_md5 %s" % ui_md5,
        "ui_bytes %d" % ui_bytes,
        "ui_lines %d" % ui_lines,
        "",
        "【文件清单】",
        "%-38s %10s  %s" % ("文件", "字节", "MD5"),
        "-" * 72,
    ]
    for full, rel in items:
        side_lines.append("%-38s %10d  %s" % (rel, os.path.getsize(full), digest(full)))

    side_path = os.path.join(BACKUP_DIR, "code-v%s.md5.txt" % version)
    with io.open(side_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(side_lines) + "\n")

    rebuild_index()

    print("版本      : %s（%s）" % (version, meta.get("name", "")))
    print("源码包    : %s（%s / %d 个文件）" % (zip_path, human(zip_size), len(items)))
    print("zip MD5   : %s" % zip_md5)
    print("zip SHA256: %s" % zip_sha)
    print("界面基线  : %s / %d B / %d 行" % (ui_md5, ui_bytes, ui_lines))
    print("索引      : %s" % os.path.join(BACKUP_DIR, "README.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
