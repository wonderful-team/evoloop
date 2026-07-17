"""M5: Atlas aliases -> L0 app slot dictionary."""

from unittest.mock import AsyncMock, patch

from app.core.routing import init_spec
from app.core.routing.init_spec import enrich_spec_with_atlas_aliases
from app.core.routing.schemas import VoiceInitSpec


def _spec() -> VoiceInitSpec:
    return VoiceInitSpec(
        version="t",
        actions=[],
        templates=[],
        slot_dictionaries={
            "app": [
                {"name": "WeChat", "bundle_id": "com.tencent.xinWeChat", "aliases": []},
                {"name": "Chrome", "bundle_id": "com.google.Chrome", "aliases": []},
            ]
        },
        aliases={"音乐": "Apple Music"},
    )


class TestEnrich:
    async def test_aliases_merged_into_slot_dict_and_global(self):
        with patch.object(
            init_spec,
            "_atlas_app_aliases",
            new=AsyncMock(return_value=[("WeChat", "com.tencent.xinWeChat", "微信"), ("Lark", "com.bytedance.macos.feishu", "飞书")]),
        ):
            spec = await enrich_spec_with_atlas_aliases(_spec())
        apps = {e["name"]: e for e in spec.slot_dictionaries["app"]}
        assert apps["WeChat"]["aliases"] == ["微信"]
        assert apps["Chrome"]["aliases"] == []
        assert spec.aliases["微信"] == "WeChat"
        assert spec.aliases["音乐"] == "Apple Music"  # untouched

    async def test_probe_failure_degrades(self):
        with patch.object(
            init_spec,
            "_atlas_app_aliases",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            spec = await enrich_spec_with_atlas_aliases(_spec())
        assert spec.slot_dictionaries["app"][0]["aliases"] == []

    async def test_no_atlas_data_noop(self):
        with patch.object(init_spec, "_atlas_app_aliases", new=AsyncMock(return_value=[])):
            spec = await enrich_spec_with_atlas_aliases(_spec())
        assert spec.slot_dictionaries["app"][0]["aliases"] == []


class TestAtlasAliasExtraction:
    """_atlas_app_aliases against a fake store: first AXMenuBarItem is the
    application menu root; different-from-canonical means spoken alias."""

    async def test_first_root_label_becomes_alias(self):
        from app.core.atlas.schemas import AtlasAppInfo

        class _El:
            def __init__(self, role, label):
                self._d = {"role": role, "label": label}

            def get(self, k, default=None):
                return self._d.get(k, default)

            def __isinstance_check__(self):
                return True

        def el(role, label):  # store returns plain dicts
            return {"role": role, "label": label}

        class _Detail:
            def __init__(self, elements):
                self.elements = elements

        details = {
            "com.tencent.xinWeChat": _Detail(
                [el("AXMenuBarItem", "微信"), el("AXMenuBarItem", "文件")]
            ),
            "com.google.Chrome": _Detail(
                [el("AXMenuBarItem", "Chrome"), el("AXMenuBarItem", "文件")]
            ),
        }
        infos = [
            AtlasAppInfo(app_name="WeChat", bundle_id="com.tencent.xinWeChat", platform="macos"),
            AtlasAppInfo(app_name="Chrome", bundle_id="com.google.Chrome", platform="macos"),
        ]

        class FakeStore:
            async def list_apps(self):
                return infos

            async def get_state_detail(self, bundle_id, state_id):
                return details.get(bundle_id)

        with patch(
            "app.core.atlas.adapters.sql_store.SQLAtlasStore", return_value=FakeStore()
        ):
            out = await init_spec._atlas_app_aliases()
        assert out == [("WeChat", "com.tencent.xinWeChat", "微信")]  # Chrome 根 == canonical -> 无别名
