"""
Dynamic Apps Triage Background Tasks.

Runs in Huey (embedded mode) or Celery (full mode) worker.
Each task processes one batch of apps, **persists verdicts to cache itself**
(processed/dynamic/reasoning keys) and returns the results map.

Fire-and-forget contract: the enqueue side (dynamic_apps.sync_dynamic_apps)
does NOT block on `.get()`. Gateway triage calls take ~100s+ per batch;
a synchronous 120s `.get()` misreported completed work as failures and,
because the processed set is written by the worker, re-triaged "lost"
batches every tick (duplicate token burn + timeout cascade over serial waits).
"""

import json
import logging

from app.constants import DEFAULT_INTERNAL_LLM_TOKENS
from app.core.environment.constants import (
    app_reasoning_key,
    dynamic_apps_key,
    processed_apps_key,
)
from app.infrastructure.cache import cache
from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


async def persist_triage_results(platform: str, results: dict[str, dict]) -> None:
    """判定落缓存：processed 集合是"不再重审"的唯一依据，必须在 worker 侧写。"""
    if not results:
        return
    pipe = cache.pipeline()
    for app_id, item in results.items():
        pipe.sadd(processed_apps_key(platform), app_id)
        if item.get("is_dynamic", False):
            pipe.sadd(dynamic_apps_key(platform), app_id)
            pipe.hset(
                app_reasoning_key(platform), app_id, item.get("reason", "Unknown")
            )
    await pipe.execute()
    for app_id, item in results.items():
        if item.get("is_dynamic", False):
            logger.info(
                f"[DynamicAppTriage] Marked '{platform}:{app_id}' as DYNAMIC: "
                f"{item.get('reason', 'Unknown')}"
            )
        else:
            logger.debug(f"[DynamicAppTriage] Marked '{platform}:{app_id}' as STATIC")


@shared_task(name="dynamic_apps_triage_batch", retries=1, retry_delay=10)
async def triage_app_batch(app_ids: list[str], platform: str) -> dict[str, dict]:
    """Background task to triage a batch of apps via LLM and persist verdicts."""
    from app.core.evocloud import evocloud_manager

    if not await evocloud_manager.get_token():
        logger.debug("[Task] Skipping LLM triage: user not authenticated")
        return {}

    from app.utils.template import render_template

    prompt = render_template(
        "domain/planning/dynamic_app_triage.prompt.j2", app_ids=app_ids
    )
    role_name = render_template(
        "domain/planning/expert_roles.prompt.j2", role="ui_dynamics"
    ).strip()

    from app.infrastructure.llm import InternalLLMService

    response = await InternalLLMService.invoke(
        messages=[
            {"role": "system", "content": role_name},
            {"role": "user", "content": prompt},
        ],
        purpose="environment_exploration",
        temperature=0,
        max_tokens=DEFAULT_INTERNAL_LLM_TOKENS,
        # 分类任务不需要深度思考：
        # - thinking:{type:disabled} 是 DeepSeek 官方关思考的参数（网关已透传）；
        # - enable_thinking/return_reasoning 兜底 DashScope 风格兼容上游，
        #   并中和 evoloop 默认注入的 enable_thinking=true，避免冲突。
        # 避免推理把 max_tokens 预算全耗在 reasoning_content 上、答案为空。
        extra_body={
            "thinking": {"type": "disabled"},
            "enable_thinking": False,
            "return_reasoning": False,
        },
    )

    content = response.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()

    try:
        data = json.loads(content)
        results = data.get("results", {}) or {}
    except json.JSONDecodeError as e:
        # 预期降级：LLM 偶尔返回空/非 JSON（返回 {} 继续），非错误，不打印 Traceback。
        # 不标 processed，下个扫描周期这些 App 会自动重试。
        logger.error(
            f"[Task] Failed to parse LLM JSON output. Error: {e}. Raw content: {content}"
        )
        return {}

    await persist_triage_results(platform, results)
    return results
