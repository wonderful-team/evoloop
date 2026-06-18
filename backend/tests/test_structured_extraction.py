import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Mock config
os.environ["LLM_MODEL"] = "kimi-k2-thinking-turbo"

# Patch the DB dependency
from app.infrastructure.config.service import SystemConfigService
original_get_value = SystemConfigService.get_value
SystemConfigService.get_value = lambda k, d=None: os.environ.get(k, d)

from app.core.engine.tasks import run_engine_audit_structured_extraction

async def main():
    # Construct a fake request
    messages_dicts = [
        {"type": "human", "content": "The project was completed. Deliverables: report.pdf. Total cost: $50."},
        {"type": "ai", "content": "I understand."}
    ]
    
    collected_schemas = [
        {
            "name": "AuditResult",
            "description": "The result of the audit",
            "schema_dict": {
                "type": "object",
                "properties": {
                    "total_cost": {"type": "number"},
                    "deliverables": {"type": "array", "items": {"type": "string"}},
                    "status": {"type": "string"}
                },
                "required": ["total_cost", "deliverables", "status"]
            }
        }
    ]
    
    print("Running extraction...")
    try:
        await run_engine_audit_structured_extraction(
            thread_id="test_thread",
            project_id=1,
            member_id=1,
            run_id="test_run",
            summary="A short project to deliver a report.",
            messages_dicts=messages_dicts,
            collected_schemas=collected_schemas,
        )
        print("Extraction completed successfully!")
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
