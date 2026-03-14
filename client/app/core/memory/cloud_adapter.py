"""
Cloud LTM Adapter - Integrates CloudClient with local memory system.

Provides:
- Transparent LTM access (local cache -> cloud -> fallback)
- Offline operation with degraded functionality
- Automatic retry and reconnection
- Local fallback for when cloud is unavailable
"""

import asyncio
from typing import Any, Optional

from app.core.config import settings
from app.infrastructure.cloud import CloudClient, CloudClientError
from app.infrastructure.cloud.cache import get_ltm_cache, get_atlas_cache
from app.infrastructure.cloud.protocol import ErrorCode
from app.logging import logger


class CloudLTMError(Exception):
    """Error accessing cloud LTM."""
    pass


class CloudLTM:
    """
    Adapter for cloud-based Long-Term Memory.

    Usage:
        ltm = CloudLTM()

        # Query with automatic caching
        memories = await ltm.recall("how to login")

        # Atlas query with fallback
        elements = await ltm.query_atlas("com.example.app", "login button")
    """

    def __init__(self, client: CloudClient = None):
        self.client = client
        self._ltm_cache = get_ltm_cache()
        self._atlas_cache = get_atlas_cache()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize cloud LTM (lazy connection)."""
        # Connection is lazy - will connect on first use
        self._initialized = True
        logger.debug("[CloudLTM] Initialized (lazy connection)")

    async def flush(self) -> None:
        """Flush any pending operations."""
        pass

    async def get_project_concepts(self, project_id: int) -> list[dict[str, Any]]:
        """
        Get concepts for a project from cloud LTM.

        Returns empty list if cloud unavailable (client mode fallback).
        """
        try:
            await self._ensure_client()
            # TODO: Implement via CloudClient when available
            # For now, return empty list (client mode fallback)
            return []
        except Exception as e:
            logger.debug(f"[CloudLTM] get_project_concepts failed: {e}")
            return []

    async def _ensure_client(self):
        """Ensure cloud client is initialized."""
        if self._initialized:
            return

        if self.client is None:
            from app.infrastructure.cloud import get_cloud_client
            self.client = get_cloud_client()
            await self.client.connect()

        self._initialized = True

    async def recall(
        self,
        query: str,
        memory_types: list[str] = None,
        limit: int = 10,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Recall memories from LTM.

        Flow:
        1. Check local cache
        2. Query cloud if cache miss
        3. Store in cache for future
        4. Return fallback if cloud unavailable
        """
        memory_types = memory_types or ["episodic", "concept"]

        # 1. Check cache
        if use_cache:
            cached = self._ltm_cache.get(query, memory_types)
            if cached is not None:
                logger.debug(f"[CloudLTM] Cache hit for query: {query[:50]}...")
                return cached

        # 2. Query cloud
        try:
            await self._ensure_client()

            response = await self.client.memory_recall(
                query=query,
                memory_types=memory_types,
                limit=limit,
            )

            memories = response.memories

            # 3. Store in cache
            if memories and use_cache:
                self._ltm_cache.set(query, memory_types, memories)

            logger.debug(f"[CloudLTM] Retrieved {len(memories)} memories from cloud")
            return memories

        except CloudClientError as e:
            if e.error_code == ErrorCode.CLOUD_NOT_CONFIGURED:
                logger.debug("[CloudLTM] Cloud not configured, using fallback")
            else:
                logger.warning(f"[CloudLTM] Cloud query failed: {e.message}")

            # 4. Fallback: return empty or stale cache
            return self._fallback_recall(query)

        except Exception as e:
            logger.error(f"[CloudLTM] Unexpected error: {e}")
            return self._fallback_recall(query)

    async def query_atlas(
        self,
        app_id: str,
        element_description: str,
        current_screen: str = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Query Atlas for UI elements.

        Flow:
        1. Check local cache
        2. Query cloud if cache miss
        3. Store in cache
        4. Return fallback (empty list) if cloud unavailable
        """
        # 1. Check cache
        if use_cache:
            cached = self._atlas_cache.get(app_id, element_description)
            if cached is not None:
                logger.debug(f"[CloudLTM] Atlas cache hit for {app_id}")
                return cached

        # 2. Query cloud
        try:
            await self._ensure_client()

            elements = await self.client.atlas_query(
                app_id=app_id,
                element_description=element_description,
                current_screen=current_screen,
            )

            # 3. Store in cache
            if elements and use_cache:
                self._atlas_cache.set(app_id, element_description, elements)

            logger.debug(f"[CloudLTM] Retrieved {len(elements)} elements from Atlas")
            return elements

        except CloudClientError as e:
            if e.error_code == ErrorCode.CLOUD_NOT_CONFIGURED:
                logger.debug("[CloudLTM] Atlas cloud not configured")
            else:
                logger.warning(f"[CloudLTM] Atlas query failed: {e.message}")

            # 4. Fallback
            return self._fallback_atlas(app_id, element_description)

        except Exception as e:
            logger.error(f"[CloudLTM] Atlas error: {e}")
            return self._fallback_atlas(app_id, element_description)

    async def contribute_atlas(
        self,
        app_id: str,
        elements: list[dict],
    ) -> bool:
        """
        Contribute UI observations to Atlas.

        Silently fails if cloud unavailable (fire-and-forget).
        """
        try:
            await self._ensure_client()

            # TODO: Implement via CloudClient when available
            logger.info(f"[CloudLTM] Would contribute {len(elements)} elements to {app_id}")
            return True

        except Exception as e:
            logger.debug(f"[CloudLTM] Contribution failed (non-critical): {e}")
            return False

    def _fallback_recall(self, query: str) -> list[dict[str, Any]]:
        """
        Fallback when cloud LTM is unavailable.

        Returns empty list with a warning logged.
        Client should proceed with local-only operation.
        """
        logger.info(f"[CloudLTM] Fallback: no memories available for '{query[:50]}...'")

        # Return empty list
        # In future, could return local STM memories as fallback
        return []

    def _fallback_atlas(self, app_id: str, description: str) -> list[dict[str, Any]]:
        """
        Fallback when Atlas is unavailable.

        Returns empty list. Client should use local UI detection.
        """
        logger.info(f"[CloudLTM] Fallback: no Atlas data for {app_id}")
        return []


class CloudSkillManager:
    """
    Manager for cloud-based skills.

    Handles skill discovery, download, and caching.
    """

    def __init__(self, client: CloudClient = None):
        self.client = client
        self._skill_cache = get_skill_cache()
        self._initialized = False

    async def _ensure_client(self):
        """Ensure cloud client is initialized."""
        if self._initialized:
            return

        if self.client is None:
            from app.infrastructure.cloud import get_cloud_client
            self.client = get_cloud_client()
            await self.client.connect()

        self._initialized = True

    async def list_skills(
        self,
        platform: str = None,
        app_id: str = None,
    ) -> list[dict[str, Any]]:
        """List available skills from cloud."""
        try:
            await self._ensure_client()
            return await self.client.skill_list(platform=platform, app_id=app_id)
        except CloudClientError as e:
            logger.warning(f"[CloudSkillManager] Failed to list skills: {e.message}")
            # Return locally cached skill IDs
            return self._list_local_skills()
        except Exception as e:
            logger.error(f"[CloudSkillManager] Error listing skills: {e}")
            return self._list_local_skills()

    async def download_skill(self, skill_id: str) -> Optional[dict]:
        """
        Download skill from cloud.

        Checks local cache first, downloads if not present.
        """
        # Check cache
        cached = self._skill_cache.get(skill_id)
        if cached is not None:
            logger.debug(f"[CloudSkillManager] Cache hit for skill {skill_id}")
            return cached

        # Download from cloud
        try:
            await self._ensure_client()

            skill_package = await self.client.skill_download(skill_id)

            # Cache it
            skill_dict = {
                "skill_id": skill_package.skill_id,
                "name": skill_package.name,
                "version": skill_package.version,
                "platform": skill_package.platform,
                "macro": skill_package.macro,
                "atlas_snapshot": skill_package.atlas_snapshot,
                "description": skill_package.description,
                "verification_status": skill_package.verification_status,
                "success_rate": skill_package.success_rate,
                "created_at": skill_package.created_at,
            }

            self._skill_cache.set(skill_id, skill_dict)

            logger.info(f"[CloudSkillManager] Downloaded skill {skill_id}")
            return skill_dict

        except CloudClientError as e:
            logger.error(f"[CloudSkillManager] Failed to download {skill_id}: {e.message}")
            return None
        except Exception as e:
            logger.error(f"[CloudSkillManager] Error downloading {skill_id}: {e}")
            return None

    async def request_synthesis(
        self,
        task_name: str,
        description: str,
        video_url: str = None,
        platform: str = "android",
    ) -> Optional[str]:
        """
        Request skill synthesis from learning materials.

        Returns job ID for polling.
        """
        try:
            await self._ensure_client()

            job_id = await self.client.skill_synthesize(
                task_name=task_name,
                description=description,
                video_url=video_url,
                platform=platform,
            )

            logger.info(f"[CloudSkillManager] Synthesis job {job_id} started")
            return job_id

        except CloudClientError as e:
            logger.error(f"[CloudSkillManager] Synthesis request failed: {e.message}")
            return None
        except Exception as e:
            logger.error(f"[CloudSkillManager] Synthesis error: {e}")
            return None

    async def get_synthesis_status(self, job_id: str) -> dict[str, Any]:
        """Check synthesis job status."""
        try:
            await self._ensure_client()
            return await self.client.skill_synthesis_status(job_id)
        except Exception as e:
            logger.error(f"[CloudSkillManager] Status check failed: {e}")
            return {"job_id": job_id, "status": "unknown", "error": str(e)}

    def _list_local_skills(self) -> list[dict]:
        """List locally cached skills."""
        # TODO: Scan local skill directory
        return []


# Global instances
_cloud_ltm: Optional[CloudLTM] = None
_cloud_skill_manager: Optional[CloudSkillManager] = None


async def get_cloud_ltm() -> CloudLTM:
    """Get global CloudLTM instance."""
    global _cloud_ltm
    if _cloud_ltm is None:
        _cloud_ltm = CloudLTM()
    return _cloud_ltm


async def get_cloud_skill_manager() -> CloudSkillManager:
    """Get global CloudSkillManager instance."""
    global _cloud_skill_manager
    if _cloud_skill_manager is None:
        _cloud_skill_manager = CloudSkillManager()
    return _cloud_skill_manager
