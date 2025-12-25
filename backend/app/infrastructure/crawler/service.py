
import logging
import asyncio
from typing import Optional, Dict, Any, List
import json
import os

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy, LLMExtractionStrategy
    HAS_CRAWL4AI = True
except ImportError:
    HAS_CRAWL4AI = False
    
from app.core.config import settings
from app.logging import logger

class CrawlerService:
    _instance = None
    
    def __init__(self):
        self.crawler = None
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def crawl(self, url: str, extraction_schema: Optional[Dict[str, Any]] = None, css_selector: Optional[str] = None) -> str:
        """
        Crawl a URL and return Markdown or JSON.
        
        Args:
            url: Target URL
            extraction_schema: Optional JSON schema for structured extraction.
            css_selector: Optional CSS selector to wait for or focus on.
        """
        if not HAS_CRAWL4AI:
            return "Error: crawl4ai library not installed. Please install it to use this feature."

        logger.info(f"Starting Crawl4AI task for: {url}")
        
        # Configure Browser (Headless, Anti-bot)
        browser_config = BrowserConfig(
            headless=True,
            verbose=True,
            # stealth=True # If supported by version, or use extra_args
        )
        
        # Configure Run
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.ENABLED,
            # css_selector=css_selector,
            # word_count_threshold=10, 
        )
        
        # Add Extraction Strategy if Schema provided
        if extraction_schema:
            run_config.extraction_strategy = JsonCssExtractionStrategy(extraction_schema)

        # Execute
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    config=run_config
                )
                
                if extraction_schema:
                    # Return Extracted JSON
                    return result.extracted_content
                else:
                    # Return Markdown
                    # We might want 'fit_markdown' offered by crawl4ai which removes noise
                    if hasattr(result, 'markdown') and hasattr(result.markdown, 'fit_markdown'):
                         return result.markdown.fit_markdown
                    elif hasattr(result, 'markdown'): 
                         return str(result.markdown)
                    else:
                         return str(result)

        except Exception as e:
            logger.error(f"Crawl failed: {e}")
            return f"Error during crawl: {str(e)}"

crawler_service = CrawlerService.get_instance()
