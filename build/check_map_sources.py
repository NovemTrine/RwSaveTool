"""№7 地图页来源开关 + 减少闪烁 的回归。

用法：
    .venv/Scripts/python.exe build/check_map_sources.py

三块判据：

A. **缓存键只认房间表**（减少闪烁的关键）
   `_regmap_key` 不再含 `flt.off`，而是含 `flt.sig`（房间表指纹）：
   * 两个来源组合导出的房间表相同 → 键相同（切来源能直接吃布局缓存）；
   * 房间表不同 → 键不同（该重排就重排，不许复用错图）。

B. **等价来源切换真的命中缓存**
   把「熄掉模组重复层」前后的 `regmap_map` 各跑一次：第二次必须 `cached=True`
   且节点名逐一如旧。

C. **地图页顶的来源条**（真实 WebView）
   * `#map-src-bar` 有 chips，亮/灭与后端 `enabled` 一致；
   * 点一下能在图上生效：关掉一个带独有房间的来源 → 图上少房间；
     再点回来 → 房间数复原；
   * 双缓冲 CSS 生效（`svg.geo-svg` 是绝对定位、有 opacity 过渡），
     且静止时舞台上只有一版 SVG。

测试会改 `_sources.json`，脚本末尾**按原字节还原**（含 userSet 这类副作用）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS: list[str] = []
PASS = 0


def check(ok, msg: str, detail: str = "") -> None:
    global PASS
    if ok:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAILS.append(msg)
        print(f"  ❌ {msg}" + (f"  ← {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# A / B：纯逻辑
# ---------------------------------------------------------------------------

def logic_part() -> None:
    from core import bridge, paths, region_store, sources

    print("\n[A] 缓存键只认房间表")
    f_same_a = {"off": ["mod:x"], "role": "White", "strict": True, "ex": [], "sig": "abc"}
    f_same_b = {"off": ["mod:x", "mod:y"], "role": "White", "strict": True, "ex": [], "sig": "abc"}
    f_diff = {"off": ["mod:x"], "role": "White", "strict": True, "ex": [], "sig": "zzz"}

    k = lambda flt: bridge._regmap_key("CC", "White", {"flt": flt})       # noqa: E731
    check(k(f_same_a) == k(f_same_b), "off 不同但房间表相同时，缓存键相同")
    check(k(f_same_a) != k(f_diff), "房间表不同则缓存键不同")

    # 指纹本身：等价层开关前后必须一致
    regions = region_store.all_regions()
    if not regions:
        print("  没有 region_data，跳过。")
        return

    saved_map, saved_reg = sources.enabled_map, sources.registry_enabled

    def with_disabled(source_id):
        def em():
            m = dict(saved_map())
            m[source_id] = False
            return m

        def rg():
            d = {k2: dict(v) for k2, v in saved_reg().items()}
            if source_id in d:
                d[source_id]["enabled"] = False
            return d

        return em, rg

    try:
        # 找一对「模组层是官方层的重复」的区域来验
        sample = "CC" if "CC" in regions else sorted(regions)[0]
        base_sig = bridge._room_set_sig(sample)
        check(bool(base_sig), f"{sample} 算得出房间表指纹", base_sig)

        sources.enabled_map, sources.registry_enabled = with_disabled("mod:moreslugcats")
        dup_sig = bridge._room_set_sig(sample)
        check(dup_sig == base_sig,
              "熄掉 MSE 模组层后指纹不变（内容重复，不该重排）", f"{base_sig} vs {dup_sig}")
    finally:
        sources.enabled_map, sources.registry_enabled = saved_map, saved_reg

    print("\n[B] 等价来源切换命中缓存")
    from core.bridge import Api

    api = Api()
    flt_all = bridge._regmap_filters(sample, "White")
    t0 = time.time()
    r1 = api.regmap_map(sample, "White", {"flt": dict(flt_all, off=[])})
    t1 = time.time() - t0
    r2 = api.regmap_map(sample, "White", {"flt": dict(flt_all, off=["mod:moreslugcats"])})
    names1 = [n["name"] for n in r1.get("nodes") or []]
    names2 = [n["name"] for n in r2.get("nodes") or []]
    check(r1.get("ok") and r2.get("ok"), f"{sample} 两次都能出图", str(r1.get("error") or r2.get("error")))
    check(r2.get("cached") is True, "第二次（只换了 off）命中布局缓存",
          f"cached={r2.get('cached')}")
    check(names1 == names2, "两次的房间完全一致", f"{len(names1)} vs {len(names2)}")
    print(f"  · 首次 {t1*1000:.0f} ms")

    # 真的换了房间表时必须重算
    unique_mod = ""
    for layer in (regions[sample].get("layers") or []):
        lid = str(layer.get("id") or "")
        if lid.startswith("mod:") and layer.get("roomCount") and lid != "mod:moreslugcats":
            if lid in ("mod:watcher",):
                continue
            unique_mod = lid
            break
    if unique_mod:
        sig_before = bridge._room_set_sig(sample)
        sources.enabled_map, sources.registry_enabled = with_disabled(unique_mod)
        try:
            sig_after = bridge._room_set_sig(sample)
            check(sig_after != sig_before,
                  f"熄掉 {unique_mod}（有独有房间）后指纹改变", f"{sig_before} vs {sig_after}")
            r3 = api.regmap_map(sample, "White")
            check(r3.get("cached") is False, "房间表变了就必须重算（不允许复用）",
                  f"cached={r3.get('cached')}")
        finally:
            sources.enabled_map, sources.registry_enabled = saved_map, saved_reg
    else:
        print("  · 该区没有「带独有房间的模组层」，跳过此项")

    _ = paths  # 保持导入（下面 UI 段用到路径）


# ---------------------------------------------------------------------------
# C：真实 WebView
# ---------------------------------------------------------------------------

def ui_part() -> None:
    import webview

    from core import paths, sources
    from core.bridge import Api

    reg_file = os.path.join(paths.data_dir(), sources.REGISTRY_FILE)
    backup = reg_file + ".bak_mapsrc"
    existed = os.path.isfile(reg_file)
    if existed:
        shutil.copy2(reg_file, backup)

    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()
    window = webview.create_window("RwSaveTool 来源开关检查", html=html, js_api=api,
                                   width=1500, height=940, hidden=True)
    api.attach(window)
    out: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out.setdefault("errors", []).append(f"{code[:60]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def worker():
        time.sleep(2.5)
        try:
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(60):
                time.sleep(0.5)
                if js("window.__rwTest && window.__rwTest.ready()"):
                    break
            time.sleep(1.0)

            out["open"] = js("window.__rwTest.map('CC'); true")
            for _ in range(60):
                time.sleep(0.5)
                if js("!!document.querySelector('#geo-stage svg.geo-svg')"):
                    break
            time.sleep(1.2)

            out["bar"] = loads(js(
                "JSON.stringify((function(){"
                "var bar=document.getElementById('map-src-bar');"
                "if(!bar) return {found:false};"
                "var chips=[].slice.call(bar.querySelectorAll('[data-msrc]'));"
                "return {found:true, n:chips.length,"
                " on:chips.filter(function(c){return c.classList.contains('on');}).length,"
                " names:chips.map(function(c){return c.getAttribute('data-msrc');}),"
                " top: bar.parentNode === document.querySelector('.map-main') &&"
                "      bar === document.querySelector('.map-main').firstElementChild};})())"
            )) or {}

            out["css"] = loads(js(
                "JSON.stringify((function(){"
                "var s=document.querySelector('#geo-stage svg.geo-svg');"
                "if(!s) return {found:false};"
                "var cs=getComputedStyle(s);"
                "return {found:true, pos:cs.position, trans:cs.transitionDuration,"
                " svgs:document.querySelectorAll('#geo-stage svg.geo-svg').length};})())"
            )) or {}

            out["before"] = loads(js(
                "JSON.stringify({meta:(document.getElementById('geo-meta')||{}).textContent||'',"
                " list:(document.getElementById('map-list')||{}).textContent.length||0})"
            )) or {}

            # 找一个「点亮且有独有房间」的模组来源来关
            target = ""
            for lid in (out["bar"].get("names") or []):
                if str(lid).startswith("mod:") and lid not in ("mod:moreslugcats", "mod:watcher"):
                    target = lid
                    break
            out["target"] = target
            if target:
                js("(function(){var b=document.querySelector('#map-src-bar [data-msrc=\"%s\"]');"
                   "if(b) b.click();})()" % target)
                for _ in range(60):
                    time.sleep(0.4)
                    if not js("(function(){var n=document.getElementById('map-src-note');"
                              "return !!(n && n.classList.contains('busy'));})()"):
                        break
                time.sleep(1.0)          # 等交叉淡入收尾 + 旧图摘除
                out["afterOff"] = loads(js(
                    "JSON.stringify({svgs:document.querySelectorAll('#geo-stage svg.geo-svg').length,"
                    " on:(function(){var b=document.querySelector('#map-src-bar [data-msrc=\"%s\"]');"
                    "return b? b.classList.contains('on') : null;})(),"
                    " meta:(document.getElementById('geo-meta')||{}).textContent||''})"
                    % target
                )) or {}
                out["enabledAfterOff"] = sources.enabled_map().get(target)

                # 点回来
                js("(function(){var b=document.querySelector('#map-src-bar [data-msrc=\"%s\"]');"
                   "if(b) b.click();})()" % target)
                for _ in range(60):
                    time.sleep(0.4)
                    if not js("(function(){var n=document.getElementById('map-src-note');"
                              "return !!(n && n.classList.contains('busy'));})()"):
                        break
                time.sleep(1.2)
                out["afterOn"] = loads(js(
                    "JSON.stringify({svgs:document.querySelectorAll('#geo-stage svg.geo-svg').length,"
                    " on:(function(){var b=document.querySelector('#map-src-bar [data-msrc=\"%s\"]');"
                    "return b? b.classList.contains('on') : null;})(),"
                    " meta:(document.getElementById('geo-meta')||{}).textContent||''})"
                    % target
                )) or {}
                out["enabledAfterOn"] = sources.enabled_map().get(target)
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = repr(exc)
        finally:
            window.destroy()

    webview.start(worker, debug=False, private_mode=False)

    restored = True
    try:
        if existed and os.path.isfile(backup):
            with open(backup, "rb") as fh:
                want = fh.read()
            os.replace(backup, reg_file)
            with open(reg_file, "rb") as fh:
                restored = fh.read() == want
        elif os.path.isfile(backup):
            os.remove(backup)
    finally:
        from core import sources as _s
        _s.invalidate_duplicates()

    bar = out.get("bar") or {}
    css = out.get("css") or {}
    off = out.get("afterOff") or {}
    on = out.get("afterOn") or {}
    before = out.get("before") or {}

    print("\n[C] 地图页顶的来源条")
    if out.get("errors"):
        print(f"  · JS 报错 {len(out['errors'])} 条：{out['errors'][:2]}")
    check(not out.get("fatal"), "开图没炸", str(out.get("fatal")))
    check(bar.get("found"), "地图页有 #map-src-bar")
    check(bar.get("top"), "来源条在 .map-main 的第一个位置（最顶端）")
    check((bar.get("n") or 0) >= 2, f"来源条有 {bar.get('n')} 个 chip")
    check((bar.get("on") or 0) >= 1, f"其中 {bar.get('on')} 个是点亮态")

    print("\n[C2] 双缓冲")
    check(css.get("pos") == "absolute", "svg.geo-svg 是绝对定位（两版能叠着）", str(css.get("pos")))
    check((css.get("trans") or "0s") != "0s", "svg.geo-svg 有 opacity 过渡", str(css.get("trans")))
    check(css.get("svgs") == 1, "静止时舞台只有一版 SVG", str(css.get("svgs")))

    check(restored, "测完把 `_sources.json` 按原字节还原（不留 userSet 残渣）")

    print("\n[C3] 点一下就地切换")
    target = out.get("target") or ""
    if not target:
        print("  · 没有可切的模组来源，跳过")
        return
    print(f"  · 目标来源：{target}")
    check(off.get("on") is False, "点一下后该 chip 灭掉", str(off.get("on")))
    check(out.get("enabledAfterOff") is False, "后端也认为它熄灭了（已落盘）",
          str(out.get("enabledAfterOff")))
    check("间" in (off.get("meta") or ""), "图重新出好了（meta 里有房间数）", off.get("meta"))
    check((off.get("meta") or "") != (before.get("meta") or ""),
          "房间数确实变了", f"{before.get('meta')} → {off.get('meta')}")
    check(off.get("svgs") == 1, "切完只留一版 SVG（旧图已摘）", str(off.get("svgs")))

    check(on.get("on") is True, "再点一下恢复点亮", str(on.get("on")))
    check(out.get("enabledAfterOn") is True, "后端也恢复点亮", str(out.get("enabledAfterOn")))
    check((on.get("meta") or "") == (before.get("meta") or ""),
          "房间数回到原来", f"{before.get('meta')} vs {on.get('meta')}")


def main() -> int:
    logic_part()
    ui_part()

    print()
    if FAILS:
        print(f"FAIL：{len(FAILS)} 项")
        for item in FAILS:
            print(f"  - {item}")
        return 1
    print(f"CHECK MAP SOURCES OK（{PASS} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
