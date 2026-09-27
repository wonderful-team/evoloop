"""Unit tests for HITL request type enum (``app.core.hitl.types``).

Covers the consolidation of ``HumanRequestType`` into the HITL subsystem:
enum values, the new ``multi_choice`` member, uniqueness, cross-module identity
(monitoring imports the same object), and the leaf-module constraint that keeps
``monitoring → hitl`` import order cycle-free.
"""

import inspect

import pytest

from app.core.hitl.types import HumanRequestType


class TestHumanRequestTypeValues:
    def test_enum_values(self):
        assert HumanRequestType.TEXT.value == "text"
        assert HumanRequestType.PROJECT_SWITCH.value == "project_switch"
        assert HumanRequestType.CONFIRMATION.value == "confirmation"
        assert HumanRequestType.APPROVAL.value == "approval"
        assert HumanRequestType.FILE_SELECT.value == "file_select"
        assert HumanRequestType.CHOICE.value == "choice"

    def test_multi_choice_present(self):
        assert HumanRequestType.MULTI_CHOICE.value == "multi_choice"
        assert HumanRequestType.MULTI_CHOICE in HumanRequestType
        assert "multi_choice" in {t.value for t in HumanRequestType}

    def test_values_unique(self):
        values = [t.value for t in HumanRequestType]
        assert len(values) == len(set(values))

    def test_str_values_match_enum_member(self):
        assert str(HumanRequestType.MULTI_CHOICE) == "HumanRequestType.MULTI_CHOICE"
        # str,Enum: value equals str(member.value) via mixin
        assert HumanRequestType.MULTI_CHOICE == "multi_choice"


class TestConsolidation:
    def test_same_object_across_modules(self):
        """monitoring 与 hitl 包导入的是同一个枚举对象（收编正确性）。"""
        from app.core.hitl import HumanRequestType as FromPackage
        from app.core.monitoring.schemas import HumanRequestType as FromMonitoring

        assert HumanRequestType is FromPackage is FromMonitoring

    def test_monitoring_payload_models_still_use_enum(self):
        """monitoring 的请求 payload 模型仍以该枚举做类型注解。"""
        from app.core.monitoring.schemas import TextInputRequest

        ann = TextInputRequest.model_fields["type"].annotation
        assert ann is HumanRequestType

    def test_types_module_is_leaf(self):
        """叶子约束：hitl.types 不得 import 任何 app 模块，否则 monitoring→hitl
        的导入顺序会触发循环导入。"""
        source = inspect.getsource(
            pytest.importorskip("app.core.hitl.types")
        )
        assert "from app." not in source
        assert "import app." not in source
