"""End-to-end tests: audit → extraction → dispatch → subscribers.

Simulates a realistic session: refactoring Flask → FastAPI.
"""

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.extraction import ExtractionContext, ExtractionPlugin, ExtractionRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    ExtractionRegistry._plugins.clear()
    ExtractionRegistry._handled_threads.clear()
    yield


# =============================================================================
# Realistic plugin schemas (mirroring actual production schemas)
# =============================================================================

KNOWLEDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short descriptive title"},
        "content": {"type": "string", "description": "Knowledge content in Markdown"},
        "category": {
            "type": "string",
            "enum": [
                "technical_rule", "business_logic", "workflow",
                "architecture", "environment",
            ],
            "description": "Knowledge category",
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "source_context": {"type": "string", "description": "Conversation excerpt"},
    },
    "required": ["title", "content", "category"],
}

TODO_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Task title"},
        "description": {"type": "string", "description": "What needs to be done"},
        "priority": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Priority",
        },
        "category": {"type": "string", "description": "Task category"},
        "reasoning": {"type": "string", "description": "Why this was identified"},
    },
    "required": ["title", "description", "priority"],
}

MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["user", "feedback", "project", "reference", "concept", "episode"],
            "description": "Memory type",
        },
        "content": {"type": "string", "description": "Memory content"},
        "title": {"type": "string", "description": "Short title"},
        "description": {"type": "string", "description": "Optional description"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["content"],
}


# =============================================================================
# Realistic LLM response simulation
# =============================================================================

REAL_SESSION_SUMMARY = (
    "Successfully refactored the Flask-based user management service "
    "to FastAPI. Migrated all REST endpoints, replaced Flask-SQLAlchemy "
    "with SQLAlchemy 2.0 async, and updated the test suite. "
    "Authentication middleware was ported to FastAPI dependencies. "
    "Two routes had breaking changes that required manual verification."
)

REAL_KNOWLEDGE_ITEMS = [
    {
        "title": "FastAPI Dependency Injection Pattern for Auth",
        "content": "Authentication middleware was ported using FastAPI's Depends() "
                   "with a get_current_user dependency that verifies JWT tokens "
                   "from the Authorization header. The pattern uses "
                   "HTTPBearer() for token extraction.",
        "category": "architecture",
        "tags": ["fastapi", "auth", "jwt", "migration"],
        "source_context": "Ported auth middleware in auth_middleware.py",
    },
    {
        "title": "SQLAlchemy 2.0 Async Session Factory Pattern",
        "content": "Replaced Flask-SQLAlchemy's scoped_session with "
                   "SQLAlchemy 2.0 async sessionmaker. Each request gets "
                   "a session via dependency override, committed on success "
                   "and rolled back on exception.",
        "category": "technical_rule",
        "tags": ["sqlalchemy", "async", "session", "fastapi"],
        "source_context": "Database session setup in database.py",
    },
    {
        "title": "Pydantic v2 Schema for Request/Response Validation",
        "content": "All request/response models migrated from marshmallow "
                   "to Pydantic v2 BaseModel. Used model_config for ORM mode "
                   "and Field() for validation constraints.",
        "category": "technical_rule",
        "tags": ["pydantic", "validation", "schemas"],
        "source_context": "Schema definitions in schemas/ directory",
    },
    {
        "title": "Flask Blueprint to FastAPI Router Mapping",
        "content": "Each Flask blueprint was converted to an APIRouter "
                   "with prefix and tags. The user blueprint routed to /api/v1/users "
                   "and admin blueprint to /api/v1/admin.",
        "category": "architecture",
        "tags": ["fastapi", "router", "blueprint", "migration"],
        "source_context": "Route organization in routers/ directory",
    },
    {
        "title": "Legacy Flask-RESTful Endpoint Deprecation Notice",
        "content": "The /api/v1/legacy/reports endpoint was using Flask-RESTful "
                   "Resource classes that don't have a direct FastAPI equivalent. "
                   "Kept as a separate legacy mount with a deprecation warning header.",
        "category": "environment",
        "tags": ["legacy", "flask-restful", "deprecation"],
        "source_context": "Legacy route in legacy_routes.py",
    },
]

REAL_TODO_ITEMS = [
    {
        "title": "Update CI/CD pipeline for new test framework",
        "description": "The test suite now uses pytest-asyncio. Update the "
                       "GitHub Actions workflow to install the correct "
                       "dependencies and run with --asyncio-mode=auto.",
        "priority": "high",
        "category": "devops",
        "reasoning": "CI pipeline currently uses Flask test runner which will fail",
    },
    {
        "title": "Verify rate limiting middleware behavior",
        "description": "The Flask rate limiting middleware used flask-limiter. "
                       "The slowapi replacement for FastAPI needs manual "
                       "testing to ensure thresholds are identical.",
        "priority": "high",
        "category": "security",
        "reasoning": "Rate limiting is a production requirement with SLA guarantees",
    },
    {
        "title": "Update API documentation",
        "description": "FastAPI auto-generates OpenAPI docs at /docs. "
                       "Update the README to point to the new docs URL "
                       "and verify all endpoint descriptions are accurate.",
        "priority": "medium",
        "category": "documentation",
        "reasoning": "Standard practice for framework migration completion",
    },
    {
        "title": "Benchmark performance regression",
        "description": "Run locust tests comparing the old Flask and new FastAPI "
                       "endpoints. Document any requests per second differences "
                       "and optimize slow endpoints.",
        "priority": "low",
        "category": "performance",
        "reasoning": "Performance improvement was a stated goal of the migration",
    },
    {
        "title": "Remove Flask from dependencies",
        "description": "After verifying everything works, remove Flask and "
                       "Flask-SQLAlchemy from requirements.txt. Keep Flask-CORS "
                       "if still needed for legacy routes.",
        "priority": "medium",
        "category": "maintenance",
        "reasoning": "Cleanup task after migration completion",
    },
]

REAL_MEMORY_ITEMS = [
    {
        "type": "user",
        "content": "Developer prefers async/await patterns over synchronous code",
        "title": "Async preference",
        "tags": ["preference", "async"],
    },
    {
        "type": "feedback",
        "content": "User was satisfied with the automated migration but wanted "
                   "manual review on auth-related changes",
        "title": "Auth migration feedback",
        "tags": ["feedback", "auth", "migration"],
    },
    {
        "type": "project",
        "content": "Project uses PostgreSQL 15 with pgvector extension. "
                   "The database connection string is loaded from environment.",
        "title": "Project database config",
        "tags": ["database", "postgresql", "pgvector"],
    },
    {
        "type": "concept",
        "content": "The service follows a repository pattern with service layer. "
                   "Repositories use SQLAlchemy 2.0 ORM queries, services "
                   "contain business logic, and routes handle request/response.",
        "title": "Service architecture pattern",
        "tags": ["architecture", "pattern", "repository"],
    },
    {
        "type": "reference",
        "content": "Official FastAPI migration guide: https://fastapi.tiangolo.com/"
                   "how-to/migration/",
        "title": "FastAPI migration guide",
        "tags": ["reference", "fastapi", "docs"],
    },
    {
        "type": "episode",
        "content": "Migrated Flask user management service to FastAPI. "
                   "Took approximately 45 minutes. Main challenges were "
                   "auth middleware and legacy route handling.",
        "title": "Flask-to-FastAPI migration session",
        "tags": ["episode", "migration", "flask", "fastapi"],
    },
]


# =============================================================================
# build_dynamic_schema — realistic schema support
# =============================================================================


class TestBuildDynamicSchema:
    def test_returns_none_when_no_plugins(self):
        assert ExtractionRegistry.build_dynamic_schema() is None

    def test_real_schemas_produce_all_fields(self):
        for name, schema in [
            ("knowledge", KNOWLEDGE_SCHEMA),
            ("todo", TODO_SCHEMA),
            ("memory", MEMORY_SCHEMA),
        ]:
            ExtractionRegistry.register(
                ExtractionPlugin(
                    name=name, description=name, output_schema=schema,
                )
            )

        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        assert DynamicVerdict is not None
        assert "is_completed" in DynamicVerdict.model_fields
        assert "summary" in DynamicVerdict.model_fields
        assert "knowledge" in DynamicVerdict.model_fields
        assert "todo" in DynamicVerdict.model_fields
        assert "memory" in DynamicVerdict.model_fields

    def test_enum_fields_accept_valid_values(self):
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="knowledge", description="Knowledge", output_schema=KNOWLEDGE_SCHEMA,
            )
        )
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        instance = DynamicVerdict(
            is_completed=True,
            summary="Done",
            knowledge=[{"title": "T", "content": "C", "category": "architecture"}],
        )
        assert instance.model_dump()["knowledge"][0]["category"] == "architecture"

    def test_optional_fields_default_to_none(self):
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="knowledge", description="Knowledge", output_schema=KNOWLEDGE_SCHEMA,
            )
        )
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        instance = DynamicVerdict(
            is_completed=True,
            summary="Done",
            knowledge=[{"title": "T", "content": "C", "category": "workflow"}],
        )
        item = instance.model_dump()["knowledge"][0]
        assert item["tags"] is None
        assert item["source_context"] is None

    def test_missing_required_field_raises(self):
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="todo", description="Todo", output_schema=TODO_SCHEMA,
            )
        )
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            DynamicVerdict(
                is_completed=True, summary="X",
                todo=[{"priority": "high"}],  # missing required: title, description
            )


# =============================================================================
# Full flow: Standard Audit with realistic data
# =============================================================================


class TestStandardAuditFlow:
    """Simulates real Standard Audit with rich extraction data."""

    @pytest.fixture(autouse=True)
    def register_real_plugins(self):
        for name, schema in [
            ("knowledge", KNOWLEDGE_SCHEMA),
            ("todo", TODO_SCHEMA),
            ("memory", MEMORY_SCHEMA),
        ]:
            ExtractionRegistry.register(
                ExtractionPlugin(
                    name=name,
                    description=name,
                    output_schema=schema,
                    confidence_threshold=0.5,
                    handler=AsyncMock(),
                )
            )

    @pytest.mark.asyncio
    async def test_llm_response_to_handler_data_flow(self):
        """Simulates the exact flow in audit_standard() and AuditService.execute()."""

        # Step 1: Build dynamic schema (same as audit_standard does)
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        assert DynamicVerdict is not None

        # Step 2: LLM returns structured data with all items (simulated)
        llm_response = DynamicVerdict(
            is_completed=True,
            summary=REAL_SESSION_SUMMARY,
            knowledge=REAL_KNOWLEDGE_ITEMS,
            todo=REAL_TODO_ITEMS,
            memory=REAL_MEMORY_ITEMS,
        )

        # Step 3: Audit service extracts data (same as audit_standard)
        extracted_data = llm_response.model_dump()
        extracted_data.pop("summary", None)
        extracted_data.pop("is_completed", None)

        assert len(extracted_data["knowledge"]) == 5
        assert len(extracted_data["todo"]) == 5
        assert len(extracted_data["memory"]) == 6

        knowledge_titles = {item["title"] for item in extracted_data["knowledge"]}
        assert "FastAPI Dependency Injection Pattern for Auth" in knowledge_titles
        assert "Legacy Flask-RESTful Endpoint Deprecation Notice" in knowledge_titles

        todo_titles = {item["title"] for item in extracted_data["todo"]}
        assert "Update CI/CD pipeline for new test framework" in todo_titles
        assert "Remove Flask from dependencies" in todo_titles

        memory_types = {item["type"] for item in extracted_data["memory"]}
        assert memory_types == {"user", "feedback", "project", "concept", "reference", "episode"}

        # Step 4: dispatch_structured (same as AuditService.execute)
        ctx = ExtractionContext(thread_id="real-flow-1", project_id=42, user_id="dev-1")
        handled = await ExtractionRegistry.dispatch_structured(extracted_data, ctx)
        assert handled == 16  # 5 knowledge + 5 todo + 6 memory

        # Step 5: Verify thread is marked
        assert ExtractionRegistry.is_thread_handled("real-flow-1")

    @pytest.mark.asyncio
    async def test_confidence_filtering_drops_low_confidence_items(self):
        """Items below confidence_threshold are skipped during dispatch."""
        knowledge_handler = ExtractionRegistry.get("knowledge").handler
        knowledge_handler.reset_mock()

        # NOTE: confidence must be set AFTER model_dump because Pydantic
        # strips fields not in the schema. dispatch_structured reads
        # confidence from the raw dict items.
        verdict = {
            "knowledge": [
                {"title": "A", "content": "low", "category": "workflow", "confidence": 0.1},
                {"title": "B", "content": "high", "category": "architecture", "confidence": 0.9},
                {"title": "C", "content": "low", "category": "workflow", "confidence": 0.4},
                {"title": "D", "content": "high", "category": "technical_rule", "confidence": 0.95},
                {"title": "E", "content": "high", "category": "environment", "confidence": 0.8},
            ],
            "todo": [],
            "memory": [],
        }
        ctx = ExtractionContext(thread_id="real-flow-2")
        handled = await ExtractionRegistry.dispatch_structured(verdict, ctx)
        # Items with confidence >= 0.5: B, D, E
        assert handled == 3
        assert knowledge_handler.await_count == 3

    @pytest.mark.asyncio
    async def test_all_subscribers_read_from_extracted_data(self):
        """Simulates what the three event subscribers do with the event data."""
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()

        llm_response = DynamicVerdict(
            is_completed=True,
            summary=REAL_SESSION_SUMMARY,
            knowledge=REAL_KNOWLEDGE_ITEMS[:2],
            todo=REAL_TODO_ITEMS[:2],
            memory=REAL_MEMORY_ITEMS[:1],
        )
        extracted_data = llm_response.model_dump()
        extracted_data.pop("summary", None)
        extracted_data.pop("is_completed", None)

        # Simulate what each subscriber does:
        # KnowledgeHarvestingSubscriber
        knowledge_items = extracted_data.get("knowledge", [])
        assert len(knowledge_items) == 2
        for item in knowledge_items:
            assert "title" in item
            assert "content" in item
            assert "category" in item
            # Optional fields may be None
            assert "tags" in item
            assert "source_context" in item

        # TodoLifecycleSubscriber
        todo_items = extracted_data.get("todo", [])
        assert len(todo_items) == 2
        for item in todo_items:
            assert "title" in item
            assert "description" in item
            assert "priority" in item

        # MemoryHarvestingSubscriber
        memory_items = extracted_data.get("memory", [])
        assert len(memory_items) == 1
        assert memory_items[0]["type"] == "user"
        assert memory_items[0]["content"]

    @pytest.mark.asyncio
    async def test_no_extracted_data_all_subscribers_skip(self):
        """When audit found nothing, all subscribers should skip."""
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()

        llm_response = DynamicVerdict(
            is_completed=True, summary="Nothing to extract",
            knowledge=[], todo=[], memory=[],
        )
        extracted_data = llm_response.model_dump()
        extracted_data.pop("summary", None)
        extracted_data.pop("is_completed", None)

        for plugin_name in ("knowledge", "todo", "memory"):
            handler = ExtractionRegistry.get(plugin_name).handler
            handler.reset_mock()

        ctx = ExtractionContext(thread_id="real-flow-nothing")
        handled = await ExtractionRegistry.dispatch_structured(extracted_data, ctx)
        assert handled == 0

        for plugin_name in ("knowledge", "todo", "memory"):
            handler = ExtractionRegistry.get(plugin_name).handler
            handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_extraction_some_empty_some_not(self):
        """Only knowledge has data; todo and memory are empty."""
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()

        llm_response = DynamicVerdict(
            is_completed=True, summary="Only knowledge",
            knowledge=[REAL_KNOWLEDGE_ITEMS[0]],
            todo=[],
            memory=[],
        )
        extracted_data = llm_response.model_dump()
        extracted_data.pop("summary", None)
        extracted_data.pop("is_completed", None)

        handlers = {
            name: ExtractionRegistry.get(name).handler
            for name in ("knowledge", "todo", "memory")
        }
        for h in handlers.values():
            h.reset_mock()

        ctx = ExtractionContext(thread_id="real-flow-partial")
        handled = await ExtractionRegistry.dispatch_structured(extracted_data, ctx)
        assert handled == 1
        handlers["knowledge"].assert_awaited_once()
        handlers["todo"].assert_not_awaited()
        handlers["memory"].assert_not_awaited()


# =============================================================================
# Full flow: Comprehensive Audit XML fallback
# =============================================================================


class TestComprehensiveAuditXMLFallback:
    """Simulates: Session Reviewer produces XML → FinishNode parses and dispatches."""

    @pytest.fixture(autouse=True)
    def register_real_plugins(self):
        for name, schema in [
            ("knowledge", KNOWLEDGE_SCHEMA),
            ("todo", TODO_SCHEMA),
            ("memory", MEMORY_SCHEMA),
        ]:
            ExtractionRegistry.register(
                ExtractionPlugin(
                    name=name,
                    description=name,
                    output_schema=schema,
                    confidence_threshold=0.0,
                    handler=AsyncMock(),
                )
            )

    @pytest.mark.asyncio
    async def test_xml_with_all_plugin_types(self):
        """Session Reviewer output containing all three extraction types."""
        from langchain_core.messages import AIMessage

        xml_output = (
            "<evoloop_session_audit>\n"
            "  <evoloop_audit_outcome>SUCCESS</evoloop_audit_outcome>\n"
            "</evoloop_session_audit>\n"
            "<evoloop_final_report>Done.</evoloop_final_report>\n"
            "<evoloop_extractions>\n"
            '  <extraction name="knowledge" confidence="0.92">\n'
            '    {"title": "Architecture Decision", "content": "Use FastAPI", "category": "architecture"}\n'
            "  </extraction>\n"
            '  <extraction name="todo" confidence="0.88">\n'
            '    {"title": "Write docs", "description": "Update README", "priority": "medium"}\n'
            "  </extraction>\n"
            '  <extraction name="memory" confidence="0.95">\n'
            '    {"type": "user", "content": "User prefers async"}\n'
            "  </extraction>\n"
            "</evoloop_extractions>"
        )
        msg = AIMessage(content=xml_output)
        ctx = ExtractionContext(thread_id="xml-full")
        handled = await ExtractionRegistry.parse_and_dispatch_from_messages([msg], ctx)

        assert handled == 3
        ExtractionRegistry.get("knowledge").handler.assert_awaited_once()
        ExtractionRegistry.get("todo").handler.assert_awaited_once()
        ExtractionRegistry.get("memory").handler.assert_awaited_once()

        # Verify handler received correct data
        knowledge_data = ExtractionRegistry.get("knowledge").handler.await_args[0][0]
        assert knowledge_data["title"] == "Architecture Decision"
        assert knowledge_data["category"] == "architecture"

    @pytest.mark.asyncio
    async def test_xml_only_some_extractions(self):
        """Session Reviewer only outputs knowledge, no todo or memory."""
        from langchain_core.messages import AIMessage

        xml_output = (
            "<evoloop_extractions>\n"
            '  <extraction name="knowledge" confidence="0.9">\n'
            '    {"title": "Only Knowledge", "content": "Test", "category": "technical_rule"}\n'
            "  </extraction>\n"
            "</evoloop_extractions>"
        )
        msg = AIMessage(content=xml_output)
        ctx = ExtractionContext(thread_id="xml-partial")
        handled = await ExtractionRegistry.parse_and_dispatch_from_messages([msg], ctx)

        assert handled == 1
        ExtractionRegistry.get("knowledge").handler.assert_awaited_once()
        ExtractionRegistry.get("todo").handler.assert_not_awaited()
        ExtractionRegistry.get("memory").handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_xml_with_mixed_confidence(self):
        """Some items below threshold are skipped."""
        from langchain_core.messages import AIMessage

        # Lower the threshold for knowledge to 0.8 to make test interesting
        knowledge_plugin = ExtractionRegistry.get("knowledge")
        knowledge_plugin.confidence_threshold = 0.8

        xml_output = (
            "<evoloop_extractions>\n"
            '  <extraction name="knowledge" confidence="0.9">\n'
            '    {"title": "High", "content": "Keep", "category": "architecture"}\n'
            "  </extraction>\n"
            '  <extraction name="knowledge" confidence="0.3">\n'
            '    {"title": "Low", "content": "Skip", "category": "workflow"}\n'
            "  </extraction>\n"
            "</evoloop_extractions>"
        )
        handler = knowledge_plugin.handler
        handler.reset_mock()

        msg = AIMessage(content=xml_output)
        ctx = ExtractionContext(thread_id="xml-conf")
        handled = await ExtractionRegistry.parse_and_dispatch_from_messages([msg], ctx)

        assert handled == 1
        handler.assert_awaited_once()
        assert handler.await_args[0][0]["title"] == "High"


class TestDoubleDispatchPrevention:
    """Thread tracking prevents running extraction twice for the same thread."""

    @pytest.fixture(autouse=True)
    def register_plugin(self):
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="knowledge",
                description="Knowledge",
                output_schema=KNOWLEDGE_SCHEMA,
                confidence_threshold=0.0,
                handler=AsyncMock(),
            )
        )
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="todo",
                description="Todo",
                output_schema=TODO_SCHEMA,
                confidence_threshold=0.0,
                handler=AsyncMock(),
            )
        )

    @pytest.mark.asyncio
    async def test_structured_then_xml_does_not_dispatch_twice(self):
        """Dispatch via AuditService → marks thread → FinishNode XML skip."""
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        structured_response = DynamicVerdict(
            is_completed=True, summary="Done",
            knowledge=[REAL_KNOWLEDGE_ITEMS[0]],
            todo=[],
        )
        extracted = structured_response.model_dump()
        extracted.pop("summary", None)
        extracted.pop("is_completed", None)

        # AuditService dispatches first
        ctx = ExtractionContext(thread_id="no-double")
        count1 = await ExtractionRegistry.dispatch_structured(extracted, ctx)
        assert count1 == 1
        assert ExtractionRegistry.is_thread_handled("no-double")

        # FinishNode checks is_thread_handled before XML path
        from langchain_core.messages import AIMessage
        msg = AIMessage(
            content="""<evoloop_extractions>
  <extraction name="knowledge" confidence="0.9">
    {"title": "Double", "content": "Should not persist", "category": "architecture"}
  </extraction>
  <extraction name="todo" confidence="0.9">
    {"title": "Double", "description": "Should not persist", "priority": "medium"}
  </extraction>
</evoloop_extractions>"""
        )
        if not ExtractionRegistry.is_thread_handled("no-double"):
            await ExtractionRegistry.parse_and_dispatch_from_messages([msg], ctx)

        # Handler called only once (from structured path)
        assert ExtractionRegistry.get("knowledge").handler.await_count == 1
        assert ExtractionRegistry.get("todo").handler.await_count == 0

    @pytest.mark.asyncio
    async def test_xml_then_structured_different_threads_ok(self):
        """Different threads don't interfere with each other."""
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()

        from langchain_core.messages import AIMessage

        # Thread A: XML dispatch
        msg_a = AIMessage(
            content="""<evoloop_extractions>
  <extraction name="knowledge" confidence="0.9">
    {"title": "From XML", "content": "Thread A", "category": "architecture"}
  </extraction>
</evoloop_extractions>"""
        )
        await ExtractionRegistry.parse_and_dispatch_from_messages(
            [msg_a], ExtractionContext(thread_id="thread-a")
        )

        # Thread B: structured dispatch
        resp = DynamicVerdict(
            is_completed=True, summary="Done",
            knowledge=[{
                "title": "From Structured", "content": "Thread B",
                "category": "technical_rule",
            }],
            todo=[],
            memory=[],
        )
        extracted = resp.model_dump()
        extracted.pop("summary", None)
        extracted.pop("is_completed", None)
        await ExtractionRegistry.dispatch_structured(
            extracted, ExtractionContext(thread_id="thread-b")
        )

        assert ExtractionRegistry.get("knowledge").handler.await_count == 2

    @pytest.mark.asyncio
    async def test_audit_then_event_subscriber_reads_extracted_data(self):
        """Full pipeline: audit dispatch → event data → subscriber reads.

        This simulates the entire flow end-to-end:
        AuditService.dispatch_structured() + SessionCompletedData.extracted_data
        → KnowledgeHarvestingSubscriber reads from event.data.extracted_data
        """
        # Step 1: Build schema and get LLM output (audit_standard)
        DynamicVerdict = ExtractionRegistry.build_dynamic_schema()
        llm_output = DynamicVerdict(
            is_completed=True,
            summary=REAL_SESSION_SUMMARY,
            knowledge=REAL_KNOWLEDGE_ITEMS[:3],
            todo=REAL_TODO_ITEMS[:2],
            memory=[],  # memory not registered in this fixture
        )

        # Step 2: Extract data (audit_standard returns this)
        extracted_data = llm_output.model_dump()
        extracted_data.pop("summary", None)
        extracted_data.pop("is_completed", None)

        # Step 3: dispatch_structured in AuditService (goes to plugin handlers)
        audited_handled = await ExtractionRegistry.dispatch_structured(
            extracted_data, ExtractionContext(thread_id="full-pipe")
        )
        assert audited_handled == 5  # 3 knowledge + 2 todo (memory not registered)

        # Reset mock counts to simulate subscriber reading AFTER audit
        for name in ("knowledge", "todo"):
            ExtractionRegistry.get(name).handler.reset_mock()

        k_items = extracted_data.get("knowledge", [])
        t_items = extracted_data.get("todo", [])
        m_items = extracted_data.get("memory", [])

        assert len(k_items) == 3
        assert len(t_items) == 2
        assert len(m_items) == 0  # memory not registered

        for item in k_items:
            assert "title" in item
            assert "content" in item
        for item in t_items:
            assert "title" in item
            assert "priority" in item


# =============================================================================
# Thread tracking edge cases
# =============================================================================


class TestThreadTrackingEdgeCases:
    @pytest.mark.asyncio
    async def test_max_handled_clears_set(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="x", description="X", output_schema={},
                confidence_threshold=0.0, handler=handler,
            )
        )
        # Fill to near limit
        for i in range(ExtractionRegistry._MAX_HANDLED):
            ExtractionRegistry.mark_thread_handled(f"bulk-{i}")

        # One more triggers clear
        ctx = ExtractionContext(thread_id="final-one")
        await ExtractionRegistry.dispatch_structured({"x": [{"v": 1}]}, ctx)

        assert len(ExtractionRegistry._handled_threads) == 1
        assert ExtractionRegistry.is_thread_handled("final-one")
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_without_thread_id_does_not_mark(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="x", description="X", output_schema={},
                confidence_threshold=0.0, handler=handler,
            )
        )
        ctx = ExtractionContext(thread_id="")
        await ExtractionRegistry.dispatch_structured({"x": [{"v": 1}]}, ctx)
        # thread_id is empty, so no marking
        assert not ExtractionRegistry.is_thread_handled("")
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handler_receives_correct_context(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="x", description="X", output_schema={},
                confidence_threshold=0.0, handler=handler,
            )
        )
        ctx = ExtractionContext(
            thread_id="ctx-test", project_id=99, user_id="alice",
            run_id="run-123", summary="Test session",
        )
        await ExtractionRegistry.dispatch_structured({"x": [{"v": 1}]}, ctx)

        handler.assert_awaited_once()
        _data, handler_ctx = handler.await_args[0]
        assert handler_ctx.thread_id == "ctx-test"
        assert handler_ctx.project_id == 99
        assert handler_ctx.user_id == "alice"
        assert handler_ctx.run_id == "run-123"
        assert handler_ctx.summary == "Test session"
