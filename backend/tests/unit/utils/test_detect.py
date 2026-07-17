"""Unit tests for P0.3c: file type detection normalization."""

from app.utils.detect import detect_language, is_code_file


class TestIsCodeFile:
    def test_is_code_file_py(self):
        assert is_code_file("main.py") is True

    def test_is_code_file_ts(self):
        assert is_code_file("main.ts") is True

    def test_is_code_file_js(self):
        assert is_code_file("app.js") is True


class TestCentralDetectLanguage:
    def test_detect_language_py(self):
        assert detect_language("server.py") == "python"

    def test_detect_language_js(self):
        assert detect_language("index.js") == "javascript"

    def test_detect_language_ts(self):
        assert detect_language("types.ts") == "typescript"

    def test_detect_language_go(self):
        assert detect_language("main.go") == "go"

    def test_detect_language_rs(self):
        assert detect_language("lib.rs") == "rust"

    def test_detect_language_md(self):
        assert detect_language("readme.md") == "markdown"
