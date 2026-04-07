"""
Memory v2 核心数据模型示例
"""
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import uuid


def generate_memory_id() -> str:
    """生成记忆 ID"""
    return f"mem_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    """获取 UTC 时间"""
    return datetime.utcnow()


class MemoryType(str, Enum):
    """四类型记忆分类（借鉴 Claude Code）"""
    USER = "user"           # 用户画像（私有）
    FEEDBACK = "feedback"   # 反馈指导（可团队共享）
    PROJECT = "project"     # 项目上下文（团队）
    REFERENCE = "reference" # 外部引用（团队）


class PrivacyLevel(str, Enum):
    """隐私级别"""
    PRIVATE = "private"  # 仅用户可见
    TEAM = "team"        # 团队成员可见


class MemorySource(str, Enum):
    """记忆来源"""
    EXTRACTED = "extracted"      # LLM 自动提取
    MANUAL = "manual"            # 用户手动添加
    IMPORTED = "imported"        # 外部导入
    CONSOLIDATED = "consolidated"  # 整理生成


class MemoryEntry(BaseModel):
    """
    统一的记忆条目模型
    
    设计特点：
    1. 统一的模型支持四类型记忆
    2. 支持 YAML Frontmatter 序列化
    3. 包含完整的元数据信息
    4. 支持扩展数据
    """
    id: str = Field(default_factory=generate_memory_id)
    type: MemoryType
    privacy: PrivacyLevel
    
    # 内容
    title: str
    content: str
    
    # 元数据
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    
    # 来源信息
    source: MemorySource = MemorySource.EXTRACTED
    confidence: float = 1.0  # 提取置信度 (0-1)
    source_thread_id: str | None = None
    source_message_id: str | None = None
    
    # 作用域
    user_id: str | None = None
    project_id: int | None = None
    
    # 扩展数据
    extra: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        frozen = False


class SearchResult(BaseModel):
    """搜索结果"""
    memory: MemoryEntry
    score: float  # 相关性分数 (0-1)
    matched_keywords: list[str] = Field(default_factory=list)


# 示例用法
if __name__ == "__main__":
    # 创建一个用户偏好记忆
    user_preference = MemoryEntry(
        type=MemoryType.USER,
        privacy=PrivacyLevel.PRIVATE,
        title="Python 编码风格偏好",
        content="""用户偏好以下 Python 代码风格：
1. 使用双引号而非单引号
2. 遵循 PEP 8 规范
3. 优先使用类型注解""",
        tags=["preferences", "coding-style", "python"],
        source=MemorySource.EXTRACTED,
        confidence=0.95,
        user_id="user_123",
    )
    
    print(f"Memory ID: {user_preference.id}")
    print(f"Type: {user_preference.type.value}")
    print(f"Privacy: {user_preference.privacy.value}")
