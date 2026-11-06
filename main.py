"""RwSaveTool · 雨世界存档分析器（桌面版）入口。"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core import __version__, paths  # type: ignore
    from core.bridge import Api  # type: ignore
else:  # pragma: no cover
    from .core import __version__, paths
    from .core.bridge import Api

APP_TITLE = "雨世界存档分析器 · RwSaveTool v%s" % __version__


def _read_ui() -> str:
    with open(paths.ui_path(), "r", encoding="utf-8") as fh:
        return fh.read()


def run_desktop(debug: bool = False) -> int:
    try:
        import webview  # noqa: F401
    except Exception as exc:  # pywebview 缺失 → 退化为浏览器窗口模式
        print(f"[提示] 桌面壳不可用（{exc}），改用浏览器应用窗口模式。")
        return run_browser_fallback()

    import webview

    api = Api()
    window = webview.create_window(
        APP_TITLE,
        html=_read_ui(),
        width=1480,
        height=1040,
        min_size=(1120, 720),
        js_api=api,
        text_select=True,
        confirm_close=False,
    )
    api.attach(window)
    webview.start(debug=debug, private_mode=False)
    return 0


def run_browser_fallback() -> int:
    """没有 WebView2 / pywebview 时，用 Edge 的 --app 窗口打开（无地址栏）。"""
    import subprocess
    import tempfile

    html_path = paths.ui_path()
    edge_candidates = [
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    edge = next((p for p in edge_candidates if p and os.path.isfile(p)), None)
    url = "file:///" + html_path.replace("\\", "/")
    if not edge:
        print(f"[错误] 未找到 Microsoft Edge，请手动打开：{url}")
        return 2
    print("[提示] 浏览器窗口模式：模组导入等原生能力不可用。")
    subprocess.Popen([edge, f"--app={url}", "--window-size=1480,1040"])  # noqa: S603
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="雨世界存档分析器（桌面版）")
    parser.add_argument("--debug", action="store_true", help="打开开发者工具")
    parser.add_argument("--browser", action="store_true", help="强制使用浏览器应用窗口模式")
    parser.add_argument("--serve", action="store_true", help="只启动本地静态服务（调试用）")
    args = parser.parse_args(argv)

    if args.serve:
        return run_static_server()
    if args.browser:
        return run_browser_fallback()
    return run_desktop(debug=args.debug)


def run_static_server() -> int:
    """调试用：起一个本地 HTTP 服务，方便在浏览器里打开界面（无原生能力）。"""
    import functools
    import http.server
    import socketserver

    root = os.path.dirname(paths.ui_path())
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    with socketserver.TCPServer(("127.0.0.1", 8777), handler) as httpd:
        print("界面地址：http://127.0.0.1:8777/rw_gui.html  （Ctrl+C 结束）")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
