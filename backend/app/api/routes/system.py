import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.schemas.system import (
    CloudStatusResponse,
    DiscoveredModelResponse,
    EmbeddingApplyResponse,
    EmbeddingConfigRequest,
    EmbeddingTestResponse,
    EmbeddingTierConfigRequest,
    EmbeddingTierStatusResponse,
    EmbeddingTierTestResponse,
    HealthCheckResponse,
    LLMApplyResponse,
    LLMConfigRequest,
    LLMTestResponse,
    ModelDiscoveryResponse,
    ModelsListResponse,
    SystemStatusResponse,
)
from app.core.config import settings
from app.core.environment import collect_cpu_mem
from app.infrastructure.config import EmbeddingConfigService
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.llm import LLMConfigService, LLMFactory
from app.infrastructure.llm.platform_service import (
    get_available_embedding_models,
    get_available_llm_models,
)
from app.models.system import SystemConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", dependencies=[Depends(get_current_user)])
def get_system_status() -> SystemStatusResponse:
    """
    Get real-time system CPU and RAM usage.
    """
    metrics = collect_cpu_mem()

    return SystemStatusResponse(
        cpu_percent=metrics["cpu_percent"] if metrics else 0.0,
        ram_percent=metrics["mem_percent"] if metrics else 0,
        ram_used_gb=round(metrics["mem_used"] / (1024**3), 2) if metrics else 0.0,
        ram_total_gb=round(metrics["mem_total"] / (1024**3), 2) if metrics else 0.0,
        status="ok",
        enable_macro_self_healing=settings.ENABLE_MACRO_SELF_HEALING,
    )


@router.get("/config", dependencies=[Depends(get_current_user)])
def get_system_config() -> list[SystemConfig]:
    configs = SystemConfigService.get_all()
    # Expose deployment mode so the frontend can gate onboarding/wizard UI.
    configs.append(
        SystemConfig(
            key="MULTI_TENANT_MODE", value=str(settings.MULTI_TENANT_MODE).lower()
        )
    )
    return configs


# --- Model Discovery ---


@router.get("/models/discover", dependencies=[Depends(get_current_user)])
async def discover_models() -> ModelDiscoveryResponse:
    """Auto-discover available models from local providers (LM Studio, Ollama, GGUF)."""
    from app.infrastructure.llm.discovery import ModelDiscoveryService

    raw_models = await ModelDiscoveryService.discover_all()
    models: list[DiscoveredModelResponse] = [
        DiscoveredModelResponse(**m.__dict__) for m in raw_models
    ]

    # Also include platform models if logged in
    try:
        platform_models = await get_available_llm_models(config_type="platform")
        for pm in platform_models:
            models.append(DiscoveredModelResponse(
                id=pm.id,
                name=pm.name,
                source="evocloud",
                model_name=pm.model,
                status="available",
                capabilities=["chat", "embedding"] if pm.supports_functions else ["embedding"],
                context_window=pm.context_window,
            ))
    except Exception as e:
        logger.debug("[Discovery] Platform models unavailable: %s", e)

    message = f"Found {len(models)} model(s)"
    return ModelDiscoveryResponse(models=models, message=message)


@router.get("/health")
def health_check() -> HealthCheckResponse:
    """
    Simple health check for startup probing.
    """
    return HealthCheckResponse(status="ok", service="evoloop-backend")


@router.post("/config", dependencies=[Depends(get_current_user)])
async def update_system_config(config: SystemConfig) -> SystemConfig:
    """Update system configuration and trigger side effects if needed."""
    return await SystemConfigService.set_value_async(config.key, config.value, config.description)

# --- Customer Service Duty (global config) ---


@router.get("/db-debug")
async def db_debug() -> dict:
    """TEMP pool-leak debugging: live pool status + holders of checked-out fairies."""
    import gc as _gc
    import types as _types

    from app.infrastructure.database.resource_manager import db_resource_manager

    def _scan(engine) -> dict:
        if engine is None:
            return {"error": "engine not ready"}
        pool = engine.sync_engine.pool
        fairies = [
            o for o in _gc.get_objects() if type(o).__name__ == "_ConnectionFairy"
        ]
        holders = []
        for f in fairies:
            refs = _gc.get_referrers(f)
            interesting = []
            for r in refs:
                t = type(r)
                if isinstance(r, _types.FrameType):
                    interesting.append(
                        f"frame:{r.f_code.co_filename.split('backend/')[-1]}:{r.f_code.co_name}:{r.f_lineno}"
                    )
                else:
                    interesting.append(f"{t.__module__}.{t.__name__}")
            # 上溯一层容器：谁持有这些 list/dict
            upstream = set()
            for r in refs:
                for r2 in _gc.get_referrers(r):
                    t2 = type(r2)
                    if isinstance(r2, _types.FrameType):
                        upstream.add(
                            f"frame:{r2.f_code.co_filename.split('backend/')[-1]}:{r2.f_code.co_name}"
                        )
                    elif not isinstance(r2, (list, dict)):
                        upstream.add(f"{t2.__module__}.{t2.__name__}")
            holders.append(
                {
                    "id": id(f),
                    "refs": interesting[:6],
                    "upstream": sorted(upstream)[:8],
                }
            )
        return {
            "pool_status": pool.status(),
            "checkedout": pool.checkedout(),
            "fairy_count": len(fairies),
            "holders": holders[:20],
        }

    engine = db_resource_manager.engine
    return await asyncio.to_thread(_scan, engine)


@router.get("/customer_service_duty", dependencies=[Depends(get_current_user)])
async def get_customer_service_duty() -> dict:
    """读取全局客服值守配置（总开关 + 渠道选择 + MCP 预加载）。"""
    from app.core.channel.duty.config import load_global_duty_config

    return load_global_duty_config()


@router.post("/customer_service_duty/validate", dependencies=[Depends(get_current_user)])
async def validate_customer_service_duty() -> dict:
    """校验全局值守开启条件（企业微信客户端就绪）。返回 {ok, errors}。"""
    from app.core.channel.duty import provision

    errors = await provision.validate_global_duty()
    return {"ok": len(errors) == 0, "errors": errors}


@router.put("/customer_service_duty", dependencies=[Depends(get_current_user)])
async def update_customer_service_duty(cfg: dict) -> dict:
    """更新全局客服值守配置。渠道启用/启停时联动（§8.5.6 全局停止）。"""
    from app.core.channel.duty import provision
    from app.core.channel.duty.config import (
        clamp_duty_interval,
        save_global_duty_config,
    )

    enabled = bool(cfg.get("enabled", False))
    old = await get_customer_service_duty()
    old_channels = old.get("channels") or []
    new_channels = cfg.get("channels") or []

    # 启用企微渠道（wecom 从无到有）时校验企业微信就绪（防御：防绕过前端）
    if "wecom" in new_channels and "wecom" not in old_channels:
        errors = await provision.validate_global_duty()
        if errors:
            raise HTTPException(400, detail={"message": "企微渠道启用失败", "errors": errors})

    # 轮巡间隔（兜底）钳制到 60~3600s
    if "poll_interval" in cfg:
        cfg["poll_interval"] = clamp_duty_interval(cfg.get("poll_interval"))

    save_global_duty_config(cfg)

    # 全局关 → 停所有项目调度 + 协作式切断（托盘"停止值守"语义）
    if not enabled and old.get("enabled"):
        await provision.stop_global()
    # 全局开 → 恢复所有保留 enabled 的项目的调度（总闸打开，分闸按项目意愿恢复）
    elif enabled and not old.get("enabled"):
        await provision.resume_global()

    # 若开启全局值守，立即发射自主值守域内唤醒信号，0ms 瞬间唤醒 Supervisor 派发就绪任务
    if enabled:
        try:
            from app.domain.tasks.runtime.wakeup import notify_duty_wakeup
            notify_duty_wakeup()
        except Exception:
            pass

    # 值守状态变更 → system:events 广播（托盘管理器即时同步，替代 15s 盲轮）。
    # system 频道走 onmessage + payload.event 分发，需带 SystemEvent 形状。
    try:
        from datetime import datetime as _dt

        from app.core.engine.message.broker import get_message_broker

        await get_message_broker().publish(
            "system:events",
            {
                "type": "duty_state_changed",
                "event": "duty_state_changed",
                "timestamp": _dt.now().isoformat(),
                "source": "system",
                "data": {
                    "enabled": enabled,
                    "channels": new_channels,
                },
            },
        )
    except Exception:
        pass  # 通知失败不影响配置本身
    return cfg


# --- Embedding Channel (independent tier chain) ---


@router.get("/embedding/tier-status", dependencies=[Depends(get_current_user)])
async def get_embedding_tier_status() -> EmbeddingTierStatusResponse:
    """Return availability of each embedding tier."""
    tiers = SystemConfigService.get_value("EMBEDDING_TIERS") or "gguf,local,remote"
    gguf = bool(SystemConfigService.get_value("EMBEDDING_GGUF_MODEL"))
    local = bool(SystemConfigService.get_value("EMBEDDING_LOCAL_URL"))
    remote = bool(SystemConfigService.get_value("EMBEDDING_PROVIDER"))
    active = None
    embedder = EmbedderFactory.get_embedder()
    if embedder is not None:
        if gguf:
            active = "gguf"
        elif local:
            active = "local"
        elif remote:
            active = "remote"
    return EmbeddingTierStatusResponse(
        active_tier=active,
        gguf_available=gguf,
        local_available=local,
        remote_available=remote,
        tiers=tiers,
    )


@router.post("/embedding/tier-apply", dependencies=[Depends(get_current_user)])
async def apply_embedding_tier_config(req: EmbeddingTierConfigRequest) -> EmbeddingApplyResponse:
    """Apply embedding tier configuration."""
    SystemConfigService.set_value("EMBEDDING_TIERS", req.tiers)
    SystemConfigService.set_value("EMBEDDING_GGUF_MODEL", req.gguf_model or "")
    SystemConfigService.set_value("EMBEDDING_LOCAL_URL", req.local_url or "")
    SystemConfigService.set_value("EMBEDDING_LOCAL_API_KEY", req.local_api_key or "")
    SystemConfigService.set_value("EMBEDDING_LOCAL_MODEL", req.local_model or "")
    SystemConfigService.set_value("EMBEDDING_PROVIDER", req.provider or "")
    SystemConfigService.set_value("EMBEDDING_BASE_URL", req.base_url or "")
    SystemConfigService.set_value("EMBEDDING_MODEL", req.model or "")
    SystemConfigService.set_value("EMBEDDING_API_KEY", req.api_key or "")
    if req.dimensions:
        SystemConfigService.set_value("EMBEDDING_DIMENSIONS", str(req.dimensions))
    EmbedderFactory.reset_cache()
    return EmbeddingApplyResponse(status="applied", message="Embedding tier configuration applied.")


@router.post("/embedding/tier-test", dependencies=[Depends(get_current_user)])
async def test_embedding_tier_connection(_req: EmbeddingTierConfigRequest) -> EmbeddingTierTestResponse:
    """Test the highest-priority available embedding tier."""
    EmbedderFactory.reset_cache()
    try:
        embedder = EmbedderFactory.get_embedder()
        if embedder is None:
            return EmbeddingTierTestResponse(success=False, error="No embedding tier available")
        emb = await embedder.embed_query("test")
        dims = len(emb) if emb else 0
        return EmbeddingTierTestResponse(success=dims > 0, dimensions=dims)
    except Exception as e:
        return EmbeddingTierTestResponse(success=False, error=str(e))


@router.post("/embedding/test", dependencies=[Depends(get_current_user)])
async def test_embedding_connection(req: EmbeddingConfigRequest) -> EmbeddingTestResponse:
    """
    Validate connection to embedding provider.
    """
    success, dim = await EmbeddingConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
    )
    return EmbeddingTestResponse(success=success, dimensions=dim)


@router.post("/embedding/apply", dependencies=[Depends(get_current_user)])
async def apply_embedding_config(req: EmbeddingConfigRequest) -> EmbeddingApplyResponse:
    """
    Apply new embedding config. THIS IS DESTRUCTIVE (Resets Vector DB).
    """
    await EmbeddingConfigService.switch_embedding_model(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
        dimensions=req.dimensions,
        current_project_id=req.project_id,
    )

    # Save Custom Model Name (always save the model name provided in the config card)
    SystemConfigService.set_value("CUSTOM_EMBEDDING_MODEL", req.model)

    # Save the default embedding model (kept as a legacy fallback for
    # CUSTOM_EMBEDDING_MODEL; the effective model lives in the custom key).
    SystemConfigService.set_value("EMBEDDING_MODEL", req.model)
    return EmbeddingApplyResponse(
        status="applied",
        message="Embedding model switched. Re-indexing triggered.",
    )


# --- LLM Config ---


@router.post("/llm/test", dependencies=[Depends(get_current_user)])
async def test_llm_connection(req: LLMConfigRequest) -> LLMTestResponse:
    """
    Validate connection to LLM provider.
    """
    success, reply = await LLMConfigService.validate_connection(
        provider=req.provider,
        base_url=req.base_url,
        model=req.model,
        api_key=req.api_key,
        headers=req.headers,
    )
    return LLMTestResponse(success=success, reply=reply)


@router.post("/llm/apply", dependencies=[Depends(get_current_user)])
async def apply_llm_config(req: LLMConfigRequest) -> LLMApplyResponse:
    """
    Apply new LLM config.

    Platform mode (no base_url): the EvoLoop Gateway assigns a default model
    on the remote side, so no local "default LLM" is stored. Any stale custom
    base_url / model keys are cleared to keep the platform route clean.
    Custom mode (base_url provided): provider/base_url/model are persisted so
    calls bypass the gateway and go straight to the user's endpoint.
    """
    # Determine config type based on whether a custom base URL is provided
    config_type = "custom" if req.base_url else "platform"
    SystemConfigService.set_value("LLM_CONFIG_TYPE", config_type)

    # Save provider details (used for Custom mode)
    SystemConfigService.set_value("LLM_PROVIDER", req.provider)
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", req.provider_type)
    SystemConfigService.set_value("LLM_BASE_URL", req.base_url or "")

    if config_type == "custom":
        # Only custom mode persists a local model — model routing is decided
        # locally via base_url when the user brings their own endpoint.
        SystemConfigService.set_value("LLM_MODEL", req.model)
        # Save Custom Model Name (always save the model name provided in the config card)
        SystemConfigService.set_value("CUSTOM_LLM_MODEL", req.model)
    else:
        # Platform mode: no local default model; the gateway assigns one.
        # Clear stale values so a previous custom config cannot bleed into
        # platform requests (also aligns with factory.py's custom-only fallback).
        SystemConfigService.set_value("LLM_MODEL", "")
        SystemConfigService.set_value("CUSTOM_LLM_MODEL", "")

    if req.vision_model:
        SystemConfigService.set_value("VISION_MODEL", req.vision_model)
    if req.vision_base_url:
        SystemConfigService.set_value("VISION_BASE_URL", req.vision_base_url)
    if req.vision_api_key:
        SystemConfigService.set_value("VISION_API_KEY", req.vision_api_key)
    if req.vision_provider_type:
        SystemConfigService.set_value("VISION_PROVIDER_TYPE", req.vision_provider_type)
    if req.api_key:
        SystemConfigService.set_value("LLM_API_KEY", req.api_key)

    # Save Custom HTTP Headers
    headers_str = json.dumps(req.headers) if req.headers else "{}"
    SystemConfigService.set_value("LLM_HEADERS", headers_str)

    # Clear LLM Factory cache
    LLMFactory.clear_cache()

    return LLMApplyResponse(status="applied", message="LLM Configuration applied successfully.")


@router.get("/cloud-status")
async def get_cloud_status() -> CloudStatusResponse:
    """
    Debug endpoint to check EvoCloud connection status.
    """
    from app.core.evocloud import evocloud_manager

    token = await evocloud_manager.get_token()
    return CloudStatusResponse(
        is_logged_in=bool(token),
        device_key=evocloud_manager.link.device_key if evocloud_manager.link else None,
        is_linked=evocloud_manager.link.is_connected() if evocloud_manager.link else False,
        device_name=evocloud_manager.link.device_name if evocloud_manager.link else "Unknown",
        api_url=evocloud_manager.api.base_url if evocloud_manager.api else "Unknown",
    )


@router.get("/llm/models")
async def get_llm_models(config_type: str = None) -> ModelsListResponse:
    """
    获取可用的 LLM 模型列表

    Args:
        config_type: 配置类型过滤 (platform/custom)
                    platform - 只返回平台提供的模型
                    custom - 只返回自定义模型
                    不传则根据系统配置自动过滤

    返回:
        符合条件的模型列表
    """
    models = [m.model_dump() for m in await get_available_llm_models(config_type=config_type)]
    return ModelsListResponse(models=models, last_updated=time.strftime("%Y-%m-%d"))


@router.get("/embedding/models")
async def get_embedding_models() -> ModelsListResponse:
    """
    获取可用的 Embedding 模型列表（包含平台模型和自定义模型）
    """
    models = [m.model_dump() for m in await get_available_embedding_models()]
    return ModelsListResponse(models=models, last_updated=time.strftime("%Y-%m-%d"))
