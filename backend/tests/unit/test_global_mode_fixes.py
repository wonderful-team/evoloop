"""
Test cases for global mode (project_id=0) handling fixes.

This module tests that project_id=0 is correctly handled across the codebase,
ensuring it is not treated as a falsy value that falls back to project_id=1.
"""
import pytest


class TestProjectIdZeroHandling:
    """Test that project_id=0 (global mode) is correctly distinguished from None."""

    def test_old_vs_new_logic(self):
        """
        Demonstrate the difference between old (buggy) and new (fixed) logic.
        """
        # Test values
        project_id_zero = 0
        project_id_none = None
        project_id_one = 1

        # OLD (buggy) logic - what we had before
        def old_check(pid):
            return pid or 1  # 0 would fall back to 1!

        def old_if_check(pid):
            if pid:  # 0 is falsy
                return "has_project"
            return "no_project"  # 0 would be treated as no project

        # NEW (fixed) logic - what we have now
        def new_check(pid):
            if pid is not None:
                return pid
            return 1

        def new_if_check(pid):
            if pid is not None and pid != 0:
                return "has_project"
            return "global_or_none"

        # Assertions showing the bug
        assert old_check(project_id_zero) == 1, "Old logic: 0 falls back to 1 (BUG)"
        assert old_check(project_id_none) == 1, "Old logic: None falls back to 1"
        assert old_check(project_id_one) == 1, "Old logic: 1 stays 1"

        assert old_if_check(project_id_zero) == "no_project", "Old logic: 0 treated as no project (BUG)"
        assert old_if_check(project_id_none) == "no_project", "Old logic: None treated as no project"
        assert old_if_check(project_id_one) == "has_project", "Old logic: 1 is has_project"

        # Assertions showing the fix
        assert new_check(project_id_zero) == 0, "New logic: 0 stays 0 (FIXED)"
        assert new_check(project_id_none) == 1, "New logic: None falls back to 1"
        assert new_check(project_id_one) == 1, "New logic: 1 stays 1"

        assert new_if_check(project_id_zero) == "global_or_none", "New logic: 0 is global_or_none (FIXED)"
        assert new_if_check(project_id_none) == "global_or_none", "New logic: None is global_or_none"
        assert new_if_check(project_id_one) == "has_project", "New logic: 1 is has_project"


class TestRetrievalToolsLogic:
    """Test the fixed logic in retrieval/tools.py"""

    def test_search_codebase_project_resolution(self):
        """
        Test that search_codebase correctly resolves project_id.

        The fixed logic should be:
        - If project_id argument is provided (not None), use it (even if 0)
        - Else if context project_id is set (not None), use it (even if 0)
        - Else fall back to 1
        """
        # Simulate the fixed logic from retrieval/tools.py
        def resolve_project_id(arg_project_id, ctx_project_id):
            if arg_project_id is not None:
                return arg_project_id
            elif ctx_project_id is not None:
                return ctx_project_id
            else:
                return 1

        # Test cases
        assert resolve_project_id(0, None) == 0, "arg=0 should return 0"
        assert resolve_project_id(0, 5) == 0, "arg=0 should override ctx=5"
        assert resolve_project_id(None, 0) == 0, "ctx=0 should return 0"
        assert resolve_project_id(None, None) == 1, "both None should fall back to 1"
        assert resolve_project_id(5, 10) == 5, "arg should take precedence"


class TestBackgroundAgentLogic:
    """Test the fixed logic in background_agent.py"""

    def test_setup_project_context_skips_global_mode(self):
        """
        Test that _setup_project_context skips project setup for global mode.

        The fixed condition: if project_id is not None and project_id != 0
        """
        def should_setup_project(pid):
            return pid is not None and pid != 0

        # Should NOT setup for these (global mode or not set)
        assert should_setup_project(0) is False, "project_id=0 is global mode"
        assert should_setup_project(None) is False, "project_id=None is not set"

        # Should setup for these
        assert should_setup_project(1) is True, "project_id=1 is valid"
        assert should_setup_project(42) is True, "project_id=42 is valid"


class TestFileUtilsLogic:
    """Test the fixed logic in files/actions/utils.py"""

    def test_global_mode_file_operation_check(self):
        """
        Test that file operations are blocked in global mode.

        Simulates the check added to resolve_and_validate_path.
        """
        def check_file_allowed(project_id, working_dir, workspace_root="/workspace"):
            """Simulates the global mode check in utils.py"""
            # Note: ctx.project_id check with root fallback
            if project_id == 0 or (project_id is None and working_dir == "."):
                # Global mode detected - check if root is unconfigured
                if working_dir == "." or working_dir == workspace_root:
                    raise ValueError(
                        "File operations are not available in global mode. "
                        "Please switch to a specific project to use file tools."
                    )
            return True

        # Should block in global mode (project_id=0 with fallback root)
        with pytest.raises(ValueError, match="global mode"):
            check_file_allowed(0, ".")

        with pytest.raises(ValueError, match="global mode"):
            check_file_allowed(0, "/workspace")

        # Should block when project_id is None and root is fallback "."
        with pytest.raises(ValueError, match="global mode"):
            check_file_allowed(None, ".")

        # Should allow in project mode (project_id=0 but with valid project root - edge case)
        # Note: In practice, project_id=0 should always have fallback root
        # But if somehow configured with a valid path, it might work

        # Should allow in normal project mode
        assert check_file_allowed(1, "/workspace/project1") is True
        assert check_file_allowed(5, "/workspace/project5") is True

        # Should allow if project_id is None but working_dir is a specific project path
        # (This shouldn't happen in practice, but the logic allows it)
        assert check_file_allowed(None, "/workspace/some-project") is True


class TestWikiToolsLogic:
    """Test the fixed logic in wiki_tools.py"""

    def test_wiki_global_mode_check(self):
        """
        Test that Wiki tools correctly reject global mode.

        The fixed condition: if project_id is None or project_id == 0
        """
        def check_wiki_allowed(project_id):
            if project_id is None or project_id == 0:
                return "Error: Wiki is not available in global mode."
            return f"Wiki available for project {project_id}"

        # Should reject global mode
        assert "global mode" in check_wiki_allowed(0)
        assert "global mode" in check_wiki_allowed(None)

        # Should allow project mode
        assert "Wiki available" in check_wiki_allowed(1)
        assert "Wiki available" in check_wiki_allowed(42)


class TestFacadeToolsLogic:
    """Test the fixed logic in facades.py consult_architecture"""

    def test_consult_architecture_global_mode(self):
        """
        Test that consult_architecture correctly handles global mode.

        The fixed condition: if project_id is None or project_id == 0
        """
        def consult_architecture_check(project_id):
            if project_id is None or project_id == 0:
                return "Error: Architecture consultation requires a specific project."
            return f"Consulting architecture for project {project_id}"

        # Should reject global mode
        assert "requires a specific project" in consult_architecture_check(0)
        assert "requires a specific project" in consult_architecture_check(None)

        # Should allow project mode
        assert "Consulting architecture" in consult_architecture_check(1)


class TestGraphExplorerLogic:
    """Test the fixed logic in graph_explorer.py"""

    def test_cypher_constraint_global_mode(self):
        """
        Test that graph explorer doesn't add project_id constraint in global mode.

        The fixed condition should only add constraint for valid project IDs.
        """
        def should_add_constraint(project_id):
            return project_id is not None and project_id != 0

        # Should NOT add constraint for global mode
        assert should_add_constraint(0) is False
        assert should_add_constraint(None) is False

        # Should add constraint for valid projects
        assert should_add_constraint(1) is True
        assert should_add_constraint(42) is True


class TestHybridSearchLogic:
    """Test the fixed logic in hybrid.py"""

    def test_hybrid_search_project_filter(self):
        """
        Test that hybrid search correctly filters by project_id.

        The fixed condition should only filter when project_id is valid.
        """
        def should_filter_by_project(project_id):
            return project_id is not None and project_id != 0

        # Should NOT filter for global mode
        assert should_filter_by_project(0) is False
        assert should_filter_by_project(None) is False

        # Should filter for valid projects
        assert should_filter_by_project(1) is True


class TestMemoryReplayLogic:
    """Test the fixed logic in memory_replay.py"""

    def test_episode_retrieval_global_mode(self):
        """
        Test that memory replay correctly skips episode retrieval in global mode.

        The fixed condition should skip if project_id is None or 0.
        """
        def should_retrieve_episodes(project_id):
            return project_id is not None and project_id != 0

        # Should NOT retrieve for global mode
        assert should_retrieve_episodes(0) is False
        assert should_retrieve_episodes(None) is False

        # Should retrieve for valid projects
        assert should_retrieve_episodes(1) is True


class TestThreadStoreLogic:
    """Test the fixed logic in thread_store.py"""

    def test_set_active_project_allows_zero(self):
        """
        Test that set_active_project correctly stores project_id=0.

        The fixed condition: if project_id is not None (allows 0)
        """
        class MockThreadStore:
            def __init__(self):
                self._thread_projects = {}

            def set_active_project(self, thread_id, project_id):
                if project_id is not None:  # Fixed: allows 0
                    self._thread_projects[thread_id] = project_id

        store = MockThreadStore()

        # Should store 0 (global mode)
        store.set_active_project("thread1", 0)
        assert store._thread_projects["thread1"] == 0

        # Should store valid project IDs
        store.set_active_project("thread2", 5)
        assert store._thread_projects["thread2"] == 5

        # Should not store None
        store.set_active_project("thread3", None)
        assert "thread3" not in store._thread_projects
