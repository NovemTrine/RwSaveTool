"""角色可达：房间级排除（角色专属 / 手动）与完成度口径。

产物： build/_shots/reach_last.json（原始读数，排查用）
会临时改 config.ui.roomExcluded / roomStrict，跑完原样还原。

口径语义（T-01 之后写清，别再按"宽松 = 全部房间"理解）：
    applyConditional() 里只有 byHand / byRole 受 state.roomStrict 门控，
    exclusiveOut / hidden（EXCLUSIVEROOM / HIDEROOM 条件房间）在两种口径下都剔除
    —— 条件房间本来就只对某角色存在，放开就永远到不了 100%。
    所以 宽松 ≠ 全部房间，恒有：
        严格 = U - |cond ∪ role ∪ manual|
        宽松 = U - |cond|
    两者的差 = |role \\ cond| + |manual \\ cond|，绝不可能等于 roleDrop
    （同一房间会同时进 roleDropped 和 conditionalDropped 两个计数器）。
"""
from __future__ import annotations

import json
import os
import sys
import time

import webview

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 回归产物统一放 build/_shots，不污染 docs（docs 只放被文档引用的图）
SHOTS = os.path.join(ROOT, "build", "_shots")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)
from core.bridge import Api  # noqa: E402

TITLE = "RwSaveTool 可达检查"
CFG = os.path.join(ROOT, "config.json")

# 与 ui/rw_gui.html 的 ROOM_OWNER 表保持一致：房间名带这些词 = 某角色专属房间。
# 改那边的正则就要同步改这里，否则下面 ok_only_role 会误报。
ROLE_HINT = (
    "SAINT", "ARTIFICER", "ARTY", "SPEARMASTER", "SPEAR",
    "RIVULET", "GOURMAND", "GOURM", "HUNTER", "NIGHT",
)


def _upper_names(raw) -> set[str]:
    return {str(n).upper() for n in (raw or [])}


def _loose_ok(strict: dict, loose: dict, role_drop: int = 0,
              manual=None) -> tuple[bool, bool, str]:
    """严格 / 宽松两口径的集合关系判定。

    纯函数，不进界面就能自检（见 build/_selftest_reach.py 的用法）。
    返回 (ok_subset, ok_only_role, msg)：
      ok_subset   —— 严格 ⊆ 宽松、宽松确实多出一批、且口径差 == 集合差；
      ok_only_role—— 多出来的每一间都是「名字带角色后缀」或「手动排除」的房间，
                     且数量不超过角色剔除数（防止哪天把条件房间也放开了）。
    """
    sn = _upper_names(strict.get("names"))
    ln = _upper_names(loose.get("names"))
    manual = {str(n).upper() for n in (manual or ())}
    st, lt = strict.get("total"), loose.get("total")
    lost, gain = sn - ln, ln - sn
    notes = []

    ok_subset = True
    if not sn or not ln:
        ok_subset = False
        notes.append("names 为空（roomSets 没返回房间清单）")
    else:
        if lost:
            ok_subset = False
            notes.append("宽松口径下丢了 %d 间：%s" % (len(lost), sorted(lost)[:5]))
        if not gain:
            ok_subset = False
            notes.append("宽松没有比严格多出任何房间")
        if st != len(sn):
            ok_subset = False
            notes.append("严格 total=%r 与 names 长度 %d 不一致" % (st, len(sn)))
        if lt != len(ln):
            ok_subset = False
            notes.append("宽松 total=%r 与 names 长度 %d 不一致" % (lt, len(ln)))
        if (lt or 0) - (st or 0) != len(gain):
            ok_subset = False
            notes.append("口径差 %d ≠ 集合差 %d" % ((lt or 0) - (st or 0), len(gain)))

    ok_only_role = True
    stray = [n for n in gain if not any(h in n for h in ROLE_HINT) and n not in manual]
    if stray:
        ok_only_role = False
        notes.append("多出的房间里有 %d 间既非角色专属也非手动：%s"
                     % (len(stray), sorted(stray)[:5]))
    # 关键咬合点：条件房间（EXCLUSIVEROOM/HIDEROOM）不受口径门控，两种口径剔除数必须一致。
    # 若有人给 exclusiveOut/hidden 加上 strict 门控，宽松会多放出一整批条件房间，这里变红。
    sc, lc = strict.get("condDrop"), loose.get("condDrop")
    if sc != lc:
        ok_only_role = False
        notes.append("条件房间剔除数不一致：严格 %r vs 宽松 %r（口径不该影响条件房间）" % (sc, lc))
    if role_drop and len(gain) > role_drop:
        ok_only_role = False
        notes.append("多出 %d 间 > 角色剔除 %d 间（宽松不该放开这么多）"
                     % (len(gain), role_drop))

    msg = "严格 %s → 宽松 %s；多出 %d 间%s" % (
        st, lt, len(gain), ("：" + ", ".join(sorted(gain)[:6])) if gain else "")
    if notes:
        msg += " ｜ " + "; ".join(notes)
    return ok_subset, ok_only_role, msg



def main() -> int:
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window(TITLE, html=html, js_api=api,
                                   width=1400, height=900, hidden=False)
    api.attach(window)

    out: dict = {"errors": []}
    results: list[tuple[bool, str, str]] = []
    cfg_backup = None
    if os.path.exists(CFG):
        with open(CFG, "rb") as fh:
            cfg_backup = fh.read()

    def js(script, default=None):
        try:
            return window.evaluate_js(script)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"{script[:50]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def check(ok, label, detail=""):
        results.append((bool(ok), label, str(detail)))
        print(("  ✅ " if ok else "  ❌ ") + label + (" — " + str(detail) if detail else ""))

    def sets(code, cat=None):
        arg = ("'%s'" % cat) if cat else "null"
        return loads(js("JSON.stringify(window.__rwTest.roomSets('%s', %s))" % (code, arg))) or {}

    def worker():
        time.sleep(2.5)
        try:
            for _ in range(40):
                if js("document.querySelectorAll('#slot-list .slot').length > 0"):
                    break
                time.sleep(0.4)
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(80):
                time.sleep(0.5)
                if js("window.__rwTest.ready() && document.querySelectorAll('#camplist .camp').length > 0"):
                    break
            time.sleep(0.8)
            js("[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0].click();")
            time.sleep(1.2)

            mine = sets("RF", "White")
            out["white"] = {k: v for k, v in mine.items() if k != "names"}
            check((mine.get("roleDrop") or 0) >= 10,
                  "白猫看 RF：角色专属房间被剔出分母",
                  str(out["white"]))
            check(not any("SAINT" in str(n).upper() for n in (mine.get("names") or [])),
                  "剔掉后清单里没有 RF_SAINT*",
                  str([n for n in (mine.get("names") or []) if "SAINT" in str(n).upper()][:3]))

            saint = sets("RF", "Saint")
            out["saint"] = {k: v for k, v in saint.items() if k != "names"}
            check((saint.get("roleDrop") or 0) == 0,
                  "圣徒看 RF：这些房间本来就是它的，不按角色剔除",
                  str(out["saint"]))

            before = mine.get("total")

            js("window.__rwTest.setStrict(false);")
            time.sleep(0.8)
            loose = sets("RF", "White")
            out["loose"] = {k: v for k, v in loose.items() if k != "names"}
            out["loose"]["gain"] = sorted(_upper_names(loose.get("names"))
                                          - _upper_names(mine.get("names")))
            ok_subset, ok_only_role, msg = _loose_ok(mine, loose, mine.get("roleDrop") or 0)
            # 注意：宽松 ≠ 全部房间。条件房间（EXCLUSIVEROOM/HIDEROOM）不受口径门控，
            # 所以这里不能断言"回到全部房间"，只能断言集合关系与"只放开角色/手动剔除"。
            check(loose.get("strict") is False and (loose.get("roleDrop") or 0) == 0 and ok_subset,
                  "切「宽松」后不再按角色剔除，且严格口径的房间一个不丢",
                  msg)
            check(ok_only_role,
                  "宽松多出的房间只由角色专属房间构成（条件房间仍剔除）",
                  msg)
            js("window.__rwTest.setStrict(true);")
            time.sleep(0.8)

            # 配置持久化：必须点真实按钮（才会走 save_config），再从磁盘读回。
            # __rwTest.setStrict 只改内存、不落盘，单靠它测不出 B-01 那类白名单裁剪缺陷。
            # 注意：口径按钮只长在「区域」页的排序栏里，必须先把页签切过去。
            js("var t=[].slice.call(document.querySelectorAll('#tabs .tab')).filter("
               "function(e){return /区域/.test(e.textContent);})[0]; if(t) t.click();")
            time.sleep(1.2)
            check(js("!!document.getElementById('reach-mode')") is True,
                  "切到「区域」页后口径按钮存在",
                  "（页面不在区域页时按钮不存在，后续点击会静默失效）")

            js("var b=document.getElementById('reach-mode'); if(b) b.click();")
            time.sleep(1.6)
            disk = (json.load(open(CFG, encoding="utf-8")).get("ui") or {})
            check(disk.get("roomStrict") is False,
                  "点按钮切「宽松」后 roomStrict=false 落到 config.json",
                  "roomStrict=%r" % (disk.get("roomStrict"),))
            js("var b=document.getElementById('reach-mode'); if(b) b.click();")
            time.sleep(1.6)
            disk = (json.load(open(CFG, encoding="utf-8")).get("ui") or {})
            check(disk.get("roomStrict") is True,
                  "再点一次切回「严格」后 roomStrict=true 落到 config.json",
                  "roomStrict=%r" % (disk.get("roomStrict"),))
            restored = sets("RF", "White")
            check(restored.get("strict") is True and (restored.get("total") or 0) == (before or 0),
                  "持久化往返后分母回到严格口径", str(restored.get("total")))

            js("window.__rwTest.exclude('RF', 'RF_B10', true);")
            time.sleep(0.9)
            man = sets("RF", "White")
            out["manual"] = {k: v for k, v in man.items() if k != "names"}
            check((man.get("manualDrop") or 0) == 1 and (man.get("total") or 0) == (before or 0) - 1,
                  "手动标记「不可达」后分母 −1", str(out["manual"]))
            cfg_now = json.load(open(CFG, encoding="utf-8"))
            saved = cfg_now.get("ui", {}).get("roomExcluded", {})
            check(saved.get("SURVIVOR", {}).get("RF") == ["RF_B10"],
                  "手动排除写进了 config.ui.roomExcluded", str(saved)[:80])

            js("window.__rwTest.exclude('RF', 'RF_B10', false);")
            time.sleep(0.9)
            back = sets("RF", "White")
            out["back"] = {k: v for k, v in back.items() if k != "names"}
            check((back.get("manualDrop") or 0) == 0 and back.get("total") == before,
                  "撤销后恢复原分母", str(out["back"]))
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"worker: {exc}")
        finally:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass

    import threading
    threading.Thread(target=worker, daemon=True).start()
    webview.start()

    if cfg_backup is not None:
        with open(CFG, "wb") as fh:
            fh.write(cfg_backup)

    ok = sum(1 for r in results if r[0])
    print("\n合计 %d 项，失败 %d 项" % (len(results), len(results) - ok))
    for flag, label, detail in results:
        if not flag:
            print("  ❌", label, detail)
    out["results"] = [{"ok": f, "label": l, "detail": d} for f, l, d in results]
    with open(os.path.join(SHOTS, "reach_last.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0 if ok == len(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
