import json
import logging
import re

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
        include_target: bool = True,
        reset_state: bool = False
    ) -> dict:
        """
        rewinds history to a specific point.
        If target_message_id is provided, deletes that message and everything after it (unless include_target=False).
        If not provided, deletes everything after the last user message (Standard Rewind).
        
        If reset_state is True, also clears the blackboard and iteration_count in LangGraph state.
        
        Returns a dict with status and potentially the checkpoint_id to rollback to.
        """
        graph = get_graph()
        if not graph:
            raise RuntimeError("Graph unavailable")

        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)

        # We need the list of messages from the graph state for RemoveMessage syncing
        graph_messages = state.values.get("messages", []) if state.values else []
        if not graph_messages:
            logger.warning(f"[perform_rewind] No messages in checkpoint for thread {thread_id}. Will attempt DB-based recovery.")

        async with get_db_session() as session:
            # 1. Determine the Human Message Sequence up to the target
            min_id_to_delete = None
            target_human_sequence = []
            
            if target_message_id:
                try:
                    msg_id_int = int(target_message_id)
                    target_msg = await session.get(Message, msg_id_int)
                    if not target_msg:
                        return {"status": "message_not_found", "removed_count": 0, "files_reverted": 0}
                    min_id_to_delete = target_msg.id
                    
                    # Fetch human sequence up to this ID for precise checkpoint matching
                    stmt = (
                        select(Message)
                        .where(Message.thread_id == thread_id)
                        .where(Message.role == "human")
                        .where(Message.id <= min_id_to_delete)
                        .order_by(Message.id.asc())
                    )
                    res = await session.execute(stmt)
                    target_human_sequence = [m.content for m in res.scalars().all()]
                except (ValueError, TypeError):
                    return {"status": "invalid_id", "removed_count": 0, "files_reverted": 0}
            else:
                # Default: find last human message
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
                target_human_sequence = [last_human.content]

            if min_id_to_delete is None:
                return {"status": "nothing_to_delete", "removed_count": 0, "files_reverted": 0}

            # Collect all messages to be deleted from DB
            if include_target:
                stmt = select(Message).where(Message.thread_id == thread_id).where(Message.id >= min_id_to_delete)
            else:
                stmt = select(Message).where(Message.thread_id == thread_id).where(Message.id > min_id_to_delete)
            
            result = await session.execute(stmt)
            msgs_to_delete = result.scalars().all()
            db_msg_ids = [str(m.id) for m in msgs_to_delete]
            stable_ids = []
            for m in msgs_to_delete:
                if m.run_id: stable_ids.append(m.run_id)
                if m.tool_calls:
                    for tc in m.tool_calls:
                        if isinstance(tc, dict) and tc.get("id"): stable_ids.append(tc["id"])

            logger.info(f"[perform_rewind] Found {len(msgs_to_delete)} DB messages to delete.")

            # [Sync Fix] Extract extra IDs from graph state before rollback (Ghost Runs)
            graph_run_ids = []
            if graph_messages:
                for gm in graph_messages:
                    rid = getattr(gm, 'additional_kwargs', {}).get('run_id') or \
                          getattr(gm, 'metadata', {}).get('run_id')
                    if rid: graph_run_ids.append(rid)

            all_cleanup_ids = list(set(db_msg_ids + stable_ids + graph_run_ids))
            files_reverted = 0
            try:
                # Cleanup side effects
                cleanup_result = await cleanup_side_effects(db_msg_ids, revert_files=revert_files, run_ids=all_cleanup_ids)
                files_reverted = cleanup_result.get("FileUndoHandler", 0)
            except Exception as e:
                logger.error(f"Side effects cleanup failed: {e}")

            # 3. LangGraph State Checkpoint Discovery (The "Sequence-Aware" Time Travel)
            checkpoint_id = None
            base_state = None
            graph_updates = []
            
            def extract_text(content):
                if not content: return ""
                if isinstance(content, (bytes, bytearray)):
                    content = content.decode("utf-8")
                
                # 1. Handle Stringified JSON/Dict (Malformed or valid)
                if isinstance(content, str):
                    content = content.strip()
                    # Try to parse if it looks like JSON/Dict
                    if (content.startswith("{") and content.endswith("}")) or (content.startswith("[") and content.endswith("]")):
                        try:
                            parsed = json.loads(content)
                            return extract_text(parsed)
                        except:
                            try:
                                import ast
                                parsed = ast.literal_eval(content)
                                return extract_text(parsed)
                            except:
                                # Fallback to regex if parsing failed
                                text_matches = re.findall(r'["\']text["\']:\s*["\'](.*?)["\']', content)
                                if text_matches:
                                    return "".join(text_matches).strip()
                    return content
                
                # 2. Handle List (LangChain content format)
                if isinstance(content, list):
                    texts = []
                    for item in content:
                        if isinstance(item, dict):
                            texts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            texts.append(item)
                    return "".join(texts).strip()
                
                # 3. Handle Dict
                if isinstance(content, dict):
                    return content.get("text", "") or content.get("content", "") or str(content)

                return str(content).strip()

            target_seq_text = [extract_text(c) for c in target_human_sequence]
            target_joined = "".join(target_seq_text).replace("\n", "").replace(" ", "")
            
            logger.info(f"LangGraph: Target human sequence (flattened): {target_joined[:100]}...")

            historical_states = []
            async for state_snapshot in graph.aget_state_history(config):
                historical_states.append(state_snapshot)
            
            # Find matching sequence (search from newest to oldest)
            for state_snapshot in historical_states:
                sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []
                sn_human_seq = [extract_text(m.content) for m in sn_msgs if isinstance(m, HumanMessage)]
                sn_joined = "".join(sn_human_seq).replace("\n", "").replace(" ", "")
                
                if sn_joined == target_joined:
                    checkpoint_id = state_snapshot.config["configurable"].get("checkpoint_id")
                    base_state = state_snapshot
                    logger.info(f"LangGraph: Found sequence match at checkpoint {checkpoint_id}.")
                    
                    found_target_human = False
                    for m in sn_msgs:
                        if isinstance(m, HumanMessage) and extract_text(m.content) == target_seq_text[-1]:
                            found_target_human = True
                            continue
                        if found_target_human and isinstance(m, (AIMessage, ToolMessage, RemoveMessage)):
                            graph_updates.append(RemoveMessage(id=m.id))
                            logger.info(f"LangGraph: Marking stale message {m.id} in base checkpoint for removal.")
                    break

            # --- FALLBACK: Prefix Matching for Edited Messages ---
            if not checkpoint_id and len(target_seq_text) > 0:
                logger.warning("LangGraph: Full sequence match failed. Attempting prefix match (handling edited messages)...")
                prefix_seq_text = target_seq_text[:-1]
                prefix_joined = "".join(prefix_seq_text).replace("\n", "").replace(" ", "")
                
                for state_snapshot in historical_states:
                    sn_msgs = state_snapshot.values.get("messages", []) if state_snapshot.values else []
                    sn_human_seq = [extract_text(m.content) for m in sn_msgs if isinstance(m, HumanMessage)]
                    sn_joined = "".join(sn_human_seq).replace("\n", "").replace(" ", "")
                    
                    if sn_joined == prefix_joined:
                        checkpoint_id = state_snapshot.config["configurable"].get("checkpoint_id")
                        base_state = state_snapshot
                        logger.info(f"LangGraph: Found prefix match at checkpoint {checkpoint_id}. This state is BEFORE the target human message.")
                        # Since we match the state before the target, we don't need to remove subsequent messages
                        # from the state values because the target hasn't been added yet in this checkpoint.
                        break

            if not checkpoint_id:
                logger.error(f"CRITICAL: No matching history found for sequence.")
                if target_message_id:
                    raise RuntimeError(f"Could not find matching LangGraph history for sequence ending in {target_message_id}")

            # 4. LangGraph State Update (Rollback/Time Travel)
            if checkpoint_id and base_state:
                updates = {}
                if graph_updates:
                    updates["messages"] = graph_updates

                if reset_state:
                    # Reset only turn-scoped data stored in blackboard
                    new_bb = base_state.values.get("blackboard", {}).copy()
                    turn_keys_to_reset = [
                        "ticket", "verification", "route_reason", "next_node", 
                        "situation_analysis", "action_plan", "error", "spawn_plan",
                        "pending_aggregation", "plan_approved"
                    ]
                    for key in turn_keys_to_reset:
                        new_bb[key] = None
                    
                    updates.update({
                        "blackboard": new_bb,
                        "iteration_count": 0,
                        "current_plan": None,
                        "structured_plan": None,
                        "next_node": None,
                        "situation_analysis": None,
                        "action_plan": None,
                        "error": None
                    })

                # Always update the state to point to the desired checkpoint
                # This ensures the next run starts from this historical point.
                try:
                    updated_config = await graph.aupdate_state(base_state.config, updates)
                    if updated_config and "configurable" in updated_config:
                        new_checkpoint_id = updated_config["configurable"].get("checkpoint_id")
                        if new_checkpoint_id:
                            logger.info(f"LangGraph: State updated, new branch/checkpoint: {new_checkpoint_id}")
                            checkpoint_id = new_checkpoint_id
                except Exception as e:
                    logger.error(f"LangGraph: Failed to update state during rewind: {e}")

            # 5. DB Deletion
            int_msg_ids = [int(mid) for mid in db_msg_ids]
            if int_msg_ids:
                await session.execute(
                    delete(MessageReference).where(MessageReference.message_id.in_(int_msg_ids))
                )
                await session.execute(
                    update(Message)
                    .where(Message.parent_id.in_(int_msg_ids))
                    .values(parent_id=None)
                )
                del_stmt = delete(Message).where(Message.id.in_(int_msg_ids))
                await session.execute(del_stmt)
                await session.commit()
                logger.info(f"HistoryService: Successfully deleted {len(db_msg_ids)} messages from DB.")

            return {
                "status": "success",
                "removed_count": len(db_msg_ids),
                "files_reverted": files_reverted,
                "msg_ids": db_msg_ids,
                "checkpoint_id": checkpoint_id
            }


history_service = HistoryService()
