"""Maintenance orchestration: fresh-skip, regenerate path, guardrail, failure isolation."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.atlas import maintenance
from app.core.atlas.surveyor import SurveyCoverage, SurveyResult
from app.core.atlas.models import AtlasApp, AtlasState


def _survey_result(bundle_id: str) -> SurveyResult:
    return SurveyResult(
        bundle_id=bundle_id,
        app=AtlasApp(
            app_name="X", bundle_id=bundle_id, platform="macos",
            states={"s1": AtlasState(state_id="s1", window_title="", elements=[])},
        ),
        coverage=SurveyCoverage(),
    )


class TestResurveyAndRegen:
    async def test_skips_when_fresh(self):
        surveyor = AsyncMock()
        surveyor.needs_resurvey.return_value = False
        out = await maintenance.resurvey_and_regen("com.x", "X", surveyor=surveyor)
        assert out["action"] == "skip_fresh"
        surveyor.survey_app.assert_not_called()

    async def test_regenerates_when_stale(self):
        surveyor = AsyncMock()
        surveyor.needs_resurvey.return_value = True
        surveyor.survey_app.return_value = _survey_result("com.x")
        with (
            patch.object(maintenance, "generate_for_atlas_app", return_value=["c1", "c2"]) as gen,
            patch.object(maintenance, "persist_native_macros", new=AsyncMock(return_value=[1, 2])) as persist,
            patch.object(maintenance, "verify_safe_native_macros", new=AsyncMock(return_value=2)),
        ):
            out = await maintenance.resurvey_and_regen("com.x", "X", surveyor=surveyor)
        assert out["action"] == "regenerated" and out["macros"] == 2
        gen.assert_called_once()
        persist.assert_called_once_with(["c1", "c2"])

    async def test_survey_failure_reported(self):
        surveyor = AsyncMock()
        surveyor.needs_resurvey.return_value = True
        surveyor.survey_app.return_value = SurveyResult(bundle_id="com.x", error="not running")
        out = await maintenance.resurvey_and_regen("com.x", "X", surveyor=surveyor)
        assert out["action"] == "survey_failed"

    async def test_guardrail_logs_but_keeps_data(self, caplog):
        surveyor = AsyncMock()
        surveyor.needs_resurvey.return_value = True
        surveyor.survey_app.return_value = _survey_result("com.x")
        huge = [f"c{i}" for i in range(maintenance.MAX_MACROS_PER_APP + 1)]
        with (
            patch.object(maintenance, "generate_for_atlas_app", return_value=huge),
            patch.object(maintenance, "persist_native_macros", new=AsyncMock(return_value=huge)),
            patch.object(maintenance, "verify_safe_native_macros", new=AsyncMock(return_value=0)),
            caplog.at_level("WARNING"),
        ):
            out = await maintenance.resurvey_and_regen("com.x", "X", surveyor=surveyor)
        assert out["action"] == "regenerated" and out["macros"] == len(huge)
        assert any("护栏" in r.message for r in caplog.records)


class TestFullPass:
    async def test_reindex_only_when_something_regenerated(self):
        async def fake_one(bundle_id, app_name, **kw):
            return {"bundle_id": bundle_id, "action": "regenerated" if bundle_id == "a" else "skip_fresh"}

        with (
            patch.object(maintenance, "resurvey_and_regen", side_effect=fake_one),
            patch("app.core.routing.sync.rebuild_route_index", new=AsyncMock()) as rebuild,
        ):
            out = await maintenance.native_atlas_maintenance(apps=[("a", "A"), ("b", "B")])
        assert len(out) == 2
        rebuild.assert_called_once()

    async def test_no_reindex_when_all_fresh(self):
        async def fake_skip(bundle_id, app_name, **kw):
            return {"bundle_id": bundle_id, "action": "skip_fresh"}

        with (
            patch.object(maintenance, "resurvey_and_regen", side_effect=fake_skip),
            patch("app.core.routing.sync.rebuild_route_index", new=AsyncMock()) as rebuild,
        ):
            await maintenance.native_atlas_maintenance(apps=[("a", "A")])
        rebuild.assert_not_called()

    async def test_one_app_failure_does_not_abort_others(self):
        async def flaky(bundle_id, app_name, **kw):
            if bundle_id == "a":
                raise RuntimeError("boom")
            return {"bundle_id": bundle_id, "action": "skip_fresh"}

        with patch.object(maintenance, "resurvey_and_regen", side_effect=flaky):
            out = await maintenance.native_atlas_maintenance(apps=[("a", "A"), ("b", "B")])
        assert out[0]["action"] == "error" and out[1]["action"] == "skip_fresh"


class TestConfiguredApps:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EVO_NATIVE_SURVEY_APPS", "com.a:A, com.b:B")
        assert maintenance.configured_apps() == [("com.a", "A"), ("com.b", "B")]

    def test_default_when_env_empty(self, monkeypatch):
        monkeypatch.delenv("EVO_NATIVE_SURVEY_APPS", raising=False)
        assert ("com.google.Chrome", "Chrome") in maintenance.configured_apps()
