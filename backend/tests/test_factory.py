import json
from app.core.engine.message.factory import MessageBlockFactory
from app.models.conversation import Message

msg = Message(
    id="msg-123",
    thread_id="th-123",
    role="tool",
    status="completed",
    tool_name="read_file",
    tool_call_id="call-123",
    meta_data={"input": {"path": "pyproject.toml"}},
    content="Success"
)

block = MessageBlockFactory.from_orm(msg)
print("Block input:", block.input)
print("Block tool_meta:", block.tool_meta)

msg_str_meta = Message(
    id="msg-124",
    thread_id="th-123",
    role="tool",
    status="completed",
    tool_name="read_file",
    tool_call_id="call-124",
    meta_data=json.dumps({"input": {"path": "pyproject.toml"}}),
    content="Success"
)

block2 = MessageBlockFactory.from_orm(msg_str_meta)
print("Block2 input:", block2.input)
print("Block2 tool_meta:", block2.tool_meta)
