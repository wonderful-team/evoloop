"""
Dynamic Apps Triage Background Tasks.

Runs in Huey (embedded mode) or Celery (full mode) worker.
Each task processes one batch of apps and returns classification results.
"""

import json
import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="dynamic_apps_triage_batch", retries=1, retry_delay=10)
async def triage_app_batch(app_ids: list[str]) -> dict[str, dict]:
    """Background task to triage a batch of apps via LLM."""
    from app.core.evocloud import evocloud_manager

    if not await evocloud_manager.get_token():
        logger.debug("[Task] Skipping LLM triage: user not authenticated")
        return {}

    from app.infrastructure.config.service import SystemConfigService

    model_name = SystemConfigService.get_value("LLM_MODEL")
    if not model_name:
        logger.debug("[Task] Skipping LLM triage: no LLM model configured")
        return {}

    from app.utils import render_template

    prompt = render_template(
        "domain/planning/dynamic_app_triage.prompt.j2", app_ids=app_ids
    )
    role_name = render_template(
        "domain/planning/expert_roles.prompt.j2", role="ui_dynamics"
    ).strip()

    from app.core.llm import InternalLLMService

    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": role_name},
            {"role": "user", "content": prompt},
        ],
        purpose="environment_exploration",
        temperature=0,
        max_tokens=4000,
        model_name=model_name,
    )

    content = response.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()

    try:
        data = json.loads(content)
        return data.get("results", {})
    except json.JSONDecodeError as e:
        logger.error(
            f"[Task] Failed to parse LLM JSON output. Error: {e}. Raw content: {content}"
        )
        return {}
