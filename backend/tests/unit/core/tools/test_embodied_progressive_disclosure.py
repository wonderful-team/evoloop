"""具身重工具渐进披露契约（L0 瘦身防回潮）。

desktop/browser/mobile/macro 四个重工具曾占工具面 ~55%（实测 7,083/12,853
tok/轮，default 域 fail-open 时逐轮重复付费）。瘦身约定：
1. description 保持短摘要（≤1,200 字符），完整 SOP 住引擎技能
   （app/config/skills/{desktop,browser,mobile}_automation、macro_authoring）；
2. description 内必须携带对应技能的加载指向（可发现性不依赖索引展示）；
3. 三个具身技能文件必须存在且 frontmatter 含 name/description/trigger_patterns。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SKILLS_DIR = REPO / "app" / "config" / "skills"

TOOL_SKILL_PAIRS = {
    "desktop": ("app.core.environment.tools.desktop", "Desktop Automation SOP"),
    "browser": ("app.core.environment.tools.browser", "Browser Automation SOP"),
    "mobile": ("app.core.environment.tools.mobile", "Mobile Device SOP"),
    "macro": ("app.core.engine.tools.react_macro", "Macro Authoring Guide"),
}

DESC_CHAR_CAP = 1200


def _import_tool(module: str, name: str):
    import importlib

    mod = importlib.import_module(module)
    return getattr(mod, name)


@pytest.mark.parametrize("tool_name", sorted(TOOL_SKILL_PAIRS))
def test_tool_description_within_cap_and_points_to_skill(tool_name: str):
    module, skill_name = TOOL_SKILL_PAIRS[tool_name]
    tool = _import_tool(module, tool_name)
    desc = tool.description or ""
    assert len(desc) <= DESC_CHAR_CAP, (
        f"{tool_name} description {len(desc)} 字符超上限 {DESC_CHAR_CAP}："
        "长 SOP 应迁技能，description 只留摘要+指向"
    )
    assert skill_name in desc, f"{tool_name} description 缺少加载「{skill_name}」的指向"


@pytest.mark.parametrize(
    "skill_dir,skill_name",
    [
        ("desktop_automation", "Desktop Automation SOP"),
        ("browser_automation", "Browser Automation SOP"),
        ("mobile_automation", "Mobile Device SOP"),
    ],
)
def test_embodied_sop_skill_exists_with_frontmatter(skill_dir: str, skill_name: str):
    f = SKILLS_DIR / skill_dir / "SKILL.md"
    assert f.is_file(), f"缺少引擎技能 {f}"
    text = f.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{skill_dir} 缺 frontmatter"
    fm = text.split("---", 2)[1]
    assert f"name: {skill_name}" in fm
    assert "description:" in fm
    assert "trigger_patterns:" in fm
