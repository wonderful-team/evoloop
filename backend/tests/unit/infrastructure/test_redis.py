"""
Unit tests for Redis client.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.database.redis import redis_client


class TestRedisClient:
    """Tests for Redis client."""

    @pytest.mark.asyncio
    async def test_redis_get_set(self):
        """Test basic get/set operations."""
        with patch.object(redis_client, 'set', new_callable=AsyncMock) as mock_set:
            with patch.object(redis_client, 'get', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = "value"

                await redis_client.set("key", "value")
                result = await redis_client.get("key")

                assert result == "value"
                mock_set.assert_called_once()
                mock_get.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_redis_hset_hget(self):
        """Test hash operations."""
        with patch.object(redis_client, 'hset', new_callable=AsyncMock) as mock_hset:
            with patch.object(redis_client, 'hget', new_callable=AsyncMock) as mock_hget:
                mock_hget.return_value = "field_value"

                await redis_client.hset("hash_key", "field", "value")
                result = await redis_client.hget("hash_key", "field")

                assert result == "field_value"

    @pytest.mark.asyncio
    async def test_redis_publish(self):
        """Test publish operation."""
        with patch.object(redis_client, 'publish', new_callable=AsyncMock) as mock_publish:
            await redis_client.publish("channel", "message")
            mock_publish.assert_called_once_with("channel", "message")

    @pytest.mark.asyncio
    async def test_redis_expire(self):
        """Test expire operation."""
        with patch.object(redis_client, 'expire', new_callable=AsyncMock) as mock_expire:
            await redis_client.expire("key", 3600)
            mock_expire.assert_called_once_with("key", 3600)
