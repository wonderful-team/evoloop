# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

# Define hidden imports
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
    'celery.concurrency.prefork', # Standard pool
    'celery.concurrency.solo',    # Pool used in our config
    'celery.apps.worker',
    'celery.worker',
    'celery.bin.worker', 
    'celery.app.log',
    'celery.app.amqp', # Critical for Celery
    'celery.events',
    'celery.worker.components', # Critical for Worker startup
    'celery.worker.autoscale', # Critical for Worker autoscale
    'celery.backends.redis', # Critical for Redis backend
    'celery.app.events', # Critical for API task dispatching
    'celery.worker.consumer', # Critical for Worker message consumption
    'celery.worker.strategy', # Likely needed next
    'celery.worker.control', # Likely needed next
    'celery.contrib',
    'billiard', # critical for multiprocessing
    'kombu.transport.redis', # if using redis
    'passlib.handlers.bcrypt',
    'bcrypt',
    'pgvector.sqlalchemy',
    'langchain_community',
    'langchain_openai',
    'langchain_core',
    'langchain_postgres',
    'psycopg_pool',
    'scipy.special.cython_special', # Often needed by scientific libs if used
    'shapely', # Used by langgraph/langchain sometimes
    'langgraph',
    'langsmith',
    'grandalf', # specific for langgraph visualization if used
]

# Explicitly collect all node modules because they are dynamically imported by graph_builder
from PyInstaller.utils.hooks import collect_submodules
hiddenimports += collect_submodules('app.core.engine.nodes')
# Also collect tools just in case
hiddenimports += collect_submodules('app.domain.tools')

# CRITICAL: Aggressively collect Celery submodules to stop "No module named" errors
hiddenimports += collect_submodules('celery.worker')
hiddenimports += collect_submodules('celery.app')
hiddenimports += collect_submodules('celery.loaders')
hiddenimports += collect_submodules('celery.concurrency')
hiddenimports += collect_submodules('celery.events') # Added for 'celery.events.state'

# Add metadata for key packages
datas = []
datas += copy_metadata('celery')
datas += copy_metadata('uvicorn')
datas += copy_metadata('langchain')
datas += copy_metadata('langchain_community')
datas += copy_metadata('langchain_core')
datas += copy_metadata('langchain_postgres')
datas += copy_metadata('langgraph')

# Add Config Files
# We need to include 'app/core/engine/config' directory.
# Source: app/core/engine/config -> Target: app/core/engine/config
datas += [
    ('app/core/engine/config', 'app/core/engine/config'),
    ('alembic.ini', '.'),
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
    excludes=[],
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
    name='evoloop-client',
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
