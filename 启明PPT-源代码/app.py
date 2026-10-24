"""启明 PPT desktop launcher (Flask + Waitress + WebView2)."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from waitress import create_server

from backend import APP_VERSION, create_app
from backend.config import APP_NAME, DATA_DIR, FRONTEND_DIR, LOG_DIR, ensure_directories

LOG = logging.getLogger("qiming")
_MUTEX_HANDLE = None
ERROR_ALREADY_EXISTS = 183


def _try_single_instance() -> bool:
    """Return False when another copy is already running (Windows only)."""
    global _MUTEX_HANDLE
    if os.name != "nt" or os.environ.get("QIMING_MULTI") == "1":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "QimingPPT_SingleInstance_v1")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            try:
                url = (DATA_DIR / "last_url.txt").read_text(encoding="utf-8").strip()
                if url:
                    try:
                        urlopen(url + "api/health", timeout=1.2).read(20)
                    except Exception:
                        url = ""
                    if url:
                        webbrowser.open(url, new=2)
                        return False
            except OSError:
                pass
            return False
    except Exception:
        pass
    return True


def _configure_logging(debug: bool = False) -> None:
    ensure_directories()
    level = logging.DEBUG if debug else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
        handler = logging.FileHandler(LOG_DIR / "launcher.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        root_logger.addHandler(handler)
    if sys.stdout and sys.stdout.isatty():
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(stream)


def _find_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class DesktopApi:
    """Methods exposed to JavaScript as window.pywebview.api.*"""

    def open_data_folder(self) -> dict[str, Any]:
        try:
            os.startfile(str(DATA_DIR))  # type: ignore[attr-defined]
            return {"ok": True, "path": str(DATA_DIR)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_external(self, url: str) -> dict[str, Any]:
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "invalid url"}
        try:
            webbrowser.open(url, new=2)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def app_info(self) -> dict[str, Any]:
        return {"name": APP_NAME, "version": APP_VERSION, "data_dir": str(DATA_DIR)}


def _run_browser(url: str) -> None:
    webbrowser.open(url, new=2)
    LOG.info("Browser mode. Open %s and press Ctrl+C to stop.", url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def run(args: argparse.Namespace) -> int:
    _configure_logging(args.debug)
    if not args.server and not args.debug and not _try_single_instance():
        LOG.info("Another instance is already running; opening the existing app.")
        return 0
    app = create_app()
    port = args.port if args.port else _find_port()
    url = f"http://127.0.0.1:{port}/?v={APP_VERSION}"
    server = create_server(app, host="127.0.0.1", port=port, threads=8)
    thread = threading.Thread(target=server.run, name="qiming-waitress", daemon=True)
    thread.start()
    time.sleep(0.35)
    LOG.info("%s %s", APP_NAME, APP_VERSION)
    LOG.info("URL: %s", url)
    LOG.info("Data: %s", DATA_DIR)
    try:
        (DATA_DIR / "last_url.txt").write_text(url, encoding="utf-8")
    except OSError:
        pass

    if args.server or args.no_window:
        _run_browser(url) if not args.server else _wait_forever()
        server.close()
        return 0

    try:
        import webview  # type: ignore

        try:
            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
            webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
        except Exception:
            pass
        icon = FRONTEND_DIR / "assets" / "icon.ico"
        webview.create_window(
            APP_NAME,
            url,
            width=1460,
            height=930,
            min_size=(1080, 720),
            resizable=True,
            background_color="#0B0F19",
            confirm_close=False,
            text_select=True,
            js_api=DesktopApi(),
            zoomable=True,
        )
        webview.start(
            debug=bool(args.debug),
            private_mode=False,
            storage_path=str(DATA_DIR / "webview"),
            icon=str(icon) if icon.exists() else None,
        )
        LOG.info("Window closed")
    except Exception:
        LOG.exception("WebView failed; falling back to the default browser")
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "未能启动桌面窗口（可能是缺少 Microsoft Edge WebView2）。\n\n"
                "将改用默认浏览器打开启明 PPT。关闭浏览器标签后，"
                "请在任务管理器中结束本程序。",
                "启明 PPT",
                0x40,
            )
        except Exception:
            pass
        _run_browser(url)
    finally:
        try:
            server.close()
        except Exception:
            pass
    return 0


def _wait_forever() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} desktop app")
    parser.add_argument("--port", type=int, default=0, help="fixed local port")
    parser.add_argument("--no-window", action="store_true", help="open in default browser instead of a desktop window")
    parser.add_argument("--server", action="store_true", help="run only the local server (for development/tests)")
    parser.add_argument("--debug", action="store_true", help="enable verbose logs")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
