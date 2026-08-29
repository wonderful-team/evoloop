"""Filename sanitization utilities (stdlib-only, no app dependencies).

Single canonical implementation; re-exported by app.utils.security for
backward compatibility and consumed directly by lightweight importers.
"""

import os
import re


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    Sanitize a filename by removing or replacing unsafe characters.

    Args:
        filename: Original filename
        replacement: Character to replace unsafe characters with

    Returns:
        Sanitized filename safe for use in filesystem
    """
    # Remove path separators and null bytes
    unsafe = ["\\", "/", "\x00", "\n", "\r", "\t"]
    result = filename
    for char in unsafe:
        result = result.replace(char, replacement)

    # Remove other special characters
    result = re.sub(r'[<>:"|?*]', replacement, result)

    # Limit length
    if len(result) > 255:
        name, ext = os.path.splitext(result)
        result = name[: 255 - len(ext)] + ext

    # Don't allow hidden files or reserved names on Windows
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    base = os.path.splitext(result)[0].upper()
    if base in reserved:
        result = replacement + result

    return result
