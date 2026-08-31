"""React engine `webfetch` tool — fetch a URL and convert to text/markdown/html
(OpenCode `tool/webfetch` semantic, §10.2.2 目标核心 12)。

用于抓取 URL 内容供模型阅读；与 `websearch`（搜索）互补。
"""

from __future__ import annotations

import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)

#: 单次抓取最大字符数（超出由 executor 统一截断，这里是保守下限）
MAX_CHARS = 200_000


@evoloop_tool(is_hidden=False)
async def webfetch(
    url: str,
    format: str = "markdown",
    timeout: float = 30.0,
) -> str:
    """抓取一个 URL 并返回其内容（转成 markdown/text/html）。

    Args:
        url: 要抓取的完整 URL（建议 https）。
        format: 输出格式——'markdown'（默认）、'text' 或 'html'。
        timeout: 请求超时秒数（默认 30）。
    """
    if not url or not url.startswith(("http://", "https://")):
        return f"Error: invalid URL: {url!r}. Must start with http:// or https://"

    from app.utils.http import create_client

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": "Mozilla/5.0 (compatible; EvoLoop/Backend; +webfetch)",
    }
    client = create_client(timeout=float(timeout), headers=headers)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[WebFetch] request failed for {url}: {e}")
        return f"Error fetching {url}: {e}"
    finally:
        await client.aclose()

    content_type = resp.headers.get("content-type", "") or ""
    html = resp.text or ""

    try:
        if format == "text":
            import re

            stripped = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
            stripped = re.sub(r"<[^>]+>", " ", stripped)
            out = re.sub(r"\s+", " ", stripped).strip()
        elif format == "html":
            out = html
        else:  # markdown
            from markdownify import markdownify as md

            out = md(html, strip=["script", "style", "nav", "footer"])
    except Exception as e:
        logger.warning(f"[WebFetch] conversion failed for {url}: {e}")
        out = html

    out = out.strip()
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS] + "\n...[TRUNCATED: content too long]"

    if not out:
        return f"No readable content at {url} (content-type: {content_type or 'unknown'})."
    return f"Content of {url}:\n\n{out}"
