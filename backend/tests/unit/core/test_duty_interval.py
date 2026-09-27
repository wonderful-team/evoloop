"""Tests for duty poll interval clamping & global poll_interval config.

v6.3: ``customer_service_duty.interval`` (seconds) is per-project configurable,
clamped to 60~3600 (1~60 minutes); anything non-integer falls back to the
system default ``DUTY_INTERVAL=60``.

v6.4: 轮巡间隔上移到全局（``CUSTOMER_SERVICE_DUTY.poll_interval``），
项目配置里的 ``interval`` 字段不再生效（保留历史兼容但被忽略）。
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel.duty import config as duty_config
from app.core.channel.duty.constants import DUTY_INTERVAL


class TestClampDutyInterval:
    def test_valid_values_passthrough(self):
        assert duty_config.clamp_duty_interval(60) == 60
        assert duty_config.clamp_duty_interval(120) == 120
        assert duty_config.clamp_duty_interval(1800) == 1800
        assert duty_config.clamp_duty_interval(3600) == 3600

    def test_below_min_clamped_to_60(self):
        # 下限 = 全局扫描粒度（engine_scheduler_tick_periodic 每 60s）
        assert duty_config.clamp_duty_interval(30) == 60
        assert duty_config.clamp_duty_interval(1) == 60

    def test_above_max_clamped_to_3600(self):
        assert duty_config.clamp_duty_interval(7200) == 3600

    def test_non_integer_falls_back_to_default(self):
        # 配置只接受整数秒；None/str/bool/float 一律回退缺省
        assert duty_config.clamp_duty_interval(None) == DUTY_INTERVAL
        assert duty_config.clamp_duty_interval("60") == DUTY_INTERVAL
        assert duty_config.clamp_duty_interval(True) == DUTY_INTERVAL
        assert duty_config.clamp_duty_interval(60.0) == DUTY_INTERVAL


@pytest.mark.asyncio
class TestLoadDutyConfigInterval:
    async def _load(self, duty_cfg: dict, global_cfg: dict | None = None):
        with patch.object(
            duty_config, "get_project_path", AsyncMock(return_value="/tmp/proj")
        ), patch.object(
            duty_config,
            "read_project_json",
            return_value={"customer_service_duty": duty_cfg},
        ), patch.object(
            duty_config,
            "load_global_duty_config",
            return_value=global_cfg or {},
        ):
            return await duty_config.load_duty_config(7)

    async def test_interval_from_global_config(self):
        cfg = await self._load({"enabled": True}, {"poll_interval": 300})
        assert cfg["poll_interval"] == 300

    async def test_missing_interval_falls_back_to_default(self):
        cfg = await self._load({"enabled": True})
        assert cfg["poll_interval"] == DUTY_INTERVAL

    async def test_out_of_range_interval_clamped(self):
        assert (await self._load({}, {"poll_interval": 30}))["poll_interval"] == 60
        assert (await self._load({}, {"poll_interval": 7200}))["poll_interval"] == 3600

    async def test_project_interval_ignored(self):
        """项目配置里的 interval 字段不再生效（历史兼容字段，被忽略）。"""
        cfg = await self._load({"interval": 300}, {"poll_interval": 60})
        assert cfg["poll_interval"] == 60

    async def test_no_local_path_returns_empty(self):
        with patch.object(
            duty_config, "get_project_path", AsyncMock(return_value=None)
        ):
            assert await duty_config.load_duty_config(7) == {}
