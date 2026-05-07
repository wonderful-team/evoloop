"""
调用所有 69 个注册工具，打印每个工具的返回值。
验证：Agent 得到的都是纯文本(str)，不是 JSON/dict。
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

import asyncio
import json
from enum import Enum
from typing import Literal, get_args, get_origin
from pydantic import BaseModel
from pydantic_core import PydanticUndefined


def _unwrap_optional(annotation):
    """解包 X | None / Optional[X] 得到内部类型"""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and type(None) in args:
        for arg in args:
            if arg is not type(None):
                return arg
    return annotation


def _safe_default(field_name: str, annotation):
    """为工具参数生成安全的测试默认值，类型正确"""
    name_lower = field_name.lower()
    unwrapped = _unwrap_optional(annotation)
    origin = get_origin(unwrapped)
    args = get_args(unwrapped)

    # Literal 类型 → 用第一个合法值
    if origin is Literal:
        for v in args:
            if v is not None:
                return v
        return None

    # 浮点数类
    if unwrapped is float:
        if 'seconds' in name_lower:
            return 0.01
        return 1.0

    # 整数类（必须是纯 int，不能是 list[int] 等泛型）
    if unwrapped is int:
        return 1

    # 布尔类
    if unwrapped is bool:
        return False

    # 列表类（包括 list[str]）
    if origin is list or unwrapped is list:
        if 'steps' in name_lower:
            return ["step 1"]
        if 'edits' in name_lower:
            return [{"target": "foo", "replacement": "bar"}]
        if 'options' in name_lower:
            return []
        if 'entities' in name_lower:
            return ["entity1"]
        if 'focus_areas' in name_lower:
            return []
        if 'concepts' in name_lower:
            return []
        if 'actions' in name_lower:
            return []
        if 'cookies' in name_lower:
            return []
        if 'intents' in name_lower:
            return []
        if 'tool_call_ids' in name_lower:
            return []
        if 'authorized_tools' in name_lower:
            return []
        if 'skill_ids' in name_lower:
            return []
        return []

    # Pydantic 模型类
    if isinstance(unwrapped, type) and issubclass(unwrapped, BaseModel):
        return unwrapped()

    # Enum 类
    if isinstance(unwrapped, type) and issubclass(unwrapped, Enum):
        for member in unwrapped:
            return member.value
        return None

    # dict 类（包括 dict[str, str]）
    if origin is dict or unwrapped is dict:
        if 'modifications' in name_lower:
            return {}
        if 'params' in name_lower:
            return {}
        if 'context' in name_lower and 'image_source' not in name_lower:
            return {}
        if 'custom_summaries' in name_lower:
            return {}
        return {}

    # 字符串类（兜底）
    if 'path' in name_lower or 'file' in name_lower:
        return "."
    if 'command' in name_lower:
        return "echo test"
    if 'code' in name_lower:
        return "def test():\n    return 'hello'\n"
    if any(k in name_lower for k in ('query', 'pattern', 'question', 'search')):
        return "test"
    if any(k in name_lower for k in ('prompt', 'message', 'description', 'content', 'title', 'intent')):
        return "test"
    if 'platform' in name_lower:
        return "macos"
    if 'risk_level' in name_lower:
        return "low"
    if 'operator' in name_lower:
        return "or"
    if 'entity_operator' in name_lower:
        return "or"
    if 'status' in name_lower:
        return "pending"
    if 'breakdown_strategy' in name_lower:
        return "module_based"
    if 'input_type' in name_lower:
        return "text"
    if 'image_source' in name_lower:
        return "screenshot"
    if 'slug' in name_lower:
        return "test"
    if 'reason' in name_lower:
        return "test"
    if 'skill_name' in name_lower:
        return "test_skill"
    if 'key' in name_lower:
        return "test_key"
    if 'value' in name_lower:
        return "test_value"
    if 'bundle_ids' in name_lower:
        return "test"
    if 'target' in name_lower and 'target_file' not in name_lower:
        return "test"
    if any(k in name_lower for k in ('memory_id', 'tool_call_id', 'analysis_id', 'document_id', 'todo_id', 'step_id')):
        return "test-id"
    if 'task_id' in name_lower:
        return "test-id"
    if 'project_id' in name_lower:
        return 1
    # skill_ids (list) must be checked before skill_id (int)
    if 'skill_ids' in name_lower:
        return []
    if 'skill_id' in name_lower:
        return 1
    if 'thread_id' in name_lower:
        return "test-thread"
    if 'execution_run_id' in name_lower:
        return "test-run"
    if 'expected_hash' in name_lower:
        return ""

    return "test"


def _build_invoke_args(tool):
    """根据工具的 args_schema 构建调用参数字典"""
    invoke_args = {}
    schema = getattr(tool, 'args_schema', None)
    if not schema:
        return invoke_args

    for field_name, field_info in schema.model_fields.items():
        if field_name in ('config',):
            continue
        annotation = field_info.annotation
        default = getattr(field_info, 'default', None)
        if default is not None and default is not ... and default is not PydanticUndefined:
            invoke_args[field_name] = default
        else:
            invoke_args[field_name] = _safe_default(field_name, annotation)

    return invoke_args


async def main():
    # 1. 登录获取 token
    try:
        from app.core.evocloud import evocloud_manager
        from app.core.identity import identity_service
        result = await evocloud_manager.api.login("preterchan", "hellomylife")
        if result.get("success"):
            await identity_service.login_with_cloud_result(result)
            member_id = await identity_service.get_member_id()
            print(f"已登录: member_id={member_id}")
        else:
            print(f"登录失败: {result.get('message')}")
    except Exception as e:
        print(f"登录失败: {e}")

    # 2. 初始化数据库连接（使用内存 SQLite，避免完整初始化超时）
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.infrastructure.database.resource_manager import db_resource_manager
        from app.infrastructure.database.sql.database import Base
        from app.models import conversation, checkpoint, codebase, learning, planning, scheduler, todo, memory, maintenance, wiki, citation, file_operation, system  # noqa: F401
        from app.domain.project.requirements.models import ProjectRequirementDocument, ProjectRequirementAnalysis  # noqa: F401
        
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
        db_resource_manager._engine = engine
        db_resource_manager._sync_engine = None
        db_resource_manager._session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        db_resource_manager._initialized = True
        print("数据库已初始化 (内存 SQLite)")
    except Exception as e:
        print(f"数据库初始化失败: {e}")

    from app.core.tools.registry import get_all_tools
    from app.core.tools.base import ToolResult

    tools = get_all_tools()
    print(f"共 {len(tools)} 个工具\n")
    print("=" * 80)

    for tool in tools:
        tool_name = tool.name
        args = _build_invoke_args(tool)

        try:
            result = await tool.ainvoke(args)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise e
            # HITL 工具会抛出中断异常，这是正常行为
            if 'Interrupt' in type(e).__name__ or 'HITL' in type(e).__name__:
                print(f"\n⏸️  {tool_name}: HITL interrupt → {type(e).__name__}")
            else:
                print(f"\n❌ {tool_name}: ERROR → {type(e).__name__}: {e}")
            continue

        is_str = isinstance(result, str)
        is_dict = isinstance(result, dict)
        is_tool_result = isinstance(result, ToolResult)
        has_meta = hasattr(result, 'meta') and isinstance(getattr(result, 'meta', None), dict)
        meta = getattr(result, 'meta', {}) if has_meta else {}
        display_name = getattr(result, 'display_name', '') if has_meta else ''

        text = str(result)
        snippet = text[:300].replace('\n', '\\n')
        if len(text) > 300:
            snippet += f" ... ({len(text)} 字符)"

        type_info = []
        if is_tool_result:
            type_info.append("ToolResult")
        elif is_str:
            type_info.append("str")
        if is_dict:
            type_info.append("dict ⚠️")
        if has_meta and meta:
            type_info.append(f"meta={meta}")
        if display_name:
            type_info.append(f"display='{display_name}'")

        type_str = " | ".join(type_info) if type_info else type(result).__name__

        print(f"\n✅ {tool_name} ({type_str})")
        print(f"   → {snippet}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
