import logging
from typing import Any

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.persistence import MessagePersistencePolicy
from app.core.engine.message.schemas import MessageHandlerResult
from app.core.engine.message.stream import MessageStreamPolicy
from app.core.tools.registry import get_tool_metadata

logger = logging.getLogger(__name__)


class ToolMessageMixin:
    async def handle_tool_start(
        self,
        tool_name: str,
        tool_call_id: str | None = None,
        input_data: dict | None = None,
        parent_id: str | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        metadata = get_tool_metadata(tool_name)
        is_hidden = metadata.is_hidden

        category = (
            MessageCategory.INTERNAL_TOOL_CALL
            if is_hidden
            else MessageCategory.TOOL_OUTPUT
        )

        display_name = metadata.get_display_name(tool_name, input_data)
        tool_meta = {
            "display_name": display_name,
            "affected_path_keys": metadata.affected_path_keys,
        }

        message_id = None
        seq = 0

        effective_parent_id = parent_id or await self._repository.get_last_message_id()

        if category.should_persist_to_db:
            dev_key, dev_name = self._get_device_attribution()
            message_id, seq = await self._repository.persist(
                role="tool",
                content="",
                category=category.value,
                action_type="tool_output",
                status="running",
                is_visible=True,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content_type="text",
                metadata={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "input": input_data,
                    "tool_meta": tool_meta,
                },
                node_source=node_source,
                parent_id=effective_parent_id,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )

        if category.is_visible_to_user:
            await self._dispatch_block(
                role="tool",
                content="",
                category=category.value,
                status="running",
                sequence_number=seq,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={"tool_meta": tool_meta, "input": input_data},
                channels={"sse"},
                parent_id=effective_parent_id,
                message_id=message_id,
            )

        logger.info(
            f"[MessageHandler] Tool start tracked: {tool_name} (seq={seq}, hidden={is_hidden})"
        )
        return MessageHandlerResult(
            category=category.value,
            persisted=category.should_persist_to_db,
            streamed=category.is_visible_to_user,
            message_id=message_id,
            sequence_number=seq,
        )

    async def handle_tool_output(
        self,
        tool_name: str,
        output: Any,
        tool_call_id: str | None = None,
        run_id: str | None = None,
        sequence_number: int | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        metadata_registry = get_tool_metadata(tool_name)
        input_data = await self._repository.resolve_tool_input(
            tool_call_id, tool_name=tool_name
        )

        result_meta = {}
        display_name = ""
        if hasattr(output, "meta") and isinstance(output.meta, dict):
            result_meta = output.meta
        if hasattr(output, "display_name"):
            display_name = output.display_name

        if not display_name or result_meta:
            summary_args = {**input_data, **result_meta}
            display_name = metadata_registry.get_display_name(tool_name, summary_args)

        tool_meta = {
            "display_name": display_name,
            "affected_path_keys": metadata_registry.affected_path_keys,
        }

        if metadata_registry.is_hidden:
            category = MessageCategory.INTERNAL_TOOL_CALL
        else:
            category = MessageClassifier.classify_tool_output(
                tool_name, output, metadata=result_meta
            )

        content = str(output) if output else ""
        persist_data = MessagePersistencePolicy.apply_policy(
            category=category,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        stream_data = MessageStreamPolicy.apply_policy(
            category=category, content=content
        )

        logger.info(
            f"[MessageHandler] Tool {tool_name} output classified as: {category.value}, persist={persist_data.should_persist}"
        )

        message_id = None
        seq = sequence_number or 0

        metadata = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": input_data,
            "output": output,
            "tool_meta": tool_meta,
        }

        if seq and persist_data.should_persist:
            update_result = await self._repository.update(
                sequence_number=seq,
                status="completed",
                content=persist_data.content,
                node_source=node_source,
                meta_data=metadata,
            )
            if update_result:
                message_id = update_result
                if category.is_visible_to_user:
                    await self._dispatch_block(
                        role="tool",
                        content=persist_data.content,
                        category=category.value,
                        status="completed",
                        sequence_number=seq,
                        tool_name=persist_data.tool_name,
                        tool_call_id=persist_data.tool_call_id,
                        metadata=metadata,
                        channels={"mobile"},
                        message_id=message_id,
                    )
        elif persist_data.should_persist:
            dev_key, dev_name = self._get_device_attribution()
            message_id, seq = await self._repository.persist(
                role="tool",
                content=persist_data.content,
                category=category.value,
                action_type="tool_output",
                is_visible=category.is_visible_to_user,
                tool_call_id=persist_data.tool_call_id,
                tool_name=persist_data.tool_name,
                content_type="text",
                metadata=metadata,
                node_source=node_source,
                executor_device_key=dev_key,
                executor_device_name=dev_name,
            )
            if message_id and category.is_visible_to_user:
                await self._dispatch_block(
                    role="tool",
                    content=persist_data.content,
                    category=category.value,
                    status="completed",
                    sequence_number=seq,
                    tool_name=persist_data.tool_name,
                    tool_call_id=persist_data.tool_call_id,
                    metadata=metadata,
                    channels={"mobile"},
                    message_id=message_id,
                )

        if stream_data.should_stream:
            await self._dispatch_block(
                role="tool",
                content=content,
                category=category.value,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                sequence_number=seq if persist_data.should_persist else 0,
                status="completed",
                metadata=metadata,
                channels={"sse"},
                message_id=message_id,
                action="update",
            )

        return MessageHandlerResult(
            category=category.value,
            persisted=persist_data.should_persist,
            streamed=stream_data.should_stream,
            message_id=message_id,
            sequence_number=seq,
        )

    async def handle_tool_error(
        self,
        tool_name: str,
        error: BaseException,
        tool_call_id: str | None = None,
        sequence_number: int | None = None,
        node_source: str | None = None,
    ) -> MessageHandlerResult:
        content = str(error) if error else "Tool execution failed"
        seq = sequence_number or 0

        metadata_registry = get_tool_metadata(tool_name)
        input_data = await self._repository.resolve_tool_input(
            tool_call_id, tool_name=tool_name
        )
        display_name = None
        if metadata_registry.summary_template and input_data:
            display_name = metadata_registry.get_display_name(tool_name, input_data)

        metadata = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "input": input_data,
            "error": content,
            "tool_meta": {"display_name": display_name},
        }

        message_id = None
        if sequence_number:
            update_result = await self._repository.update(
                sequence_number=sequence_number,
                status="failed",
                content=content,
                node_source=node_source,
                meta_data=metadata,
            )
            if update_result:
                message_id = update_result if isinstance(update_result, str) else None

        return MessageHandlerResult(
            category=(
                MessageCategory.INTERNAL_TOOL_CALL
                if metadata_registry.is_hidden
                else MessageCategory.TOOL_OUTPUT
            ).value,
            persisted=bool(sequence_number),
            streamed=False,
            message_id=message_id,
            sequence_number=seq,
        )
