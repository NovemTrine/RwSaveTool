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

            # 选中一个角色 → 统计页
            # v1.3.2：收集页已整页下线（代币 / 珍珠 / 回响 / 广播全删），只剩「各战役统计」。
            # 这一组改为看表里的角色名是否带中文译名 —— 同样走 `slugZh()` 那条链。
            js("[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0].click();")
            time.sleep(0.6)
            js("var t=document.querySelector('[data-tab=\"stats\"]'); if(t) t.click();")
            time.sleep(1.0)

            rows = loads(js(
                "JSON.stringify([].slice.call(document.querySelectorAll('#detail-body tbody tr'))"
                ".map(function(tr){var c0=tr.cells[0];"
                "var sp=c0?c0.querySelector('span'):null;"
                "return {name:c0?c0.textContent.replace(/\\s+/g,' ').trim():'',"
                "zh:sp?sp.textContent.trim():''};}))"
            )) or []
            out["statsRows"] = rows

            check("统计页有战役行", len(rows) > 0, f"{len(rows)} 行")
            check("战役名带中文译名", any(r.get("zh") for r in rows),
                  str([r.get("name") for r in rows][:4]))
            check("「琥珀色 = …保留原始代码」那段说明已随庇护所 chips 下线",
                  js("(function(){var b=document.getElementById('detail-body');"
                     "return b? b.textContent.indexOf('琥珀色') : -1;})()") == -1, "")

            # 用「有数据、但内置对照表里没有」的区域做译名测试：正是用户遇到的 Z1 那类。
            # v1.3.2：不再从庇护所 chips 里挑（那段已下线），直接问页面要一个这样的代码。
            code = js("window.__rwTest.modRegionCode()") or ""
            out["target"] = {"code": code}
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
            named_code = code   # 同一个区：它的 rows 里应该带区域原名（displayName）
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

            # 关弹窗，确认改名立刻生效（问页面要这个区域当前的显示名；
            # v1.3.2 起不再依赖已下线的庇护所 chips）
            js("var b=document.getElementById('modal-close'); if(b) b.click();")
            time.sleep(1.0)
            label_after = js("window.__rwTest.regionLabelOf('%s')" % code) or ""
            out["labelAfter"] = label_after
            check("改名后该区域立刻显示新中文名", TEST_NAME in label_after, str(label_after))

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

            def set_bulk(text, expect):
                """粘贴表格，等解析结果里出现 expect 再返回。

                直接赋值 + dispatch('input') 有竞态：面板刚重建时监听还没挂上，事件会被
                吞掉（实测偶发「解析 0 行」）。所以按「期望内容」重试，而不是按「有内容」。
                """
                note = ""
                for _ in range(6):
                    js("var t=document.getElementById('tr-bulk'); t.value=%s;"
                       "t.dispatchEvent(new Event('input',{bubbles:true}));"
                       % json.dumps(text, ensure_ascii=False))
                    for _ in range(12):
                        time.sleep(0.15)
                        note = js("(document.getElementById('tr-bulk-note')||{}).textContent") or ""
                        if expect in note:
                            return note
                return note

            # 注释 / 空行 / 空中文都要跳过；代码与英文名混写都要命中；跨分类要生效
            # v1.3.2：「通行证」分类随 №4 下线，这里换成「角色」——仍然要跨分类命中
            table = ("//注释行\n#另一种注释\n\nRF|珊瑚洞窟Z\nBig Eel|大鳗Z\n"
                     "Gourmand|美食家Z\nNoSuchRegion|随便\nBlank|   \n")
            out["bulkNote"] = set_bulk(table, "命中 3 条")
            check("批量解析：命中 3（区域/生物/角色各一）· 未匹配 1 · 跳过 1",
                  "命中 3 条" in (out["bulkNote"] or "")
                  and "未匹配 1" in (out["bulkNote"] or "")
                  and "跳过 1" in (out["bulkNote"] or ""), str(out["bulkNote"]))
            check("跨分类命中体现在统计里（区域/生物/角色）",
                  all(k in (out["bulkNote"] or "") for k in ("区域 1", "生物 1", "角色 1")),
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
                set_bulk("RF|%s" % rf_zh, "不会写入")
                time.sleep(0.3)
                out["bulkSame"] = {
                    "note": js("(document.getElementById('tr-bulk-note')||{}).textContent"),
                    "text": js("(document.getElementById('tr-bulk-apply')||{}).textContent"),
                    "disabled": js("(document.getElementById('tr-bulk-apply')||{}).disabled"),
                }
                check("与内置相同的条目：提示「不会写入」且应用按钮禁用",
                      "与内置相同" in (out["bulkSame"]["note"] or "")
                      and out["bulkSame"]["disabled"] is True, str(out["bulkSame"]))

            # 真正写入：连点两次（应用 → 确认写入）
            set_bulk(table, "命中 3 条")
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
                "slugcats": "美食家Z" in raw,
                "backToList": js("!!document.getElementById('tr-save')"),
            }
            check("确认后一次写入多个分类（区域/生物/角色），并回到列表",
                  all(out["bulkWritten"][k] for k in ("regions", "creatures", "slugcats"))
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
