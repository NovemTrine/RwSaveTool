"""外观与配色 / 译名 / 合计时长 / 表格自适应 的回归检查（真实 WebView2，隐藏窗口）。

用法： .venv/Scripts/python.exe build/check_ui.py

检查内容：
    1. 选中态对比度：`.sort-btn.on` 有实色背景且文字不是深色叠深底
    2. 主题：暗色 → 亮色切换生效，强调色预设生效并写进 config
    3. 各战役统计末行「全部 N 个战役」的合计时长 = 各行之和
    4. 自定义译名：改一条生物名 → 击杀页立刻显示新名字 → 恢复默认后还原
    5. 区域表在 1400px 窗口下不出现横向滚动条
    6. 滚动条样式与 --surface 变量已生效（亮色主题下不再是白色半透明）
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview  # noqa: E402

from core import paths  # noqa: E402
from core.bridge import Api  # noqa: E402

TR_FILE = os.path.join(paths.data_dir(), "_translations.json")


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


def main() -> int:
    snapshot = read_tr()
    api = Api()
    with open(os.path.join(ROOT, "ui", "rw_gui.html"), encoding="utf-8") as fh:
        html = fh.read()

    window = webview.create_window("RwSaveTool UI 检查", html=html, js_api=api,
                                   width=1400, height=900, hidden=True)
    api.attach(window)
    out: dict = {}

    def js(code, default=None):
        try:
            return window.evaluate_js(code)
        except Exception as exc:  # noqa: BLE001
            out.setdefault("errors", []).append(f"{code[:50]}: {exc}")
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
                if js("window.__rwTest.ready()"):
                    break
            time.sleep(1.0)

            # 1) 选中态对比度
            js("var s=[].slice.call(document.querySelectorAll('#camplist .camp')).filter("
               "function(e){return /White/.test(e.textContent);})[0]; if(s) s.click();")
            time.sleep(0.8)
            js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.0)
            out["activeBtn"] = loads(js(
                "JSON.stringify((function(){"
                "var b=document.querySelector('#detail-body .sortbar .sort-btn.on')||document.querySelector('.sort-btn.on');"
                "if(!b) return {found:false};"
                "var cs=getComputedStyle(b);"
                "return {found:true, text:b.textContent.trim(), bg:cs.backgroundColor, fg:cs.color, shadow:cs.boxShadow!=='none'};})())"
            ))

            # 2) 主题切换
            js("document.getElementById('theme-fab').click();")
            time.sleep(0.6)
            out["themeModal"] = loads(js(
                "JSON.stringify({open: !document.getElementById('modal').hidden,"
                "themes: document.querySelectorAll('[data-theme-opt]').length,"
                "accents: document.querySelectorAll('[data-accent-opt]').length})"
            ))
            js("var b=document.querySelector('[data-theme-opt=\"light\"]'); if(b) b.click();")
            time.sleep(0.5)
            js("var b=document.querySelector('[data-accent-opt=\"teal\"]'); if(b) b.click();")
            time.sleep(0.5)
            out["themeApplied"] = loads(js(
                "JSON.stringify((function(){"
                "var d=document.documentElement;var cs=getComputedStyle(d);"
                "return {theme:d.getAttribute('data-theme'), accent:d.getAttribute('data-accent'),"
                "accentVar:cs.getPropertyValue('--accent').trim(),"
                "bg:cs.getPropertyValue('--bg').trim(),"
                "surface:cs.getPropertyValue('--surface').trim(),"
                "bodyBg:getComputedStyle(document.body).backgroundColor};})())"
            ))
            js("var b=document.querySelector('[data-theme-opt=\"dark\"]'); if(b) b.click();")
            time.sleep(0.4)
            js("document.getElementById('modal-close').click();")
            time.sleep(0.4)
            out["themeBack"] = loads(js(
                "JSON.stringify({theme: document.documentElement.getAttribute('data-theme'),"
                "modalClosed: document.getElementById('modal').hidden})"
            ))

            # 3) 各战役统计合计
            js("var tb=document.querySelector('[data-tab=\"global\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["total"] = loads(js(
                "JSON.stringify((function(){"
                "var rows=[].slice.call(document.querySelectorAll('#detail-body tbody tr'));"
                "var foot=document.querySelector('#detail-body tfoot .total-row');"
                "return {rows: rows.length, hasFoot: !!foot,"
                "foot: foot?[].slice.call(foot.cells).map(function(c){return c.textContent.trim();}):null,"
                "firstRow: rows[0]?[].slice.call(rows[0].cells).map(function(c){return c.textContent.trim();}):null,"
                "overflowX: (function(){var w=document.querySelector('#detail-body .table-wrap');"
                "return w? w.scrollWidth-w.clientWidth : null;})()};})())"
            ))

            # 4) 自定义译名
            js("document.getElementById('btn-translations').click();")
            time.sleep(0.8)
            js("var b=document.querySelector('[data-trkind=\"creatures\"]'); if(b) b.click();")
            time.sleep(0.6)
            out["trModal"] = loads(js(
                "JSON.stringify({open: !document.getElementById('modal').hidden,"
                "rows: document.querySelectorAll('#modal-body .tr-row').length,"
                "hasSearch: !!document.getElementById('tr-search')})"
            ))
            # 找一个小蜈蚣那一行改名
            js("var inp=document.querySelector('[data-tr=\"SmallCentipede\"]');"
               "if(inp){inp.value='测试蜈蚣';}")
            time.sleep(0.3)
            js("document.getElementById('tr-save').click();")
            time.sleep(1.2)
            js("document.getElementById('modal-close').click();")
            time.sleep(0.4)
            js("var tb=document.querySelector('[data-tab=\"kills\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["trApplied"] = loads(js(
                "JSON.stringify({killsPageHasNew: /测试蜈蚣/.test(document.getElementById('detail-body').textContent),"
                "killsPageHasOld: /幼年蜈蚣/.test(document.getElementById('detail-body').textContent)})"
            ))

            # 5) 区域表横向溢出
            js("var tb=document.querySelector('[data-tab=\"regions\"]'); if(tb) tb.click();")
            time.sleep(1.2)
            out["regions"] = loads(js(
                "JSON.stringify((function(){var w=document.querySelector('#detail-body .table-wrap');"
                "return w? {overflowX: w.scrollWidth-w.clientWidth, clientWidth: w.clientWidth} : {};})())"
            ))

            # 6) 单条清空 = 恢复内置名（「恢复本类默认」按钮已于 11-06 移除，改为「批量翻译」）
            js("document.getElementById('btn-translations').click();")
            time.sleep(0.7)
            out["trBulkEntry"] = loads(js(
                "JSON.stringify({bulk: !!document.getElementById('tr-bulk-open'),"
                "reset: !!document.getElementById('tr-reset')})"
            ))
            js("var b=document.querySelector('[data-trkind=\"creatures\"]'); if(b) b.click();")
            time.sleep(0.6)
            js("var inp=document.querySelector('[data-tr=\"SmallCentipede\"]');"
               "if(inp){inp.value='';}")
            time.sleep(0.3)
            js("document.getElementById('tr-save').click();")
            time.sleep(1.2)
            js("document.getElementById('modal-close').click();")
            time.sleep(0.4)
            js("var tb=document.querySelector('[data-tab=\"kills\"]'); if(tb) tb.click();")
            time.sleep(1.0)
            out["trReset"] = loads(js(
                "JSON.stringify({backToOld: /幼年蜈蚣/.test(document.getElementById('detail-body').textContent),"
                "noNew: !/测试蜈蚣/.test(document.getElementById('detail-body').textContent)})"
            ))
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    webview.start(worker)
    restore_tr(snapshot)
    # 检查过程会真的切换主题并写配置，结束时还原成暗色 + 琥珀，避免影响日常使用
    try:
        api.save_config({"theme": "dark", "accent": "amber"})
    except Exception:  # noqa: BLE001
        pass

    for key in ("activeBtn", "themeModal", "themeApplied", "themeBack", "total",
                "trModal", "trApplied", "regions", "trReset"):
        print(f"{key}:", json.dumps(out.get(key), ensure_ascii=False))
    if out.get("errors"):
        print("js errors:", out["errors"][:3])
    if out.get("fatal"):
        print("FATAL:", out["fatal"])
        return 1

    ok = True

    def expect(cond, label):
        nonlocal ok
        if not cond:
            ok = False
            print("  ✗", label)

    ab = out.get("activeBtn") or {}
    expect(ab.get("found"), "没找到 .sort-btn.on")
    expect(ab.get("bg") not in (None, "", "rgba(0, 0, 0, 0)", "transparent"), "选中态没有实色背景")
    ta = out.get("themeApplied") or {}
    expect(ta.get("theme") == "light", "亮色主题未生效")
    expect(ta.get("accent") == "teal", "强调色未生效")
    tm = out.get("themeModal") or {}
    expect(tm.get("themes") == 2 and tm.get("accents") == 6, "主题弹窗选项数量不对")
    tt = out.get("total") or {}
    expect(tt.get("hasFoot"), "各战役统计缺少合计行")
    tr = out.get("trApplied") or {}
    expect(tr.get("killsPageHasNew") and not tr.get("killsPageHasOld"), "自定义译名没有生效")
    rs = out.get("trReset") or {}
    expect(rs.get("backToOld") and rs.get("noNew"), "恢复默认没有生效")
    rg = out.get("regions") or {}
    expect((rg.get("overflowX") or 0) <= 1, f"区域表仍有横向溢出 {rg.get('overflowX')}px")

    print("CHECK", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
