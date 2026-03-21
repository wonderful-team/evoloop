import asyncio
from app.core.tools.base import evoloop_tool


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
    except Exception:
        return None


async def _search_baidu(query: str) -> list[str] | None:
    """使用 requests + BeautifulSoup 爬取百度搜索结果。"""
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import quote

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    url = f"https://www.baidu.com/s?wd={quote(query)}"

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(url, headers=headers, timeout=15)
    )
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


@evoloop_tool(
    is_pollable=False,
    name_map={"zh": "搜索网页", "en": "Search Web"}
)
async def search_web(query: str) -> str:
    """
    Searches the web for the given query using DuckDuckGo or Baidu.
    Returns a list of search results with titles and URLs.
    """
    from app.utils import ContentFormatter, ControllerResponse
    
    # 首先尝试 DuckDuckGo
    results = await _search_duckduckgo(query)
    if results:
        return ContentFormatter.web_search_results(query, results)

    # 回退到百度搜索
    results = await _search_baidu(query)
    if results:
        return ContentFormatter.web_search_results(query, results)

    # 两个都失败了
    return ControllerResponse.error(
        "Unable to search the web",
        details="Search services are currently unavailable",
        note="Use 'browser_control' to navigate to target sites directly for higher reliability"
    )
