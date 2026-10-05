# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — backend desktop do AuditAI (Django + waitress).
#
# Build:  cd desktop-backend && pyinstaller audit-backend.spec --noconfirm
# Saída:  desktop-backend/dist/audit-backend(.exe)
#
# Todos os pacotes do ecossistema Django + Excel/PDF são recolhidos com
# collect_all (código, dados, submódulos) para que migrações, management
# commands, templates do admin/DRF e ficheiros de locale sobrevivam ao freeze.

import os
import sys

# As aplicações locais (dashboard/auditportal) têm de ser IMPORTÁVEIS durante
# a execução do spec para que collect_all/collect_submodules as enumerate.
sys.path.insert(0, os.path.abspath(os.path.join(SPECPATH, "..", "django_app")))

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

PACKAGES = [
    # núcleo Django
    "django", "rest_framework", "django_filters", "corsheaders",
    # aplicações locais (modelos, migrações, management commands)
    "dashboard", "auditportal",
    # Excel/PDF/numérico
    "openpyxl", "xlrd", "pandas", "numpy", "reportlab", "dateutil",
    # servidor WSGI + infra assíncrona inline
    "waitress", "celery", "kombu", "billiard", "vine", "amqp",
    # clientes HTTP/IA
    "requests", "qdrant_client", "urllib3", "certifi", "charset_normalizer",
]

for _pkg in PACKAGES:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        # pacote opcional ausente no ambiente de build — ignorar
        pass

hiddenimports += collect_submodules("dashboard")
hiddenimports += collect_submodules("auditportal")

a = Analysis(
    ["serve.py"],
    pathex=[os.path.join(SPECPATH, "..", "django_app")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "torch", "IPython",
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
    name="audit-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
