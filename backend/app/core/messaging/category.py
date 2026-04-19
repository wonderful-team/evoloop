"""
MessageCategory - 统一消息分类体系

定义所有消息的分类，用于决定消息的存储、推送和显示策略。
"""

from enum import Enum


class MessageCategory(str, Enum):
    """
    消息分类枚举
    
    每个消息必须有且只有一个明确的分类，用于决定：
    1. 是否持久化到数据库
    2. 是否推送到前端
    3. 如何显示给用户
    
    分类命名规则：
    - USER_*: 用户产生的消息
    - ASSISTANT_*: AI 助手产生的消息
    - TOOL_*: 工具相关的消息
    - INTERNAL_*: 内部处理消息（用户不可见）
    """

    # ========== 用户消息 ==========
    USER = "user"
    """用户输入的消息"""

    # ========== AI 助手消息 ==========
    ASSISTANT_RESPONSE = "assistant_response"
    """AI 助手的最终回复，用户可见"""

    ASSISTANT_TOOL_CALL = "assistant_tool_call"
    """AI 助手调用工具的中间消息，包含可见工具调用"""

    # ========== 工具消息 ==========
    TOOL_OUTPUT = "tool_output"
    """工具执行结果（visible 工具），会折叠显示在 AI 消息中"""

    # ========== 内部消息（不显示给用户） ==========
    INTERNAL_TOOL_CALL = "internal_tool_call"
    """AI 只调用 hidden 工具的消息，不应被用户看到"""

    INTERNAL_REASONING = "internal_reasoning"
    """AI 思考过程（<think> 标签内容），存入 thinking 字段"""

    INTERNAL_SYSTEM = "internal_system"
    """系统事件（如 SESSION COMPLETE），不入库"""

    INTERNAL_LLM_JSON = "internal_llm_json"
    """内部 LLM 的 JSON 响应（如 memory 选择），不入库不推送"""

    # ========== 错误消息（不入库，仅通知用户） ==========
    ERROR_SYSTEM = "error_system"
    """系统基础设施错误（401/429/500/recursion等），不入库，仅通过SSE通知用户"""

    AUTH_EXPIRED = "auth_expired"
    """认证过期（云端token失效），不入库，仅通过SSE通知用户跳转登录页"""

    # ========== 错误消息（入库，供Agent学习） ==========
    ERROR_BUSINESS = "error_business"
    """业务逻辑错误（Worker失败/Aggregation失败等），入库供Agent总结经验"""

    @property
    def is_visible_to_user(self) -> bool:
        """是否对用户可见
        
        注意：INTERNAL_REASONING 虽然是内部消息，但会显示给用户（作为思考过程）
        ERROR 类别不入消息列表，通过 error 事件通知用户
        """
        return self in {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,  # 思考过程对用户可见
            # ERROR_SYSTEM 和 ERROR_BUSINESS 不入消息列表
        }

    @property
    def should_persist_to_db(self) -> bool:
        """是否应该持久化到数据库"""
        return self in {
            MessageCategory.USER,
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,  # 思考过程存入 thinking 字段
            MessageCategory.ERROR_BUSINESS,  # 业务错误入库供Agent学习
            # ERROR_SYSTEM 不入库
        }

    @property
    def should_stream_to_frontend(self) -> bool:
        """是否应该通过 SSE 推送到前端"""
        return self in {
            MessageCategory.USER,  # 用户自己的消息需要确认
            MessageCategory.ASSISTANT_RESPONSE,
            MessageCategory.ASSISTANT_TOOL_CALL,
            MessageCategory.TOOL_OUTPUT,
            MessageCategory.INTERNAL_REASONING,  # 思考过程实时推送
            MessageCategory.ERROR_SYSTEM,
            MessageCategory.ERROR_BUSINESS,
            MessageCategory.AUTH_EXPIRED,
        }

    @property
    def storage_field(self) -> str | None:
        """
        存储字段映射
        
        Returns:
            "content": 存入 content 字段
            "thinking": 存入 thinking 字段
            None: 不存储
        """
        mapping = {
            MessageCategory.USER: "content",
            MessageCategory.ASSISTANT_RESPONSE: "content",
            MessageCategory.ASSISTANT_TOOL_CALL: "content",
            MessageCategory.TOOL_OUTPUT: "content",
            MessageCategory.INTERNAL_REASONING: "thinking",
            MessageCategory.ERROR_BUSINESS: "content",
            MessageCategory.ERROR_SYSTEM: None,
            MessageCategory.INTERNAL_TOOL_CALL: None,
            MessageCategory.INTERNAL_SYSTEM: None,
            MessageCategory.INTERNAL_LLM_JSON: None,
        }
        return mapping.get(self)

    @classmethod
    def get_visible_categories(cls) -> set:
        """获取所有前端可见的类别集合"""
        return {
            cls.USER,
            cls.ASSISTANT_RESPONSE,
            cls.ASSISTANT_TOOL_CALL,
            cls.TOOL_OUTPUT,
            cls.INTERNAL_REASONING,  # 思考过程对用户可见
        }

    @classmethod
    def get_invisible_categories(cls) -> set:
        """获取所有前端不可见的类别集合"""
        return {
            cls.INTERNAL_TOOL_CALL,
            cls.INTERNAL_SYSTEM,
            cls.ERROR_SYSTEM,  # 系统错误不入消息列表
            cls.ERROR_BUSINESS,  # 业务错误不入消息列表（但入库供Agent学习）
        }

    @classmethod
    def get_persisted_categories(cls) -> set:
        """获取所有入库的类别集合"""
        return {
            cls.USER,
            cls.ASSISTANT_RESPONSE,
            cls.ASSISTANT_TOOL_CALL,
            cls.TOOL_OUTPUT,
            cls.INTERNAL_REASONING,
            cls.ERROR_BUSINESS,  # 业务错误入库供Agent学习
        }

    @classmethod
    def get_non_persisted_categories(cls) -> set:
        """获取所有不入库的类别集合"""
        return {
            cls.INTERNAL_TOOL_CALL,
            cls.INTERNAL_SYSTEM,
            cls.ERROR_SYSTEM,  # 系统错误不入库
        }
