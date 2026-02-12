import asyncio
import logging
from sqlalchemy import select

from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models import Repository
from app.domain.codebase.indexing.service import IndexingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reindex_all():
    logger.info("Starting Full Re-indexing of all repositories...")
    
    service = IndexingService()
    
    async with AsyncSessionLocal() as session:
        # Get all repos
        stmt = select(Repository)
        result = await session.execute(stmt)
        repos = result.scalars().all()
        
        if not repos:
            logger.info("No repositories found in database.")
            return

        for repo in repos:
            logger.info(f"Indexing Repository: {repo.name} ({repo.local_path})")
            try:
                await service.index_repository(repo.local_path, repo.id, force=True)
                logger.info(f"Successfully indexed {repo.name}")
            except Exception as e:
                logger.error(f"Failed to index {repo.name}: {e}")

    logger.info("Re-indexing complete.")

if __name__ == "__main__":
    asyncio.run(reindex_all())
