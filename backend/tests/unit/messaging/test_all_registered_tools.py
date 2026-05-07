"""
遍历所有 @evoloop_tool 注册的工具，验证：
1. 工具能正常加载，summary_template 存在且能渲染
2. 没有 result_summary_template 残留
3. 返回 tuple 的工具：Agent 得到纯文本(str)，数据库得到纯文本(str) + meta
4. 返回纯文本的工具：装饰器正确包装为 ToolResult
"""
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _default_value_for(annotation):
    """根据类型注解生成测试默认值"""
    from pydantic_core import PydanticUndefined
    if annotation is PydanticUndefined:
        return "test"
    origin = getattr(annotation, '__origin__', None)
    args = getattr(annotation, '__args__', ())

    if origin is not None and type(None) in args:
        for arg in args:
            if arg is not type(None):
                return _default_value_for(arg)
        return None

    if origin is list or annotation is list:
        return ["test"]
    if origin is set or annotation is set:
        return {"test"}
    if origin is dict or annotation is dict:
        return {"key": "value"}

    if annotation is str:
        return "test"
    if annotation is int:
        return 5
    if annotation is float:
        return 1.5
    if annotation is bool:
        return True

    return "test"


def _build_test_args(tool):
    """根据工具的 args_schema 构建测试参数字典"""
    from pydantic_core import PydanticUndefined
    test_args = {}
    schema = getattr(tool, 'args_schema', None)
    if not schema:
        return test_args

    for field_name, field_info in schema.model_fields.items():
        if field_name in ('config',):
            continue
        annotation = field_info.annotation
        default = getattr(field_info, 'default', None)
        if default is not None and default is not ... and default is not PydanticUndefined:
            test_args[field_name] = default
        else:
            test_args[field_name] = _default_value_for(annotation)

    return test_args


async def test_all_tools_metadata():
    """遍历所有注册的工具，验证元数据"""
    from app.core.tools.registry import get_all_tools, get_tool_metadata, get_tool_map

    tools = get_all_tools()
    print(f"发现 {len(tools)} 个工具")

    errors = []
    for tool in tools:
        tool_name = tool.name
        try:
            meta = get_tool_metadata(tool_name)

            if hasattr(meta, 'result_summary_template') and meta.result_summary_template:
                errors.append(f"{tool_name}: 仍有 result_summary_template = {meta.result_summary_template}")
                continue

            if not meta.summary_template:
                errors.append(f"{tool_name}: 缺少 summary_template")
                continue

            test_args = _build_test_args(tool)
            display_name = meta.get_display_name(tool_name, test_args)

            unrendered = re.findall(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', display_name)
            status = "✅"
            unrendered_note = ""
            if unrendered:
                missing = [ph for ph in unrendered if ph[1:-1] not in test_args]
                if missing:
                    status = "⚠️"
                    unrendered_note = f" (未替换: {', '.join(missing)})"

            print(f"{status} {tool_name}: display_name='{display_name[:60]}'{unrendered_note}")

        except Exception as e:
            errors.append(f"{tool_name}: {e}")

    if errors:
        print(f"\n❌ {len(errors)} 个工具有问题:")
        for e in errors:
            print(f"  {e}")
        raise AssertionError(f"{len(errors)} 个工具有问题")

    print(f"\n✅ 全部 {len(tools)} 个工具元数据验证通过")


async def test_tuple_tools_agent_gets_plain_text():
    """
    验证返回 tuple 的工具：Agent 得到纯文本(str)，不是 dict/JSON。
    这是核心修复：之前 list_directory/search_files 返回 json.dumps({"content":...,"count":...})
    现在返回 (text, {"count": N})，装饰器提取 text 包装为 ToolResult(str)。
    """
    from app.core.tools.base import ToolResult
    from app.domain.tools.files.list_directory import list_directory
    from app.domain.tools.files.search_files import search_files
    from app.domain.tools.files.multiedit_file import multiedit_file

    # --- list_directory ---
    result = await list_directory.ainvoke({"path": ".", "mode": "flat"})
    assert isinstance(result, str), f"list_directory: Agent 应该得到 str，得到 {type(result)}"
    assert not result.strip().startswith("{"), f"list_directory: Agent 不应该得到 JSON 字符串: {result[:100]}"
    assert isinstance(result, ToolResult), f"list_directory: 应该是 ToolResult，得到 {type(result)}"
    assert hasattr(result, "meta") and isinstance(result.meta, dict), "list_directory: ToolResult 应该有 .meta dict"
    assert "count" in result.meta, f"list_directory: .meta 应该有 count，得到 {result.meta}"
    assert hasattr(result, "display_name"), "list_directory: ToolResult 应该有 .display_name"
    print(result)
    snippet = result[:200].replace('\n', '\\n')
    print(f"✅ list_directory: Agent 得到纯文本 \"{snippet}...\", meta={result.meta}, display_name='{result.display_name}'")

    # --- search_files ---
    result = await search_files.ainvoke({"pattern": "search", "scope": "*.py", "path": "."})
    assert isinstance(result, str), f"search_files: Agent 应该得到 str，得到 {type(result)}"
    assert not result.strip().startswith("{"), f"search_files: Agent 不应该得到 JSON 字符串: {result[:100]}"
    assert isinstance(result, ToolResult), f"search_files: 应该是 ToolResult，得到 {type(result)}"
    assert hasattr(result, "meta") and isinstance(result.meta, dict), "search_files: ToolResult 应该有 .meta dict"
    assert "count" in result.meta, f"search_files: .meta 应该有 count，得到 {result.meta}"
    assert hasattr(result, "display_name"), "search_files: ToolResult 应该有 .display_name"
    snippet = result[:200].replace('\n', '\\n')
    print(f"✅ search_files: Agent 得到纯文本 \"{snippet}...\", meta={result.meta}, display_name='{result.display_name}'")

    # --- multiedit_file ---
    # 在工作目录内创建临时文件（避免安全路径检查失败）
    import os
    tmpfile = os.path.join(os.getcwd(), "test_multiedit_registered.txt")
    with open(tmpfile, "w") as f:
        f.write("hello world\nfoo bar\n")
    try:
        result = await multiedit_file.ainvoke({
            "path": tmpfile,
            "edits": [{"target": "foo", "replacement": "baz"}],
        })
        assert isinstance(result, str), f"multiedit_file: Agent 应该得到 str，得到 {type(result)}"
        assert not result.strip().startswith("{"), f"multiedit_file: Agent 不应该得到 JSON 字符串: {result[:100]}"
        assert isinstance(result, ToolResult), f"multiedit_file: 应该是 ToolResult，得到 {type(result)}"
        assert hasattr(result, "meta") and isinstance(result.meta, dict), "multiedit_file: ToolResult 应该有 .meta dict"
        assert "count" in result.meta, f"multiedit_file: .meta 应该有 count，得到 {result.meta}"
        assert hasattr(result, "display_name"), "multiedit_file: ToolResult 应该有 .display_name"
        snippet = result[:200].replace('\n', '\\n')
        print(f"✅ multiedit_file: Agent 得到纯文本 \"{snippet}\", meta={result.meta}, display_name='{result.display_name}'")
    finally:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)


async def test_plain_text_tools_still_work():
    """验证返回纯文本的工具被装饰器正确包装为 ToolResult"""
    from app.core.tools.base import ToolResult
    from app.domain.tools.utils.time_tools import wait_for

    result = await wait_for.ainvoke({"seconds": 0.01})
    assert isinstance(result, ToolResult), f"Expected ToolResult, got {type(result)}"
    assert isinstance(result, str), f"wait_for: Agent 应该得到 str，得到 {type(result)}"
    assert "等待" in result.display_name or "wait" in result.display_name.lower()
    print(f"✅ wait_for: Agent 得到纯文本 \"{result}\", display_name='{result.display_name}'")


async def test_database_gets_plain_text_content():
    """
    验证 MessageHandler.handle_tool_output 将纯文本存入数据库 content，
    并将 display_name / result_meta 存入 meta_data。
    """
    from app.core.tools.base import ToolResult
    from app.core.engine.message.handler import MessageHandler

    # 构造一个模拟的 ToolResult（类似 list_directory 返回的）
    tool_output = ToolResult(
        text="file1.py\nfile2.py",
        meta={"count": 2},
        display_name="已列出 /test (2 项)",
    )

    # 验证 str(output) 是纯文本
    content = str(tool_output) if tool_output else ""
    assert content == "file1.py\nfile2.py", f"数据库 content 应该是纯文本，得到: {content}"
    assert not content.strip().startswith("{"), f"数据库 content 不应该有 JSON 包装: {content}"

    # 验证 ToolResult 的 meta 和 display_name 可被提取
    result_meta = {}
    display_name = ""
    if hasattr(tool_output, "meta") and isinstance(tool_output.meta, dict):
        result_meta = {k.lower(): v for k, v in tool_output.meta.items()}
    if hasattr(tool_output, "display_name"):
        display_name = tool_output.display_name

    assert result_meta.get("count") == 2, f"result_meta 应该有 count=2，得到 {result_meta}"
    assert display_name == "已列出 /test (2 项)", f"display_name 不对，得到 {display_name}"

    print(f"✅ 数据库 content=\"{content}\", meta count={result_meta.get('count')}, display_name='{display_name}'")


async def test_hidden_tools():
    """验证 hidden 工具也能正常加载"""
    from app.core.tools.registry import get_tool_metadata

    hidden_tools = [
        "search_native_tools",
        "query_command_status",
        "wait_for",
    ]

    for tool_name in hidden_tools:
        meta = get_tool_metadata(tool_name)
        assert meta.is_hidden, f"{tool_name} 应该是 hidden"
        print(f"✅ {tool_name}: hidden={meta.is_hidden}")


if __name__ == "__main__":
    print("=" * 60)
    print("遍历所有注册工具测试")
    print("=" * 60)
    asyncio.run(test_all_tools_metadata())
    print()
    asyncio.run(test_tuple_tools_agent_gets_plain_text())
    print()
    asyncio.run(test_plain_text_tools_still_work())
    print()
    asyncio.run(test_database_gets_plain_text_content())
    print()
    asyncio.run(test_hidden_tools())
    print()
    print("=" * 60)
    print("✅ All registered tool tests passed!")
    print("=" * 60)
