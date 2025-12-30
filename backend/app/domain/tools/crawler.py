from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.crawler.service import crawler_service


class CrawlerToolInput(BaseModel):
    url: str = Field(description="The URL to crawl.")
    # extraction_schema: Optional[str] = Field(description="Optional JSON schema string to extract structured data.")


class CrawlerTool(BaseTool):
    name: str = "crawl_web_page"
    description: str = "Fast web crawler. Use this to read the content of a specific URL. It returns clean Markdown. Prefer this over browser_agent for simple reading tasks as it is much faster."
    args_schema: Type[BaseModel] = CrawlerToolInput
    
    def _run(self, url: str):
        raise NotImplementedError("Use _arun")
        
    async def _arun(self, url: str):
        # We handle schema later for advanced usage
        return await crawler_service.crawl(url)


crawler_tool = CrawlerTool()
