import re

from app.core.routing import init_spec
from app.core.routing.schemas import VoiceInitSpec


def test_build_init_spec_structure(monkeypatch):
    # Deterministic, host-independent: pretend no apps are installed.
    monkeypatch.setattr(init_spec, "_probe_apps", lambda: ([], []))

    spec = init_spec.build_init_spec()

    assert isinstance(spec, VoiceInitSpec)
    assert re.match(r"^\d{8}-\d{6}$", spec.version)
    # 16 grouped template entries carrying 50 concrete patterns (design §6.2.2).
    assert len(spec.templates) == 16
    total_patterns = sum(len(t.get("patterns", [])) for t in spec.templates)
    assert total_patterns == 50
    # Voice-local actions are always present even with no registry/apps.
    action_ids = {a["id"] for a in spec.actions}
    for expected in (
        "paste",
        "play_pause",
        "set_volume",
        "open_app",
        "press_key",
        "end",
    ):
        assert expected in action_ids
    # Capabilities contract the client relies on.
    for key in (
        "platforms",
        "accessibility",
        "input_monitoring",
        "android_connected",
        "network",
        "disabled_actions",
    ):
        assert key in spec.capabilities
    assert spec.default_apps.get("browser")
    assert spec.default_apps.get("music")


def test_build_init_spec_slot_dictionaries(monkeypatch):
    monkeypatch.setattr(init_spec, "_probe_apps", lambda: ([], []))
    spec = init_spec.build_init_spec()

    assert spec.slot_dictionaries["app"] == []
    assert spec.slot_dictionaries["key"]["回车"] == "Return"
    assert spec.slot_dictionaries["delta"]["大一点"] == "+10"
    assert spec.aliases.get("音乐") == "Apple Music"


def test_build_init_spec_serializes(monkeypatch):
    monkeypatch.setattr(init_spec, "_probe_apps", lambda: ([], []))
    spec = init_spec.build_init_spec()

    # What gets cached (tasks.py) and shipped over HTTP must be JSON-clean.
    dumped = spec.model_dump()
    assert dumped["version"] == spec.version
    assert dumped["capabilities"]["network"] is True
    assert isinstance(dumped["templates"], list)
    assert isinstance(dumped["slot_dictionaries"], dict)


def test_init_spec_actions_keep_destructive_flags_current_behavior(monkeypatch):
    monkeypatch.setattr(init_spec, "_probe_apps", lambda: ([], []))
    spec = init_spec.build_init_spec()
    actions = {a["id"]: a for a in spec.actions}

    assert actions["quit_app"]["destructive"] is True
    assert actions["lock_screen"]["destructive"] is True
    assert "destructive" not in actions["open_app"]
