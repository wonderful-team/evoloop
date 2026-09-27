"""G1 覆盖率契约——元工具时代（2026-09-18 重写）。

架构现状：member-center MCP server 已收敛为 **capability-matrix-mcp 元工具门面**——
业务工具（PHP elements 内 75 个）不再直接暴露，统一经 ``tool_search`` /
``tool_invoke`` 两个元工具访问。包的 ``capability.tools`` 因此只声明
capability-matrix-mcp 元工具，不再逐个声明业务工具（v2 时代的「无孤儿工具」契约失效）。

本契约锁定：
1. 门面唯一性：所有包只声明 capability-matrix-mcp，include 只含元工具；
2. 元工具存在性：mcp-server 侧必须定义 tool_search / tool_invoke；
3. 业务工具防呆：elements 工具数量在合理区间（防止误删/异常改动）；
4. 关键包在场。
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[6]
MCP_SERVER_DIR = _REPO_ROOT / "member-center/backend/mcp-server"
PROJECT_SKILLS_DIR = _REPO_ROOT / "member-center/backend/.evoloop/skills"

ELEMENTS_DIR = MCP_SERVER_DIR / "elements"

META_TOOLS = {"tool_search", "tool_invoke"}
META_SERVER = "capability-matrix-mcp"


def _server_tool_names() -> set[str]:
    """业务工具名 = elements/ 全部 PHP 的 McpTool(name:...) 声明（递归）。"""
    names: set[str] = set()
    for path in ELEMENTS_DIR.rglob("*.php"):
        for m in re.finditer(r"McpTool\(name:\s*'([a-z_0-9]+)'\)", path.read_text()):
            names.add(m.group(1))
    return names


def _package_declarations() -> dict[str, dict]:
    """从项目侧 SKILL.md 提取 {包名: capability}（无 DB 依赖）。"""
    import yaml

    out: dict[str, dict] = {}
    for skill_md in sorted(PROJECT_SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        meta = yaml.safe_load(m.group(1)) or {}
        cap = meta.get("capability")
        if isinstance(cap, dict):
            out[meta.get("name") or skill_md.parent.name] = cap
    return out


class TestCoverageContract:
    def test_server_tool_count_reasonable(self) -> None:
        """业务工具（elements）数量防呆：元工具门面包裹它们，不删除它们。"""
        names = _server_tool_names()
        assert 25 <= len(names) <= 150, f"工具数异常：{len(names)}"

    def test_packages_declare_only_meta_facade(self) -> None:
        """门面唯一性：包 capability.tools 只声明 capability-matrix-mcp 元工具。

        若出现业务工具直连声明或第二个 server，说明有人绕过元工具架构——
        要么是迁移残留，要么是新架构决策（应更新本契约而非静默通过）。
        """
        bad: dict[str, list] = {}
        for name, cap in _package_declarations().items():
            for entry in cap.get("tools") or []:
                server = entry.get("mcp_server")
                include = entry.get("include")
                problems = []
                if server != META_SERVER:
                    problems.append(f"server={server!r}")
                if isinstance(include, list) and set(include) - META_TOOLS:
                    problems.append(f"include 含非元工具: {sorted(set(include) - META_TOOLS)}")
                if problems:
                    bad.setdefault(name, []).append("; ".join(problems))
        assert not bad, f"包声明绕过元工具门面：{bad}"

    def test_meta_tools_defined_server_side(self) -> None:
        """元工具必须在 mcp-server 侧有定义（包 include 引用不能是空头支票）。"""
        hits = set()
        for path in MCP_SERVER_DIR.rglob("*.php"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for tool in META_TOOLS:
                if re.search(rf"name:\s*'{tool}'", text):
                    hits.add(tool)
        missing = META_TOOLS - hits
        assert not missing, f"capability-matrix-mcp 元工具缺少服务端定义：{sorted(missing)}"

    def test_expected_packages_present(self) -> None:
        packages = _package_declarations()
        expected = {
            "mall-orders", "mall-products", "mall-refunds", "mall-shops",
            "mall-sourcing", "mall-publish", "mall-category-mapping",
            "mall-channel", "mall-servicer", "mall-insights",
        }
        missing = expected - set(packages)
        assert not missing, f"缺失能力包：{sorted(missing)}"
