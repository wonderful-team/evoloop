"""
Inference telemetry recording utilities.
"""

from app.core.monitoring.telemetry import agent_telemetry


def record_inference_telemetry(
    name: str,
    turn_id: int,
    system_prompt: str,
    history_messages: list,
    loop_messages: list,
    response,
    latency: float,
    metadata: dict,
):
    """Record inference telemetry."""
    agent_telemetry.record_inference(
        node_name=name,
        turn_id=turn_id,
        prompt_info={
            "system_len": len(system_prompt),
            "history_len": sum(len(str(m.content)) for m in history_messages),
            "total_len": len(system_prompt) + sum(len(str(m.content)) for m in loop_messages)
        },
        response_info={
            "content": response.content,
            "usage": getattr(response, "usage_metadata", {}),
            "is_tool_call": bool(response.tool_calls),
            "tool_names": [tc["name"] for tc in response.tool_calls]
        },
        latency_ms=latency * 1000,
        metadata=metadata,
    )
