# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = [
    (str(root / "templates"), "templates"),
    (str(root / "static"), "static"),
]

hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    datas += collect_data_files("webview")
    hiddenimports += collect_submodules("webview")
except Exception:
    pass

binaries = []
dll = root / "vendor" / "libdiscid" / "discid.dll"
if dll.exists():
    binaries.append((str(dll), "vendor/libdiscid"))
    hiddenimports.append("discid")

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AuraCD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "static" / "img" / "auracd.ico"),
    version=str(root / "packaging" / "version_info.txt"),
    uac_admin=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AuraCD",
)
