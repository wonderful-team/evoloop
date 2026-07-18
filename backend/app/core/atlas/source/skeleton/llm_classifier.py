"""Language-agnostic file classification using an LLM.

This module classifies source files into architecture roles (controller, model,
service, route, middleware, view, repository, config, entry_point, library, test,
unknown) without relying on framework-specific Tree-sitter queries.

It is intended as a universal fallback/enrichment layer for the AppMap skeleton
generator and for semantic flag assignment when language providers do not cover a
framework.
"""

from __future__ import annotations

import json
import logging

from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.llm import InternalLLMService

logger = logging.getLogger(__name__)


VALID_ROLES = {
    "controller",
    "model",
    "service",
    "repository",
    "route",
    "middleware",
    "view",
    "config",
    "entry_point",
    "library",
    "test",
    "unknown",
}

MAX_FILES_PER_LLM_CALL = 150


class LLMFileClassifier:
    """Classify files by architecture role using an LLM."""

    async def classify_files(
        self,
        file_paths: list[str],
        summaries: dict[str, str] | None = None,
        module_name: str = "",
    ) -> dict[str, str]:
        """Classify a list of files into architecture roles.

        Args:
            file_paths: Relative paths of files to classify.
            summaries: Optional file path -> brief content summary.
            module_name: Name of the module (for context).

        Returns:
            Mapping from file path to role string. Missing paths mean the LLM
            did not return a classification for them.
        """
        if not file_paths:
            return {}

        summaries = summaries or {}
        results: dict[str, str] = {}

        # Process in batches to keep prompts small and latency reasonable.
        for i in range(0, len(file_paths), MAX_FILES_PER_LLM_CALL):
            batch = file_paths[i : i + MAX_FILES_PER_LLM_CALL]
            batch_results = await self._classify_batch(batch, summaries, module_name)
            results.update(batch_results)

        return results

    async def _classify_batch(
        self,
        file_paths: list[str],
        summaries: dict[str, str],
        module_name: str,
    ) -> dict[str, str]:
        model_name = SystemConfigService.get_value("LLM_MODEL")
        if not model_name:
            logger.warning(
                "[LLMFileClassifier] No LLM_MODEL configured; skipping classification"
            )
            return {}

        prompt_lines = [
            "You are a language-agnostic software architect. Classify each file below "
            "into one of these architecture roles based on its path, name, and optional summary.",
            "",
            "Valid roles:",
            "- controller: handles HTTP/API requests and routes",
            "- model: data structures, entities, ORM models, database mapping",
            "- service: business logic layer, use cases, application services",
            "- repository: data access objects, database queries, mappers",
            "- route: explicit route definitions, routers, URL mapping",
            "- middleware: interceptors, filters, guards, request/response middleware",
            "- view: templates, UI components, pages, presentation layer",
            "- config: configuration, settings, constants, environment setup",
            "- entry_point: main application entry, bootstrap, index, server start",
            "- library: shared utilities, helpers, third-party extensions, common code",
            "- test: test files, specs, fixtures",
            "- unknown: does not fit above or is a data/asset file",
            "",
            "Rules:",
            "1. Prefer the most specific role. If a file is in a 'controller' directory or ends with 'Controller.*', use 'controller'.",
            "2. For convention-based frameworks (e.g., ThinkPHP, Rails, Django), infer roles from path conventions.",
            "3. Return ONLY a JSON object mapping each file path to its role. No explanations.",
            "4. Do not change the file paths; use them exactly as provided.",
            "",
        ]
        if module_name:
            prompt_lines.append(f"Module context: {module_name}")
            prompt_lines.append("")

        prompt_lines.append("Files:")
        for path in file_paths:
            summary = summaries.get(path, "")
            if summary:
                summary = summary.replace("\n", " ")[:200]
                prompt_lines.append(f"- {path} | {summary}")
            else:
                prompt_lines.append(f"- {path}")

        prompt_lines.append("")
        prompt_lines.append("JSON output:")
        prompt = "\n".join(prompt_lines)

        try:
            response = await InternalLLMService.invoke(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a language-agnostic software architect. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                purpose="appmap_file_classification",
                temperature=0.1,
                max_tokens=2000,
                model_name=model_name,
            )
            content = response.content if hasattr(response, "content") else str(response)
            return self._parse_json_response(content, file_paths)
        except Exception as e:
            logger.error(f"[LLMFileClassifier] LLM classification failed: {e}")
            return {}

    def _parse_json_response(
        self, content: str, expected_paths: list[str]
    ) -> dict[str, str]:
        content = content.strip()
        if content.startswith("```"):
            # Strip markdown code fences
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"[LLMFileClassifier] Failed to parse LLM JSON: {e}")
            return {}

        if not isinstance(data, dict):
            logger.error("[LLMFileClassifier] LLM response is not a JSON object")
            return {}

        results: dict[str, str] = {}
        for path in expected_paths:
            role = data.get(path)
            if isinstance(role, str) and role.lower() in VALID_ROLES:
                results[path] = role.lower()
            elif isinstance(role, str):
                # Accept unknown roles by mapping them to 'unknown'
                results[path] = "unknown"
        return results


classifier = LLMFileClassifier()


async def classify_files_with_llm(
    file_paths: list[str],
    summaries: dict[str, str] | None = None,
    module_name: str = "",
) -> dict[str, str]:
    """Convenience wrapper for the global LLM file classifier."""
    return await classifier.classify_files(file_paths, summaries, module_name)
