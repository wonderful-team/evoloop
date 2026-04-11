import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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
        prompt_info: Dict[str, Any],
        response_info: Dict[str, Any],
        latency_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record the performance metrics of a single LLM inference call.
        """
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "node_name": node_name,
                "turn_id": turn_id,
                "latency_ms": round(latency_ms, 2),
                "prompt": {
                    "system_len": prompt_info.get("system_len", 0),
                    "history_len": prompt_info.get("history_len", 0),
                    "total_len": prompt_info.get("total_len", 0),
                },
                "usage": {
                    "prompt_tokens": response_info.get("usage", {}).get("prompt_tokens"),
                    "completion_tokens": response_info.get("usage", {}).get("completion_tokens"),
                    "total_tokens": response_info.get("usage", {}).get("total_tokens"),
                },
                "response": {
                    "content_len": len(response_info.get("content", "")),
                    "is_tool_call": response_info.get("is_tool_call", False),
                    "tool_names": response_info.get("tool_names", []),
                },
                "metadata": metadata or {}
            }
            
            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                
        except Exception as e:
            # Observability should never crash the engine
            print(f"[Telemetry] Failed to record inference: {e}")

# Global instance
agent_telemetry = TelemetryCollector()
