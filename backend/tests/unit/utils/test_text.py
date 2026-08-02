"""Tests for app.utils.text utilities."""

from app.utils.text import strip_markdown_for_tts


class TestStripMarkdownForTts:
    def test_empty_input(self):
        assert strip_markdown_for_tts("") == ""
        assert strip_markdown_for_tts(None) is None

    def test_plain_text_unchanged(self):
        assert strip_markdown_for_tts("hello world") == "hello world"

    def test_bold_and_italic_removed(self):
        text = "**bold** and *italic* and __underline__ and ~~strike~~"
        assert strip_markdown_for_tts(text) == "bold and italic and underline and strike"

    def test_links_keep_text(self):
        text = "See [the docs](https://example.com) for details."
        assert strip_markdown_for_tts(text) == "See the docs for details."

    def test_images_keep_alt_text(self):
        text = "An ![important chart](chart.png) is shown."
        assert strip_markdown_for_tts(text) == "An important chart is shown."

    def test_headings_removed(self):
        text = "# Title\n## Subtitle\ncontent"
        assert strip_markdown_for_tts(text) == "Title\nSubtitle\ncontent"

    def test_list_markers_removed(self):
        text = "- first\n* second\n1. third"
        assert strip_markdown_for_tts(text) == "first\nsecond\nthird"

    def test_blockquotes_and_pipes_removed(self):
        text = "> quote\n| a | b |"
        assert strip_markdown_for_tts(text) == "quote\n a b"

    def test_horizontal_rules_removed(self):
        text = "before\n---\nafter"
        assert strip_markdown_for_tts(text) == "before\nafter"

    def test_inline_code_backticks_removed(self):
        text = "run `python main.py` now"
        assert strip_markdown_for_tts(text) == "run python main.py now"
