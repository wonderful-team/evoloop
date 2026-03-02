"""
Unit tests for Identity Authentication System.
Tests JWT handling, IdentityStore, and IdentityService.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from app.core.identity.jwt import create_local_jwt, decode_local_jwt, ALGORITHM
from app.core.identity.store import IdentityStore
from app.core.identity.service import IdentityService


class TestJWTFunctions:
    """Tests for JWT creation and decoding."""

    def test_create_local_jwt_with_default_expiry(self):
        """Test creating JWT with default expiration."""
        data = {"sub": "123", "member_id": 123}

        token = create_local_jwt(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_local_jwt_with_custom_expiry(self):
        """Test creating JWT with custom expiration."""
        data = {"sub": "456", "member_id": 456}
        expires = timedelta(hours=2)

        token = create_local_jwt(data, expires)

        # Decode to verify expiry
        decoded = decode_local_jwt(token)
        exp_timestamp = decoded["exp"]
        exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        # Should be approximately 2 hours from now
        assert (exp_time - datetime.now(timezone.utc)) < timedelta(hours=2, minutes=1)

    def test_decode_local_jwt_success(self):
        """Test successful JWT decoding."""
        data = {"sub": "789", "member_id": 789, "custom_claim": "value"}
        token = create_local_jwt(data)

        decoded = decode_local_jwt(token)

        assert decoded is not None
        assert decoded["sub"] == "789"
        assert decoded["member_id"] == 789
        assert decoded["custom_claim"] == "value"
        assert "exp" in decoded

    def test_decode_local_jwt_invalid(self):
        """Test decoding invalid JWT."""
        result = decode_local_jwt("invalid.token.here")

        assert result is None

    def test_decode_local_jwt_expired(self):
        """Test decoding expired JWT."""
        data = {"sub": "999"}
        # Create token that expired 1 hour ago
        expired_delta = timedelta(hours=-1)
        token = create_local_jwt(data, expired_delta)

        result = decode_local_jwt(token)

        assert result is None

    def test_create_local_jwt_preserves_original_data(self):
        """Test that JWT preserves all original data."""
        data = {
            "sub": "user123",
            "member_id": 123,
            "role": "admin",
            "permissions": ["read", "write"]
        }

        token = create_local_jwt(data)
        decoded = decode_local_jwt(token)

        assert decoded["sub"] == "user123"
        assert decoded["member_id"] == 123
        assert decoded["role"] == "admin"
        assert decoded["permissions"] == ["read", "write"]


class TestIdentityStore:
    """Tests for IdentityStore with mocked keyring."""

    @pytest.fixture(autouse=True)
    def mock_keyring(self):
        """Mock keyring for all tests."""
        with patch("app.core.identity.store.keyring") as mock_keyring:
            # Create mock errors module with proper exception class
            class MockPasswordDeleteError(Exception):
                pass
            mock_errors = MagicMock()
            mock_errors.PasswordDeleteError = MockPasswordDeleteError
            mock_keyring.errors = mock_errors
            self.mock_keyring = mock_keyring
            yield mock_keyring

    def test_save_cloud_token_success(self, mock_keyring):
        """Test saving cloud token successfully."""
        mock_keyring.set_password.return_value = None

        result = IdentityStore.save_cloud_token("test_token_123")

        assert result is True
        mock_keyring.set_password.assert_called_once_with(
            IdentityStore.SERVICE_NAME, "cloud_token", "test_token_123"
        )

    def test_save_cloud_token_failure(self, mock_keyring):
        """Test saving cloud token when keyring fails."""
        mock_keyring.set_password.side_effect = Exception("Keychain locked")

        result = IdentityStore.save_cloud_token("test_token")

        assert result is False

    def test_get_cloud_token_success(self, mock_keyring):
        """Test retrieving cloud token."""
        mock_keyring.get_password.return_value = "stored_token_123"

        result = IdentityStore.get_cloud_token()

        assert result == "stored_token_123"
        mock_keyring.get_password.assert_called_with(
            IdentityStore.SERVICE_NAME, "cloud_token"
        )

    def test_get_cloud_token_not_found(self, mock_keyring):
        """Test retrieving non-existent cloud token."""
        mock_keyring.get_password.return_value = None

        result = IdentityStore.get_cloud_token()

        assert result is None

    def test_get_cloud_token_failure(self, mock_keyring):
        """Test retrieving token when keyring fails."""
        mock_keyring.get_password.side_effect = Exception("Keychain error")

        result = IdentityStore.get_cloud_token()

        assert result is None

    def test_delete_cloud_token_success(self, mock_keyring):
        """Test deleting cloud token."""
        mock_keyring.delete_password.return_value = None

        result = IdentityStore.delete_cloud_token()

        assert result is True

    def test_delete_cloud_token_already_deleted(self, mock_keyring):
        """Test deleting already deleted token."""
        # Use the mock exception class from the fixture
        mock_keyring.delete_password.side_effect = mock_keyring.errors.PasswordDeleteError()

        result = IdentityStore.delete_cloud_token()

        assert result is True  # Should return True even if already deleted

    def test_delete_cloud_token_failure(self, mock_keyring):
        """Test deleting token when keyring fails."""
        mock_keyring.delete_password.side_effect = Exception("Keychain error")

        result = IdentityStore.delete_cloud_token()

        assert result is False

    def test_save_device_key(self, mock_keyring):
        """Test saving device key."""
        mock_keyring.set_password.return_value = None

        result = IdentityStore.save_device_key("device_key_abc")

        assert result is True
        mock_keyring.set_password.assert_called_with(
            IdentityStore.SERVICE_NAME, "device_key", "device_key_abc"
        )

    def test_get_device_key(self, mock_keyring):
        """Test retrieving device key."""
        mock_keyring.get_password.return_value = "device_key_xyz"

        result = IdentityStore.get_device_key()

        assert result == "device_key_xyz"

    def test_save_member_id(self, mock_keyring):
        """Test saving member ID."""
        mock_keyring.set_password.return_value = None

        result = IdentityStore.save_member_id(12345)

        assert result is True
        mock_keyring.set_password.assert_called_with(
            IdentityStore.SERVICE_NAME, "member_id", "12345"
        )

    def test_get_member_id(self, mock_keyring):
        """Test retrieving member ID."""
        mock_keyring.get_password.return_value = "67890"

        result = IdentityStore.get_member_id()

        assert result == 67890

    def test_get_member_id_not_found(self, mock_keyring):
        """Test retrieving non-existent member ID."""
        mock_keyring.get_password.return_value = None

        result = IdentityStore.get_member_id()

        assert result is None

    def test_get_member_id_invalid_value(self, mock_keyring):
        """Test retrieving member ID with invalid value."""
        mock_keyring.get_password.return_value = "not_a_number"

        result = IdentityStore.get_member_id()

        # Should handle the exception and return None
        assert result is None


class TestIdentityService:
    """Tests for IdentityService."""

    @pytest.fixture
    def service(self):
        return IdentityService()

    @pytest.fixture(autouse=True)
    def mock_store(self):
        """Mock IdentityStore methods."""
        with patch.object(IdentityStore, "save_cloud_token") as mock_save_token, \
             patch.object(IdentityStore, "save_member_id") as mock_save_member, \
             patch.object(IdentityStore, "delete_cloud_token") as mock_delete, \
             patch.object(IdentityStore, "get_cloud_token") as mock_get_token, \
             patch.object(IdentityStore, "get_member_id") as mock_get_member:

            self.mock_save_token = mock_save_token
            self.mock_save_member = mock_save_member
            self.mock_delete = mock_delete
            self.mock_get_token = mock_get_token
            self.mock_get_member = mock_get_member

            mock_save_token.return_value = True
            mock_save_member.return_value = True
            mock_delete.return_value = True

            yield

    @pytest.mark.asyncio
    async def test_login_with_cloud_result_success(self, service, mock_store):
        """Test successful cloud login."""
        cloud_result = {
            "token": "cloud_token_123",
            "member_id": 12345
        }

        local_token = await service.login_with_cloud_result(cloud_result)

        assert local_token is not None
        assert isinstance(local_token, str)

        # Verify store was called
        self.mock_save_token.assert_called_once_with("cloud_token_123")
        self.mock_save_member.assert_called_once_with(12345)

        # Verify JWT contains correct data
        decoded = decode_local_jwt(local_token)
        assert decoded["sub"] == "12345"
        assert decoded["member_id"] == 12345

    @pytest.mark.asyncio
    async def test_login_with_cloud_result_missing_token(self, service, mock_store):
        """Test login with missing token."""
        cloud_result = {
            "member_id": 12345
            # Missing "token"
        }

        result = await service.login_with_cloud_result(cloud_result)

        assert result is None
        self.mock_save_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_with_cloud_result_default_member_id(self, service, mock_store):
        """Test login with default member_id of 0."""
        cloud_result = {
            "token": "cloud_token_123"
            # Missing "member_id", should default to 0
        }

        local_token = await service.login_with_cloud_result(cloud_result)

        assert local_token is not None
        decoded = decode_local_jwt(local_token)
        assert decoded["member_id"] == 0

    def test_logout(self, service, mock_store):
        """Test logout clears auth state."""
        service.logout()

        self.mock_delete.assert_called_once()

    def test_get_cloud_token(self, service, mock_store):
        """Test retrieving cloud token."""
        self.mock_get_token.return_value = "stored_cloud_token"

        result = service.get_cloud_token()

        assert result == "stored_cloud_token"
        self.mock_get_token.assert_called_once()

    def test_get_member_id(self, service, mock_store):
        """Test retrieving member ID."""
        self.mock_get_member.return_value = 12345

        result = service.get_member_id()

        assert result == 12345
        self.mock_get_member.assert_called_once()

    def test_is_logged_in_true(self, service, mock_store):
        """Test is_logged_in when token exists."""
        self.mock_get_token.return_value = "valid_token"

        result = service.is_logged_in()

        assert result is True

    def test_is_logged_in_false(self, service, mock_store):
        """Test is_logged_in when no token."""
        self.mock_get_token.return_value = None

        result = service.is_logged_in()

        assert result is False

    def test_global_identity_service_instance(self):
        """Test that global identity_service exists."""
        from app.core.identity.service import identity_service

        assert identity_service is not None
        assert isinstance(identity_service, IdentityService)


class TestJWTEdgeCases:
    """Tests for JWT edge cases and error handling."""

    def test_create_jwt_with_empty_data(self):
        """Test creating JWT with empty data."""
        token = create_local_jwt({})

        assert isinstance(token, str)
        decoded = decode_local_jwt(token)
        assert decoded is not None
        assert "exp" in decoded

    def test_create_jwt_with_unicode_data(self):
        """Test creating JWT with unicode characters."""
        data = {"sub": "用户123", "name": "测试用户"}

        token = create_local_jwt(data)
        decoded = decode_local_jwt(token)

        assert decoded["sub"] == "用户123"
        assert decoded["name"] == "测试用户"

    def test_decode_jwt_malformed(self):
        """Test decoding malformed JWT."""
        test_cases = [
            "",
            "not.a.token",
            "header.payload",
            "header.payload.signature.extra",
            "invalid_base64.invalid.invalid"
        ]

        for case in test_cases:
            result = decode_local_jwt(case)
            assert result is None

    def test_decode_jwt_wrong_secret(self):
        """Test decoding JWT with wrong secret."""
        import jwt as jwt_module
        data = {"sub": "123"}
        # Create with different secret
        wrong_token = jwt_module.encode(data, "wrong_secret", algorithm=ALGORITHM)

        result = decode_local_jwt(wrong_token)

        assert result is None
