# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files, collect_submodules
import os

SPEC_DIR = Path(SPECPATH)

hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'celery.fixups',
    'celery.fixups.django',
    'celery.loaders',
    'celery.loaders.app',
    'celery.loaders.default',
    'celery.concurrency',
    'celery.concurrency.prefork',
    'celery.concurrency.solo',
    'celery.apps.worker',
    'celery.bin.worker',
    'celery.worker',
    'celery.app.log',
    'celery.app.amqp',
    'celery.events',
    'celery.worker.components',
    'celery.worker.autoscale',
    'celery.worker.consumer',
    'celery.worker.strategy',
    'celery.worker.control',
    'celery.backends.redis',
    'celery.app.events',
    'celery.contrib',
    'billiard',
    'kombu.transport.redis',
    'passlib.handlers.bcrypt',
    'bcrypt',
    'pgvector.sqlalchemy',
    'langchain_community',
    'langchain_openai',
    'langchain_core',
    'langchain_postgres',
    'psycopg_pool',
    'scipy.special.cython_special',
    'shapely',
    'langgraph',
    'langsmith',
    'grandalf',
    'bs4',
    'docx',
    'aiofiles',
    'tenacity',
    'rich',
    'anytree',
    'rapidfuzz',
    'croniter',
    'edge_tts',
    'PIL',
    'PIL._imagingtk',
    'PIL._tkinter_finder',
    'lancedb',
    'pyarrow',
    'tree_sitter',
    'tree_sitter_python',
    'tree_sitter_javascript',
    'tree_sitter_typescript',
    'app',
    'app.main',
    'app.api',
    'app.api.main',
    'app.api.api_v1',
    'app.api.api_v1.endpoints',
    'app.core',
    'app.core.config',
    'app.models',
    'app.domain',
    'app.domain.tools',
    'app.infrastructure',
    'app.infrastructure.database',
    'app.services',
]

hiddenimports += collect_submodules('app.core.engine.nodes')
hiddenimports += collect_submodules('app.domain.tools')

hiddenimports += collect_submodules('celery.worker')
hiddenimports += collect_submodules('celery.app')
hiddenimports += collect_submodules('celery.loaders')
hiddenimports += collect_submodules('celery.concurrency')
hiddenimports += collect_submodules('celery.events')

datas = []
datas += copy_metadata('celery')
datas += copy_metadata('uvicorn')
datas += copy_metadata('langchain')
datas += copy_metadata('langchain_community')
datas += copy_metadata('langchain_core')
datas += copy_metadata('langchain_postgres')
datas += copy_metadata('langgraph')

datas += [
    (str(SPEC_DIR / 'app' / 'core' / 'engine' / 'config'), 'app/core/engine/config'),
    (str(SPEC_DIR / 'app' / 'config' / 'templates'), 'app/config/templates'),
    (str(SPEC_DIR / 'alembic.ini'), '.'),
    (str(SPEC_DIR / 'pyproject.toml'), '.'),
    (str(SPEC_DIR.parent / '.env'), '.'),
]

block_cipher = None

a = Analysis(
    ['bin/run_sidecar.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'scipy',
        'pytest',
        '_pytest',
        'unittest',
        'pdb',
        'pudb',
        'IPython',
        'jupyter',
        'notebook',
        'sphinx',
        'alabaster',
        'babel',
        'torch',
        'torch.utils.tensorboard',
        'sentence_transformers',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='evoloop-backend',
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

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='EvoLoop Backend.app',
        icon=None,
        bundle_identifier='com.evoloop.backend',
    )
