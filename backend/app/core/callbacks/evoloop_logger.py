from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.i18n.service import i18n


class EvoLoopCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that pushes logs to EvoLoop Link (Server-side Plugin).
    """

    def __init__(self, client: Any, thread_id: str, command_id: int | None = None):
        self.client = client
        self.thread_id = thread_id
        self.command_id = command_id
        self.token_buffer = ""

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> Any:
        # Notify start of thinking
        self.token_buffer = ""
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="thought",
            content=i18n.get("prompts.evoloop_logger.thinking"),
            command_id=self.command_id
        )

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
        # User requested to disable streaming. Accumulate silently only if needed for local logic,
        # but here we rely on LLMResult in on_llm_end.
        # Actually, on_llm_end provides the full generation, so we don't need to buffer manually.
        pass

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        if not response.generations:
            return

        # Capture the first generation text
        text = response.generations[0][0].text
        if text:
            await self.client.upload_log(
                thread_id=self.thread_id,
                log_type="thought",
                content=text,
                command_id=self.command_id
            )

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        # Ignore events with missing tool name to prevent "Unknown Tool" ghosts
        # caused by duplicate callbacks (e.g. from ToolExecutor vs internal invocation)
        if not serialized or not serialized.get("name"):
            return

        tool_name = serialized.get("name")
        self.current_tool_name = tool_name
        self.current_tool_path = None

        # Try to extract file path for read operations
        # Phase 18: Support new atomic file tools
        if tool_name in ["read_file", "view_file", "read_file_content", "manage_file", "list_files"]:
            import ast
            import json

            data = None
            try:
                # Agent inputs are often JSON strings
                if input_str.strip().startswith("{"):
                    data = json.loads(input_str)
            except:
                pass

            # Fallback: LangChain sometimes logs inputs as Python dict string (single quotes)
            if data is None:
                try:
                    if input_str.strip().startswith("{"):
                        data = ast.literal_eval(input_str)
                except:
                    pass

            if data and isinstance(data, dict):
                path = None

                if tool_name == "manage_file":
                    if data.get("action") == "read":
                        path = data.get("path")
                elif tool_name in ["read_file", "list_files"]:
                    path = data.get("path")
                else:
                    path = data.get("AbsolutePath") or data.get("file_path") or data.get("path") or data.get("TargetFile")

                if path:
                    self.current_tool_path = path

        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=i18n.get("prompts.evoloop_logger.running_tool", tool=tool_name, input=input_str[:200]),
            command_id=self.command_id
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        # Capture tool output
        content_to_log = output

        # Strict sanitation for file reads (including manage_file read)
        is_read_tool = self.current_tool_name in ["read_file", "view_file", "read_file_content", "list_files"]
        is_manage_read = (self.current_tool_name == "manage_file" and self.current_tool_path)

        if (is_read_tool or is_manage_read) and self.current_tool_path:
            lines = output.split('\n')
            count = len(lines)
            if not output: count = 0
            content_to_log = i18n.get("prompts.evoloop_logger.file_output", path=self.current_tool_path, count=count)

        # 1. Truncate for other large outputs (e.g. search results, huge diffs)
        # If the output is huge, we assume it's file content.
        elif len(output) > 500:
            lines = output.split('\n')
            if len(lines) > 20:
                content_to_log = i18n.get("prompts.evoloop_logger.truncated_output", preview=output[:300], lines=len(lines), chars=len(output))

        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            content=content_to_log,
            command_id=self.command_id
        )

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> Any:
        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="error",
            content=str(error),
            command_id=self.command_id
        )
