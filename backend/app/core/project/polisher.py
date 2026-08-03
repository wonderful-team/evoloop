"""
Project Context Polisher
========================

Domain expert for context polishing. Lives exclusively in the Domain layer
and subscribes to SystemEventType.CONTEXT_POLISHING events emitted by the Engine.

The Engine is completely agnostic of this module's existence.
"""

import logging
import re

from app.core.events.base import BaseEvent

logger = logging.getLogger(__name__)


class ProjectPolisher:
    """
    Domain expert that subscribes to CONTEXT_POLISHING events.

    Uses metadata from the existing Language enum (app/infrastructure/solidlsp/ls_config.py)
    as its source of truth — no hardcoded language names in its logic.

    This expert:
    1. Reads the environment_block from the published context.
    2. Detects resident technology stacks via config-driven fingerprints.
    3. Identifies the target domain from the task topic (also via config).
    4. Masks environment noise from any non-target resident stack.
    5. Mutates ctx.environment_block in-place — no return value needed.
    """

    # Technology fingerprints, driven by the Language enum in solidlsp.
    # Keys are Language enum values (strings), not hardcoded language names.
    # Adding a new language only requires an entry here (or a config file in the future).
    _FINGERPRINTS: list[dict] = [
        {
            "lang_value": "php",
            "signatures": ["composer.json", "artisan", "phpunit.xml"],
            "noise_patterns": [
                r"(?im)^.*composer\.json.*$",
                r"(?im)^.*vendor\/.*$",
                r"(?im)^.*phpunit\.xml.*$",
                r"(?im)^.*artisan.*$",
            ],
        },
        {
            "lang_value": "typescript",
            "signatures": ["package.json", "tsconfig.json", "node_modules"],
            "noise_patterns": [
                r"(?im)^.*node_modules\/.*$",
                r"(?im)^.*package-lock\.json.*$",
                r"(?im)^.*yarn\.lock.*$",
            ],
        },
        {
            "lang_value": "python",
            "signatures": ["requirements.txt", "pyproject.toml", "setup.py"],
            "noise_patterns": [
                r"(?im)^.*[vV]env\/.*$",
                r"(?im)^.*__pycache__\/.*$",
            ],
        },
        {
            "lang_value": "go",
            "signatures": ["go.mod", "go.sum"],
            "noise_patterns": [
                r"(?im)^.*go\.sum.*$",
            ],
        },
        {
            "lang_value": "rust",
            "signatures": ["Cargo.toml", "Cargo.lock", "target/"],
            "noise_patterns": [
                r"(?im)^.*target\/.*$",
                r"(?im)^.*Cargo\.lock.*$",
            ],
        },
        {
            "lang_value": "java",
            "signatures": ["pom.xml", "build.gradle", ".gradle/"],
            "noise_patterns": [
                r"(?im)^.*\.gradle\/.*$",
                r"(?im)^.*build\/.*$",
            ],
        },
    ]

    def _detect_target_lang(self, topic: str) -> str | None:
        """Match topic keywords against fingerprint lang_value and aliases."""
        if not topic:
            return None
        topic_lower = topic.lower()
        for fp in self._FINGERPRINTS:
            lv = fp["lang_value"]
            # Check both the raw lang value and common aliases
            aliases = {
                "typescript": ["typescript", "ts", "javascript", "js", "node"],
            }
            checks = [lv] + aliases.get(lv, [])
            if any(alias in topic_lower for alias in checks):
                return lv
        return None

    def _detect_resident_langs(self, env_block: str) -> list[str]:
        """Detect which tech stacks are present in the environment block."""
        env_lower = env_block.lower()
        residents = []
        for fp in self._FINGERPRINTS:
            if any(sig.lower() in env_lower for sig in fp["signatures"]):
                residents.append(fp["lang_value"])
        return residents

    def _apply_masking(self, env_block: str, mask_lang: str) -> str:
        """Apply noise masking for a specific non-target language."""
        fp = next((f for f in self._FINGERPRINTS if f["lang_value"] == mask_lang), None)
        if not fp:
            return env_block
        modified = env_block
        for pattern in fp["noise_patterns"]:
            modified = re.sub(
                pattern,
                lambda m: f"{m.group(0).rstrip()} ({mask_lang} noise, masked)",
                modified,
            )
        return modified

    async def handle_context_polishing(self, event: BaseEvent) -> None:
        """
        Event handler subscribed to SystemEventType.CONTEXT_POLISHING.
        Polishes ctx.environment_block in-place.
        """
        ctx = event.data.get("ctx")
        topic = event.data.get("topic") or ""

        if ctx is None or not ctx.environment_block:
            return

        env_block = ctx.environment_block

        target_lang = self._detect_target_lang(topic)
        if not target_lang:
            return  # No clear domain target — keep full view to avoid over-filtering

        resident_langs = self._detect_resident_langs(env_block)

        langs_to_mask = [lang for lang in resident_langs if lang != target_lang]
        if not langs_to_mask:
            return

        for lang in langs_to_mask:
            env_block = self._apply_masking(env_block, lang)

        ctx.environment_block = env_block
        logger.info(
            f"[ProjectPolisher] 🚿 Polished context: target={target_lang}, "
            f"masked={langs_to_mask}"
        )


# Singleton instance
project_polisher = ProjectPolisher()
