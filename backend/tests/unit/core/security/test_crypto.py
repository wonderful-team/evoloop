"""Unit tests for app.core.security.crypto."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security.constants import ALGORITHM
from app.core.security.crypto import (
    create_access_token,
    generate_hmac_signature,
    get_password_hash,
    verify_password,
)


class TestGenerateHmacSignature:
    def test_generates_deterministic_signature(self):
        sig1 = generate_hmac_signature("secret", "message")
        sig2 = generate_hmac_signature("secret", "message")
        assert sig1 == sig2
        assert len(sig1) == 64  # SHA-256 hex

    def test_empty_secret_returns_empty(self):
        assert generate_hmac_signature("", "message") == ""

    def test_different_secrets_produce_different_signatures(self):
        assert generate_hmac_signature("a", "msg") != generate_hmac_signature("b", "msg")


class TestJwtSigning:
    def test_create_access_token_signed_with_secret_key(self):
        token = create_access_token(subject="user-123", expires_delta=timedelta(minutes=5))
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "user-123"

    def test_token_rejected_with_wrong_key(self):
        token = create_access_token(subject="user-123", expires_delta=timedelta(minutes=5))
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "wrong-key" * 10, algorithms=[ALGORITHM])

    def test_token_expiry(self):
        token = create_access_token(subject="u", expires_delta=timedelta(seconds=-10))
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


class TestPasswordHash:
    def test_password_hash_and_verify(self):
        hashed = get_password_hash("my-password")
        assert verify_password("my-password", hashed) is True
        assert verify_password("wrong-password", hashed) is False
