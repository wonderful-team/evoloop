import re
from collections.abc import Sequence


def truncate_output(text: str, max_len: int = 6000, suffix: str = "...") -> str:
    """
    Truncate long output strings with simple indicator.

    Args:
        text: The text to truncate
        max_len: Maximum length (default 6000)
        suffix: Suffix string

    Returns:
        Truncated text
    """
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n{suffix} [truncated, total {len(text)} chars]"


def chunk_text(text: str, limit: int) -> list[str]:
    """Split a long reply into chunks not exceeding ``limit`` characters.

    Prefers newline boundaries, then sentence period, then a hard cut at the
    half-way point. No content is dropped.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind("。", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


# ============================================================================
# Text Normalization
# ============================================================================


def should_flush_text(
    text: str,
    min_chars: int | None = None,
    min_tokens: int | None = None,
    has_boundary: bool | None = None,
) -> bool:
    """判断累积文本是否达到发送阈值。

    Args:
        text: 累积的文本内容
        min_chars: 最小字符数（如 VoiceChannel 30 字才发 TTS）
        min_tokens: 最小 token 数（如 TokenFilter 100 tokens 才发）
        has_boundary: 是否含有句子边界（换行/标点）

    Returns:
        True 表示应发送，False 表示继续累积
    """
    if not text:
        return False
    if min_chars is not None and len(text) >= min_chars:
        return True
    if min_tokens is not None:
        from app.utils.token import estimate_tokens

        if estimate_tokens(text) >= min_tokens:
            return True
    if has_boundary and "\n" in text:
        return True
    return False


def normalize_text(text: str | None) -> str:
    """
    Normalize text for comparison: NFC unicode, lowercase, no spaces.

    Used for element name matching across different platforms.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    import unicodedata

    if not text:
        return ""

    return (
        unicodedata.normalize("NFC", str(text))
        .lower()
        .strip()
        .replace(" ", "")
        .replace("\u3000", "")
    )


# ============================================================================
# Markdown cleanup for TTS
# ============================================================================


def strip_filler_words(value: str, prefixes: Sequence[str], suffixes: Sequence[str]) -> str:
    """从槽位值中剥离口语填充词（词表数据驱动，最长词优先）。

    LocalMatcher 与 MacroResolver 共用同一实现；词表全空时仅做 strip。
    """
    if not prefixes and not suffixes:
        return value.strip()
    v = value.strip()
    prefix_list = sorted(prefixes, key=len, reverse=True)
    suffix_list = sorted(suffixes, key=len, reverse=True)
    while True:
        changed = False
        for p in prefix_list:
            if v.startswith(p):
                v = v[len(p) :].strip()
                changed = True
                break
        for s in suffix_list:
            if v.endswith(s):
                v = v[: -len(s)].strip()
                changed = True
                break
        if not changed:
            break
    return v


def strip_markdown_for_tts(text: str) -> str:
    """Strip markdown formatting that would be spoken verbatim in TTS."""
    if not text:
        return text

    # 1. Images: keep alt text if present, otherwise remove.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 2. Links: keep link text only.
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 3. Structural markers first so list bullets are removed before inline
    #    emphasis markers strip the leading * / - characters.
    # 3a. Heading markers (line start only).
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    # 3b. Blockquote markers (line start only).
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)
    # 3c. Numbered list markers (line start only).
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 3d. Bullet list markers (line start only).
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    # 4. Inline formatting markers.
    text = re.sub(r"\*\*|\*|__|_|~~|`", "", text)
    # 5. Table pipes.
    text = re.sub(r"\|", "", text)
    # 6. Horizontal rules (line only).
    text = re.sub(r"^\s*[-*_]{2,}\s*$", "", text, flags=re.MULTILINE)
    # 7. Normalize excessive whitespace.
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def normalize_ws(text: str) -> str:
    """Collapse any run of whitespace to a single space."""
    return " ".join(text.split())


def normalize_compact(text: str | None) -> str:
    """Normalize app/process names for cross-source matching.

    Strips runs of whitespace, hyphens and underscores, then lowercases.
    """
    return re.sub(r"[\s\-_]+", "", text or "").lower()
