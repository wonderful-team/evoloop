import ast
import json
import time
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.i18n.service import i18n


class EvoLoopCallbackHandler(AsyncCallbackHandler):
    """
    Callback Handler that pushes logs to EvoLoop Link (Server-side Plugin).
    """

    def __init__(self, client: Any, thread_id: str, project_id: int | None = None, command_id: int | None = None):
        self.client = client
        self.thread_id = thread_id
        self.project_id = project_id
        self.command_id = command_id
        self.token_buffer = ""
        # Deduplication and Merging State
        self._last_tool_log = {"content": None, "timestamp": 0, "name": None}
        self._last_thought_log = {"content": None, "timestamp": 0}
        self._active_tools = {}  # {run_id: {name, arguments, path}}

    def _normalize_content(self, content: str) -> str:
        """Normalize content to handle JSON vs Python repr differences."""
        if not content:
            return ""
        try:
            # Try parsing as JSON first
            if content.strip().startswith("{") or content.strip().startswith("["):
                try:
                    data = json.loads(content)
                    return json.dumps(data, sort_keys=True)
                except json.JSONDecodeError:
                    pass

            # Try parsing as Python literal (for LangChain's str(dict))
            if (content.strip().startswith("{") or content.strip().startswith("[")) and "'" in content:
                try:
                    data = ast.literal_eval(content)
                    return json.dumps(data, sort_keys=True)
                except (ValueError, SyntaxError):
                    pass

            return content.strip()
        except Exception:
            return content.strip()

    async def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> Any:
        # Notify start of thinking
        self.token_buffer = ""
        content = i18n.get("prompts.evoloop_logger.thinking")

        # Simple Dedup for "Thinking..." start
        now = time.time()
        if self._last_thought_log["content"] == content and (now - self._last_thought_log["timestamp"] < 2.0):
            return

        self._last_thought_log = {"content": content, "timestamp": now}

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> Any:
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
                command_id=self.command_id,
                project_id=self.project_id,
            )

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        if not serialized or not serialized.get("name"):
            return

        tool_name = serialized.get("name")
        self.current_tool_name = tool_name
        self.current_tool_path = None

        if tool_name in [
            "read_file",
            "view_file",
            "read_file_content",
            "manage_file",
            "list_files",
            "search_code",
            "find_by_name",
            "grep_search",
        ]:
            data = None
            try:
                if input_str.strip().startswith("{"):
                    data = json.loads(input_str)
            except Exception:
                pass

            if data is None:
                try:
                    if input_str.strip().startswith("{"):
                        data = ast.literal_eval(input_str)
                except Exception:
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

        # Normalization & Deduplication
        normalized_input = self._normalize_content(input_str)
        display_input = normalized_input[:500]

        # Structured JSON for frontend
        content_to_log = json.dumps({
            "name": tool_name,
            "arguments": normalized_input,
            "display": i18n.get(
                "prompts.evoloop_logger.running_tool",
                tool=tool_name,
                input=display_input,
            )
        })

        run_id = str(kwargs.get("run_id", "default"))
        self._active_tools[run_id] = {
            "name": tool_name,
            "arguments": normalized_input,
            "path": self.current_tool_path
        }

        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            name=tool_name,
            content=content_to_log,
            command_id=self.command_id,
            project_id=self.project_id,
            persistent=False,  # WebSocket only for "Running" status
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        tool_info = self._active_tools.pop(run_id, {})
        if not tool_info:
            return

        tool_name = tool_info.get("name", "Tool")
        arguments = tool_info.get("arguments", "")
        tool_path = tool_info.get("path")

        is_read_tool = tool_name in [
            "read_file",
            "view_file",
            "read_file_content",
            "list_files",
            "search_code",
            "find_by_name",
            "grep_search",
        ]
        is_manage_read = (tool_name == "manage_file" and tool_path)

        # Optimization: Summarize heavy tool outputs as requested by user
        final_output = output
        if tool_name in ["read_file", "view_file", "read_file_content"] and output:
            try:
                line_count = len(output.splitlines())
                file_info = tool_path or "file"
                final_output = i18n.get("prompts.evoloop_logger.read_summary", path=file_info, count=line_count)
            except Exception:
                pass
        elif tool_name == "list_files" and output:
            try:
                item_count = len(output.splitlines())
                dir_info = tool_path or "directory"
                final_output = i18n.get("prompts.evoloop_logger.list_summary", path=dir_info, count=item_count)
            except Exception:
                pass

        combined_content = json.dumps({
            "name": tool_name,
            "arguments": arguments,
            "output": final_output,
            "status": "success",
            "is_file_content": is_read_tool or is_manage_read
        })

        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            name=tool_name,
            content=combined_content,
            command_id=self.command_id,
            project_id=self.project_id,
            persistent=True, # Combined log is persisted to DB
        )

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        run_id = str(kwargs.get("run_id"))
        tool_info = self._active_tools.pop(run_id, {})

        tool_name = tool_info.get("name", "error")
        arguments = tool_info.get("arguments", "")

        combined_content = json.dumps({
            "name": tool_name,
            "arguments": arguments,
            "output": str(error),
            "status": "error"
        })

        await self.client.upload_log(
            thread_id=self.thread_id,
            log_type="tool",
            name=tool_name,
            content=combined_content,
            command_id=self.command_id,
            project_id=self.project_id,
            persistent=True,  # Persist error state
        )
