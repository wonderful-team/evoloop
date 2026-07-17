"""Unit tests for app.domain.codebase.security.scanner."""

import pytest

from app.domain.codebase.security.scanner import SecurityScanner, scan_file


class TestSecurityScanner:
    def test_sql_injection_finds_string_concat(self):
        content = "def get_user(user_id):\n    sql = \"SELECT * FROM users WHERE id = \" + user_id\n    cursor.execute(sql)"
        findings = SecurityScanner().scan("test.py", content)
        assert any(f.finding_type == "sql_injection" for f in findings)

    def test_sql_injection_safe_parameterized_ignored(self):
        content = "def get_user(user_id):\n    cursor.execute(\"SELECT * FROM users WHERE id = ?\", (user_id,))"
        findings = SecurityScanner().scan("test.py", content)
        assert not any(f.finding_type == "sql_injection" for f in findings)

    def test_command_injection_finds_os_system(self):
        content = "import os\ndef run(cmd):\n    os.system(\"ls \" + cmd)"
        findings = SecurityScanner().scan("test.py", content)
        assert any(f.finding_type == "command_injection" for f in findings)

    def test_command_injection_safe_list_ignored(self):
        content = "import subprocess\ndef run(cmd):\n    subprocess.run([\"ls\", cmd], shell=False)"
        findings = SecurityScanner().scan("test.py", content)
        assert not any(f.finding_type == "command_injection" for f in findings)

    def test_hardcoded_secret_found(self):
        content = 'API_KEY = "sk_live_a0b1c2d3e4f5g6h7"'
        findings = SecurityScanner().scan("test.py", content)
        assert any(f.finding_type == "hardcoded_secret" for f in findings)

    def test_hardcoded_secret_placeholder_ignored(self):
        content = 'API_KEY = "your_api_key_here"'
        findings = SecurityScanner().scan("test.py", content)
        assert not any(f.finding_type == "hardcoded_secret" for f in findings)

    def test_path_traversal_found(self):
        content = "def read(path):\n    with open(\"data/\" + path) as f:\n        return f.read()"
        findings = SecurityScanner().scan("test.py", content)
        assert any(f.finding_type == "path_traversal" for f in findings)

    def test_ssrf_found(self):
        content = "import requests\ndef fetch(url):\n    return requests.get(url)"
        findings = SecurityScanner().scan("test.py", content)
        assert any(f.finding_type == "ssrf" for f in findings)

    def test_scan_file_wrapper(self):
        content = "import os\nos.system(\"echo \" + input)"
        findings = scan_file("test.py", content)
        assert isinstance(findings, list)
        assert any(f.finding_type == "command_injection" for f in findings)

    def test_no_false_positives_on_config_file(self):
        content = "config_path = os.path.join(os.path.dirname(__file__), 'config.json')"
        findings = SecurityScanner().scan("test.py", content)
        assert not any(f.finding_type == "path_traversal" for f in findings)
