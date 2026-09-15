# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files, collect_submodules
from importlib.metadata import PackageNotFoundError
import os

SPEC_DIR = Path(SPECPATH)


def _copy_metadata_safe(pkg):
    try:
        return copy_metadata(pkg)
    except PackageNotFoundError:
        return []


def _collect_submodules_safe(pkg):
    try:
        return collect_submodules(pkg)
    except PackageNotFoundError:
        return []
    except ImportError:
        return []

hiddenimports = [
    # Uvicorn / ASGI
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    # FastAPI / Pydantic / multipart
    'fastapi',
    'fastapi.middleware',
    'fastapi.openapi',
    'multipart',
    'email_validator',
    'pydantic.v1',
    'pydantic_settings',
    # SQL / DB / migrations
    'sqlmodel',
    'alembic',
    'alembic.runtime',
    'alembic.context',
    'pgvector.sqlalchemy',
    'psycopg',
    'psycopg_binary',
    'psycopg2',
    'psycopg_pool',
    'aiosqlite',
    # Auth
    'passlib.handlers.bcrypt',
    'bcrypt',
    'jwt',
    # HTTP / network
    'httpx',
    'h2',
    'requests',
    'aiohttp',
    'websockets',
    # Task queue / cache
    'huey',
    'huey.consumer',
    'huey.storage',
    'redis',
    'kombu.transport.redis',
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
    'croniter',
    # LLM / AI clients
    'google.genai',
    'openai',
    'anthropic',
    'sentry_sdk',
    'sentry_sdk.integrations.fastapi',
    # Tree-sitter (language parsers used by code agents)
    'tree_sitter',
    'tree_sitter_python',
    'tree_sitter_javascript',
    'tree_sitter_typescript',
    'tree_sitter_go',
    'tree_sitter_java',
    'tree_sitter_cpp',
    'tree_sitter_rust',
    'tree_sitter_php',
    'tree_sitter_ruby',
    'tree_sitter_c_sharp',
    'tree_sitter_kotlin',
    'tree_sitter_swift',
    'tree_sitter_sql',
    'tree_sitter_html',
    'tree_sitter_language_pack',
    # Documents / data
    'bs4',
    'docx',
    'aiofiles',
    'tenacity',
    'rich',
    'anytree',
    'rapidfuzz',
    'PIL',
    'PIL._imagingtk',
    'pandas',
    'openpyxl',
    'pypdf',
    'markdownify',
    'mammoth',
    'yaml',
    'yamllint',
    # Search / DB / misc
    'lancedb',
    'pyarrow',
    'watchdog',
    'mcp',
    'pathspec',
    'psutil',
    'docker',
    'imagehash',
    'keyring',
    'googlesearch',
    'ddgs',
    'networkx',
    'itsdangerous',
    'pypinyin',
    'graspologic',
    # ML / local inference
    'llama_cpp',
    'einops',
    'sherpa_onnx',
    'onnxruntime',
    'tokenizers',
    # Email / templates
    'emails',
    'jinja2',
    # macOS native APIs
    'objc',
    'Quartz',
    'Vision',
    # Browser automation
    'playwright',
    # App top-level packages
    'app',
    'app.main',
    'app.api',
    'app.api.main',
    'app.api.routes',
    'app.api.schemas',
    'app.api.dependencies',
    'app.core',
    'app.core.config',
    'app.core.engine',
    'app.models',
    'app.domain',
    'app.infrastructure',
    'app.infrastructure.database',
    'app.services',
    'app.utils',
    'app.i18n',
]

# Deep-collect all app submodules so PyInstaller bundles dynamic imports and
# runtime-discovered modules (tasks, nodes, tools, skills, etc.)
hiddenimports += collect_submodules('app.core')
hiddenimports += collect_submodules('app.domain')
hiddenimports += collect_submodules('app.infrastructure')
hiddenimports += collect_submodules('app.api')
hiddenimports += collect_submodules('app.models')
hiddenimports += collect_submodules('app.utils')
hiddenimports += collect_submodules('app.i18n')
hiddenimports += collect_submodules('app.config')

# Collect all tree-sitter language bindings (they contain native .so / .dylib)
for _ts in (
    'tree_sitter_python', 'tree_sitter_javascript', 'tree_sitter_typescript',
    'tree_sitter_go', 'tree_sitter_java', 'tree_sitter_cpp', 'tree_sitter_rust',
    'tree_sitter_php', 'tree_sitter_ruby', 'tree_sitter_c_sharp',
    'tree_sitter_kotlin', 'tree_sitter_swift', 'tree_sitter_sql',
    'tree_sitter_html', 'tree_sitter_language_pack',
):
    hiddenimports += collect_submodules(_ts)

# Explicit Huey/Celery task modules: the worker discovers tasks via AST scan of
# source files, which doesn't work in a frozen bundle. Importing them eagerly
# ensures decorators are registered.
_task_modules = [
    'app.core.engine.message.tasks',
    'app.core.engine.tasks',
    'app.core.environment.explorers.tasks',
    'app.core.evocloud.bridge.sync_tasks',
    'app.core.learning.macro.tasks',
    'app.core.memory.maintenance',
    'app.core.project.summarizer',
    'app.core.project.sync_tasks',
    'app.core.routing.tasks',
    'app.domain.codebase.indexing.tasks',
    'app.infrastructure.vision.cleanup',
]
for _mod in _task_modules:
    hiddenimports.append(_mod)

# Celery submodules (safe-fail in case celery is not installed)
hiddenimports += _collect_submodules_safe('celery.worker')
hiddenimports += _collect_submodules_safe('celery.app')
hiddenimports += _collect_submodules_safe('celery.loaders')
hiddenimports += _collect_submodules_safe('celery.concurrency')
hiddenimports += _collect_submodules_safe('celery.events')

datas = []
for _pkg in ('celery', 'uvicorn', 'alembic', 'sqlmodel', 'pydantic', 'sentry_sdk'):
    datas += _copy_metadata_safe(_pkg)

datas += [
    (str(SPEC_DIR / 'app' / 'core' / 'engine' / 'config'), 'app/core/engine/config'),
    (str(SPEC_DIR / 'app' / 'config' / 'templates'), 'app/config/templates'),
    (str(SPEC_DIR / 'app' / 'i18n' / 'locales'), 'app/i18n/locales'),
    (str(SPEC_DIR / 'app' / 'core' / 'routing' / 'data'), 'app/core/routing/data'),
    (str(SPEC_DIR / 'app' / 'infrastructure' / 'client' / 'client_tools.yaml'), 'app/infrastructure/client'),
    (str(SPEC_DIR / 'app' / 'config' / 'skills'), 'app/config/skills'),
    (str(SPEC_DIR / 'app' / 'alembic' / 'script.py.mako'), 'app/alembic'),
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
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='EvoLoop Backend.app',
        icon=None,
        bundle_identifier='com.evoloop.backend',
        info_plist={
            'NSMicrophoneUsageDescription': 'EvoLoop Backend needs access to microphone to record voice commands.',
            'NSScreenCaptureUsageDescription': 'EvoLoop Backend needs access to screen capture for visual context.',
            'NSAppleEventsUsageDescription': 'EvoLoop Backend needs access to control the system.',
            'LSBackgroundOnly': 'True'
        }
    )
