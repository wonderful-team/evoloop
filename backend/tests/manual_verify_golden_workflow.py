"""
手动验证脚本：测试 Agent 黄金工作流 (Locate -> Inspect -> Modify) 
并验证文件工具的 Rewind (回撤) 集成。

验证范围：
- write_file
- grep_search
- read_file
- edit_file
- move_file
- delete_file
"""

import asyncio
import hashlib
import os
import sys
import uuid
from unittest.mock import patch, MagicMock

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.tools.files.write_file import write_file
from app.domain.tools.files.edit_file import edit_file
from app.domain.tools.files.grep_search import grep_search
from app.domain.tools.files.read_file import read_file
from app.domain.tools.files.move_file import move_file
from app.domain.tools.files.delete_file import delete_file

from app.core.context import ContextManager, EvoContext

# 记录 mock 的持久化调用
persisted_operations = []

async def mock_persist_file_operation_task(*args, **kwargs):
    persisted_operations.append(kwargs)
    print(f"  [Rewind Persistence Triggered] Operation: {kwargs.get('operation')} on {kwargs.get('file_path')}")

def make_test_file(content: str) -> str:
    """在工作目录创建临时测试文件"""
    root = os.path.abspath(os.getcwd())
    path = os.path.join(root, f"_test_golden_{uuid.uuid4().hex}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def cleanup(path: str):
    if path and os.path.exists(path):
        os.unlink(path)

async def test_golden_workflow():
    print("\n" + "=" * 60)
    print("TEST: Golden Workflow & Rewind Integration")
    print("=" * 60)

    # 清空记录
    persisted_operations.clear()

    # 初始化虚拟上下文 (模拟 Agent 正在执行)
    ctx = EvoContext(thread_id="test_thread_123", run_id="test_run_456")
    ctx.current_tool_call_id = "call_abc123"
    token = ContextManager.set(ctx)

    try:
        # Patch the persistence function across modules that use it
        with patch('app.domain.tools.files.write_file.persist_file_operation_task', new=mock_persist_file_operation_task), \
             patch('app.domain.tools.files.edit_file.persist_file_operation_task', new=mock_persist_file_operation_task), \
             patch('app.domain.tools.files.move_file.persist_file_operation_task', new=mock_persist_file_operation_task), \
             patch('app.domain.tools.files.delete_file.persist_file_operation_task', new=mock_persist_file_operation_task):

            # -----------------------------------------------------
            # 1. Write File (Create)
            # -----------------------------------------------------
            print("\n--- 1. write_file (Create) ---")
            root = os.path.abspath(os.getcwd())
            filename = f"test_gw_{uuid.uuid4().hex}.txt"
            path = os.path.join(root, filename)
            content = "def hello():\n    print('world')\n"
            
            result_write = await write_file.ainvoke({
                "path": path,
                "content": content,
                "overwrite": False
            })
            print(f"Write result: {result_write}")
            assert "success" in result_write.lower() or "✅" in result_write or "成功" in result_write
            assert len(persisted_operations) == 1
            assert persisted_operations[-1]["operation"] == "ADD"

            # -----------------------------------------------------
            # 2. grep_search (Locate)
            # -----------------------------------------------------
            print("\n--- 2. grep_search (Locate) ---")
            search_res = await grep_search.ainvoke({
                "pattern": "def hello",
                "search_in_name": False
            })
            assert filename in str(search_res), f"未找到文件: {search_res}"

            # -----------------------------------------------------
            # 3. Read File (Inspect)
            # -----------------------------------------------------
            print("\n--- 3. read_file (Inspect) ---")
            result_read = await read_file.ainvoke({
                "path": path,
            })
            assert "print('world')" in result_read

            # -----------------------------------------------------
            # 4. Edit File (Modify)
            # -----------------------------------------------------
            print("\n--- 4. edit_file (Modify) ---")
            result_edit = await edit_file.ainvoke({
                "path": path,
                "target": "    print('world')",
                "replacement": "    print('evoloop')",
            })
            print(f"Edit result: {result_edit}")
            assert "success" in result_edit.lower() or "✅" in result_edit or "成功" in result_edit
            assert len(persisted_operations) == 2
            assert persisted_operations[-1]["operation"] == "EDIT"
            assert persisted_operations[-1]["original_content"] == content # 应该能回撤到原始内容

            # -----------------------------------------------------
            # 5. Move File (Rename)
            # -----------------------------------------------------
            print("\n--- 5. move_file (Rename) ---")
            new_path = path + ".renamed"
            result_move = await move_file.ainvoke({
                "source": path,
                "destination": new_path
            })
            print(f"Move result: {result_move}")
            assert "success" in result_move.lower() or "✅" in result_move or "成功" in result_move
            assert len(persisted_operations) == 4
            assert persisted_operations[-2]["operation"] == "DELETE"
            assert persisted_operations[-1]["operation"] == "ADD"
            assert not os.path.exists(path)
            assert os.path.exists(new_path)

            # -----------------------------------------------------
            # 6. Delete File (Remove)
            # -----------------------------------------------------
            print("\n--- 6. delete_file (Remove) ---")
            result_delete = await delete_file.ainvoke({
                "path": new_path,
                "confirm": True
            })
            print(f"Delete result: {result_delete}")
            assert "success" in result_delete.lower() or "✅" in result_delete or "成功" in result_delete
            assert len(persisted_operations) == 5
            assert persisted_operations[-1]["operation"] == "DELETE"
            assert not os.path.exists(new_path)

            print("\n✅ Golden Workflow and Rewind Integration Test Passed!")
            return True

    finally:
        ContextManager.reset(token)
        cleanup(path)
        cleanup(path + ".renamed")

async def main():
    success = await test_golden_workflow()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
