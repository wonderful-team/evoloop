import asyncio
import logging
import re
from urllib.parse import quote, quote_plus

import requests

from app.core.tools import evoloop_tool
from app.utils.controller_response import ControllerResponse
from app.utils.search_results_formatter import format_web_search_results

logger = logging.getLogger(__name__)


def _detect_wiki_language(query: str) -> str:
    """根据查询内容自动检测 Wikipedia 语言版本。

    规则：
    - 包含中文字符 → zh（中文 Wikipedia）
    - 否则 → en（英文 Wikipedia）
    """
    # CJK Unified Ideographs 范围
    if re.search(r"[\u4e00-\u9fff]", query):
        return "zh"
    return "en"


async def _search_duckduckgo(query: str) -> list[str] | None:
    """尝试使用 DuckDuckGo 搜索。"""
    try:
        from ddgs import DDGS

        results = []
        with DDGS(backend="api", timeout=30) as ddgs:
            for result in ddgs.text(query, max_results=5, backend="api"):
                results.append(
                    f"Title: {result['title']}\n"
                    f"URL: {result['href']}\n"
                    f"Description: {result['body']}\n"
                )
        return results if results else None
    except Exception as e:
        logger.debug("Suppressed error: %s", e, exc_info=True)
        return None


async def _search_baidu(query: str) -> list[str] | None:
    """使用 requests + BeautifulSoup 爬取百度搜索结果。"""
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    url = f"https://www.baidu.com/s?wd={quote_plus(query)}"

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=15))
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    # 百度搜索结果选择器
    containers = soup.select("div.c-container")
    if not containers:
        # 备选选择器
        containers = soup.select("div.result, div.c-result")

    for container in containers[:5]:
        try:
            # 标题
            title_elem = container.select_one("h3.t, h3, a[href]")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # URL
            url_elem = container.select_one("a[href]")
            result_url = url_elem.get("href", "") if url_elem else ""

            # 描述
            desc_elem = container.select_one(
                "span.content-right_8Zs40, "
                "div.content-right_8Zs40, "
                "div.c-abstract, "
                "span, p.content"
            )
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            if title and result_url:
                results.append(
                    f"Title: {title}\n"
                    f"URL: {result_url}\n"
                    f"Description: {description}\n"
                )
        except Exception:
            continue

    return results if results else None


async def _search_wikipedia(query: str) -> list[str] | None:
    """使用 Wikipedia MediaWiki API 搜索百科条目。

    自动根据查询内容选择语言版本（中文/英文）。
    返回格式与其他搜索引擎保持一致：Title/URL/Description。
    """
    lang = _detect_wiki_language(query)
    api_url = f"https://{lang}.wikipedia.org/w/api.php"

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 5,
        "srprop": "snippet|timestamp|wordcount",
    }

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(api_url, params=params, timeout=15))
        response.raise_for_status()
        data = response.json()

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return None

        results = []
        for item in search_results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            # 清理 HTML 标签
            snippet_clean = re.sub(r"<[^>]+>", "", snippet)
            page_url = (f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}")

            results.append(
                f"Title: {title}\n"
                f"URL: {page_url}\n"
                f"Description: {snippet_clean}\n"
            )

        return results if results else None

    except Exception as e:
        logger.debug("Suppressed error: %s", e, exc_info=True)
        return None


async def _fetch_wikipedia_summary(title: str, lang: str = "en") -> str | None:
    """获取 Wikipedia 条目的摘要（纯文本）。"""

    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": title,
        "exintro": 1,
        "explaintext": 1,
        "format": "json",
    }

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(api_url, params=params, timeout=15))
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            extract = page_data.get("extract", "")
            if extract:
                return extract.strip()
        return None
    except Exception as e:
        logger.debug("Suppressed error: %s", e, exc_info=True)
        return None


@evoloop_tool(summary_template="evoloop.tool_summary.search_web")
async def search_web(query: str) -> str:
    """
    Searches the web for the given query using DuckDuckGo, Baidu, or Wikipedia.
    Returns a list of search results with titles and URLs.
    """
    # 首先尝试 DuckDuckGo
    results = await _search_duckduckgo(query)
    if results:
        res = format_web_search_results(query, results)
        if isinstance(res, tuple):
            text, meta = res
            meta["page"] = 1
            return text, meta
        return res, {"count": len(results), "page": 1}

    # 回退到百度搜索
    results = await _search_baidu(query)
    if results:
        res = format_web_search_results(query, results)
        if isinstance(res, tuple):
            text, meta = res
            meta["page"] = 1
            return text, meta
        return res, {"count": len(results), "page": 1}

    # 回退到 Wikipedia 百科搜索
    results = await _search_wikipedia(query)
    if results:
        res = format_web_search_results(query, results)
        if isinstance(res, tuple):
            text, meta = res
            meta["page"] = 1
            return text, meta
        return res, {"count": len(results), "page": 1}

    # 三个都失败了
    return ControllerResponse.error(
        "Unable to search the web",
        details="Search services are currently unavailable",
        note="Use 'browser_control' to navigate to target sites directly for higher reliability",
    ), {"count": 0}
