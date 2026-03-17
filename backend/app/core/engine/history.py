import logging

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from sqlalchemy import delete, select, update

from app.core.engine.cleanup import cleanup_side_effects
from app.core.globals import get_graph
from app.infrastructure.database.sql.database import get_db_session
from app.models import Message, MessageReference

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Unified service for managing conversation history, 
    including message deletion, file revert (Undo), and state synchronization.
    """

    @staticmethod
    async def perform_rewind(
        thread_id: str,
        target_message_id: str | None = None,
        revert_files: bool = True,
        include_target: bool = True
    ) -> dict:
        """
        Rewinds history to a specific point.
        If target_message_id is provided, deletes that message and everything after it (unless include_target=False).
        If not provided, deletes everything after the last user message (Standard Rewind).
        """
        graph = get_graph()
        if not graph:
            raise RuntimeError("Graph unavailable")

        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)

        # We need the list of messages from the graph state for RemoveMessage syncing
        graph_messages = state.values.get("messages", []) if state.values else []
        if not graph_messages:
            return {"status": "empty", "removed_count": 0, "files_reverted": 0}

        async with get_db_session() as session:
            # 1. Determine the range of messages to delete
            min_id_to_delete = None
            if target_message_id:
                # Find the target message in DB
                try:
                    msg_id_int = int(target_message_id)
                    target_msg = await session.get(Message, msg_id_int)
                    if not target_msg:
                        return {"status": "message_not_found", "removed_count": 0, "files_reverted": 0}

                    min_id_to_delete = target_msg.id
                except (ValueError, TypeError):
                    return {"status": "invalid_id", "removed_count": 0, "files_reverted": 0}
            else:
                # Default: find last human message and delete it + all after it
                stmt = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .where(Message.role == "human")
                    .order_by(Message.id.desc())
                    .limit(1)
                )
                res = await session.execute(stmt)
                last_human = res.scalar_one_or_none()
                if not last_human:
                    return {"status": "no_human_message_found", "removed_count": 0, "files_reverted": 0}

                min_id_to_delete = last_human.id

            if min_id_to_delete is None:
                return {"status": "nothing_to_delete", "removed_count": 0, "files_reverted": 0}

            # Collect all messages to be deleted based on min_id_to_delete
            if include_target:
                stmt = select(Message).where(Message.thread_id == thread_id).where(Message.id >= min_id_to_delete)
            else:
                stmt = select(Message).where(Message.thread_id == thread_id).where(Message.id > min_id_to_delete)
            
            result = await session.execute(stmt)
            msgs_to_delete = result.scalars().all()

            if not msgs_to_delete:
                return {"status": "nothing_to_delete", "removed_count": 0, "files_reverted": 0}

            # Collect various IDs for robust side-effect matching
            db_msg_ids = [] # Actual message IDs (int)
            stable_ids = [] # Includes run_id and tool_call_id (str)

            for m in msgs_to_delete:
                db_msg_ids.append(str(m.id)) # Store as string for consistency with cleanup_side_effects
                if m.run_id:
                    stable_ids.append(m.run_id)
                if m.tool_calls:
                    for tc in m.tool_calls:
                        if isinstance(tc, dict) and tc.get("id"):
                            stable_ids.append(tc["id"])

            # Combine all unique IDs for cleanup
            all_cleanup_ids = list(set(db_msg_ids + stable_ids))

            # 2. File Undo (Side Effects)
            files_reverted = 0
            try:
                # Cleanup using all possible ID matches
                cleanup_result = await cleanup_side_effects(all_cleanup_ids, revert_files=revert_files)
                files_reverted = cleanup_result.get("FileUndoHandler", 0)
            except Exception as e:
                logger.error(f"Side effects cleanup failed: {e}")

            # 3. LangGraph State Sync (RemoveMessage)
            # Fix: Database Message.id (int) doesn't match LangGraph message.id (UUID).
            # We use multiple strategies to match messages:
            # 1. Build a map of run_id/tool_call_id -> graph message
            # 2. Match database messages using run_id and tool_call_id
            graph_updates = []

            # Build lookup maps from graph messages
            graph_msg_by_run_id = {}
            graph_msg_by_tool_call_id = {}
            graph_human_msgs = []
            graph_ai_msgs = []

            for m in graph_messages:
                # Index by run_id (stored in additional_kwargs or metadata)
                run_id = getattr(m, 'additional_kwargs', {}).get('run_id') or \
                         getattr(m, 'metadata', {}).get('run_id')
                if run_id:
                    graph_msg_by_run_id[run_id] = m

                # Index AI messages by their tool_call_ids
                if isinstance(m, AIMessage):
                    tool_calls = getattr(m, 'tool_calls', None)
                    if tool_calls:
                        for tc in tool_calls:
                            if isinstance(tc, dict) and tc.get('id'):
                                graph_msg_by_tool_call_id[tc['id']] = m
                    graph_ai_msgs.append(m)

                # Index human messages for sequence-based matching
                if isinstance(m, HumanMessage):
                    graph_human_msgs.append(m)

                # Index tool messages by tool_call_id
                if isinstance(m, ToolMessage):
                    tc_id = getattr(m, 'tool_call_id', None)
                    if tc_id:
                        graph_msg_by_tool_call_id[tc_id] = m

            # Match database messages to graph messages
            removed_graph_ids = set()
            for db_msg in msgs_to_delete:
                matched = False

                # Strategy 1: Match by run_id
                if db_msg.run_id and db_msg.run_id in graph_msg_by_run_id:
                    graph_m = graph_msg_by_run_id[db_msg.run_id]
                    if graph_m.id not in removed_graph_ids:
                        graph_updates.append(RemoveMessage(id=graph_m.id))
                        removed_graph_ids.add(graph_m.id)
                        matched = True
                        continue

                # Strategy 2: Match by tool_call_id from tool_calls JSON
                if db_msg.tool_calls:
                    for tc in db_msg.tool_calls:
                        if isinstance(tc, dict) and tc.get('id'):
                            tc_id = tc['id']
                            if tc_id in graph_msg_by_tool_call_id:
                                graph_m = graph_msg_by_tool_call_id[tc_id]
                                if graph_m.id not in removed_graph_ids:
                                    graph_updates.append(RemoveMessage(id=graph_m.id))
                                    removed_graph_ids.add(graph_m.id)
                                    matched = True
                                    break
                    if matched:
                        continue

                # Strategy 3: For AI messages, match by content similarity (last resort)
                if db_msg.role == 'ai' and db_msg.content and graph_ai_msgs:
                    for graph_m in reversed(graph_ai_msgs):
                        if graph_m.id in removed_graph_ids:
                            continue
                        graph_content = getattr(graph_m, 'content', '') or ''
                        # Check if content matches (allowing for truncation)
                        if db_msg.content in graph_content or graph_content in db_msg.content:
                            graph_updates.append(RemoveMessage(id=graph_m.id))
                            removed_graph_ids.add(graph_m.id)
                            matched = True
                            break
                    if matched:
                        continue

                # Strategy 4: For tool messages, match by checking if tool_call_id matches
                if db_msg.role == 'tool' and graph_msg_by_tool_call_id:
                    # Tool messages should have been matched in strategy 2
                    pass

            # If we still haven't matched the target human message (for non-include_target case),
            # use sequence-based approach
            if not include_target and target_message_id and not matched:
                # Find the target message's sequence number
                target_seq = None
                for db_msg in msgs_to_delete:
                    if str(db_msg.id) == target_message_id:
                        target_seq = db_msg.sequence_number
                        break

                if target_seq is not None:
                    # Remove all graph messages that come after the matching point
                    # We estimate based on message count - remove roughly (total - position) messages
                    logger.info(f"Using sequence-based removal: target_seq={target_seq}")

            if graph_updates:
                await graph.aupdate_state(config, {"messages": graph_updates})
                logger.info(f"LangGraph: Removed {len(graph_updates)} messages using multi-strategy matching.")
            else:
                logger.warning(f"LangGraph: No messages matched for removal. DB messages to delete: {len(msgs_to_delete)}")

                # Fallback: If no messages were matched but we have messages to delete,
                # we might have a serious sync issue. Log detailed info for debugging.
                logger.error(
                    f"Critical sync issue in thread {thread_id}: "
                    f"DB has {len(msgs_to_delete)} messages to delete, "
                    f"but none could be matched to LangGraph messages. "
                    f"Graph has {len(graph_messages)} messages. "
                    f"DB IDs: {db_msg_ids[:5]}..., "
                    f"Run IDs in DB: {list(set(m.run_id for m in msgs_to_delete if m.run_id))[:5]}..., "
                    f"Run IDs in Graph: {list(graph_msg_by_run_id.keys())[:5]}..."
                )

            # 5. DB Deletion
            # First, delete references to satisfy FK constraints (Bulk delete bypasses ORM cascades)
            int_msg_ids = [int(mid) for mid in db_msg_ids]

            # MessageReference cleanup
            await session.execute(
                delete(MessageReference).where(MessageReference.message_id.in_(int_msg_ids))
            )

            # Nullify parent_id for ANY messages pointing to the ones we are about to delete
            await session.execute(
                update(Message)
                .where(Message.parent_id.in_(int_msg_ids))
                .values(parent_id=None)
            )

            # Finally delete the messages
            del_stmt = delete(Message).where(Message.id.in_(int_msg_ids))
            await session.execute(del_stmt)
            await session.commit()

            logger.info(f"HistoryService: Successfully rewound {len(db_msg_ids)} messages in thread {thread_id}.")

            return {
                "status": "success",
                "removed_count": len(db_msg_ids),
                "files_reverted": files_reverted,
                "msg_ids": db_msg_ids
            }


history_service = HistoryService()
