# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
if SPEC_DIR.is_file():
    SPEC_DIR = SPEC_DIR.parent
ROOT = SPEC_DIR.parent
PACKAGE_DIR = ROOT / "h_denoise_utils"
UI_DIR = PACKAGE_DIR / "ui"
ICONS_DIR = UI_DIR / "icons"

datas = [(str(UI_DIR / "style.qss"), "h_denoise_utils/ui")]
datas.extend(
    (str(path), "h_denoise_utils/ui/icons")
    for path in ICONS_DIR.iterdir()
    if path.is_file()
)

a = Analysis(
    [str(PACKAGE_DIR / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide2",
        "PyQt5",
        "PyQt6",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="h-denoise",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICONS_DIR / "logo.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="h-denoise",
)
