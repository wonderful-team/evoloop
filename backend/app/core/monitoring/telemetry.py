from datetime import datetime
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class TelemetryMetadata(DynamicBaseModel):
    """Dynamic metadata attached to an inference telemetry event."""


class PromptStats(BaseModel):
    """Metrics for the input prompt."""
    system_len: int = 0
    history_len: int = 0
    total_len: int = 0


class UsageMetadata(BaseModel):
    """Token usage metrics from the LLM provider."""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ResponseStats(BaseModel):
    """Metrics for the LLM response."""
    content_len: int = 0
    is_tool_call: bool = False
    tool_names: List[str] = Field(default_factory=list)


class InferenceEvent(DynamicBaseModel):
    """A complete record of a single inference call."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    node_name: str
    turn_id: int
    latency_ms: float
    prompt: PromptStats
    usage: UsageMetadata
    response: ResponseStats
    metadata: TelemetryMetadata = Field(default_factory=TelemetryMetadata)


class TelemetryCollector:
    """
    Structured telemetry collector for Agent performance monitoring.
    Saves metrics to JSON-L files for later analysis.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TelemetryCollector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir: str = "tests/monitoring/telemetry"):
        if self._initialized:
            return
            
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a new session file for each run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = self.log_dir / f"trace_{timestamp}.jsonl"
        self._initialized = True

    def record_inference(
        self,
        node_name: str,
        turn_id: int,
        prompt_info: Union[Dict[str, Any], PromptStats],
        response_info: Dict[str, Any],
        latency_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record the performance metrics of a single LLM inference call.
        """
        try:
            # 1. Handle PromptStats
            if isinstance(prompt_info, dict):
                prompt = PromptStats(
                    system_len=prompt_info.get("system_len", 0),
                    history_len=prompt_info.get("history_len", 0),
                    total_len=prompt_info.get("total_len", 0),
                )
            else:
                prompt = prompt_info

            # 2. Handle Usage
            usage_raw = response_info.get("usage", {})
            usage = UsageMetadata(
                prompt_tokens=usage_raw.get("prompt_tokens"),
                completion_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )

            # 3. Handle Response
            response = ResponseStats(
                content_len=len(response_info.get("content", "")),
                is_tool_call=response_info.get("is_tool_call", False),
                tool_names=response_info.get("tool_names", []),
            )

            # 4. Construct Event
            event = InferenceEvent(
                node_name=node_name,
                turn_id=turn_id,
                latency_ms=round(latency_ms, 2),
                prompt=prompt,
                usage=usage,
                response=response,
                metadata=TelemetryMetadata(**(metadata or {}))
            )
            
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")
                
        except Exception as e:
            # Observability should never crash the engine
            print(f"[Telemetry] Failed to record inference: {e}")


# Global instance
agent_telemetry = TelemetryCollector()
