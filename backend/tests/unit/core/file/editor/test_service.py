import pytest
import os
import shutil
from app.core.file.editor.service import FileEditorService
from app.core.file.editor.models import FileEditOperation, MatchConfidence

@pytest.fixture
def test_workspace():
    path = "temp_test_workspace"
    os.makedirs(path, exist_ok=True)
    yield path
    if os.path.exists(path):
        shutil.rmtree(path)

@pytest.mark.asyncio
async def test_preview_edit_success(test_workspace):
    file_path = os.path.join(test_workspace, "test.py")
    content = "def foo():\n    return 42\n"
    with open(file_path, "w") as f:
        f.write(content)
    
    result = await FileEditorService.preview_edit(
        path="test.py",
        target="return 42",
        replacement="return 100",
        absolute_path=file_path
    )
    
    assert result.success is True
    assert result.confidence == MatchConfidence.HIGH
    assert "return 100" in result.new_content
    assert "diff" in result.diff or "@@" in result.diff

@pytest.mark.asyncio
async def test_apply_edits_atomic(test_workspace):
    file_path = os.path.join(test_workspace, "test.py")
    content = "a = 1\nb = 2\nc = 3\n"
    with open(file_path, "w") as f:
        f.write(content)
    
    edits = [
        FileEditOperation(target="a = 1", replacement="a = 10"),
        FileEditOperation(target="b = 2", replacement="b = 20")
    ]
    
    result = await FileEditorService.apply_edits(
        absolute_path=file_path,
        edits=edits,
        display_path="test.py"
    )
    
    assert result["success"] is True
    assert result["applied_edits"] == 2
    
    with open(file_path, "r") as f:
        new_content = f.read()
    assert "a = 10" in new_content
    assert "b = 20" in new_content
    assert "c = 3" in new_content

@pytest.mark.asyncio
async def test_apply_edits_failure_rollback(test_workspace):
    file_path = os.path.join(test_workspace, "test.py")
    content = "a = 1\nb = 2\n"
    with open(file_path, "w") as f:
        f.write(content)
    
    # Second edit will fail
    edits = [
        FileEditOperation(target="a = 1", replacement="a = 10"),
        FileEditOperation(target="NON_EXISTENT", replacement="fail")
    ]
    
    result = await FileEditorService.apply_edits(
        absolute_path=file_path,
        edits=edits
    )
    
    assert result["success"] is False
    assert "failed validation" in result["message"]
    
    # File should remain unchanged (atomicity)
    with open(file_path, "r") as f:
        new_content = f.read()
    assert new_content == content
    assert "a = 10" not in new_content

@pytest.mark.asyncio
async def test_fuzzy_matching_integration(test_workspace):
    file_path = os.path.join(test_workspace, "test.py")
    # Content with specific indentation
    content = "class MyClass:\n    def method(self):\n        print('hello')\n"
    with open(file_path, "w") as f:
        f.write(content)
    
    # Target with slightly different indentation/spacing
    # Note: IndentationFlexibleReplacer should handle this
    result = await FileEditorService.preview_edit(
        path="test.py",
        target="def method(self):\nprint('hello')", # Missing 8 spaces
        replacement="def method(self):\n        print('world')",
        absolute_path=file_path
    )
    
    assert result.success is True
    # The system might use line_trimmed_replacer first as it's earlier in the strategy list
    assert result.strategy_used in ["indentation_flexible_replacer", "line_trimmed_replacer"]
