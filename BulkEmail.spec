# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None
BASE_DIR = os.path.abspath('.')

a = Analysis(
    ['bulk_email.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=[
        ('email-templates', 'email-templates'),
        ('.env.example', '.'),
    ],
    hiddenimports=[
        'email_validator',
        'jinja2',
        'pandas',
        'dotenv',
        'dkim',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy.testing',
        'pytest', 'unittest', 'xmlrpc',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BulkEmailManager',
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
    version='file_version_info.txt' if os.path.exists('file_version_info.txt') else None,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BulkEmailManager',
)
