# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:\\Users\\22615\\Documents\\my_python_local\\Video_whisper\\t02_whisper_transcript_tui_v1.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['questionary', 'moviepy.editor', 'faster_whisper'],
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
    name='t02_whisper_transcript_tui_v1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
