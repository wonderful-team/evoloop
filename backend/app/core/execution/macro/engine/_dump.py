import json
import logging
import os
from datetime import datetime, timezone

from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger(__name__)


class DumpMixin:
    @classmethod
    async def _handle_dump(cls, thread_id, payload, extracted_data):
        sink_type = payload.get("sink_type", "file")

        data_to_dump = dict(extracted_data)
        if payload.get("include_state_items"):
            state_file = extracted_data.get("collect_results", {}).get("state_file")
            if state_file and os.path.exists(state_file):
                try:
                    with open(state_file, encoding='utf-8') as f:
                        state_data = json.load(f)
                        data_to_dump["batch_items"] = state_data.get("items", [])
                        logger.info(f"[{thread_id}] Enriched dump with {len(data_to_dump['batch_items'])} items from state file")
                except Exception as e:
                    logger.warning(f"[{thread_id}] Failed to load state file for enriched dump: {e}")

        if sink_type == "file":
            await cls._dump_to_file(thread_id, payload, data_to_dump)
        elif sink_type == "mcp":
            await cls._dump_to_mcp(thread_id, payload, data_to_dump)
        elif sink_type == "webhook":
            await cls._dump_to_webhook(thread_id, payload, data_to_dump)
        else:
            logger.warning(f"Unknown sink_type: {sink_type}, falling back to file")
            await cls._dump_to_file(thread_id, payload, data_to_dump)

    @classmethod
    async def _dump_to_file(cls, thread_id, payload, extracted_data):
        sink_path = payload.get("path", f"/tmp/macro_results_{thread_id}.json")
        await activity_monitor.log_event("macro_thought", {"text": f"Dump extracted data to {sink_path}"}, thread_id)
        try:
            with open(sink_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[MacroEngine] Data dumped to file: {sink_path}")
        except Exception as e:
            logger.warning(f"Failed to dump data to file: {e}")

    @classmethod
    async def _dump_to_mcp(cls, thread_id, payload, extracted_data):
        from app.core.mcp import mcp_client_manager

        mcp_server = payload.get("mcp_server", "supabase")
        mcp_tool_name = payload.get("mcp_tool")
        table = payload.get("table", "extracted_data")
        operation = payload.get("operation", "insert")

        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Pushing data to MCP server '{mcp_server}' using {mcp_tool_name or operation}"},
            thread_id
        )

        try:
            tools = await mcp_client_manager.get_tools(mcp_server)
            if not tools:
                logger.error(f"[MacroEngine] MCP server '{mcp_server}' not available")
                return

            target_tool = None
            for tool in tools:
                if mcp_tool_name:
                    formatted_name = f"mcp__{mcp_server.replace(' ', '_').replace('-', '_')}__{mcp_tool_name.replace(' ', '_').replace('-', '_')}"
                    if tool.name == mcp_tool_name or tool.name == formatted_name:
                        target_tool = tool
                        break

                if not mcp_tool_name:
                    tool_name = tool.name.lower()
                    if operation in tool_name or "insert" in tool_name or "store" in tool_name:
                        target_tool = tool
                        break

            if not target_tool:
                if mcp_tool_name:
                    logger.error(f"[MacroEngine] MCP tool '{mcp_tool_name}' not found on server '{mcp_server}'")
                    return
                target_tool = tools[0]
                logger.warning(f"[MacroEngine] Using total fallback MCP tool: {target_tool.name}")

            mapping = payload.get("data_mapping")
            if mapping:
                data_payload = {}
                for target_key, source_key in mapping.items():
                    if source_key == "$thread_id":
                        data_payload[target_key] = thread_id
                    elif source_key == "$timestamp":
                        data_payload[target_key] = datetime.now(timezone.utc).isoformat()
                    else:
                        data_payload[target_key] = extracted_data.get(source_key)

                if not data_payload:
                    logger.warning(f"[{thread_id}] MCP data_mapping resulted in empty payload")
            else:
                data_payload = {
                    "table": table,
                    "data": extracted_data,
                    "thread_id": thread_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            result = await target_tool.ainvoke(data_payload)
            logger.info(f"[MacroEngine] Data pushed to MCP '{mcp_server}': {result}")

        except Exception as e:
            logger.error(f"[MacroEngine] Failed to push data to MCP: {e}", exc_info=True)

    @classmethod
    async def _dump_to_webhook(cls, thread_id, payload, extracted_data):
        import httpx

        webhook_url = payload.get("webhook_url")
        if not webhook_url:
            logger.error("[MacroEngine] webhook_url required for webhook sink_type")
            return

        headers = payload.get("headers", {})
        method = payload.get("method", "POST").upper()

        await activity_monitor.log_event(
            "macro_thought",
            {"text": f"Pushing data to webhook: {webhook_url}"},
            thread_id
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                request_data = {
                    "thread_id": thread_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": extracted_data
                }

                if method == "POST":
                    response = await client.post(webhook_url, json=request_data, headers=headers)
                elif method == "PUT":
                    response = await client.put(webhook_url, json=request_data, headers=headers)
                else:
                    logger.error(f"[MacroEngine] Unsupported HTTP method: {method}")
                    return

                response.raise_for_status()
                logger.info(f"[MacroEngine] Data pushed to webhook: {response.status_code}")

        except Exception as e:
            logger.error(f"[MacroEngine] Failed to push data to webhook: {e}", exc_info=True)
