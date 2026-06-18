"""
Functional tests for skill lifecycle events — publishing and subscribing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.events import SystemEventType
from app.core.events.publishers import publish_skill_mutated


# =============================================================================
# Event publishing
# =============================================================================

class TestPublishSkillMutated:

    @pytest.mark.asyncio
    async def test_publish_create(self):
        """publish_skill_mutated(action='create') → SKILL_CREATED event."""
        with patch("app.core.events.publishers.system_bus.publish", new_callable=AsyncMock) as mock_pub:
            await publish_skill_mutated(skill_id=1, action="create")

            mock_pub.assert_called_once()
            event = mock_pub.call_args[0][0]
            assert event.event_type == SystemEventType.SKILL_CREATED
            assert event.data["skill_id"] == 1
            assert event.data["action"] == "create"

    @pytest.mark.asyncio
    async def test_publish_update(self):
        """publish_skill_mutated(action='update') → SKILL_UPDATED event."""
        with patch("app.core.events.publishers.system_bus.publish", new_callable=AsyncMock) as mock_pub:
            await publish_skill_mutated(skill_id=42, action="update")

            event = mock_pub.call_args[0][0]
            assert event.event_type == SystemEventType.SKILL_UPDATED
            assert event.data["skill_id"] == 42

    @pytest.mark.asyncio
    async def test_publish_delete_includes_namespace_and_name(self):
        """publish_skill_mutated(action='delete') → SKILL_DELETED with namespace+name."""
        with patch("app.core.events.publishers.system_bus.publish", new_callable=AsyncMock) as mock_pub:
            await publish_skill_mutated(
                skill_id=99, action="delete",
                namespace="roles", name="my_skill",
            )

            event = mock_pub.call_args[0][0]
            assert event.event_type == SystemEventType.SKILL_DELETED
            assert event.data["skill_id"] == 99
            assert event.data["namespace"] == "roles"
            assert event.data["name"] == "my_skill"

    @pytest.mark.asyncio
    async def test_publish_invalid_action_does_nothing(self):
        """Unknown action → no event published."""
        with patch("app.core.events.publishers.system_bus.publish", new_callable=AsyncMock) as mock_pub:
            await publish_skill_mutated(skill_id=1, action="invalid")
            mock_pub.assert_not_called()


# =============================================================================
# Event type values
# =============================================================================

class TestSkillEventTypes:

    def test_event_type_values(self):
        """Verify event type string values match expected."""
        assert SystemEventType.SKILL_CREATED.value == "learning.skill_created"
        assert SystemEventType.SKILL_UPDATED.value == "learning.skill_updated"
        assert SystemEventType.SKILL_DELETED.value == "learning.skill_deleted"

    def test_event_types_are_unique(self):
        """No duplicate values across all SystemEventType members."""
        values = [e.value for e in SystemEventType]
        assert len(values) == len(set(values)), f"Duplicate event types: {values}"


# =============================================================================
# Event subscriber integration (subscribers.py handlers)
# =============================================================================

class TestSkillSubscribers:

    @pytest.fixture
    def mock_event(self):
        """Factory for creating mock events."""
        def _make(action, skill_id, namespace=None, name=None):
            event = MagicMock()
            event.data = {
                "skill_id": skill_id,
                "action": action,
                "namespace": namespace,
                "name": name,
            }
            return event
        return _make

    @pytest.mark.asyncio
    async def test_on_skill_created_calls_export(self, mock_event):
        """SKILL_CREATED subscriber → calls export_skill_to_file."""
        from app.core.learning.event.subscribers import LearningLifecycleSubscriber

        subscriber = LearningLifecycleSubscriber()
        event = mock_event("create", 42)

        with patch(
            "app.core.learning.event.subscribers.skill_sync_service.export_skill_to_file",
            new_callable=AsyncMock,
            return_value="/path/to/SKILL.md",
        ) as mock_export:
            await subscriber.on_skill_created(event)
            mock_export.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_on_skill_updated_calls_export(self, mock_event):
        """SKILL_UPDATED subscriber → calls export_skill_to_file."""
        from app.core.learning.event.subscribers import LearningLifecycleSubscriber

        subscriber = LearningLifecycleSubscriber()
        event = mock_event("update", 7)

        with patch(
            "app.core.learning.event.subscribers.skill_sync_service.export_skill_to_file",
            new_callable=AsyncMock,
        ) as mock_export:
            await subscriber.on_skill_updated(event)
            mock_export.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_on_skill_deleted_calls_delete(self, mock_event):
        """SKILL_DELETED subscriber → calls delete_skill_file with all params."""
        from app.core.learning.event.subscribers import LearningLifecycleSubscriber

        subscriber = LearningLifecycleSubscriber()
        event = mock_event("delete", 99, namespace="roles", name="my_skill")

        with patch(
            "app.core.learning.event.subscribers.skill_sync_service.delete_skill_file",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_delete:
            await subscriber.on_skill_deleted(event)
            mock_delete.assert_called_once_with(
                skill_id=99, namespace="roles", name="my_skill",
            )

    @pytest.mark.asyncio
    async def test_on_skill_deleted_without_namespace(self, mock_event):
        """SKILL_DELETED without namespace → still calls delete_skill_file."""
        from app.core.learning.event.subscribers import LearningLifecycleSubscriber

        subscriber = LearningLifecycleSubscriber()
        event = mock_event("delete", 99)

        with patch(
            "app.core.learning.event.subscribers.skill_sync_service.delete_skill_file",
            new_callable=AsyncMock,
        ) as mock_delete:
            await subscriber.on_skill_deleted(event)
            mock_delete.assert_called_once_with(
                skill_id=99, namespace=None, name=None,
            )
