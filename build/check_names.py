"""区域名回退与「自定义译名」覆盖模组区域的回归检查（真实 WebView2，隐藏窗口）。

用法： .venv/Scripts/python.exe build/check_names.py

检查内容：
    1. 全局解锁页：不在对照表里的区域显示「区域原名 + 缩写」，不再只有裸代码
    2. 全局解锁页不再有「琥珀色 = …保留原始代码：…」那段说明
    3. 自定义译名 → 区域：模组区域（如 Z1）能被搜到、能加译名
    4. 搜索过滤后保存，不会把没显示出来的其它译名一起删掉（整表合并）
    5. 存完译名后，全局解锁页立刻显示新中文名
产物： docs/names_last.json（原始读数，排查用）
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 回归产物统一放 build/_shots，不污染 docs（docs 只放被文档引用的图）
SHOTS = os.path.join(ROOT, "build", "_shots")
os.makedirs(SHOTS, exist_ok=True)
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core import paths  # noqa: E402
from core.bridge import Api  # noqa: E402

TR_FILE = os.path.join(paths.data_dir(), "_translations.json")
TEST_NAME = "测试译名勿留"


def read_tr() -> str:
    try:
        with open(TR_FILE, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def restore_tr(snapshot: str) -> None:
    try:
        if snapshot:
            with open(TR_FILE, "w", encoding="utf-8") as fh:
                fh.write(snapshot)
        elif os.path.isfile(TR_FILE):
            os.remove(TR_FILE)
    except OSError:
        pass


def region_count(raw: str) -> int:
    try:
        data = json.loads(raw or "{}")
        return len(data.get("regions") or {})
    except ValueError:
        return 0


def main() -> int:
    snapshot = read_tr()
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool 区域名检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out: dict = {"errors": []}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"{code[:60]}: {exc}")
            return default

    def loads(raw):
        try:
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    results: list[tuple[bool, str, str]] = []

    def check(name, cond, detail=""):
        results.append((bool(cond), name, detail))

    def worker():
        time.sleep(2.5)
        try:
            js("var b=document.querySelector('#slot-list .slot'); if(b) b.click();")
            for _ in range(60):
                time.sleep(0.5)
                if js("window.__rwTest.ready()"):
                    break
            time.sleep(1.0)

            # 选中一个角色 → 全局解锁页
            js("[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0].click();")
            time.sleep(0.6)
            js("var t=document.querySelector('[data-tab=\"global\"]'); if(t) t.click();")
            time.sleep(1.2)

            chips = loads(js(
                "JSON.stringify([].slice.call(document.querySelectorAll('#detail-body .chips .chip'))"
                ".map(function(c){return {text:c.textContent.replace(/\\s+/g,' ').trim().replace(/\\s+\\d+$/,''),"
                "code:c.getAttribute('data-code')||'', tip:c.getAttribute('data-tip')||'',"
                " unrec:c.classList.contains('unrec')};}))"
            )) or []
            out["chips"] = chips
            named = [c for c in chips if "区域原名" in (c.get("tip") or "")]
            unknown = [c for c in chips if (c.get("tip") or "").startswith("缩写 ")]
            bare_ok = all(c.get("unrec") for c in unknown) and all(
                (c.get("text") or "").strip() == (c.get("code") or "") for c in unknown)
            body_note = js(
                "(function(){var b=document.getElementById('detail-body');"
                "return b? b.textContent.indexOf('琥珀色') : -1;})()"
            )

            check("全局解锁页有庇护所区域chip", len(chips) > 0, f"{len(chips)} 个")
            check("每个chip都带来源提示", all(c.get("tip") for c in chips),
                  str([c.get("text") for c in chips if not c.get("tip")][:3]))
            check("不在对照表的区域显示「原名 + 缩写」", len(named) > 0,
                  f"{len(named)} 个：{[c.get('text') for c in named][:4]}")
            check("只有真的查不到名字时才只剩代码（且标琥珀色）", bare_ok,
                  str([c.get("code") for c in unknown][:6]))
            check("「琥珀色 = …保留原始代码」那段说明已去掉", body_note == -1,
                  f"index={body_note}")

            # 用「连名字都没有」的那个区域做译名测试：这正是用户遇到的 Z1 那类
            target = unknown[0] if unknown else (named[0] if named else None)
            code = (target or {}).get("code") or ""
            out["target"] = {"code": code, "text": (target or {}).get("text"),
                             "tip": (target or {}).get("tip")}
            check("找到一个可测的模组区域", bool(code), str(out["target"]))

            before_n = region_count(read_tr())
            out["trBefore"] = before_n

            js("document.getElementById('btn-translations').click();")
            time.sleep(0.6)
            js("var b=document.querySelector('[data-trkind=\"regions\"]'); if(b) b.click();")
            time.sleep(0.6)
            out["trRowsAll"] = js("document.querySelectorAll('#modal-body [data-tr]').length")

            # 搜索该代码
            js("(function(){var s=document.getElementById('tr-search');"
               "s.value='%s';s.dispatchEvent(new Event('input',{bubbles:true}));})()" % code.lower())
            time.sleep(0.7)
            row = loads(js(
                "JSON.stringify((function(){var r=document.querySelector('#modal-body [data-tr=\"%s\"]');"
                "if(!r) return {found:false};"
                "var rowEl=r.closest('.tr-row');"
                "return {found:true, en:(rowEl.querySelector('.tr-en')||{}).textContent||'',"
                "rows:document.querySelectorAll('#modal-body [data-tr]').length};})())" % code
            )) or {}
            out["row"] = row
            check("模组区域能在译名列表里搜到", row.get("found"), f"code={code} {row}")
            # 再搜一个「导入过数据、但没内置译名」的区域，确认那一行带原名
            named_code = (named[0].get("code") if named else "")
            out["namedRow"] = {}
            if named_code:
                js("(function(){var s=document.getElementById('tr-search');"
                   "s.value='%s';s.dispatchEvent(new Event('input',{bubbles:true}));})()" % named_code.lower())
                time.sleep(0.7)
                out["namedRow"] = loads(js(
                    "JSON.stringify((function(){var r=document.querySelector('#modal-body [data-tr=\"%s\"]');"
                    "if(!r) return {found:false};"
                    "return {found:true, en:(r.closest('.tr-row').querySelector('.tr-en')||{}).textContent||''};})())"
                    % named_code
                )) or {}
            check("导入过数据的区域在列表里带原名",
                  bool(named_code) and bool((out["namedRow"].get("en") or "").strip()),
                  f"code={named_code} en={out['namedRow'].get('en')}")
            check("搜索会过滤列表", (row.get("rows") or 0) >= 1 and (row.get("rows") or 0) < (out.get("trRowsAll") or 0),
                  f"{row.get('rows')} < {out.get('trRowsAll')}")

            # 写入测试译名并保存（先把搜索改回目标区域，否则那一行不在 DOM 里）
            js("(function(){var s=document.getElementById('tr-search');"
               "s.value='%s';s.dispatchEvent(new Event('input',{bubbles:true}));})()" % code.lower())
            time.sleep(0.7)
            js("(function(){var r=document.querySelector('#modal-body [data-tr=\"%s\"]');"
               "r.value='%s';})()" % (code, TEST_NAME))
            js("document.getElementById('tr-save').click();")
            time.sleep(1.4)
            after_raw = read_tr()
            out["trAfter"] = region_count(after_raw)
            check("保存后译名文件里有这条", TEST_NAME in after_raw, f"regions={out['trAfter']}")
            check("搜索过滤下保存不会丢掉其它译名", out["trAfter"] >= before_n + 1,
                  f"保存前 {before_n} 条 → 保存后 {out['trAfter']} 条")

            # 关弹窗看全局解锁页是否立刻用新名字
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(1.0)
            js("var t=document.querySelector('[data-tab=\"global\"]'); if(t) t.click();")
            time.sleep(1.0)
            refreshed = loads(js(
                "JSON.stringify([].slice.call(document.querySelectorAll('#detail-body .chips .chip'))"
                ".map(function(c){return c.textContent.replace(/\\s+/g,' ').trim();}))"
            )) or []
            out["chipsAfter"] = refreshed
            check("全局解锁页立刻显示新中文名",
                  any(TEST_NAME in t for t in refreshed), str(refreshed[:3]))

            # ---------------- 批量翻译（11-06：取代了「恢复本类默认」） ----------------
            js("document.getElementById('btn-translations').click();")
            time.sleep(0.7)
            out["trButtons"] = {"bulk": js("!!document.getElementById('tr-bulk-open')"),
                                "reset": js("!!document.getElementById('tr-reset')")}
            check("「批量翻译」取代了「恢复本类默认」",
                  out["trButtons"]["bulk"] is True and out["trButtons"]["reset"] is False,
                  str(out["trButtons"]))

            js("var b=document.querySelector('[data-trkind=\"regions\"]'); if(b) b.click();")
            time.sleep(0.5)
            js("document.getElementById('tr-bulk-open').click();")
            time.sleep(0.5)
            check("点「批量翻译」进入粘贴面板", js("!!document.getElementById('tr-bulk')") is True, "")

            # 注释 / 空行 / 空中文都要跳过；代码与英文名混写都要命中；跨分类要生效
            table = ("//注释行\n#另一种注释\n\nRF|珊瑚洞窟Z\nBig Eel|大鳗Z\n"
                     "Survivor|生还者Z\nNoSuchRegion|随便\nBlank|   \n")
            js("var t=document.getElementById('tr-bulk'); t.value=%s;"
               "t.dispatchEvent(new Event('input',{bubbles:true}));"
               % json.dumps(table, ensure_ascii=False))
            time.sleep(0.9)
            out["bulkNote"] = js("(document.getElementById('tr-bulk-note')||{}).textContent")
            check("批量解析：命中 3（区域/生物/通行证各一）· 未匹配 1 · 跳过 1",
                  "命中 3 条" in (out["bulkNote"] or "")
                  and "未匹配 1" in (out["bulkNote"] or "")
                  and "跳过 1" in (out["bulkNote"] or ""), str(out["bulkNote"]))
            check("跨分类命中体现在统计里（区域/生物/通行证）",
                  all(k in (out["bulkNote"] or "") for k in ("区域 1", "生物 1", "通行证 1")),
                  str(out["bulkNote"]))

            # 与内置译名完全相同的表 → 一条都不该写
            rmap_path = os.path.join(ROOT, "data", "region_map.json")
            rf_zh = ""
            try:
                with open(rmap_path, encoding="utf-8") as fh:
                    rf_zh = next((e["zh"] for e in json.load(fh).get("entries", [])
                                  if e.get("abbr") == "RF"), "")
            except (OSError, ValueError):
                rf_zh = ""
            if rf_zh:
                js("var t=document.getElementById('tr-bulk'); t.value='RF|%s';"
                   "t.dispatchEvent(new Event('input',{bubbles:true}));" % rf_zh)
                time.sleep(0.9)
                out["bulkSame"] = {
                    "note": js("(document.getElementById('tr-bulk-note')||{}).textContent"),
                    "text": js("(document.getElementById('tr-bulk-apply')||{}).textContent"),
                    "disabled": js("(document.getElementById('tr-bulk-apply')||{}).disabled"),
                }
                check("与内置相同的条目：提示「不会写入」且应用按钮禁用",
                      "与内置相同" in (out["bulkSame"]["note"] or "")
                      and out["bulkSame"]["disabled"] is True, str(out["bulkSame"]))

            # 真正写入：连点两次（应用 → 确认写入）
            js("var t=document.getElementById('tr-bulk'); t.value=%s;"
               "t.dispatchEvent(new Event('input',{bubbles:true}));"
               % json.dumps(table, ensure_ascii=False))
            time.sleep(0.9)
            js("document.getElementById('tr-bulk-apply').click();")
            time.sleep(0.4)
            out["bulkArmed"] = js("(document.getElementById('tr-bulk-apply')||{}).textContent")
            check("第一次点「应用」只是二次确认，还没落盘",
                  "确认写入" in (out["bulkArmed"] or "")
                  and "珊瑚洞窟Z" not in read_tr(), str(out["bulkArmed"]))

            js("document.getElementById('tr-bulk-apply').click();")
            time.sleep(2.0)
            raw = read_tr()
            out["bulkWritten"] = {
                "regions": "珊瑚洞窟Z" in raw,
                "creatures": "大鳗Z" in raw,
                "passages": "生还者Z" in raw,
                "backToList": js("!!document.getElementById('tr-save')"),
            }
            check("确认后一次写入多个分类（区域/生物/通行证），并回到列表",
                  all(out["bulkWritten"][k] for k in ("regions", "creatures", "passages"))
                  and out["bulkWritten"]["backToList"] is True, str(out["bulkWritten"]))
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"worker: {exc}")
            out["trace"] = repr(exc)
        finally:
            restore_tr(snapshot)
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass

    import threading
    threading.Thread(target=worker, daemon=True).start()
    webview.start()

    print("\n===== 结果 =====")
    bad = 0
    for ok, name, detail in results:
        print(("  ✅ " if ok else "  ❌ ") + name + (" — " + detail if detail else ""))
        if not ok:
            bad += 1
    if out["errors"]:
        print("\n--- 脚本告警 ---")
        for e in out["errors"][:6]:
            print(" ", e)
    print(f"\n合计 {len(results)} 项，失败 {bad} 项")
    with open(os.path.join(SHOTS, "names_last.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0 if bad == 0 and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
