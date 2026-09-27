"""Unit tests for ``RequestHumanInputArgs`` schema (multi_choice support)."""

import pytest
from pydantic import ValidationError

from app.core.hitl.schemas import RequestHumanInputArgs


class TestRequestHumanInputArgs:
    def test_multi_choice_validates(self):
        m = RequestHumanInputArgs(
            prompt="请勾选要处理的退款工单",
            input_type="multi_choice",
            options=["全部", "仅待转账", "仅申请售后", "暂不处理"],
        )
        assert m.input_type == "multi_choice"
        assert m.options == ["全部", "仅待转账", "仅申请售后", "暂不处理"]
        assert m.prompt == "请勾选要处理的退款工单"

    def test_multi_choice_options_optional_in_schema(self):
        """schema 层不强制 options；工具层负责运行时校验。"""
        m = RequestHumanInputArgs(prompt="p", input_type="multi_choice")
        assert m.options is None

    def test_choice_still_valid(self):
        m = RequestHumanInputArgs(prompt="p", input_type="choice", options=["A", "B"])
        assert m.input_type == "choice"

    def test_invalid_input_type_rejected(self):
        with pytest.raises(ValidationError):
            RequestHumanInputArgs(prompt="p", input_type="bogus_type")
