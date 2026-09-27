"""Import-order regression tests for the HITL type consolidation.

``HumanRequestType`` 从 ``app.core.monitoring.schemas`` 收编到
``app.core.hitl.types`` 后，``monitoring`` 会反向导入 ``hitl``。本组测试确保
各导入顺序（先 monitoring、先 hitl、先 domain tools）都不会触发循环导入，
且三处引用是同一个枚举对象。
"""

import typing


class TestImportOrderMonitoringFirst:
    def test_import_monitoring_schemas(self):
        from app.core.monitoring.schemas import (
            HumanRequestType,
            TextInputRequest,
        )

        assert HumanRequestType.MULTI_CHOICE.value == "multi_choice"
        assert TextInputRequest is not None

    def test_import_hitl_after_monitoring(self):
        import app.core.hitl as hitl_pkg
        from app.core.hitl.types import HumanRequestType

        assert hitl_pkg.HumanRequestType is HumanRequestType
        # 包不再急切导出 core/orchestrator（避免循环）
        assert "HumanInputRequest" not in hitl_pkg.__all__


class TestImportOrderHitlFirst:
    def test_import_hitl_package(self):
        import app.core.hitl as hitl_pkg

        assert hitl_pkg.HumanRequestType.MULTI_CHOICE.value == "multi_choice"

    def test_import_hitl_core(self):
        from app.core.hitl.core import HumanInputRequest, create_request

        args = typing.get_args(
            HumanInputRequest.model_fields["request_type"].annotation
        )
        assert "multi_choice" in args
        assert callable(create_request)

    def test_import_monitoring_after_hitl(self):
        from app.core.monitoring.schemas import HumanRequestType

        assert HumanRequestType.MULTI_CHOICE.value == "multi_choice"


class TestImportOrderDomainTools:
    def test_import_domain_tools(self):
        from app.core.engine.tools.react_macro import raise_hitl_interrupt
        from app.core.hitl.tools import ask_confirm, ask_human

        assert callable(ask_confirm)
        assert callable(ask_human)
        assert callable(raise_hitl_interrupt)

    def test_orchestrator_normalize_import(self):
        from app.core.hitl.orchestrator import normalize_hitl_input

        assert callable(normalize_hitl_input)


class TestFreeTextSemantics:
    def test_multi_choice_in_free_text_request_types(self):
        from app.core.hitl.orchestrator import _FREE_TEXT_REQUEST_TYPES

        assert "multi_choice" in _FREE_TEXT_REQUEST_TYPES

    def test_normalize_multi_choice_verbatim(self):
        """multi_choice 属 free-text：resume 时逗号分隔串原样回传，不做批准/拒绝归一化。"""
        from app.core.hitl.orchestrator import normalize_hitl_input

        result = normalize_hitl_input(
            {"request_type": "multi_choice"}, "全部,待转账,单533"
        )
        assert result == "全部,待转账,单533"

    def test_normalize_multi_choice_does_not_coerce_yes(self):
        """"yes" 在 multi_choice 里是合法选项文本，不得转成 APPROVED。"""
        from app.core.hitl.orchestrator import normalize_hitl_input

        result = normalize_hitl_input({"request_type": "multi_choice"}, "yes")
        assert result == "yes"
