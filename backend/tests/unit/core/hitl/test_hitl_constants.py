"""Unit tests for HITL enums (``app.core.hitl.types``) and constants.

Covers the consolidation of decision tokens / statuses / message contract
values introduced alongside ``HumanRequestType``:
- ``HITLDecision`` / ``HITLRequestStatus`` enum values;
- ``constants.py`` message-contract values (category derives from
  ``MessageCategory``, single source) and authorization defaults;
- leaf-module constraint that keeps ``types.py`` import-order cycle-free.
"""

import inspect

import pytest

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.constants import MessageStatus
from app.core.hitl.constants import (
    DEFAULT_AUTHORIZATION_TTL_DAYS,
    DEFAULT_DECISION,
    DEFAULT_GRANTED_BY,
    MESSAGE_ACTION_TYPE_HUMAN_REQUEST,
    MESSAGE_CATEGORY_HITL_REQUEST,
)
from app.core.hitl.types import (
    HITLDecision,
    HITLRequestStatus,
    HumanRequestType,
)


class TestHITLDecision:
    def test_values(self):
        assert HITLDecision.APPROVED.value == "APPROVED"
        assert HITLDecision.REJECTED.value == "REJECTED"
        assert HITLDecision.CANCELLED.value == "CANCELLED"

    def test_str_enum_equality(self):
        assert HITLDecision.REJECTED == "REJECTED"
        assert HITLDecision.APPROVED == "APPROVED"

    def test_default_decision_is_rejected(self):
        assert DEFAULT_DECISION == HITLDecision.REJECTED.value == "REJECTED"


class TestHITLRequestStatus:
    def test_values(self):
        assert HITLRequestStatus.PENDING.value == "pending"
        assert HITLRequestStatus.COMPLETED.value == "completed"
        assert HITLRequestStatus.CANCELLED.value == "cancelled"
        assert HITLRequestStatus.TIMEOUT.value == "timeout"


class TestConstants:
    def test_message_category_single_source(self):
        """category 常量必须与 MessageCategory 枚举同源，杜绝两套字面量漂移。"""
        assert MESSAGE_CATEGORY_HITL_REQUEST == MessageCategory.HITL_REQUEST.value
        assert MESSAGE_CATEGORY_HITL_REQUEST == "hitl_request"

    def test_message_contract_values(self):
        assert MessageStatus.WAITING_HUMAN == "waiting_human"
        assert MessageStatus.WAITING_HUMAN.value == "waiting_human"
        assert MESSAGE_ACTION_TYPE_HUMAN_REQUEST == "human_request"

    def test_authorization_defaults(self):
        assert DEFAULT_GRANTED_BY == "hitl-approval"
        assert DEFAULT_AUTHORIZATION_TTL_DAYS == 7

    def test_statuses_disjoint_from_decisions(self):
        """状态与决策令牌是两套词表，值互不混淆。"""
        decision_values = {d.value for d in HITLDecision}
        status_values = {s.value for s in HITLRequestStatus}
        assert not (decision_values & status_values)


class TestEnumConsolidation:
    def test_types_module_is_leaf(self):
        """叶子约束：hitl.types 不得 import 任何 app 模块（新增枚举也适用）。"""
        source = inspect.getsource(pytest.importorskip("app.core.hitl.types"))
        assert "from app." not in source
        assert "import app." not in source

    def test_all_hitl_share_same_enum_objects(self):
        """hitl 包内各模块引用同一批枚举对象。"""
        from app.core.hitl import core as hitl_core
        from app.core.hitl import orchestrator as hitl_orch

        assert hitl_core.HITLRequestStatus is HITLRequestStatus
        assert hitl_core.HumanRequestType is HumanRequestType
        assert hitl_orch.HITLDecision is HITLDecision
        assert hitl_orch.HumanRequestType is HumanRequestType
