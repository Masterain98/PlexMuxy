# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


block_cipher = None

a = Analysis(
    ["packaging/gui_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[("plexmuxy_gui/static", "plexmuxy_gui/static"), ("plexmuxy/locales", "plexmuxy/locales")],
    hiddenimports=(
        collect_submodules("fontTools")
        + collect_submodules("patoolib")
        + collect_submodules("py7zr")
        + collect_submodules("webview")
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
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
    name="plexmuxy-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="logo/plexmuxy-app.ico",
    manifest="packaging/plexmuxy-gui.manifest",
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
    name="plexmuxy-gui",
)
