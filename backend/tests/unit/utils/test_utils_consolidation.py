"""Consolidated generic utilities deduplication regression tests.

Covers utilities migrated/consolidated into app/utils:
- app/utils/hash.py (moved from app/core/file/hash.py)
- app/utils/text.py normalize_ws (deduplicated from editing strategies)
- app/utils/security.py sanitize_filename (supersedes app/core/file/path_utils copy)
"""

import hashlib
import time
from datetime import datetime

import pytest

from app.core.file import sanitize_filename as core_file_sanitize_filename
from app.utils.audio import s16le_to_f32le
from app.utils.hash import (
    compute_file_hash,
    compute_md5,
    compute_sha256,
    compute_state_id,
    compute_version_hash,
    sha256_digest,
)
from app.utils.id import stamped_id, unique_id
from app.utils.json import safe_load_json_list
from app.utils.security import sanitize_filename
from app.utils.text import chunk_text, normalize_compact, normalize_ws
from app.utils.time import elapsed_ms, parse_iso_timestamp, ts_from_dt


class TestSanitizeFilename:
    def test_unsafe_characters_replaced(self):
        assert sanitize_filename('a/b:c?|*"<>') == "a_b_c______"

    def test_path_separators_and_control_chars(self):
        assert sanitize_filename("a\\b\x00\n\r\tc") == "a_b____c"

    def test_length_limited_with_extension_preserved(self):
        long_name = "x" * 300 + ".py"
        result = sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".py")

    def test_windows_reserved_name_prefix_replaced(self):
        assert sanitize_filename("CON.txt")[0] == "_"

    def test_core_file_reexport_is_same_function(self):
        assert core_file_sanitize_filename is sanitize_filename


class TestNormalizeWs:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", ""),
            ("   ", ""),
            ("a   b\n\t c", "a b c"),
            ("already spaced", "already spaced"),
        ],
    )
    def test_collapses_whitespace(self, text, expected):
        assert normalize_ws(text) == expected


class TestSafeLoadJsonList:
    def test_none_or_empty(self):
        assert safe_load_json_list(None) == []
        assert safe_load_json_list("") == []

    def test_direct_list_passthrough(self):
        assert safe_load_json_list(["a", "b"]) == ["a", "b"]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('["a", "b"]', ["a", "b"]),
            ('"[\\"x\\"]"', ["x"]),
            ('{"a": 1}', []),
            ("not json", []),
        ],
    )
    def test_various_inputs(self, raw, expected):
        assert safe_load_json_list(raw) == expected


class TestHashConsolidation:
    def test_compute_md5(self):
        assert compute_md5("hello") == hashlib.md5(b"hello").hexdigest()

    def test_compute_sha256(self):
        assert compute_sha256("hello") == hashlib.sha256(b"hello").hexdigest()

    def test_compute_file_hash_matches_content_hash(self, tmp_path):
        target = tmp_path / "sample.txt"
        target.write_text("hello", encoding="utf-8")
        assert compute_file_hash(str(target), algo="md5") == compute_md5("hello")

    def test_compute_version_hash_fixed_length(self):
        result = compute_version_hash("a", "b", length=12)
        assert len(result) == 12

    def test_compute_state_id_fixed_length(self):
        assert len(compute_state_id("id1", "id2")) == 8

    def test_sha256_digest(self):
        digest = sha256_digest(b"hello")
        assert len(digest) == 32
        assert digest == hashlib.sha256(b"hello").digest()


class TestElapsedMs:
    def test_measures_elapsed(self):
        start = time.time()
        result = elapsed_ms(start)
        assert result >= 0.0
        assert result < 1000.0

    def test_explicit_end(self):
        start = time.time()
        assert elapsed_ms(start, start + 0.1) == pytest.approx(100.0, abs=1e-3)


class TestUniqueId:
    def test_label_key_epoch_shape(self):
        now = int(time.time())
        assert unique_id("auton", "t-1") == f"auton-t-1-{now}"

    def test_multi_part(self):
        value = unique_id("appmap-gen", "p1", "entity")
        assert value.startswith("appmap-gen-p1-entity-")

    def test_no_parts_ms(self):
        value = unique_id("ro", use_ms=True)
        assert value.startswith("ro-")
        assert len(value) > len("ro-") + 9

    def test_epoch_is_second_granularity(self):
        now = int(time.time())
        assert unique_id("k").endswith(f"-{now}")


class TestStampedId:
    def test_defaults_to_now(self):
        value = stamped_id("maint")
        assert value.startswith("maint_")
        assert len(value) == len("maint_") + 15

    def test_bare_timestamp(self):
        assert len(stamped_id()) == 15

    def test_explicit_dt(self):
        dt = datetime(2026, 8, 30, 21, 59, 59)
        assert stamped_id("dream_cross", dt) == "dream_cross_20260830_215959"


class TestS16leToF32le:
    def test_converts_samples(self):
        import struct

        raw = struct.pack("<4h", 32767, -32768, 1000, 0)
        out = struct.unpack(
            "<4f", s16le_to_f32le(raw)
        )
        assert out[0] == pytest.approx(32767 / 32768.0, abs=1e-6)
        assert out[1] == pytest.approx(-1.0, abs=1e-6)
        assert out[2] == pytest.approx(1000 / 32768.0, abs=1e-6)
        assert out[3] == 0.0

    def test_empty_input(self):
        assert s16le_to_f32le(b"") == b""


class TestChunkText:
    def test_short_text_single_chunk(self):
        assert chunk_text("short", 10) == ["short"]

    def test_empty(self):
        assert chunk_text("", 10) == []
        assert chunk_text(None, 10) == []

    def test_prefers_newline_boundary(self):
        text = "a" * 50 + "\n" + "b" * 50
        assert chunk_text(text, 50) == ["a" * 50, "b" * 50]

    def test_hard_cut_drops_nothing(self):
        text = "x" * 120
        chunks = chunk_text(text, 50)
        assert "".join(chunks) == text

    def test_long_exceeds_limit(self):
        text = "很" * 200
        chunks = chunk_text(text, 100)
        assert all(len(c) <= 100 for c in chunks)
        assert "".join(chunks) == text


class TestNormalizeCompact:
    def test_strips_separators_and_lowercases(self):
        assert normalize_compact("  Google Chrome - App  ") == "googlechromeapp"
        assert normalize_compact("微信_Client") == "微信client"
        assert normalize_compact("a-b_c d") == "abcd"

    def test_none(self):
        assert normalize_compact(None) == ""


class TestParseIsoTimestampCompat:
    def test_z_and_naive_equivalent(self):
        aware = parse_iso_timestamp("2026-08-30T10:00:00Z")
        naive = parse_iso_timestamp("2026-08-30T10:00:00")
        assert ts_from_dt(aware) == ts_from_dt(naive)

    def test_invalid_falls_back_to_default(self):
        assert ts_from_dt(parse_iso_timestamp("not a date"), default=0) == 0
