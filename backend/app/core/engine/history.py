import logging

from langchain_core.messages import HumanMessage, RemoveMessage
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
        revert_files: bool = True
    ) -> dict:
        """
        Rewinds history to a specific point.
        If target_message_id is provided, deletes that message and everything after it.
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
            stmt = select(Message).where(Message.thread_id == thread_id).where(Message.id >= min_id_to_delete)
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
            # Find which of the deleted DB messages exist in the current graph checkpoint
            # Note: message IDs in graph state (langchain) might be strings or UUIDs.
            # We match them by checking if the graph message ID is in our set of DB message IDs.
            graph_updates = []
            db_id_set = set(db_msg_ids) # Use only actual message IDs for graph sync

            # Optimization: for large histories, we only want to Remove the specific IDs.
            # LangGraph's RemoveMessage requires the ID of the message to remove.
            for m in graph_messages:
                # We assume m.id is what corresponds to our Message.id or checkpoint metadata
                if hasattr(m, "id") and str(m.id) in db_id_set:
                    graph_updates.append(RemoveMessage(id=m.id))
                elif isinstance(m, HumanMessage) and not target_message_id:
                    # Special case for standard rewind: if we found the last human message in graph
                    # but didn't match ID exactly (rare but possible if IDs differ)
                    # For now we strictly rely on ID matching as we synced them in storage.
                    pass

            if graph_updates:
                await graph.aupdate_state(config, {"messages": graph_updates})
                logger.info(f"LangGraph: Removed {len(graph_updates)} messages.")

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
