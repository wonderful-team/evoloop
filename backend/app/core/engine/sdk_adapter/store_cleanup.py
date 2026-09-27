"""SDK conversation store 的磁盘清理。

每个 thread 的 EventLog 持久化在 ``APP_DATA_DIR/sdk-conversations/<uuid5>``
（``delete_on_close=False``），删除会话/回滚会清对应 store，但**正常完结**
的会话 store 会一直留存。长期运行下目录线性增长（实测 3 天 1109 个
store / 122MB），启动时按 TTL 清理陈旧 store。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = 7


def cleanup_stale_conversation_stores(ttl_days: int | None = None) -> int:
    """删除 mtime 超过 TTL 的 SDK conversation store，返回清理数量。

    失败按目录逐个跳过（单个 store 删除失败不影响其余）；只清理
    ``settings.APP_DATA_DIR`` 下的 sdk-conversations 根，防误删。
    """

    ttl = ttl_days or _DEFAULT_TTL_DAYS
    root = (Path(settings.APP_DATA_DIR) / "sdk-conversations").resolve()
    allowed_root = (Path(settings.APP_DATA_DIR) / "sdk-conversations").resolve()
    if root != allowed_root or not root.is_dir():
        return 0

    cutoff = time.time() - ttl * 86400
    removed = 0
    import shutil

    for entry in root.iterdir():
        try:
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            logger.warning(
                "[SDKBridge] cleanup failed for %s", entry, exc_info=True
            )
    if removed:
        logger.info("[SDKBridge] cleaned %d stale conversation stores", removed)
    return removed
