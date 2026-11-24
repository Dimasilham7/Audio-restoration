# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir spec for audiorestorer-engine

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "scipy.signal",
    "scipy.special",
    "soundfile",
    "pyloudnorm",
    "pedalboard",
    "multipart",
    "email.mime",
]

# soundfile needs libsndfile
binaries += collect_dynamic_libs("soundfile")

tmp_ret = collect_all("pedalboard")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ["../src/audiorestorer_engine/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["librosa", "numba", "llvmlite", "matplotlib", "torch", "torchaudio"],
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
    name="audiorestorer-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="audiorestorer-engine",
)
