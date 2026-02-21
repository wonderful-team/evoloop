"""
Preference Priming - Loads user preferences and system rules during awakening.
"""

import logging

from app.core.environment.models import PreferenceContext

logger = logging.getLogger(__name__)


async def prime_preferences(project_id: int | None = None) -> PreferenceContext:
    """
    Load user preferences and system rules.
    
    Args:
        project_id: Optional project ID to scope preference retrieval.
        
    Returns:
        PreferenceContext with preferences and rules.
    """
    preferences = {}
    rules = []
    
    # 1. Retrieve user preferences from Preference Store
    try:
        from app.core.memory import memory_manager
        from app.infrastructure.config.service import SystemConfigService
        
        user_id = 1  # Default user
        prefs_text = await memory_manager.preferences.get_merged_preferences(
            user_id=user_id,
            project_id=project_id,
        )
        preferences = _parse_preferences(prefs_text)
        
        # Add language preference
        language = SystemConfigService.get_language_preference()
        if language:
            preferences["language"] = language
            
    except Exception as e:
        logger.warning(f"Failed to retrieve preferences: {e}")
    
    # 2. System-level inviolable rules (hardcoded for safety)
    rules = [
        "禁止删除 .git 目录",
        "禁止执行 rm -rf / 或任何递归删除根目录的命令",
        "未经用户确认不得修改 package.json 或 requirements.txt 的核心依赖版本",
        "禁止在生产数据库上执行 DROP 或 TRUNCATE 操作",
        "禁止暴露或打印用户的 API 密钥、密码等敏感信息",
    ]
    
    return PreferenceContext(
        preferences=preferences,
        rules=rules,
    )


def _parse_preferences(raw_text: str) -> dict[str, str]:
    """Parse preference text into key-value pairs."""
    prefs = {}
    
    if not raw_text:
        return prefs
    
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Try to split on colon or equals
        for sep in [":", "="]:
            if sep in line:
                key, value = line.split(sep, 1)
                prefs[key.strip().lower().replace(" ", "_")] = value.strip()
                break
    
    return prefs
