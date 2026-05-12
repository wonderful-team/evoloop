"""
MessageClassifier - 消息分类器

根据消息内容和上下文确定其 MessageCategory。
这是消息处理流水线的第一个环节。
"""

import json
import logging
import re
from typing import Any

from app.core.engine.message.category import MessageCategory
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


class MessageClassifier:
    """
    消息分类器
    
    负责在消息创建时确定其分类，基于：
    - 消息角色（user/ai/tool/system）
    - 消息内容
    - 工具调用信息
    - 元数据标记
    """

    # 内部 JSON 响应的特征键（用于识别内部 LLM 响应）
    _INTERNAL_JSON_KEYS = {
        "selected_indices",  # memory selection
        "reasoning",         # memory selection reasoning
        "match_found",       # skill discovery
        "skill_id",          # skill reference
        "subtasks",          # task decomposition
        "can_parallelize",   # task analysis
    }

    @classmethod
    def classify_ai_message(
        cls,
        content: str,
        tool_calls: list | None = None,
        metadata: dict | None = None,
    ) -> MessageCategory:
        """
        分类 AI 助手的消息
        
        Args:
            content: 消息内容
            tool_calls: 工具调用列表
            metadata: 消息元数据（可能包含 source 标记）
            
        Returns:
            MessageCategory 分类
            
        分类逻辑（按优先级）：
        1. 如果 metadata 中标记为 internal → INTERNAL_LLM_JSON
        2. 识别需存入 thinking 字段的内容（原生推理或内部审计标签） → INTERNAL_REASONING
        3. 如果只调用 hidden 工具 → INTERNAL_TOOL_CALL
        4. 如果调用 visible 工具 → ASSISTANT_TOOL_CALL
        5. 如果是 JSON 格式且有内部特征 → INTERNAL_LLM_JSON
        6. 否则 → ASSISTANT_RESPONSE
        """
        # 1. 检查元数据标记（最高优先级）
        if metadata:
            source = metadata.get("source", "")
            error_type = metadata.get("error_type", "")

            # Skip flags (Don't save to DB, but keep streaming if needed)
            if metadata.get("skip_persistence") or metadata.get("skip_message_persistence"):
                return MessageCategory.TRANSIENT_MESSAGE

            # source 标记优先于 is_error 推断
            if source == "error_system":
                return MessageCategory.ERROR_SYSTEM
            if source == "error_business":
                return MessageCategory.ERROR_BUSINESS

            # 区分系统错误和业务错误
            if metadata.get("is_error"):
                # 系统预定义的错误类型
                system_error_types = (
                    "llm_auth",
                    "rate_limit",
                    "quota_exhausted",
                    "recursion_limit",
                    "llm_invocation_system",
                    "service_unavailable",
                    "network_error",
                    "invalid_config",
                    "auth_expired",
                )

                if error_type in system_error_types:
                    return MessageCategory.ERROR_SYSTEM

                # 检查状态码（支持数值或字符串）
                status_code = str(metadata.get("status_code", ""))
                if status_code in ("401", "403", "429", "500", "502", "503", "504"):
                    return MessageCategory.ERROR_SYSTEM

                return MessageCategory.ERROR_BUSINESS

            if source == "internal_llm" or source.startswith("internal_"):
                return MessageCategory.INTERNAL_LLM_JSON

        # 2. 识别需存入 thinking 字段的内容（原生推理内容或内部审计标签）
        has_reasoning = (metadata and metadata.get("reasoning_content")) or (content and cls._has_hidden_audit_tags(content))
        
        # 只有在没有实际回复正文且没有工具调用时，才分类为 INTERNAL_REASONING (纯推理消息)
        # 如果包含正文或工具调用，则由后续逻辑分类为 ASSISTANT_RESPONSE 或 ASSISTANT_TOOL_CALL，
        # 并由 PersistencePolicy 负责将 reasoning 存入 thinking 字段
        if has_reasoning and not (content and content.strip()) and not tool_calls:
            return MessageCategory.INTERNAL_REASONING

        # 3. 分析工具调用
        if tool_calls:
            has_visible, has_hidden = cls._analyze_tool_visibility(tool_calls)

            if has_hidden and not has_visible:
                # 只调用 hidden 工具
                return MessageCategory.INTERNAL_TOOL_CALL
            elif has_visible:
                # 调用 visible 工具（可能也包含 hidden）
                return MessageCategory.ASSISTANT_TOOL_CALL

        # 4. 检查是否是内部 JSON 响应
        if content and cls._is_internal_json_response(content):
            return MessageCategory.INTERNAL_LLM_JSON

        # 5. 检查系统事件
        if content and cls._is_system_event(content):
            return MessageCategory.INTERNAL_SYSTEM

        # 默认：AI 助手最终回复
        return MessageCategory.ASSISTANT_RESPONSE

    @classmethod
    def classify_tool_output(
        cls,
        tool_name: str,
        output: Any,
        metadata: dict | None = None,
    ) -> MessageCategory:
        """
        分类工具输出消息
        
        Args:
            tool_name: 工具名称
            output: 工具输出内容
            
        Returns:
            MessageCategory.TOOL_OUTPUT 或 MessageCategory.INTERNAL_TOOL_CALL
        """
        # Check metadata from tool result
        if metadata and (metadata.get("skip_persistence") or metadata.get("skip_message_persistence")):
            return MessageCategory.TRANSIENT_MESSAGE

        tool_metadata = get_tool_metadata(tool_name)

        if tool_metadata.is_hidden:
            return MessageCategory.INTERNAL_TOOL_CALL

        return MessageCategory.TOOL_OUTPUT

    @classmethod
    def classify_user_message(
        cls,
        content: str,
        metadata: dict | None = None,
    ) -> MessageCategory:
        """
        分类用户消息
        
        目前用户消息只有一种分类，但保留扩展性
        """
        return MessageCategory.USER

    @staticmethod
    def _has_hidden_audit_tags(content: str) -> bool:
        """检查内容是否包含隐藏的审计标签"""
        if not content:
            return False

        patterns = [
            r"<evoloop_session_audit>.*?</evoloop_session_audit>",
            r"<audit>.*?</audit>",
        ]

        for pattern in patterns:
            if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
                return True

        return False

    @staticmethod
    def _analyze_tool_visibility(tool_calls: list) -> tuple[bool, bool]:
        """
        分析工具调用的可见性
        
        Returns:
            (has_visible, has_hidden): 是否包含可见/隐藏工具
        """
        # 延迟导入，避免循环依赖
        from app.core.tools.registry import get_tool_metadata

        has_visible = False
        has_hidden = False

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if not tool_name:
                continue

            metadata = get_tool_metadata(tool_name) or {}
            if metadata.get("is_hidden", False):
                has_hidden = True
            else:
                has_visible = True

        return has_visible, has_hidden

    @classmethod
    def _is_internal_json_response(cls, content: str) -> bool:
        """检查是否是内部 LLM 的 JSON 响应"""
        if not content or not content.strip().startswith("{"):
            return False

        try:
            data = json.loads(content.strip())
            if not isinstance(data, dict):
                return False

            # 检查是否包含内部特征键
            keys = set(data.keys())
            if keys & cls._INTERNAL_JSON_KEYS:
                return True

            return False

        except json.JSONDecodeError:
            return False

    @staticmethod
    def _is_system_event(content: str) -> bool:
        """检查是否是系统事件"""
        if not content:
            return False

        # SESSION COMPLETE 等系统消息
        system_patterns = [
            r"^✅\s*SESSION\s*COMPLETE",
            r"^❌\s*SESSION\s*COMPLETE",
            r"^SESSION\s*COMPLETE",
        ]

        for pattern in system_patterns:
            if re.search(pattern, content.strip(), re.IGNORECASE):
                return True

        return False
