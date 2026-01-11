import os
import sys
import asyncio
import logging
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, Optional

# Add src to path
# sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
# Installed via pip, so import should work directly if setup.py is good.
# Falling back to src import if needed.
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
except ImportError:
    # If pip install didn't link it as top level package properly (unlikely but possible)
    sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode


# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crawl4ai_server")

mcp = FastMCP("Crawl4AI Service")

@mcp.tool()
async def crawl_url(url: str, include_links: bool = False, css_selector: str = None) -> str:
    """
    Crawl a URL and return its content in Markdown format.
    Args:
        url: The URL to crawl.
        include_links: Whether to output links found in the page.
        css_selector: Optional CSS selector to scope the crawl content.
    """
    logger.info(f"Received crawling request for: {url}")
    
    run_config = CrawlerRunConfig(
        css_selector=css_selector,
        # cache_mode=CacheMode.BYPASS # Always fresh? Or use default.
    )

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=url,
                config=run_config
            )
            
            if not result.success:
                logger.error(f"Crawl failed: {result.error_message}")
                return f"Error crawling {url}: {result.error_message}"
            
            # Construct output
            # result.markdown is the main goal
            output = f"## Crawl Result for {url}\n\n"
            output += result.markdown
            
            if include_links and result.links:
                 output += "\n\n### Extracted Links\n"
                 for link in list(result.links.keys())[:20]: # Limit to 20 links
                     output += f"- {link}\n"
            
            return output

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run(transport="sse")
