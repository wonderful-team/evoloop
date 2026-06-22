"""Tests for unified AuditService (tier classification removed)."""

import pytest
from pydantic import ValidationError

from app.core.engine.services.audit_service import AuditResult


class TestAuditResult:
    def test_basic_audit_result(self):
        result = AuditResult(summary="Task done.")
        assert result.summary == "Task done."
        assert result.meta == {}
        assert result.messages == []

    def test_audit_result_with_meta(self):
        result = AuditResult(summary="Done", meta={"duration_ms": 150, "outcome": "COMPLETED"})
        assert result.meta["duration_ms"] == 150
        assert result.meta["outcome"] == "COMPLETED"

    def test_audit_result_requires_summary(self):
        with pytest.raises(ValidationError):
            AuditResult()
