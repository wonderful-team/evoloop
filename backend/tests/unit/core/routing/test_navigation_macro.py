"""Navigation macro detection used by the routing action layer."""

from app.core.execution.macro.runner import is_navigation_macro
from app.models.macro import Macro


class TestIsNavigationMacro:
    def test_old_plain_list_format(self):
        macro = Macro(
            id=1,
            name="显示主界面",
            description="",
            trigger_patterns=[],
            parameters=[],
            macro_script="""
- event_type: frontend_navigate
  payload:
    route: /chat
  source: desktop
  type: action
""",
        )
        assert is_navigation_macro(macro) == "/chat"

    def test_new_metadata_wrapped_format(self):
        macro = Macro(
            id=2,
            name="打开项目管理",
            description="",
            trigger_patterns=[],
            parameters=[],
            macro_script="""version: '1.0'
metadata:
  format: evoloop-macro
  step_count: 1
steps:
- event_type: frontend_navigate
  payload:
    route: /projects
  source: desktop
  type: action
""",
        )
        assert is_navigation_macro(macro) == "/projects"

    def test_non_navigation_macro_returns_none(self):
        macro = Macro(
            id=3,
            name="静音",
            description="",
            trigger_patterns=[],
            parameters=[],
            macro_script="""version: '1.0'
metadata:
  format: evoloop-macro
  step_count: 1
steps:
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: set volume with output muted
""",
        )
        assert is_navigation_macro(macro) is None

    def test_invalid_yaml_returns_none(self):
        macro = Macro(
            id=4,
            name="broken",
            description="",
            trigger_patterns=[],
            parameters=[],
            macro_script="not: [valid yaml: : :",
        )
        assert is_navigation_macro(macro) is None

    def test_empty_script_returns_none(self):
        macro = Macro(
            id=5,
            name="empty",
            description="",
            trigger_patterns=[],
            parameters=[],
            macro_script="",
        )
        assert is_navigation_macro(macro) is None
