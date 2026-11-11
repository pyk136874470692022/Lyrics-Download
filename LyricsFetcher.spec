# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)
APP_NAME = "歌词下载器"

# 单文件模式默认会解压到 %TEMP%，普通用户遇到临时目录被限制时会报
# “Could not create temporary directory!”。这里固定使用每个用户都存在的
# LocalAppData，避免依赖 TEMP/TMP。
RUNTIME_TMPDIR = r"%LOCALAPPDATA%"

a = Analysis(
    [str(ROOT / "lyrics_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets" / "app.ico"), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    runtime_tmpdir=RUNTIME_TMPDIR,
    icon=str(ROOT / "assets" / "app.ico"),
    version=str(ROOT / "version_info.txt"),
)
