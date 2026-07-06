"""Mock chat simulation helpers for publishing events."""

import asyncio

from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.publisher import MessagePublisher


async def publish_ai_tool_call(
    thread_id: str,
    seq_num: int,
    tool_name: str,
    tool_args: dict,
    call_id: str,
    run_id: str,
):
    """Publish an AI thinking message with tool calls (Supervisor's decision)."""
    publisher = MessagePublisher(thread_id)
    msg_block = MessageBlockFactory.from_event(
        thread_id=thread_id,
        sequence_number=seq_num,
        role="ai",
        content="",
        category="ai_response",
        status="completed",
        run_id=run_id,
        tool_calls=[
            {
                "id": call_id,
                "name": tool_name,
                "args": tool_args,
                "type": "tool_call",
            }
        ],
    )
    await publisher.publish(msg_block)
    await asyncio.sleep(0.4)


async def publish_tool_start(
    thread_id: str,
    seq_num: int,
    tool_name: str,
    call_id: str,
    input_args: dict,
    run_id: str,
):
    """Publish a tool starting event (status='running')."""
    publisher = MessagePublisher(thread_id)
    tool_block = MessageBlockFactory.from_event(
        thread_id=thread_id,
        sequence_number=seq_num,
        role="tool",
        content="",
        category="tool_output",
        status="running",
        run_id=run_id,
        tool_name=tool_name,
        tool_call_id=call_id,
        metadata={"input": input_args},
    )
    await publisher.publish(tool_block)
    await asyncio.sleep(0.4)


async def publish_tool_output(
    thread_id: str,
    seq_num: int,
    tool_name: str,
    call_id: str,
    input_args: dict,
    output_content: str,
    run_id: str,
):
    """Publish a tool output event (status='completed')."""
    publisher = MessagePublisher(thread_id)
    tool_block = MessageBlockFactory.from_event(
        thread_id=thread_id,
        sequence_number=seq_num,
        role="tool",
        content=output_content,
        category="tool_output",
        status="completed",
        run_id=run_id,
        tool_name=tool_name,
        tool_call_id=call_id,
        metadata={"input": input_args, "output": output_content},
    )
    await publisher.publish(tool_block)
    await asyncio.sleep(0.4)
