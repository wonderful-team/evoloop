import asyncio
import logging
import os
import sys
import uuid
from sqlalchemy import select
from unittest.mock import patch, PropertyMock, AsyncMock

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("verify_devops_vault_integration")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.memory.lifespan import MemoryLifespanManager
from app.core.events.discovery import auto_discover_handlers
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph, get_graph
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.config.vault import SecureVaultService
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message
from app.models.codebase import Repository
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.inference_engine import InferenceEngine
from langchain_core.messages import AIMessage, HumanMessage
from app.core.engine.signals import RouteToSignal, RoutingContext
from app.core.engine.routers import RoutingTarget

class SmartMockInferenceEngine(InferenceEngine):
    def __init__(self, scenarios: dict):
        self._llm_factory = AsyncMock()
        self._scenarios = scenarios
        self._counters = {}

    async def create_llm(self, model, temperature):
        return AsyncMock(), "openai"

    def bind_tools(self, llm, tools):
        if tools:
            return llm, {t.name: t for t in tools}
        return llm, {}

    async def run_react_loop(
        self,
        llm_with_tools,
        messages,
        system_prompt,
        provider,
        config,
        name,
        max_steps=5,
        tool_executor=None,
        interceptors=None,
        on_thinking=None,
        model=None,
        **kwargs,
    ):
        idx = self._counters.get(name, 0)
        self._counters[name] = idx + 1

        scenario_list = self._scenarios.get(name, [])
        if idx >= len(scenario_list):
            ai_msg = AIMessage(content="任务完成")
            return {
                "messages": [ai_msg],
                "tool_history": [],
                "last_response": ai_msg,
                "is_truncated": False,
                "signal": None,
            }

        step = scenario_list[idx]
        new_messages = []
        local_tool_history = []

        ai_msg = AIMessage(
            content=step.get("content", ""),
            tool_calls=step.get("tool_calls", []),
        )
        new_messages.append(ai_msg)

        remaining = []
        for tc in step.get("tool_calls", []):
            if not interceptors or tc["name"] not in interceptors:
                remaining.append(tc)

        if remaining and tool_executor is not None:
            tool_results, sig = await tool_executor.execute_batch(remaining, local_tool_history)
            new_messages.extend(tool_results)

        if step.get("final_content"):
            new_messages.append(AIMessage(content=step["final_content"]))

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": ai_msg,
            "is_truncated": False,
            "signal": step.get("signal"),
        }

    async def run_single_shot(self, llm_with_tools, messages, system_prompt, provider, config, name, tool_executor=None, interceptors=None, **kwargs):
        return await self.run_react_loop(
            llm_with_tools, messages, system_prompt, provider, config, name,
            max_steps=1, tool_executor=tool_executor, interceptors=interceptors, **kwargs
        )

# Mock skill hydration and fallback SOPs to avoid extra DB calls / complex resolution
from app.core.engine.context_hydrator import AgentContextHydrator
_orig_hydrate = AgentContextHydrator.hydrate
async def _mock_hydrate(*args, **kwargs):
    return
AgentContextHydrator.hydrate = _mock_hydrate

from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver

_orig_get_node_skills = SkillHydrator.get_node_skills
async def _mock_get_node_skills(state, node_name):
    return []
SkillHydrator.get_node_skills = _mock_get_node_skills

_orig_inject_fallback = SkillResolver.inject_fallback_sops
async def _mock_inject_fallback(sops, config):
    return sops
SkillResolver.inject_fallback_sops = _mock_inject_fallback

# Settings override
from app.core.config import settings
if not hasattr(settings, "DEFAULT_PROJECT_ID"):
    object.__setattr__(settings, "DEFAULT_PROJECT_ID", 1)

async def initialize_system():
    logger.info("Initializing Real System for DevOps + Vault + HITL Integration Test...")
    # Force SQLite test db filepath to not affect dev db
    settings.EMBEDDED_MODE = True
    settings.SQLITE_PATH = "test_devops_integration.db"
    
    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    await MemoryLifespanManager.ainitialize()
    auto_discover_handlers()
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    graph = builder.build(os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    set_graph(graph)
    logger.info("System Base Ready.")
    return graph

async def run_verification():
    graph = None
    try:
        graph = await initialize_system()
        
        project_id = 1001
        thread_id = f"devops-vault-hitl-test-{uuid.uuid4().hex[:6]}"
        
        # 1. Mock EvoCloud project path mapping
        mock_project = {
            "id": project_id,
            "name": "EvoLoop DevOps Verification",
            "path": "/Users/xujin/Projects/evoloop"
        }
        
        # 2. Seed credential inside SecureVaultService
        SecureVaultService.add_credential(
            identifier="customer_test_ssh",
            type="ssh",
            payload={"password": "secret_password_test_123"},
            project_id=project_id,
            description="Integration test DevOps credential"
        )
        logger.info(f"Seeded credential: customer_test_ssh under project_id: {project_id}")

        # 3. Create scenarios for SmartMockInferenceEngine
        # Execute the command calling devops.sh, then ask_confirm (HITL)
        scenarios = {
            "Supervisor": [
                {
                    "content": '<route_to target="worker" reason="Check config using credential"/>',
                    "signal": RouteToSignal(
                        target=RoutingTarget.WORKER,
                        reason="Check config using credential",
                        context=RoutingContext(topic="DevOps check_config"),
                    ),
                },
                {
                    "content": '<route_to target="finish" reason="DevOps check completed after human confirmation"/>',
                    "signal": RouteToSignal(
                        target=RoutingTarget.FINISH,
                        reason="DevOps check completed after human confirmation",
                        context=RoutingContext(topic="Complete session"),
                    ),
                }
            ],
            "Worker": [
                # Turn 1: Calls execute_command with secure placeholder, then asks confirmation
                {
                    "tool_calls": [
                        {
                            "name": "execute_command",
                            "args": {
                                "command": "echo 'Vault secret password is: {{vault.customer_test_ssh.password}}' && bash skills/evoloop_devops/scripts/devops.sh --action check_config --customer customer_test"
                            },
                            "id": "tc-execute-command-1"
                        },
                        {
                            "name": "ask_confirm",
                            "args": {
                                "action_description": "Do you confirm deploying customer_test configuration?",
                                "risk_level": "medium"
                            },
                            "id": "tc-ask-confirm-1"
                        }
                    ],
                    "final_content": "Preparing configuration validation and waiting for user confirmation."
                },
                # Turn 2 (resuming): Simple final confirmation
                {
                    "content": "Deployment simulated successfully.",
                    "tool_calls": [],
                }
            ],
            "Finish": [
                {
                    "content": "<evoloop_session_audit>Session completed successfully</evoloop_session_audit>",
                }
            ]
        }

        # Inject SmartMockInferenceEngine
        smart_engine = AgentEngine(inference_engine=SmartMockInferenceEngine(scenarios))
        set_default_engine(smart_engine)

        with patch("app.core.evocloud.evocloud_manager.get_project_by_id", new_callable=AsyncMock, return_value=mock_project):
            # 4. Dispatch the first agent run
            user_input = "Please run config check for customer_test using password from vault."
            logger.info(f"🚀 Dispatching first agent run: {user_input}")
            dispatch_res = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=user_input,
                project_id=project_id,
                model="kimi-k2-thinking-turbo"
            )
            assert dispatch_res.status == "queued"
            
            # Run the agent in background. This should raise AgentHumanInterruptException internally
            # and exit cleanly (returning status of thread).
            logger.info("Executing agent background loop (Turn 1)...")
            await run_agent_background(thread_id, dispatch_res.inputs)
            
            # 5. Audit results of Turn 1
            async with session_scope() as session:
                stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
                res = await session.execute(stmt)
                all_msgs = res.scalars().all()
            
            logger.info(f"Messages after Turn 1: {len(all_msgs)}")
            for m in all_msgs:
                logger.info(f"  * {m.role.upper()} ({m.action_type}/{m.category}): {str(m.content)[:200]}")
            
            # Check execute_command message and verify password was masked
            exec_tool_msg = next((m for m in all_msgs if m.tool_name == "execute_command"), None)
            assert exec_tool_msg is not None, "execute_command tool response was not recorded"
            assert "secret_password_test_123" not in exec_tool_msg.content, "Censorship hook FAILED: Raw secret found in logs!"
            assert "Vault secret password is: ******" in exec_tool_msg.content, "Censorship hook FAILED: Placeholder output was not masked properly!"
            logger.info("✅ SUCCESS: Vault replacement and output censorship hooks verified!")

            # Verify that we have a pending HITL request
            hitl_msg = next((m for m in all_msgs if m.status == "waiting_human" or m.action_type == "hitl"), None)
            assert hitl_msg is not None, "HITL ask_confirm request was not recorded"
            logger.info("✅ SUCCESS: HITL interrupt recorded in database!")

            # 6. Resume the agent run (Turn 2) — via run_agent_background with hitl_resume_response
            logger.info("\n🚀 Resuming execution with user confirmation response...")
            await run_agent_background(thread_id, {
                "messages": [],
                "project_id": project_id,
                "model": "kimi-k2-thinking-turbo",
                "hitl_resume_response": "approved",
            })
            
            # 7. Audit results of Turn 2
            async with session_scope() as session:
                stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
                res = await session.execute(stmt)
                all_msgs_final = res.scalars().all()
                
            logger.info(f"Messages after Resumption: {len(all_msgs_final)}")
            for m in all_msgs_final:
                logger.info(f"  * {m.role.upper()} ({m.action_type}/{m.category}): {str(m.content)[:200]}")
                
            # Verify the session finished successfully via graph state
            real_graph = get_graph()
            final_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}
            final_state = await real_graph.aget_state(final_config)
            logger.info(f"[DEBUG] Final graph state next: {final_state.next}")
            if final_state.values and "messages" in final_state.values:
                for idx, m in enumerate(final_state.values["messages"]):
                    logger.info(f"   - graph msg {idx}: type={type(m).__name__}, content={str(m.content)[:120]}")

            graph_completed = not final_state.next
            finish_msg = next((m for m in all_msgs_final if m.role == "ai" and "Session completed successfully" in str(m.content)), None)
            assert graph_completed or finish_msg is not None, (
                "Resumption failed: Agent did not reach Finish state! "
                f"graph.next={final_state.next}, db_messages={len(all_msgs_final)}"
            )
            logger.info("✅ SUCCESS: HITL resume successfully executed and agent ran to completion!")

    finally:
        try:
            await db_resource_manager.shutdown()
        except Exception as e:
            logger.warning(f"Error during db shutdown: {e}")
        # Clean up database file
        if os.path.exists("test_devops_integration.db"):
            try:
                os.remove("test_devops_integration.db")
            except Exception as e:
                logger.warning(f"Failed to delete test_devops_integration.db: {e}")
        logger.info("Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(run_verification())
