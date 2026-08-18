"""
Desktop controller shared utilities.
"""

import ast
import asyncio
import functools
import logging
from typing import Any

from app.core.atlas import atlas_engine
from app.core.environment import get_current_app_context
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


async def _trigger_atlas_harvest_macos(bundle_id: str):
    try:
        app_info = get_current_app_context()
        if app_info.bundle_id != bundle_id:
            logger.debug(f"[AtlasHarvest] App mismatch, skipping harvest for {bundle_id}")
            return
        ax_output = macos_driver.dump_ax_tree()
        if not ax_output or "Error" in ax_output:
            logger.debug(f"[AtlasHarvest] Failed to get AX tree for {bundle_id}")
            return
        try:
            elements_data = await _async_literal_eval(ax_output.replace("missing value", "None"))
        except Exception:
            logger.debug(f"[AtlasHarvest] Failed to parse AX tree for {bundle_id}", exc_info=True)
            return
        event = type('Event', (), {
            'data': {
                'bundle_id': bundle_id,
                'window_title': app_info.title or 'Unknown',
                'platform': 'macos',
                'screenshot_hash': '',
                'version_hash': ''
            },
            'elements': elements_data
        })()
        await atlas_engine.on_ui_tree_observed(event)
        logger.info(f"[AtlasHarvest] Completed harvest for static app: {bundle_id}")
    except Exception as e:
        logger.warning(f"[AtlasHarvest] Failed to harvest for {bundle_id}: {e}", exc_info=True)


async def _async_literal_eval(data: str) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(ast.literal_eval, data))
