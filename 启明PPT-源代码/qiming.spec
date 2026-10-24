# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("frontend", "frontend")]
datas += collect_data_files("webview")
binaries = []
hiddenimports = [
    "waitress",
    "flask",
    "jinja2",
    "werkzeug",
    "pptx",
    "docx",
    "pypdf",
    "openpyxl",
    "et_xmlfile",
    "edge_tts",
    "aiohttp",
    "PIL",
    "numpy",
    "requests",
    "bs4",
    "lxml",
    "imageio_ffmpeg",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]

for package in ("pythonnet", "clr_loader", "imageio_ffmpeg"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "fitz",
        "pymupdf",
        "playwright",
        "pytest",
        "matplotlib",
        "pandas",
        "IPython",
        "notebook",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "qtpy",
        "gi",
        "cefpython3",
        "webview.platforms.qt",
        "webview.platforms.gtk",
        "webview.platforms.android",
        "webview.platforms.cef",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="QimingPPT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="frontend/assets/icon.ico",
    version="version_info.txt",
)
