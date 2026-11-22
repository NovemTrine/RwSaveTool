"""出口 → 方向（兼容层）。

判边逻辑已经搬到 `doorrule.py`；这里保留旧函数名，因为 `report.py`、`standalone.py`
和 `analysis/` 下的探针都在用。新代码请直接用 `doorrule.evidence()`。
"""
from __future__ import annotations

from . import doorrule

SIDES = doorrule.SIDES
OPP = doorrule.OPP
classify = doorrule.classify
exit_t = doorrule.exit_t


def evidence(room, ex, opts=None):
    return doorrule.evidence(room, ex, opts)


def exit_side(room, ex, edge_tol=2, opts=None):
    """一条出口 → (方向, 置信度, 依据)。依据是 channel/effective/edge/camera/center。"""
    o = dict(opts or {})
    o.setdefault("edge_tol", edge_tol)
    ev = doorrule.evidence(room, ex, o)
    return ev["side"], ev["conf"], ev["src"]
