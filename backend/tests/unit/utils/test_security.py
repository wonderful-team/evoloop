"""
Unit tests for security utilities.
"""

import pytest
from datetime import timedelta
from unittest.mock import patch, MagicMock

from app.utils.security import (
    create_access_token,
    verify_password,
    get_password_hash,
    generate_hmac_signature,
    pwd_context,
)


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_token_success(self):
        """Test creating access token."""
        with patch('app.utils.security.settings') as mock_settings:
            mock_settings.SECRET_KEY = "test-secret-key"

            token = create_access_token("user123", timedelta(hours=1))

            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 0

    def test_create_token_with_different_subjects(self):
        """Test creating tokens with different subjects."""
        with patch('app.utils.security.settings') as mock_settings:
            mock_settings.SECRET_KEY = "test-secret-key"

            token1 = create_access_token("user1", timedelta(minutes=30))
            token2 = create_access_token("user2", timedelta(minutes=30))

            assert token1 != token2


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_get_password_hash(self):
        """Test hashing a password."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != password  # Hash should be different from plaintext

    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        result = verify_password(password, hashed)

        assert result is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        password = "mysecretpassword"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)

        result = verify_password(wrong_password, hashed)

        assert result is False

    def test_password_hash_unique(self):
        """Test that same password produces different hashes (due to salt)."""
        password = "mysecretpassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # Should be different due to salt
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestGenerateHmacSignature:
    """Tests for generate_hmac_signature function."""

    def test_generate_signature_success(self):
        """Test generating HMAC signature."""
        secret = "my-secret"
        message = "my-message"

        signature = generate_hmac_signature(secret, message)

        assert signature is not None
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA-256 produces 64 hex characters

    def test_generate_signature_consistency(self):
        """Test that same inputs produce same signature."""
        secret = "my-secret"
        message = "my-message"

        sig1 = generate_hmac_signature(secret, message)
        sig2 = generate_hmac_signature(secret, message)

        assert sig1 == sig2

    def test_generate_signature_different_secrets(self):
        """Test that different secrets produce different signatures."""
        message = "my-message"

        sig1 = generate_hmac_signature("secret1", message)
        sig2 = generate_hmac_signature("secret2", message)

        assert sig1 != sig2

    def test_generate_signature_different_messages(self):
        """Test that different messages produce different signatures."""
        secret = "my-secret"

        sig1 = generate_hmac_signature(secret, "message1")
        sig2 = generate_hmac_signature(secret, "message2")

        assert sig1 != sig2

    def test_generate_signature_empty_secret(self):
        """Test generating signature with empty secret."""
        result = generate_hmac_signature("", "message")
        assert result == ""

    def test_generate_signature_with_sha512(self):
        """Test generating signature with SHA-512."""
        import hashlib

        secret = "my-secret"
        message = "my-message"

        signature = generate_hmac_signature(secret, message, hash_alg=hashlib.sha512)

        assert signature is not None
        assert isinstance(signature, str)
        assert len(signature) == 128  # SHA-512 produces 128 hex characters
