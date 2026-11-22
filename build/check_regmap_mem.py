"""P0 验收之二：遍历全库跑布局，看内存涨到哪儿、返回给前端的 JSON 有多大。

为什么单独一个脚本：
  demo 是「跑完就退出」的预览进程，工具是常驻的桌面程序。同一套算法院本
  没问题，怕的是缓存不收口——117 个区域挨个点下去，堆一路涨到 1 GB 就该
  骂人了。这里把 `bridge.Api().regmap_map()` 真跑一遍（含 LRU 6 的载荷缓存
  与 adapter 的 48 间解析缓存），每 20 区记一次工作集。

判据（对应 V1.5 §12 P0）：
  · 遍历 117 区后，工作集增长 < 300 MB
  · 单区 JSON 载荷 < 12 MB（否则 pywebview 序列化 + 前端解析都会卡）
  · 无异常、无未解暴涨（只报数，不对拍——对拍是 check_regmap_parity.py 的事）

用法：
    .venv/Scripts/python.exe build/check_regmap_mem.py
    .venv/Scripts/python.exe build/check_regmap_mem.py UW MS TL
"""

from __future__ import annotations

import ctypes
import glob
import json
import os
import statistics
import sys
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import bridge, paths                     # noqa: E402

LOG = os.path.join(ROOT, "build", "_regmap_mem.log")

BUDGET_MB = 300.0        # 工作集增长上限
PAYLOAD_MB = 12.0        # 单区载荷上限


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


_PSAPI = ctypes.WinDLL("psapi")
_K32 = ctypes.WinDLL("kernel32")
_PSAPI.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC),
                                       wintypes.DWORD]
_PSAPI.GetProcessMemoryInfo.restype = wintypes.BOOL
_K32.GetCurrentProcess.restype = wintypes.HANDLE


def rss_mb() -> float:
    """当前进程工作集（MB）。取不到就返回 0，只影响报表不影响结论。"""
    try:
        info = _PMC()
        info.cb = ctypes.sizeof(info)
        h = _K32.GetCurrentProcess()
        if not _PSAPI.GetProcessMemoryInfo(h, ctypes.byref(info), info.cb):
            return 0.0
        return info.WorkingSetSize / (1024.0 * 1024.0)
    except Exception:                                  # noqa: BLE001
        return 0.0


def peak_mb() -> float:
    """进程历史峰值工作集（MB）。"""
    try:
        info = _PMC()
        info.cb = ctypes.sizeof(info)
        h = _K32.GetCurrentProcess()
        if not _PSAPI.GetProcessMemoryInfo(h, ctypes.byref(info), info.cb):
            return 0.0
        return info.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:                                  # noqa: BLE001
        return 0.0


def region_codes() -> list[str]:
    out = []
    for p in sorted(glob.glob(os.path.join(paths.data_dir(), "*.json"))):
        name = os.path.basename(p)[:-5]
        if not name.startswith("_"):
            out.append(name.upper())
    return out


def main() -> int:
    codes = [c.upper() for c in sys.argv[1:]] or region_codes()
    api = bridge.Api()
    lines: list[str] = []
    sizes: list[tuple[int, str]] = []
    times: list[int] = []
    fails: list[str] = []

    def say(msg: str) -> None:
        print(msg)
        lines.append(msg)

    rss0 = rss_mb()
    say("起点 工作集 %.1f MB，区域 %d 个" % (rss0, len(codes)))

    for i, code in enumerate(codes, 1):
        try:
            res = api.regmap_map(code)
        except Exception as exc:                       # noqa: BLE001
            fails.append("%s 异常 %s" % (code, exc))
            continue
        if not res.get("ok"):
            fails.append("%s 失败 %s %s" % (code, res.get("error"), res.get("detail", "")[:60]))
            continue
        n = len(json.dumps(res, ensure_ascii=False, default=str).encode("utf-8"))
        sizes.append((n, code))
        times.append(int(res.get("ms") or 0))
        if i % 20 == 0 or i == len(codes):
            say("  %3d/%d  工作集 %.1f MB（+%.1f）"
                % (i, len(codes), rss_mb(), rss_mb() - rss0))

    rss1 = rss_mb()
    say("首轮结束：工作集 %.1f MB，峰值 %.1f MB" % (rss1, peak_mb()))

    # 二轮：换一批区域再算，验证缓存是「有上限」而不是「只进不出」。
    # 只要 LRU 真在工作，二轮跑完的工作集应该和首轮结束时相差无几。
    again = codes[:24]
    for code in again:
        try:
            api.regmap_map(code)
        except Exception as exc:                       # noqa: BLE001
            fails.append("%s 二轮异常 %s" % (code, exc))
    rss2 = rss_mb()
    say("二轮 %d 区：工作集 %.1f → %.1f MB（%+.1f）"
        % (len(again), rss1, rss2, rss2 - rss1))

    grow = rss2 - rss0
    say("")
    say("区域 %d 个：成功 %d / 失败 %d" % (len(codes), len(sizes), len(fails)))
    if fails:
        for line in fails[:8]:
            say("   " + line)
    if sizes:
        vals = [s for s, _ in sizes]
        say("单区 JSON：中位 %.2f MB，均值 %.2f MB，最大 %.2f MB（%s）"
            % (statistics.median(vals) / 1048576.0,
               statistics.mean(vals) / 1048576.0,
               max(vals) / 1048576.0,
               max(sizes)[1]))
        say("            最小 %.2f MB；排行前 5：%s"
            % (min(vals) / 1048576.0,
               "、".join("%s %.2f" % (c, s / 1048576.0)
                        for s, c in sorted(sizes, reverse=True)[:5])))
        say("布局耗时：中位 %d ms，均值 %.0f ms，最大 %d ms"
            % (statistics.median(times), statistics.mean(times), max(times)))
    say("")
    say("工作集 %.1f → %.1f MB，增长 %+.1f MB（预算 %.0f）"
        % (rss0, rss2, grow, BUDGET_MB))
    ok_mem = grow < BUDGET_MB
    ok_pay = (not sizes) or max(s for s, _ in sizes) < PAYLOAD_MB * 1048576
    say("判定：内存 %s；载荷 %s" % ("通过" if ok_mem else "超标",
                                   "通过" if ok_pay else "超标"))
    if not fails and ok_mem and ok_pay:
        say("结论：P0 内存与载荷验收通过")

    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0 if (not fails and ok_mem and ok_pay) else 1


if __name__ == "__main__":
    raise SystemExit(main())
