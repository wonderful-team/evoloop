"""React engine `webfetch` tool — fetch a URL and convert to text/markdown/html
(OpenCode `tool/webfetch` semantic, §10.2.2 目标核心 12)。

用于抓取 URL 内容供模型阅读；与 `websearch`（搜索）互补。
"""

from __future__ import annotations

import logging
import re

from app.core.tools import evoloop_tool
from app.utils.http import is_http_url

logger = logging.getLogger(__name__)

#: 单次抓取最大字符数（超出由 executor 统一截断，这里是保守下限）
MAX_CHARS = 200_000


def _is_private_target(url: str) -> bool:
    """判断 URL 目标是否为回环/私网地址（多租户 SSRF 门，fail-closed）。

    覆盖：明显的 localhost 文件式写法、IPV4 私有段（含十进制/十六进制等
    变体转回 int 校验）、IPV6 [::1]/fc00::/fe80::、以及按域名解析后的
    实际地址（防 DNS rebinding 指私网）。
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return True

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return True
    if hostname in ("localhost", "intranet", "internal"):
        return True
    if hostname.endswith(".localhost"):
        return True

    # 域名解析到哪都算（DNS rebinding 防护：以解析后的地址为准）
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError):
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            return True
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_multicast
            or ip.is_reserved
        ):
            return True
    return False


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
    if not url or not is_http_url(url):
        return f"Error: invalid URL: {url!r}. Must start with http:// or https://"

    # 多租户 SSRF 门：宿主进程发起的请求能直达回环/私网（宿主与内网服务，
    # 甚至 127.0.0.1:20161 的 API 自身）。隔离容器内 bash 已被防火墙封死内网，
    # 这里保持同一防线——成员仅允许抓取公网地址（fail-closed）。
    from app.core.config import settings as _settings

    if _settings.MULTI_TENANT_MODE and _is_private_target(url):
        logger.info(f"[WebFetch] blocked private/loopback target: {url!r}")
        return (
            "Error: access to private/loopback addresses is not allowed "
            "in multi-tenant mode (host-internal services are out of reach)."
        )

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
