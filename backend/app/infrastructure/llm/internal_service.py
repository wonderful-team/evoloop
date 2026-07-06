"""
InternalLLMService - 内部 LLM 调用服务

所有内部 LLM 调用的统一入口，特点：
1. 自动禁用所有回调（防止消息泄露到前端/数据库）
2. 标记调用来源（便于调试和追踪）
3. 统一的超时和重试机制
4. 类型安全的返回

使用场景：
- Memory 选择/提取
- Task 分解/分析
- 审计总结生成
- 环境探索
- 等等内部处理

使用示例：
    from app.infrastructure.llm import InternalLLMService
    from app.infrastructure.config.service import SystemConfigService

    model_name = SystemConfigService.get_value("LLM_MODEL")

    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": "You are a memory selector."},
            {"role": "user", "content": prompt},
        ],
        purpose="memory_selection",  # 用于调试和追踪
        temperature=0.3,
        max_tokens=500,
        model_name=model_name,  # 必须显式传入，禁止隐式 fallback
    )

    content = response.content
"""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class InternalLLMService:
    """
    内部 LLM 调用服务
    
    所有内部处理都应该使用此服务，而不是直接调用 LLM。
    这确保了内部处理不会意外触发回调，导致消息泄露。
    """

    @staticmethod
    async def invoke(
        messages: list[dict],
        purpose: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        model_name: str | None = None,
        **kwargs
    ) -> Any:
        """
        调用 LLM 进行内部处理
        
        Args:
            messages: 消息列表，OpenAI 格式
            purpose: 调用用途，如 "memory_selection", "task_decomposition"
                    用于调试、追踪和日志记录
            temperature: 温度参数
            max_tokens: 最大 token 数
            model_name: 指定模型（可选，默认使用系统配置）
            **kwargs: 其他参数传递给 LLM
            
        Returns:
            LLM 响应对象
            
        关键特性：
            - 自动禁用所有回调（config={"callbacks": []}）
            - 标记 metadata 表明是内部调用
            - 记录调用日志（仅用于调试，不存储消息）
        """
        from app.infrastructure.llm.factory import get_default_llm

        if not model_name:
            raise ValueError(
                "[InternalLLMService] No model specified. "
                "Please pass 'model_name' argument explicitly. "
                f"purpose={purpose}"
            )

        # 获取 LLM 实例
        llm = await get_default_llm(
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
        )

        # 关键：禁用所有回调，防止消息泄露
        config = {
            "callbacks": [],  # 空列表 = 禁用所有回调
            "metadata": {
                "source": "internal_llm",
                "purpose": purpose,
                "should_persist": False,
                "should_stream": False,
            },
            **kwargs.get("config", {}),
        }

        # 记录内部调用（仅用于调试）
        logger.debug(
            f"[InternalLLM] Calling LLM for purpose: {purpose}, "
            f"messages: {len(messages)}, temp: {temperature}, max_tokens: {max_tokens}"
        )

        try:
            response = await llm.ainvoke(messages, config=config)

            logger.debug(f"[InternalLLM] Completed: {purpose}")

            return response

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[InternalLLM] Failed for purpose '{purpose}': {e}")
            raise

    @staticmethod
    async def invoke_structured(
        messages: list[dict],
        output_schema: type[T],
        purpose: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        model_name: str | None = None,
        structured_output_method: str = "function_calling",
        **kwargs
    ) -> T:
        """
        使用结构化输出模式调用 LLM
        """
        from app.infrastructure.llm.factory import get_default_llm

        if not model_name:
            raise ValueError(
                "[InternalLLMService] No model specified. "
                "Please pass 'model_name' argument explicitly. "
                f"purpose={purpose}"
            )

        llm = await get_default_llm(
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
            **kwargs
        )

        # 绑定结构化输出
        structured_llm = llm.with_structured_output(output_schema, method=structured_output_method)

        config = {
            "callbacks": [],
            "metadata": {
                "source": "internal_llm",
                "purpose": purpose,
                "output_schema": output_schema.__name__,
                "should_persist": False,
                "should_stream": False,
            },
        }

        logger.debug(
            f"[InternalLLM] Structured call: {purpose}, "
            f"schema: {output_schema.__name__}"
        )

        try:
            result = await structured_llm.ainvoke(messages, config=config)
            logger.debug(f"[InternalLLM] Structured completed: {purpose}")
            return result
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(
                f"[InternalLLM] Structured call failed for '{purpose}': {e}. "
                "Attempting fallback to clean text generation and custom parsing."
            )
            
            # 1. 尝试直接从 ValidationError 中提取原始 LLM 返回的文本（零延迟，避免重新请求网络）
            raw_content = None
            if isinstance(e, ValidationError):
                try:
                    errors = e.errors()
                    # 仅当 JSON 反序列化失败且输入为字符串时，将输入拿出来
                    if errors and errors[0].get("type") == "json_invalid" and isinstance(errors[0].get("input"), str):
                        raw_content = errors[0]["input"]
                        logger.info(f"[InternalLLM] Extracted raw content directly from ValidationError for '{purpose}'.")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as extract_err:
                    logger.warning(f"[InternalLLM] Failed to extract input from ValidationError: {extract_err}")
            
            # 2. 尝试从 OutputParserException.llm_output 提取（若适用）
            if not raw_content and hasattr(e, "llm_output") and isinstance(e.llm_output, str):
                raw_content = e.llm_output
                logger.info(f"[InternalLLM] Extracted raw content from OutputParserException.llm_output for '{purpose}'.")
            
            # 3. 只有实在拿不到原始响应时，才作为终极手段重新调用一次 llm.ainvoke
            if not raw_content:
                try:
                    logger.info(f"[InternalLLM] Re-invoking LLM as fallback for '{purpose}'...")
                    fallback_response = await llm.ainvoke(messages, config=config)
                    raw_content = fallback_response.content if hasattr(fallback_response, "content") else str(fallback_response)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as fallback_err:
                    logger.error(
                        f"[InternalLLM] Fallback LLM re-invocation also failed for '{purpose}': {fallback_err}"
                    )
                    raise e
            
            # 4. 复用系统已有的 utils/extract 进行解析与验证；model_validate 前先做通用兼容修复
            try:
                from app.utils.extract import extract_json_block

                parsed_data = extract_json_block(raw_content)
                if parsed_data is None:
                    raise ValueError("Failed to extract or parse JSON block from content")

                parsed_data = InternalLLMService._coerce_data_to_schema(parsed_data, output_schema)
                result = output_schema.model_validate(parsed_data)
                logger.info(f"[InternalLLM] Fallback parsing succeeded for '{purpose}'.")
                return result
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as parse_err:
                logger.error(
                    f"[InternalLLM] Fallback parsing failed to parse/validate JSON for '{purpose}': {parse_err}. "
                    f"Raw content preview: {repr(raw_content[:200]) if raw_content else 'None'}"
                )
                raise parse_err

    @staticmethod
    def _coerce_data_to_schema(data: dict, schema: type[BaseModel]) -> dict:
        """
        通用 Schema 驱动的数据容错兼容层。

        在 model_validate 之前对大模型输出做最小修复，使其通过 Pydantic 校验。
        不包含任何业务知识，完全由 Schema 字段类型驱动：

        1. 必填字段缺失 → 按类型补零值（bool→False, str→"", list→[], dict→{}, 其他→None）
        2. list[BaseModel] 字段收到 list[str] → 将每个字符串填入子模型的
           第一个必填 str 字段，其余必填字段同样按类型补零值。

        该方法永远不会对字段名或字段值做任何业务假设。
        """
        if not isinstance(data, dict):
            return data

        import typing

        from pydantic_core import PydanticUndefined

        def _zero_value(annotation: type) -> object:
            """按类型返回零值，完全业务无关。"""
            origin = typing.get_origin(annotation)
            if annotation is bool:
                return False
            if annotation is str:
                return ""
            if annotation is int:
                return 0
            if annotation is float:
                return 0.0
            if annotation is list or origin is list:
                return []
            if annotation is dict or origin is dict:
                return {}
            return None

        def _fill_missing_required(d: dict, model_fields: dict) -> dict:
            """补齐 model 中所有必填但缺失的字段（零值兜底）。"""
            result = d.copy()
            for fname, finfo in model_fields.items():
                if fname not in result and finfo.default is PydanticUndefined:
                    result[fname] = _zero_value(finfo.annotation)
            return result

        coerced = data.copy()

        for field_name, field_info in schema.model_fields.items():
            annotation = field_info.annotation

            # A. 补齐必填但缺失的顶层字段
            if field_name not in coerced:
                if field_info.default is PydanticUndefined:
                    coerced[field_name] = _zero_value(annotation)
                continue

            # B. 处理 list[BaseModel] 字段：将 list[str] 转为 list[dict]
            val = coerced[field_name]
            if not isinstance(val, list):
                continue

            # 解析 list 的泛型参数，确认元素类型是否为 BaseModel 子类
            item_model: type[BaseModel] | None = None
            args = typing.get_args(annotation)
            if args:
                arg = args[0]
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    item_model = arg
                else:
                    # 处理 Union 的情况（如 BaseModel | None）
                    for sub in typing.get_args(arg):
                        if isinstance(sub, type) and issubclass(sub, BaseModel):
                            item_model = sub
                            break

            if item_model is None:
                continue

            # 找到子模型中第一个必填的 str 字段（完全由 schema 驱动，不猜字段名）
            first_required_str_field: str | None = None
            for fname, finfo in item_model.model_fields.items():
                if finfo.default is PydanticUndefined and finfo.annotation is str:
                    first_required_str_field = fname
                    break

            new_list = []
            for item in val:
                if isinstance(item, str) and first_required_str_field is not None:
                    # 将字符串放入第一个必填 str 字段，其余必填字段补零值
                    new_item = _fill_missing_required(
                        {first_required_str_field: item},
                        item_model.model_fields,
                    )
                    new_list.append(new_item)
                else:
                    # 已是 dict / BaseModel 实例：只补齐缺失的必填字段
                    if isinstance(item, dict):
                        new_list.append(_fill_missing_required(item, item_model.model_fields))
                    else:
                        new_list.append(item)

            coerced[field_name] = new_list

        return coerced


    @staticmethod
    def validate_purpose(purpose: str) -> bool:
        """
        验证 purpose 是否有效
        
        有效的 purpose 应该：
        1. 使用小写字母和下划线
        2. 清晰描述调用用途
        3. 在已知列表中（可选）
        
        已知的 purpose 列表：
        - memory_selection: 记忆选择
        - memory_extraction: 记忆提取
        - task_decomposition: 任务分解
        - task_analysis: 任务分析
        - audit_summary: 审计总结
        - environment_triage: 环境探索
        - result_aggregation: 结果聚合
        - intent_matching: 意图匹配
        - vision_analysis: 视觉分析
        """
        import re

        # 格式验证：小写字母和下划线
        if not re.match(r'^[a-z_]+$', purpose):
            return False

        # 已知用途列表（可选验证）
        known_purposes = {
            "memory_selection",
            "memory_extraction",
            "task_decomposition",
            "task_analysis",
            "audit_summary",
            "environment_triage",
            "environment_exploration",
            "result_aggregation",
            "intent_matching",
            "intent_classification",
            "vision_analysis",
            "skill_discovery",
            "skill_matching",
        }

        # 如果不是已知用途，发出警告但不阻止
        if purpose not in known_purposes:
            logger.warning(
                f"[InternalLLM] Unknown purpose: {purpose}. "
                f"Consider adding it to the known purposes list."
            )

        return True
