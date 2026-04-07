"""
Memory v2 配置示例
"""

# settings.py 添加的配置项

MEMORY_SYSTEM_CONFIG = {
    # 记忆系统版本：v1 或 v2
    "USE_MEMORY_V2": True,
    
    # 文件后端配置（嵌入式模式）
    "MEMORY_ROOT": "~/.evoloop/memory",
    
    # 自动提取配置
    "MEMORY_AUTO_EXTRACT": True,
    "MEMORY_EXTRACT_MIN_CONFIDENCE": 0.7,
    "MEMORY_EXTRACT_MAX_ENTRIES": 5,
    
    # 检索配置
    "MEMORY_RETRIEVAL_MAX_TOKENS": 2000,
    "MEMORY_RETRIEVAL_DEFAULT_LIMIT": 10,
    
    # 索引更新配置
    "MEMORY_INDEX_AUTO_UPDATE": True,
    "MEMORY_INDEX_UPDATE_INTERVAL": 300,  # 秒
    
    # 向后兼容配置
    "MEMORY_V1_COMPATIBILITY": True,
}

# 环境变量配置示例
"""
# .env 文件

# 启用 Memory v2
USE_MEMORY_V2=true

# 记忆存储路径
MEMORY_ROOT=~/.evoloop/memory

# 启用自动记忆提取
MEMORY_AUTO_EXTRACT=true

# 保持 v1 兼容
MEMORY_V1_COMPATIBILITY=true
"""
