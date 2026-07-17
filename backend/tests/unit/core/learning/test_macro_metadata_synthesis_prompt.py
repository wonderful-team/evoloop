from app.core.learning.prompts.builder import LearningPromptBuilder
from app.i18n.service import i18n


class TestMacroMetadataSynthesisPrompt:
    def test_prompt_does_not_include_skill_guide(self, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService.get_value",
            lambda key, default: "zh" if key == "LANGUAGE" else default,
        )

        lang_code = "zh"
        language_constraint = i18n.get(
            "learning.synthesis_lang_constraint", lang=lang_code
        )

        builder = LearningPromptBuilder()
        prompt = builder.build_macro_metadata_synthesis_prompt(
            {
                "trace_narrative": "test trace",
                "macro_script": "steps: []",
                "total_steps": 1,
                "human_steps": 0,
                "agent_steps": 1,
                "tools_used": "browser_control",
                "user_intent_hint": "fill web form",
                "language_constraint": language_constraint,
            }
        )

        assert "Macro Metadata Architect" in prompt
        assert "name" in prompt
        assert "trigger_patterns" in prompt
        assert "Expert Skill Guide" not in prompt
        assert "## 0. Tool Requirements" not in prompt
        assert "NO SKILL GUIDE" in prompt

    def test_prompt_contains_language_constraint(self, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService.get_value",
            lambda key, default: "en" if key == "LANGUAGE" else default,
        )

        lang_code = "en"
        language_constraint = i18n.get(
            "learning.synthesis_lang_constraint", lang=lang_code
        )

        builder = LearningPromptBuilder()
        prompt = builder.build_macro_metadata_synthesis_prompt(
            {
                "trace_narrative": "test trace",
                "macro_script": "steps: []",
                "total_steps": 1,
                "human_steps": 0,
                "agent_steps": 1,
                "tools_used": "browser_control",
                "user_intent_hint": "fill web form",
                "language_constraint": language_constraint,
            }
        )

        assert "English" in prompt
        assert "name" in prompt
        assert "namespace" in prompt
