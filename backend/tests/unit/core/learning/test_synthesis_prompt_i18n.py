from app.core.learning.prompts.builder import LearningPromptBuilder
from app.i18n.service import i18n


class TestSynthesisPromptLanguageConstraint:
    def test_prompt_contains_language_constraint_for_chinese(self, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService.get_value",
            lambda key, default: "zh" if key == "LANGUAGE" else default,
        )

        lang_code = "zh"
        language_constraint = i18n.get(
            "learning.synthesis_lang_constraint", lang=lang_code
        )

        builder = LearningPromptBuilder()
        prompt = builder.build_skill_synthesis_prompt(
            {
                "trace_narrative": "test trace",
                "total_steps": 1,
                "human_steps": 0,
                "agent_steps": 1,
                "tools_used": "desktop_control",
                "user_intent_hint": "get current date",
                "language_constraint": language_constraint,
            }
        )

        assert "中文" in prompt
        assert "name" in prompt
        assert "trigger_patterns" in prompt
        assert "EXAMPLE FORMAT ONLY" in prompt

    def test_prompt_contains_language_constraint_for_english(self, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService.get_value",
            lambda key, default: "en" if key == "LANGUAGE" else default,
        )

        lang_code = "en"
        language_constraint = i18n.get(
            "learning.synthesis_lang_constraint", lang=lang_code
        )

        builder = LearningPromptBuilder()
        prompt = builder.build_skill_synthesis_prompt(
            {
                "trace_narrative": "test trace",
                "total_steps": 1,
                "human_steps": 0,
                "agent_steps": 1,
                "tools_used": "desktop_control",
                "user_intent_hint": "get current date",
                "language_constraint": language_constraint,
            }
        )

        assert "English" in prompt
        assert "MUST ALL" in prompt
        assert "name" in prompt
        assert "trigger_patterns" in prompt

    def test_synthesis_language_constraint_key_exists(self):
        assert i18n.get("learning.synthesis_lang_constraint", lang="zh") is not None
        assert i18n.get("learning.synthesis_lang_constraint", lang="zh") != "learning.synthesis_lang_constraint"
        assert i18n.get("learning.synthesis_lang_constraint", lang="en") is not None
        assert i18n.get("learning.synthesis_lang_constraint", lang="en") != "learning.synthesis_lang_constraint"

    def test_prompt_requires_specificity_and_uses_intent_for_name(self, monkeypatch):
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService.get_value",
            lambda key, default: "zh" if key == "LANGUAGE" else default,
        )

        lang_code = "zh"
        language_constraint = i18n.get(
            "learning.synthesis_lang_constraint", lang=lang_code
        )

        builder = LearningPromptBuilder()
        prompt = builder.build_skill_synthesis_prompt(
            {
                "trace_narrative": "test trace",
                "total_steps": 1,
                "human_steps": 0,
                "agent_steps": 1,
                "tools_used": "desktop_control",
                "user_intent_hint": "获取当前日期",
                "language_constraint": language_constraint,
            }
        )

        assert "Use this for name, description, and trigger_patterns" in prompt
        assert "BE SPECIFIC" in prompt
        assert "不要过度泛化" in prompt or "over-generalize" in prompt
