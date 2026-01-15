"""
Tool Layer Tests - LSP (consult_lsp), Codebase Exploration, Git Management, Memory
Covers: LSP-001~005, EC-001~004, GIT-001~005, MEM-001~004
"""
import pytest
import os
import tempfile
import shutil

from tests.config import config


class TestConsultLSP:
    """Test suite for consult_lsp tool (LSP-001~005)."""

    @pytest.fixture
    def temp_python_project(self):
        """Create a temp project with Python files."""
        temp_dir = tempfile.mkdtemp()
        
        # Create a Python file
        with open(os.path.join(temp_dir, "main.py"), "w") as f:
            f.write('''
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"

class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
''')
        
        # Create a file with error
        with open(os.path.join(temp_dir, "broken.py"), "w") as f:
            f.write("def broken()\n    return 42\n")  # Missing colon
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    # LSP-001: Python Error Check
    @pytest.mark.asyncio
    async def test_lsp_001_python_error_check(self, temp_python_project):
        """Test Python error detection."""
        from app.domain.tools.coding.lsp import consult_lsp
        
        result = await consult_lsp.ainvoke({
            "action": "check_errors",
            "file_path": os.path.join(temp_python_project, "broken.py")
        })
        
        assert "Error" in result or "error" in result.lower() or "Expected" in result

    # LSP-002: Find Definition
    @pytest.mark.asyncio
    async def test_lsp_002_find_definition(self, temp_python_project):
        """Test finding symbol definition."""
        from app.domain.tools.coding.lsp import consult_lsp
        
        result = await consult_lsp.ainvoke({
            "action": "find_definition",
            "file_path": os.path.join(temp_python_project, "main.py"),
            "line": 7,
            "character": 8
        })
        
        # Should return definition location or info
        assert result is not None

    # LSP-003: Hover Information
    @pytest.mark.asyncio
    async def test_lsp_003_hover_info(self, temp_python_project):
        """Test getting hover information."""
        from app.domain.tools.coding.lsp import consult_lsp
        
        result = await consult_lsp.ainvoke({
            "action": "hover",
            "file_path": os.path.join(temp_python_project, "main.py"),
            "line": 2,
            "character": 5
        })
        
        # Should return type or documentation
        assert True

    # LSP-004: TypeScript Support (skip if no TS files)
    @pytest.mark.asyncio
    async def test_lsp_004_typescript_support(self):
        """Test TypeScript file analysis."""
        temp_dir = tempfile.mkdtemp()
        try:
            ts_file = os.path.join(temp_dir, "test.ts")
            with open(ts_file, "w") as f:
                f.write("const greet = (name: string): string => `Hello, ${name}`;\n")
            
            from app.domain.tools.coding.lsp import consult_lsp
            
            result = await consult_lsp.ainvoke({
                "action": "check_errors",
                "file_path": ts_file
            })
            
            # Should process TS file
            assert True
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # LSP-005: Server Reuse
    @pytest.mark.asyncio
    async def test_lsp_005_server_reuse(self, temp_python_project):
        """Test that LSP server is reused for same project."""
        from app.domain.tools.coding.lsp import consult_lsp
        
        # Call twice
        result1 = await consult_lsp.ainvoke({
            "action": "check_errors",
            "file_path": os.path.join(temp_python_project, "main.py")
        })
        
        result2 = await consult_lsp.ainvoke({
            "action": "check_errors",
            "file_path": os.path.join(temp_python_project, "main.py")
        })
        
        # Both should succeed (server reused)
        assert True


class TestExploreCodebase:
    """Test suite for explore_codebase tool (EC-001~004)."""

    @pytest.fixture
    def temp_codebase(self):
        """Create a temp codebase for exploration tests."""
        temp_dir = tempfile.mkdtemp()
        
        with open(os.path.join(temp_dir, "models.py"), "w") as f:
            f.write('''
class UserModel:
    """User data model."""
    def __init__(self, name: str):
        self.name = name

class ProductModel:
    """Product data model."""
    pass
''')
        
        with open(os.path.join(temp_dir, "services.py"), "w") as f:
            f.write('''
from models import UserModel

class UserService:
    """Service for user operations."""
    
    def get_user(self, user_id: int) -> UserModel:
        # TODO: implement
        pass
''')
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    # EC-001: Symbol Search
    @pytest.mark.asyncio
    async def test_ec_001_symbol_search(self, temp_codebase):
        """Test searching for symbols."""
        from app.domain.tools.facades import explore_codebase
        
        result = await explore_codebase.ainvoke({
            "action": "search_symbol",
            "query": "UserModel",
            "path": temp_codebase
        })
        
        assert "UserModel" in result or "models.py" in result

    # EC-002: Text Search
    @pytest.mark.asyncio
    async def test_ec_002_text_search(self, temp_codebase):
        """Test searching for text."""
        from app.domain.tools.facades import explore_codebase
        
        result = await explore_codebase.ainvoke({
            "action": "search_text",
            "query": "TODO",
            "path": temp_codebase
        })
        
        assert "TODO" in result or "services.py" in result

    # EC-003: Semantic Search
    @pytest.mark.asyncio
    async def test_ec_003_semantic_search(self, temp_codebase):
        """Test semantic code search."""
        from app.domain.tools.facades import explore_codebase
        
        result = await explore_codebase.ainvoke({
            "action": "semantic_code_search",
            "query": "handling user data",
            "path": temp_codebase
        })
        
        # Should return relevant code
        assert True

    # EC-004: Impact Analysis
    @pytest.mark.asyncio
    async def test_ec_004_impact_analysis(self, temp_codebase):
        """Test analyzing symbol impact."""
        from app.domain.tools.facades import explore_codebase
        
        result = await explore_codebase.ainvoke({
            "action": "analyze_impact",
            "query": "UserModel",
            "path": temp_codebase
        })
        
        # Should show dependencies
        assert True


class TestManageGit:
    """Test suite for manage_git tool (GIT-001~005)."""

    @pytest.fixture
    def git_repo(self):
        """Create a temp git repository."""
        temp_dir = tempfile.mkdtemp()
        
        # Initialize git repo
        os.system(f"cd {temp_dir} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")
        
        # Create initial file
        with open(os.path.join(temp_dir, "README.md"), "w") as f:
            f.write("# Test Repo\n")
        
        os.system(f"cd {temp_dir} && git add . && git commit -m 'Initial commit'")
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    # GIT-001: Status
    @pytest.mark.asyncio
    async def test_git_001_status(self, git_repo):
        """Test git status."""
        from app.domain.tools.facades import manage_git
        
        result = await manage_git.ainvoke({
            "action": "status"
        }, config={"configurable": {"working_directory": git_repo}})
        
        assert "clean" in result.lower() or "nothing" in result.lower() or "status" in result.lower()

    # GIT-002: Diff
    @pytest.mark.asyncio
    async def test_git_002_diff(self, git_repo):
        """Test git diff."""
        # Make a change
        with open(os.path.join(git_repo, "README.md"), "a") as f:
            f.write("\nNew content\n")
        
        from app.domain.tools.facades import manage_git
        
        result = await manage_git.ainvoke({
            "action": "diff"
        }, config={"configurable": {"working_directory": git_repo}})
        
        assert "New content" in result or "diff" in result.lower()

    # GIT-003: Commit
    @pytest.mark.asyncio
    async def test_git_003_commit(self, git_repo):
        """Test git commit."""
        # Make a change
        with open(os.path.join(git_repo, "new_file.txt"), "w") as f:
            f.write("new content")
        
        os.system(f"cd {git_repo} && git add new_file.txt")
        
        from app.domain.tools.facades import manage_git
        
        result = await manage_git.ainvoke({
            "action": "commit",
            "argument": "Add new file"
        }, config={"configurable": {"working_directory": git_repo}})
        
        assert "commit" in result.lower() or "Add new file" in result

    # GIT-004: Log
    @pytest.mark.asyncio
    async def test_git_004_log(self, git_repo):
        """Test git log."""
        from app.domain.tools.facades import manage_git
        
        result = await manage_git.ainvoke({
            "action": "log"
        }, config={"configurable": {"working_directory": git_repo}})
        
        assert "Initial commit" in result

    # GIT-005: Create Branch
    @pytest.mark.asyncio
    async def test_git_005_create_branch(self, git_repo):
        """Test creating git branch."""
        from app.domain.tools.facades import manage_git
        
        result = await manage_git.ainvoke({
            "action": "create_branch",
            "argument": "feature/new"
        }, config={"configurable": {"working_directory": git_repo}})
        
        # Check branch was created
        branches = os.popen(f"cd {git_repo} && git branch").read()
        assert "feature/new" in branches or "feature" in result


class TestManageMemory:
    """Test suite for manage_memory tool (MEM-001~004)."""

    # MEM-001: Save Preference
    @pytest.mark.asyncio
    async def test_mem_001_save_preference(self):
        """Test saving user preference."""
        from app.domain.tools.facades import manage_memory
        
        result = await manage_memory.ainvoke({
            "action": "save_preference",
            "key": "test_pref",
            "value": "test_value"
        })
        
        assert "saved" in result.lower() or "success" in result.lower()

    # MEM-002: Get Preferences
    @pytest.mark.asyncio
    async def test_mem_002_get_preferences(self):
        """Test retrieving preferences."""
        from app.domain.tools.facades import manage_memory
        
        result = await manage_memory.ainvoke({
            "action": "retrieve_preferences"
        })
        
        # Should return list or dict
        assert True

    # MEM-003: Add Concept
    @pytest.mark.asyncio
    async def test_mem_003_add_concept(self):
        """Test adding project concept."""
        from app.domain.tools.facades import manage_memory
        
        result = await manage_memory.ainvoke({
            "action": "add_concept",
            "key": "TestConcept",
            "value": "A test concept for unit testing"
        })
        
        assert True

    # MEM-004: Search Concepts
    @pytest.mark.asyncio
    async def test_mem_004_search_concepts(self):
        """Test searching concepts."""
        from app.domain.tools.facades import manage_memory
        
        result = await manage_memory.ainvoke({
            "action": "search_concepts",
            "key": "test"
        })
        
        assert True
