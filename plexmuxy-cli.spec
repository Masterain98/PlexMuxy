# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["packaging/cli_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[("plexmuxy/locales", "plexmuxy/locales"), ("plexmuxy/VERSION", "plexmuxy")],
    hiddenimports=(
        collect_submodules("fontTools")
        + collect_submodules("patoolib")
        + collect_submodules("py7zr")
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["plexmuxy_gui", "webview", "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="plexmuxy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon="logo/plexmuxy-app.ico",
    version="packaging/version_info.txt",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="plexmuxy",
)
