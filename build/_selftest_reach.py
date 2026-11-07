"""check_reach 的口径判定自检（纯函数，不开界面、不动 config）。

跑法：.venv/Scripts/python.exe build/_selftest_reach.py

为什么要有这个：T-01 的旧断言写成 `宽松 == 严格 + roleDrop`，看起来"能检测"，
实际永远算不成立（把同一房间在 roleDrop / condDrop 两个计数器里算了两次），
红了一年也没人知道红在哪。新断言必须证明"该红的时候真的红"，
否则很容易又写成一条恒真的假绿。这里用真实读数比例造的夹具锁住三种破坏。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_reach import _loose_ok  # noqa: E402

# 真实读数：白猫看 RF（mod:coral.caves 一层）严格 65 间 / 宽松 66 间，
# roleDrop 15、condDrop 14，且这 14 间条件房间全在 15 间角色专属里，
# 所以宽松只比严格多 1 间（RF_SAINTI01，唯一没被声明 EXCLUSIVEROOM 的角色房间）。
STRICT_NAMES = ["RF_%02d" % i for i in range(64)] + ["RF_SAINTI01"]
LOOSE_NAMES = STRICT_NAMES + ["RF_SAINTB02"]
STRICT = {"total": 65, "roleDrop": 15, "condDrop": 14, "strict": True, "names": STRICT_NAMES}
LOOSE = {"total": 66, "roleDrop": 0, "condDrop": 14, "strict": False, "names": LOOSE_NAMES}

CASES = [
    # (说明, strict, loose, role_drop, 期望 ok_subset, 期望 ok_only_role)
    ("正确读数：多出的正是角色专属房间", STRICT, LOOSE, 15, True, True),
    ("宽松把条件房间也放开了（condDrop 归零，多出 14 间）",
     STRICT, {**LOOSE, "condDrop": 0, "total": 80,
              "names": LOOSE_NAMES + ["RF_SAINTX%02d" % i for i in range(14)]},
     15, True, False),
    ("宽松也按角色剔（一间都没多出）",
     STRICT, {**STRICT, "strict": False, "roleDrop": 0}, 15, False, True),
    ("宽松混进非角色房间（旧断言的错误模型）",
     STRICT, {**LOOSE, "total": 67, "names": LOOSE_NAMES + ["RF_CAVE99"]}, 15, True, False),
    ("total 与 names 脱钩",
     STRICT, {**LOOSE, "total": 66, "names": LOOSE_NAMES[:-1]}, 15, False, True),
]


def main() -> int:
    failed = 0
    for desc, st, lo, role_drop, want_subset, want_role in CASES:
        got_subset, got_role, msg = _loose_ok(st, lo, role_drop)
        ok = (got_subset, got_role) == (want_subset, want_role)
        print(("  ✅ " if ok else "  ❌ ") + desc)
        if not ok:
            failed += 1
            print("      期望 (%s, %s) 实得 (%s, %s) ｜ %s"
                  % (want_subset, want_role, got_subset, got_role, msg))
    print("\n合计 %d 项，失败 %d 项" % (len(CASES), failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
