"""
MessageClassifier - 消息分类器

根据消息内容和上下文确定其 MessageCategory。
这是消息处理流水线的第一个环节。
"""

import json
import logging
import re
from typing import Any, Optional

from app.core.messaging.category import MessageCategory

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
        tool_calls: Optional[list] = None,
        metadata: Optional[dict] = None,
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
        2. 如果内容包含 <think> 或 <audit> → INTERNAL_REASONING
        3. 如果只调用 hidden 工具 → INTERNAL_TOOL_CALL
        4. 如果调用 visible 工具 → ASSISTANT_TOOL_CALL
        5. 如果是 JSON 格式且有内部特征 → INTERNAL_LLM_JSON
        6. 否则 → ASSISTANT_RESPONSE
        """
        # 1. 检查元数据标记（最高优先级）
        if metadata:
            source = metadata.get("source", "")
            error_type = metadata.get("error_type", "")
            
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
            
            if source == "error_system":
                return MessageCategory.ERROR_SYSTEM
            if source == "error_business":
                return MessageCategory.ERROR_BUSINESS
            if source == "internal_llm" or source.startswith("internal_"):
                return MessageCategory.INTERNAL_LLM_JSON
        
        # 2. 检查思考/审计标签
        if content and cls._has_thinking_tags(content):
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
    ) -> MessageCategory:
        """
        分类工具输出消息
        
        Args:
            tool_name: 工具名称
            output: 工具输出内容
            
        Returns:
            MessageCategory.TOOL_OUTPUT 或 MessageCategory.INTERNAL_TOOL_CALL
        """
        # 延迟导入，避免循环依赖
        from app.core.tools.registry import get_tool_metadata
        
        metadata = get_tool_metadata(tool_name) or {}
        
        if metadata.get("is_hidden", False):
            return MessageCategory.INTERNAL_TOOL_CALL
        
        return MessageCategory.TOOL_OUTPUT
    
    @classmethod
    def classify_user_message(
        cls,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageCategory:
        """
        分类用户消息
        
        目前用户消息只有一种分类，但保留扩展性
        """
        return MessageCategory.USER
    
    @staticmethod
    def _has_thinking_tags(content: str) -> bool:
        """检查内容是否包含思考或审计标签"""
        if not content:
            return False
        
        patterns = [
            r"<think>.*?</think>",
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
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
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
