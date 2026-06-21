"""
File Filter Module - Provides codebase file filtering functionality.
Ported from evoloop-engineer.
"""

import logging
import math
import os
import re
from collections import Counter, OrderedDict

from app.constants import (
    CODE_QUALITY_THRESHOLDS,
    COMPRESSED_FILE_PATTERNS,
    COMPRESSIBLE_EXTENSIONS,
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_FILES,
    LIKELY_COMPRESSED_CODE_DIRS,
    SEMANTIC_LANGUAGE_MAP,
    SOURCE_MAP_EXTENSIONS,
    SUSPICIOUS_JS_PATTERNS,
)
from app.core.file.service import is_text_file
from app.core.file import get_file_ext, is_encrypted_path, is_ignored_path


class FileFilter:
    """File filter, responsible for determining if a file should be included in analysis."""

    _CACHE_MAX_SIZE = 4096

    def __init__(self):
        """Initialize the file filter."""
        # Cache for file inclusion results (LRU, bounded)
        self._file_inclusion_cache: OrderedDict[str, bool] = OrderedDict()

    def _get_cached(self, cache_key: str) -> bool | None:
        """Return cached result and refresh LRU order, or None if missing."""
        if cache_key in self._file_inclusion_cache:
            self._file_inclusion_cache.move_to_end(cache_key)
            return self._file_inclusion_cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, result: bool) -> None:
        """Store result and evict oldest entries if cache exceeds max size."""
        self._file_inclusion_cache[cache_key] = result
        self._file_inclusion_cache.move_to_end(cache_key)
        while len(self._file_inclusion_cache) > self._CACHE_MAX_SIZE:
            self._file_inclusion_cache.popitem(last=False)

    def parse_file(self, file_path: str) -> dict:
        """Parse inclusion or exclusion file.

        The format for each line should be:
        # Comments start with #
        ext:.my-extension  for extensions
        file:my-file.py    for filenames
        dir:my-directory   for directories
        """
        with open(file_path) as f:
            lines = f.readlines()

        parsed_data = {"ext": [], "file": [], "dir": []}
        for line in lines:
            if line.startswith("#"):
                continue
            try:
                key, value = line.strip().split(":")
                if key in parsed_data:
                    parsed_data[key].append(value)
                else:
                    logging.error("Unrecognized key in line: %s, skipping.", line)
            except ValueError:
                pass  # Skip malformed lines

        return parsed_data

    def should_include(
        self,
        file_path: str,
        inclusions: dict | None = None,
        exclusions: dict | None = None,
    ) -> bool:
        """
        Check if a file should be included, using multi-dimensional checks for compression and encryption.

        Args:
            file_path: File path
            inclusions: Inclusion rules
            exclusions: Exclusion rules

        Returns:
            True if file should be included, False otherwise.
        """
        # Check cache
        cache_key = f"{file_path}:{hash(str(inclusions))}:{hash(str(exclusions))}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Exclude symlinks
        if os.path.islink(file_path):
            self._set_cached(cache_key, False)
            return False

        # Unified Path Check (Hidden patterns, Blacklisted directories/files)
        if is_ignored_path(file_path):
            self._set_cached(cache_key, False)
            return False

        # If no explicit rules, include all safe text files
        if not inclusions and not exclusions:
            result = is_text_file(file_path) and not is_encrypted_path(file_path)
            # Add compression check here as well for default behavior
            if result:
                result = not self._is_likely_compressed_file(file_path)

            self._set_cached(cache_key, result)
            return result

        # Non-text or encrypted files are always excluded
        if not is_text_file(file_path) or is_encrypted_path(file_path):
            self._set_cached(cache_key, False)
            return False

        # Check file size
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > CODE_QUALITY_THRESHOLDS["max_file_size_mb"]:
                logging.debug(f"Excluding too large file: {file_path} ({file_size_mb:.2f}MB)")
                self._set_cached(cache_key, False)
                return False
        except OSError:
            pass

        # Check for compressed file - Fast check first
        if self._is_likely_compressed_file(file_path):
            self._set_cached(cache_key, False)
            return False

        # Filter based on extension, filename, and directory
        file_name = os.path.basename(file_path)
        ext = get_file_ext(file_path)
        dirs = os.path.dirname(file_path).split("/")

        if inclusions:
            result = (
                ext in inclusions.get("ext", [])
                or file_name in inclusions.get("file", [])
                or any(d in dirs for d in inclusions.get("dir", []))
            )
            self._set_cached(cache_key, result)
            return result
        elif exclusions:
            result = (
                ext not in exclusions.get("ext", [])
                and file_name not in exclusions.get("file", [])
                and all(d not in dirs for d in exclusions.get("dir", []))
            )
            self._set_cached(cache_key, result)
            return result

        # Default include
        self._set_cached(cache_key, True)
        return True

    def _is_likely_compressed_file(self, file_path: str) -> bool:
        """Fast check if file is likely compressed."""
        file_name = os.path.basename(file_path)
        dir_path = os.path.dirname(file_path)

        # Check if in directory likely to contain compressed code
        if any(compressed_dir in dir_path for compressed_dir in LIKELY_COMPRESSED_CODE_DIRS):
            if self._check_compressed_content_sample(file_path):
                return True

        # Check filename patterns
        for pattern in COMPRESSED_FILE_PATTERNS:
            if re.search(pattern, file_name, re.IGNORECASE):
                return True

        # Check source map extensions
        for ext in SOURCE_MAP_EXTENSIONS:
            if file_name.endswith(ext):
                return True

        # Valid extensions for content check
        ext = get_file_ext(file_path)
        if ext in COMPRESSIBLE_EXTENSIONS:
            return self._is_compressed_content(file_path)

        return False

    def _check_compressed_content_sample(self, file_path: str) -> bool:
        """Simple sample check for compressed content."""
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                sample = f.read(1000)

            if not sample:
                return False

            lines = sample.split("\n")

            # 1. Single long line
            if len(lines) > 0 and len(lines[0]) > 500:
                return True

            # 2. Lack of newlines
            if len(lines) < 3 and len(sample) > 500:
                return True

            # 3. Low whitespace ratio
            whitespace_ratio = sum(1 for c in sample if c.isspace()) / len(sample)
            if whitespace_ratio < 0.1:
                return True

            return False
        except Exception:
            return False

    def _is_compressed_content(self, file_path: str) -> bool:
        """Detailed content analysis to identify compressed/obfuscated code."""
        try:
            sample_size = CODE_QUALITY_THRESHOLDS["sample_size"]
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read(sample_size)

            if not content:
                return False

            # 1. Line length
            lines = content.split("\n")
            if lines:
                max_line_length = max(len(line) for line in lines)
                if max_line_length > CODE_QUALITY_THRESHOLDS["max_line_length"]:
                    return True

            # 2. Newline ratio
            newline_ratio = content.count("\n") / max(len(content), 1)
            if newline_ratio < CODE_QUALITY_THRESHOLDS["min_newline_ratio"] and len(content) > 1000:
                return True

            # 3. Whitespace ratio
            whitespace_chars = sum(1 for c in content if c.isspace())
            whitespace_ratio = whitespace_chars / max(len(content), 1)
            if whitespace_ratio < CODE_QUALITY_THRESHOLDS["min_whitespace_ratio"]:
                return True

            # 4. Semicolon density (for JS)
            ext = get_file_ext(file_path)
            if ext in SEMANTIC_LANGUAGE_MAP["javascript"]:
                semicolon_ratio = content.count(";") / max(len(content), 1)
                if semicolon_ratio > CODE_QUALITY_THRESHOLDS["max_semicolon_ratio"]:
                    return True

            # 5. Character Entropy
            char_counts = Counter(content)
            total_chars = len(content)
            entropy = -sum(
                (count / total_chars) * math.log2(count / total_chars)
                for count in char_counts.values()
            )
            if entropy > CODE_QUALITY_THRESHOLDS["max_char_entropy"]:
                return True

            # 6. Variable Name Analysis (Short vars)
            if ext in SEMANTIC_LANGUAGE_MAP["javascript"] or ext in SEMANTIC_LANGUAGE_MAP["typescript"]:
                short_vars = len(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]?\b", content))
                total_words = len(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", content))

                if total_words > 50 and short_vars / max(total_words, 1) > 0.7:
                    return True

            # 7. Pattern Matching
            for pattern in SUSPICIOUS_JS_PATTERNS:
                if re.search(pattern, content):
                    return True

            return False

        except Exception as e:
            logging.debug(f"Error analyzing file {file_path}: {str(e)}")
            return False
