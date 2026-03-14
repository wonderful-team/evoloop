"""Long-term memory interface for persistent knowledge and experiences."""

from abc import abstractmethod

from app.core.memory.interfaces.base import IMemoryProvider


class SearchResult:
    """Result from a concept search."""

    def __init__(self, name: str, description: str, score: float, files: list[str] | None = None):
        self.name = name
        self.description = description
        self.score = score
        self.files = files or []


class Concept:
    """Semantic knowledge unit."""

    def __init__(self, name: str, description: str, project_id: int, related_files: list[str] | None = None):
        self.name = name
        self.description = description
        self.project_id = project_id
        self.related_files = related_files or []


class Episode:
    """Past task execution record."""

    def __init__(
        self,
        goal: str,
        result: str,
        plan_summary: str,
        error_msg: str | None,
        project_id: int,
        source_message_id: str | None = None,
    ):
        self.goal = goal
        self.result = result
        self.plan_summary = plan_summary
        self.error_msg = error_msg
        self.project_id = project_id
        self.source_message_id = source_message_id


class ILongTermMemory(IMemoryProvider):
    """
    Interface for long-term (persistent) memory.
    Handles concepts, experiences, and vectorized knowledge.
    """

    @abstractmethod
    async def store_concept(self, concept: Concept) -> None:
        """
        Store a knowledge concept.

        Args:
            concept: The concept to store
        """
        pass

    async def search_concepts(
        self, query: str, project_id: int | None = None, min_score: float = 0.7
    ) -> list[SearchResult]:
        """
        Semantic search for concepts.

        Args:
            query: The search query
            project_id: Project context for filtering
            min_score: Minimum similarity score (0-1)

        Returns:
            List of matching concepts with scores
        """
        pass

    @abstractmethod
    async def search_concepts_data(self, query: str, project_id: int | None = None) -> list[dict]:
        """
        Raw data version of search (for internal use).

        Args:
            query: The search query
            project_id: Project context for filtering

        Returns:
            List of concept dictionaries
        """
        pass

    @abstractmethod
    async def record_episode(self, episode: Episode) -> str | None:
        """
        Store a completed task execution as an episode.

        Args:
            episode: The episode to record

        Returns:
            Episode ID if successful, None otherwise
        """
        pass

    @abstractmethod
    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        """
        Find past episodes similar to the current goal.

        Args:
            goal: The current goal to match against
            project_id: Project context
            top_k: Number of similar episodes to retrieve

        Returns:
            Formatted string of relevant past experiences
        """
        pass

    @abstractmethod
    async def link_episode_to_concepts(
        self, episode_id: str, concept_names: list[str], project_id: int
    ) -> None:
        """
        Link an episode to specific concepts.

        Args:
            episode_id: The episode identifier
            concept_names: List of concept names to link
            project_id: Project context
        """
        pass

    @abstractmethod
    async def find_episodes_by_concept(
        self, concept_name: str, project_id: int, limit: int = 10
    ) -> list[dict]:
        """
        Find episodes related to a specific concept.

        Args:
            concept_name: The concept to search for
            project_id: Project context
            limit: Maximum number of episodes to return

        Returns:
            List of episode dictionaries
        """
        pass

    @abstractmethod
    async def list_concepts(self, project_id: int, limit: int = 50) -> list[dict]:
        """
        List all concepts for a project.

        Args:
            project_id: Project context
            limit: Maximum number of concepts to return

        Returns:
            List of concept dictionaries with episode counts
        """
        pass

    @abstractmethod
    async def get_project_concepts(self, project_id: int) -> list[str]:
        """
        Retrieve all concepts associated with a project.

        Args:
            project_id: Project identifier

        Returns:
            List of formatted concept strings
        """
        pass

    @abstractmethod
    async def delete_episodes_by_message_ids(self, message_ids: list[str]) -> int:
        """
        Delete episodes associated with specific source message IDs.

        Args:
            message_ids: List of source message IDs

        Returns:
            Number of deleted episodes
        """
        pass
