"""
Unit tests for API dependencies.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException


class TestGetDb:
    """Tests for get_db dependency."""

    def test_get_db_yields_session(self):
        """Test that get_db yields a database session."""
        from app.api.deps import get_db

        # Create a mock context manager
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)

        with patch('app.api.deps.Session', return_value=mock_context):
            gen = get_db()
            session = next(gen)

            assert session is mock_session

            # Complete the generator
            try:
                next(gen)
            except StopIteration:
                pass


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        """Test successful user retrieval."""
        from app.api.deps import get_current_user

        mock_payload = {"member_id": "123", "email": "test@example.com"}
        mock_user_data = {"id": "123", "member_id": "123", "email": "test@example.com", "is_active": True}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            with patch('app.api.deps.redis_client.get', new_callable=AsyncMock) as mock_redis_get:
                mock_redis_get.return_value = json.dumps(mock_user_data)

                with patch('app.api.deps.User.model_validate', return_value=MagicMock(is_active=True)) as mock_validate:
                    result = await get_current_user("test_token")

                    assert result is not None
                    mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test with invalid token."""
        from app.api.deps import get_current_user

        with patch('app.api.deps.decode_local_jwt', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user("invalid_token")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_no_member_id(self):
        """Test with payload missing member_id."""
        from app.api.deps import get_current_user

        with patch('app.api.deps.decode_local_jwt', return_value={}):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user("test_token")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_cache_miss_cloud_success(self):
        """Test Redis cache miss with successful cloud fetch."""
        from app.api.deps import get_current_user

        mock_payload = {"member_id": "123"}
        mock_cloud_response = {"code": 0, "data": {"id": "123", "member_id": "123", "is_active": True}}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            with patch('app.api.deps.redis_client.get', new_callable=AsyncMock, return_value=None):
                with patch('app.api.deps.identity_service.get_cloud_token', return_value="cloud_token"):
                    with patch('app.api.deps.evocloud_manager.api.get_user_info', new_callable=AsyncMock) as mock_cloud:
                        mock_cloud.return_value = mock_cloud_response

                        with patch('app.api.deps.redis_client.set', new_callable=AsyncMock):
                            with patch('app.api.deps.User.model_validate', return_value=MagicMock(is_active=True)):
                                result = await get_current_user("test_token")

                                assert result is not None

    @pytest.mark.asyncio
    async def test_get_current_user_cloud_failure(self):
        """Test cloud API failure."""
        from app.api.deps import get_current_user

        mock_payload = {"member_id": "123"}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            with patch('app.api.deps.redis_client.get', new_callable=AsyncMock, return_value=None):
                with patch('app.api.deps.identity_service.get_cloud_token', return_value="cloud_token"):
                    with patch('app.api.deps.evocloud_manager.api.get_user_info', new_callable=AsyncMock) as mock_cloud:
                        mock_cloud.return_value = {"code": 401, "message": "Unauthorized"}

                        with pytest.raises(HTTPException) as exc_info:
                            await get_current_user("test_token")

                        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_inactive(self):
        """Test with inactive user."""
        from app.api.deps import get_current_user

        mock_payload = {"member_id": "123"}
        mock_user_data = {"id": "123", "is_active": False}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            with patch('app.api.deps.redis_client.get', new_callable=AsyncMock) as mock_redis_get:
                mock_redis_get.return_value = json.dumps(mock_user_data)

                with patch('app.api.deps.User.model_validate', return_value=MagicMock(is_active=False)):
                    with pytest.raises(HTTPException) as exc_info:
                        await get_current_user("test_token")

                    assert exc_info.value.status_code == 400


class TestGetCurrentUserOptional:
    """Tests for get_current_user_optional dependency."""

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        """Test that None token returns None."""
        from app.api.deps import get_current_user_optional

        result = await get_current_user_optional(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Test that valid token returns user."""
        from app.api.deps import get_current_user_optional

        mock_payload = {"member_id": "123"}
        mock_user_data = {"id": "123", "is_active": True}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            with patch('app.api.deps.redis_client.get', new_callable=AsyncMock) as mock_redis_get:
                mock_redis_get.return_value = json.dumps(mock_user_data)

                with patch('app.api.deps.User.model_validate', return_value=MagicMock(is_active=True)):
                    result = await get_current_user_optional("valid_token")

                    assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Test that invalid token returns None instead of raising."""
        from app.api.deps import get_current_user_optional

        with patch('app.api.deps.decode_local_jwt', return_value=None):
            result = await get_current_user_optional("invalid_token")
            assert result is None


class TestVerifyGuestAccess:
    """Tests for verify_guest_access dependency."""

    @pytest.mark.asyncio
    async def test_authenticated_user_skips_check(self):
        """Test that authenticated users bypass guest checks."""
        from app.api.deps import verify_guest_access

        mock_user = MagicMock()

        # Should not raise
        result = await verify_guest_access(current_user=mock_user)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_query_token(self):
        """Test valid query token allows access."""
        from app.api.deps import verify_guest_access

        mock_payload = {"member_id": "123"}

        with patch('app.api.deps.decode_local_jwt', return_value=mock_payload):
            result = await verify_guest_access(
                current_user=None,
                token="valid_token"
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_no_user_no_guest_id_raises(self):
        """Test that missing both user and guest_id raises 401."""
        from app.api.deps import verify_guest_access

        with pytest.raises(HTTPException) as exc_info:
            await verify_guest_access(current_user=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_guest_within_limit(self):
        """Test guest access within daily limit."""
        from app.api.deps import verify_guest_access

        with patch('app.api.deps.evocloud_manager.api.get_ai_global_config', new_callable=AsyncMock) as mock_config:
            mock_config.return_value = {"code": 0, "data": {"guest_daily_limit": 10}}

            with patch('app.api.deps.redis_client.incr', new_callable=AsyncMock) as mock_incr:
                mock_incr.return_value = 5  # Under limit

                with patch('app.api.deps.redis_client.expire', new_callable=AsyncMock):
                    # Should not raise
                    result = await verify_guest_access(
                        current_user=None,
                        x_guest_id="guest123"
                    )
                    assert result is None

    @pytest.mark.asyncio
    async def test_guest_limit_reached(self):
        """Test guest access exceeding daily limit."""
        from app.api.deps import verify_guest_access

        with patch('app.api.deps.evocloud_manager.api.get_ai_global_config', new_callable=AsyncMock) as mock_config:
            mock_config.return_value = {"code": 0, "data": {"guest_daily_limit": 10}}

            with patch('app.api.deps.redis_client.incr', new_callable=AsyncMock) as mock_incr:
                mock_incr.return_value = 11  # Over limit

                with patch('app.api.deps.redis_client.expire', new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_guest_access(
                            current_user=None,
                            x_guest_id="guest123"
                        )

                    assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_guest_disabled(self):
        """Test guest access when disabled (limit=0)."""
        from app.api.deps import verify_guest_access

        with patch('app.api.deps.evocloud_manager.api.get_ai_global_config', new_callable=AsyncMock) as mock_config:
            mock_config.return_value = {"code": 0, "data": {"guest_daily_limit": 0}}

            with pytest.raises(HTTPException) as exc_info:
                await verify_guest_access(
                    current_user=None,
                    x_guest_id="guest123"
                )

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_redis_error_fails_closed(self):
        """Test that Redis errors fail closed (deny access)."""
        from app.api.deps import verify_guest_access

        with patch('app.api.deps.evocloud_manager.api.get_ai_global_config', new_callable=AsyncMock) as mock_config:
            mock_config.return_value = {"code": 0, "data": {"guest_daily_limit": 10}}

            with patch('app.api.deps.redis_client.incr', new_callable=AsyncMock) as mock_incr:
                mock_incr.side_effect = Exception("Redis connection error")

                with pytest.raises(HTTPException) as exc_info:
                    await verify_guest_access(
                        current_user=None,
                        x_guest_id="guest123"
                    )

                assert exc_info.value.status_code == 503
