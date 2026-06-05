"""
验证 from_orm 能正确重新渲染历史工具消息的 display_name，
包括含有工具输出结果（如 count）的情况。
"""
import sys
sys.path.insert(0, '.')

from app.core.engine.message.factory import MessageBlockFactory

class MockOrmMsg:
    """模拟数据库中的 Message ORM 对象"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def run_tests():
    print("=" * 60)
    print("验证 MessageBlockFactory.from_orm 历史消息渲染")
    print("=" * 60)
    
    # ─── 测试 1：list_dir 历史消息，含 {count} 未解析 ───
    print("\n[Test 1] list_dir 含 count 参数")
    # 模拟旧的数据库记录：display_name 中 {count} 未渲染
    msg1 = MockOrmMsg(
        id="uuid-1",
        role="tool",
        content='{"content": "file1.py\\nfile2.py\\nfile3.py", "count": 3}',
        tool_name="list_dir",
        tool_call_id="call-1",
        status="completed",
        thread_id="t1",
        created_at=None,
        meta_data={
            "input": {"path": "src/", "recursive": False},
            "output": '{"content": "file list...", "count": 3}',
            # 旧的 display_name 含有未解析占位符 (模拟旧数据)
            "tool_meta": {"display_name": "已列出 'src/' ({count} 项)", "affected_path_keys": ["path"]},
        },
    )
    block1 = MessageBlockFactory.from_orm(msg1)
    dn1 = block1.tool_meta['display_name']
    print(f"  display_name = {dn1!r}")
    if "{count}" not in dn1 and "3" in dn1:
        print("  ✅ PASS: count 占位符已被正确替换")
    elif "{count}" in dn1:
        print("  ❌ FAIL: count 占位符仍未解析")
    else:
        print(f"  ⚠️  WARNING: 结果可能不符合预期，请检查")

    # ─── 测试 2：read_file 历史消息，含 {lines} 未解析 ───
    print("\n[Test 2] read_file 含 start_line/end_line 参数")
    msg2 = MockOrmMsg(
        id="uuid-2",
        role="tool",
        content="def hello(): pass",
        tool_name="read_file",
        tool_call_id="call-2",
        status="completed",
        thread_id="t1",
        created_at=None,
        meta_data={
            "input": {"path": "app/main.py", "start_line": 10, "end_line": 50},
            "output": "def hello(): pass",
            "tool_meta": {"display_name": "已读取 'app/main.py' ({lines} 行)", "affected_path_keys": ["path"]},
        },
    )
    block2 = MessageBlockFactory.from_orm(msg2)
    dn2 = block2.tool_meta['display_name']
    print(f"  display_name = {dn2!r}")
    if "{" not in dn2:
        print("  ✅ PASS: 所有占位符已解析")
    else:
        print("  ❌ FAIL: 仍存在未解析的占位符")

    # ─── 测试 3：search_files 完成后显示搜索结果数量 ───
    print("\n[Test 3] search_files 完成后摘要显示结果数")
    import json
    output_json = json.dumps({"content": "匹配内容...", "count": 17, "pattern": "def handle"})
    msg3 = MockOrmMsg(
        id="uuid-3",
        role="tool",
        content=output_json,
        tool_name="search_files",
        tool_call_id="call-3",
        status="completed",
        thread_id="t1",
        created_at=None,
        meta_data={
            "input": {"pattern": "def handle", "path": "src/"},
            "output": output_json,
            "tool_meta": {"display_name": "搜索代码 'def handle'", "affected_path_keys": ["path"]},
        },
    )
    block3 = MessageBlockFactory.from_orm(msg3)
    dn3 = block3.tool_meta['display_name']
    print(f"  display_name = {dn3!r}")
    if "17" in dn3 or "找到" in dn3:
        print("  ✅ PASS: 搜索结果数量正确显示")
    else:
        print(f"  ⚠️  WARNING: 可能未使用 result_summary_template，检查 zh.json 配置")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
