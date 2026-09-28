"""Prompt template full-scan tests.

Scans every Jinja2 template in ``app/config/templates`` and asserts that:

1. No template references **obsolete/renamed** tool names (e.g. the old
   ``read_skill_sop`` which became ``get_skill``).
2. Every known tool-name reference found in a template is a **currently
   registered** tool name. The set of current tools is derived dynamically
   from ``@evoloop_tool`` decorators in the codebase (plus a static fallback
   for tools registered via other mechanisms), so a future rename automatically
   exposes stale template references.

Also keeps direct render tests for the core prompt templates so that
rendering failures (undefined vars, Jinja syntax errors) are caught.
"""

import re
from pathlib import Path

import pytest

from app.utils.template import render_template

TEMPLATES_DIR = Path(__file__).parents[3] / "app" / "config" / "templates"
APP_DIR = TEMPLATES_DIR.parents[1]  # app/

#: Tool names that used to exist but have been renamed/removed.
#: Templates MUST NOT reference these. Word-boundary matched.
OBSOLETE_TOOLS = {
    "read_skill_sop",  # → get_skill
    "synthesize_skill",  # → create_skill_from_session
    "execute_skill",  # → run_skill (backend handler)
    "cancel_voice_task",  # removed
    "route_by_next_node",  # removed
    "route_to",  # removed (graph-era dispatch tool, replaced by task)
    "run_single_shot",  # removed
    "create_skill",  # removed (replaced by create_skill_from_session)
    "update_skill_from_prompt",  # removed (replaced by update_skill)
    "todo",  # removed (todo domain retired; plan is the only work checklist)
    "create_todo",  # removed (todo domain retired)
    "list_todos",  # removed (todo domain retired)
    "complete_todo",  # removed (todo domain retired)
    "cancel_todo",  # removed (todo domain retired)
    # ---- 2026-09 工具面收敛删除（详见 docs/dead-code-report-2026-09.md）----
    "analyze_feasibility",
    "clear_app_atlas",
    "list_app_atlas",
    "list_app_maps",
    "query_app_atlas",
    "read_app_map",
    "write_app_map",
    "find_element",
    "get_app_usage_ranker",
    "quick_check_screen",
    "verify_ui_state",
    "auto_harvest_from_git",
    "delete_skill",
    "get_skill",
    "list_skills",
    "update_skill",
    "reconcile_skill",
    "delete_macro",
    "list_macros",
    "read_macro",
    "update_macro",
    "query_command_status",
    "create_python_tool",
    # ---- 2026-09 工具面收敛·二批（零接线直删，见 dead-code-report §6.3）----
    "query_code_chunks",
    "query_code_relations",
    "query_security_findings",
    "query_source_files",
    "query_excel_sql",
    "wait_for",
    # ---- 2026-09 工具面收敛·三批（macro facade 吸收独立工具 + skill 候选下线）----
    "run_macro",
    "create_macro",
    "create_skill_from_session",
}

#: Static fallback: tools registered via mechanisms the dynamic scan cannot
#: see (legacy decorators, aliases). Tools that the dynamic @evoloop_tool scan
#: CAN discover must NOT be listed here, otherwise a future rename would be
#: masked by this fallback.
STATIC_TOOLS = {
    # tools not discoverable by the textual @evoloop_tool scan
    "remember", "recall", "search_history",
    "create_plan", "update_step_status",
    "clipboard", "open_app", "list_devices",
    # aliases / internal-only
    "search_result", "ask_user",
}


def _scan_registered_tools() -> set[str]:
    """Dynamically derive tool names from ``@evoloop_tool`` decorators."""
    names = set()
    for py in APP_DIR.rglob("*.py"):
        try:
            src = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(r"@evoloop_tool\b", src):
            after = src[m.end() : m.end() + 2000]
            d = re.search(r"async\s+def\s+([a-z_0-9]+)", after)
            if d:
                names.add(d.group(1))
    return names


def _current_tools() -> set[str]:
    return _scan_registered_tools() | STATIC_TOOLS


def _all_templates() -> list[Path]:
    # 提示词已从 .j2 迁移到 .txt（react 引擎），两者都纳入扫描
    return sorted(list(TEMPLATES_DIR.rglob("*.j2")) + list(TEMPLATES_DIR.rglob("*.txt")))


def _tool_references(text: str) -> set[str]:
    """Extract known tool-name references from template text.

    Only tokens that exist in CURRENT ∪ OBSOLETE are considered, avoiding
    false positives on generic English prose.
    """
    current = _current_tools()
    known = current | OBSOLETE_TOOLS
    found = set()
    for m in re.finditer(r"\b[a-z][a-z0-9_]{3,}\b", text):
        token = m.group(0)
        if token in known:
            found.add(token)
    return found


@pytest.fixture(scope="module")
def templates() -> list[tuple[str, str]]:
    """(relative path, raw text) for every template."""
    return [(p.relative_to(TEMPLATES_DIR).as_posix(), p.read_text(encoding="utf-8")) for p in _all_templates()]


class TestObsoleteToolScan:
    """Every template must be free of renamed/removed tool names."""

    def test_no_template_references_obsolete_tools(self, templates):
        offenders = []
        for rel, text in templates:
            for obsolete in OBSOLETE_TOOLS:
                # word-boundary match so `create_skill_from_session` is not
                # flagged by the obsolete `create_skill` entry
                if re.search(rf"\b{re.escape(obsolete)}\b", text):
                    offenders.append((rel, obsolete))
        assert offenders == [], f"Obsolete tool names found in templates: {offenders}"

    def test_scan_covers_all_templates(self, templates):
        # 图架构 .j2 已删除（supervisor/worker/finish），react 改为 .txt；
        # 2026-09-28 级联清理删除 15 个零引用孤儿模板（compaction/planning/
        # project-content/codebase/vision 旧模板等）；
        # 阈值按实际模板数校验，防意外删减。
        assert len(templates) >= 40, f"Unexpectedly few templates, found {len(templates)}"


class TestToolNameConsistency:
    """Any known tool reference inside a template must be currently registered."""

    def test_tool_references_are_current(self, templates):
        current = _current_tools()
        offenders = []
        for rel, text in templates:
            found = _tool_references(text)
            for name in found:
                if name not in current:
                    offenders.append((rel, name))
        assert offenders == [], f"Stale tool references in templates: {offenders}"

    def test_dynamic_scan_discovers_tools(self):
        dynamic = _scan_registered_tools()
        assert len(dynamic) >= 25, f"Dynamic scan found too few tools: {len(dynamic)}"
        # sanity: core tools must be discoverable dynamically
        assert "list_dir" in dynamic
        assert "macro" in dynamic


class TestCorePromptRender:
    """Core prompt templates must render with the expected variables."""

    def _render(self, template: str, **vars) -> str:
        return render_template(template, **vars)


    def test_skill_directive_renders(self):
        rendered = self._render(
            "core/learning/skill_directive.prompt.j2",
            skill_name="test_skill",
            parameters={},
        )
        assert "skill" in rendered
        assert "test_skill" in rendered


