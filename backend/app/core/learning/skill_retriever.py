
import json
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.domain.codebase.indexing.vectors.factory import EmbedderFactory

logger = logging.getLogger(__name__)


class SkillRetriever:
    """
    Retrieves relevant LearnedSkills from the database based on context.
    Uses a hybrid approach combining:
    1. Semantic similarity (vector search via pgvector)
    2. Keyword matching (fallback and boost)
    """
    
    def __init__(self):
        self._embedder = None
    
    @property
    def embedder(self):
        """Lazy-load embedder to avoid import issues at module load time."""
        if self._embedder is None:
            try:
                self._embedder = EmbedderFactory.get_embedder()
            except Exception as e:
                logger.warning(f"Failed to initialize embedder: {e}")
        return self._embedder

    async def get_relevant_skills(
        self, 
        topic: str, 
        top_k: int = 5,
        min_similarity: float = 0.6,
        use_semantic: bool = True
    ) -> list[LearnedSkill]:
        """
        Find skills relevant to the given topic string using hybrid search.
        
        Args:
            topic: The search query (user intent or task description)
            top_k: Maximum number of skills to return
            min_similarity: Minimum cosine similarity threshold for semantic search
            use_semantic: Whether to attempt semantic search (falls back to keyword if unavailable)
            
        Returns:
            List of matched LearnedSkill objects, ordered by relevance
        """
        if not topic:
            return []
        
        matched_skills: list[LearnedSkill] = []
        seen_ids: set[int] = set()
        
        # 1. Semantic Search (Primary)
        if use_semantic and self.embedder:
            semantic_results = await self._semantic_search(topic, top_k, min_similarity)
            for skill in semantic_results:
                if skill.id not in seen_ids:
                    matched_skills.append(skill)
                    seen_ids.add(skill.id)
        
        # 2. Keyword Search (Fallback/Supplement)
        keyword_results = await self._keyword_search(topic)
        for skill in keyword_results:
            if skill.id not in seen_ids:
                matched_skills.append(skill)
                seen_ids.add(skill.id)
        
        # Limit total results
        return matched_skills[:top_k]
    
    async def _semantic_search(
        self, 
        topic: str, 
        top_k: int = 5,
        min_similarity: float = 0.6
    ) -> list[LearnedSkill]:
        """
        Perform semantic similarity search using pgvector.
        
        Uses the cosine distance operator (<=> in pgvector) to find
        skills with embeddings similar to the query embedding.
        """
        try:
            # Generate query embedding
            query_embedding = await self.embedder.embed_query(topic)
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []
            
            # Format embedding as PostgreSQL array literal
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            
            async with session_scope() as db:
                # pgvector similarity search using cosine distance
                # Note: <=> returns distance (0 = identical), so we compute 1 - distance for similarity
                # We use f-string for the vector since :param::vector causes syntax issues with psycopg
                sql = text(f"""
                    SELECT id, name,
                           1 - (embedding <=> '{embedding_str}'::vector) as similarity
                    FROM learned_skills
                    WHERE is_active = true
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> '{embedding_str}'::vector) >= :min_similarity
                    ORDER BY embedding <=> '{embedding_str}'::vector
                    LIMIT :top_k
                """)
                
                result = await db.execute(
                    sql,
                    {
                        "min_similarity": min_similarity,
                        "top_k": top_k
                    }
                )
                rows = result.fetchall()
                
                # Convert rows to LearnedSkill objects
                skills = []
                for row in rows:
                    skill = await db.get(LearnedSkill, row.id)
                    if skill:
                        skills.append(skill)
                        logger.debug(f"Semantic match: {skill.name} (similarity: {row.similarity:.3f})")
                
                return skills
                
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            return []
    
    async def _keyword_search(self, topic: str) -> list[LearnedSkill]:
        """
        Keyword-based skill matching (original implementation).
        Serves as fallback when semantic search is unavailable.
        """
        topic_lower = topic.lower()
        keywords = set(topic_lower.split())
        
        # Expand CJK keywords into 2-char n-grams for better matching
        if any(ord(c) > 127 for c in topic_lower):
            clean_topic = "".join(c for c in topic_lower if not c.isspace())
            for i in range(len(clean_topic)-1):
                keywords.add(clean_topic[i:i+2])
        
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
            result = await db.execute(stmt)
            all_skills = result.scalars().all()
            
            matched_skills = []
            for skill in all_skills:
                # Check Name
                if skill.name.lower() in topic_lower or topic_lower in skill.name.lower():
                    matched_skills.append(skill)
                    continue
                
                # Check Triggers (JSON string list)
                if skill.trigger_patterns:
                    try:
                        triggers = json.loads(skill.trigger_patterns)
                        # 1. Direct or substring match
                        if any(t.lower() in topic_lower or (len(topic_lower) >= 2 and topic_lower in t.lower()) for t in triggers):
                            matched_skills.append(skill)
                            continue
                        
                        # 2. Atomic keyword overlap (especially for CJK)
                        all_trigger_keywords = set()
                        for t in triggers:
                            all_trigger_keywords.update(t.lower().replace("_", " ").split())
                            # For CJK, add 2-char n-grams
                            if any(ord(c) > 127 for c in t):
                                for i in range(len(t)-1):
                                    all_trigger_keywords.add(t[i:i+2])
                        
                        if any(k in all_trigger_keywords for k in keywords if len(k) >= 2 or any(ord(c) > 127 for c in k)):
                            matched_skills.append(skill)
                            continue

                    except Exception:
                        # Fallback for old/non-json data
                        if any(k in skill.trigger_patterns.lower() for k in keywords if len(k) >= 2 or any(ord(c) > 127 for c in k)):
                            matched_skills.append(skill)
                            continue
                         
            return matched_skills

    async def ensure_skill_embeddings(self, batch_size: int = 50) -> int:
        """
        Generate embeddings for skills that don't have them yet.
        
        This should be called periodically (e.g., via Celery task) to ensure
        all skills are searchable via semantic similarity.
        
        Returns:
            Number of skills that were updated with new embeddings
        """
        if not self.embedder:
            logger.warning("Embedder not available, cannot generate skill embeddings")
            return 0
        
        updated_count = 0
        
        async with session_scope() as db:
            # Find skills without embeddings
            stmt = select(LearnedSkill).where(
                LearnedSkill.is_active == True,
                LearnedSkill.embedding == None
            ).limit(batch_size)
            
            result = await db.execute(stmt)
            skills_without_embedding = result.scalars().all()
            
            for skill in skills_without_embedding:
                try:
                    # Create embedding from skill metadata
                    embedding_text = self._build_embedding_text(skill)
                    embedding = await self.embedder.embed_query(embedding_text)
                    
                    if embedding:
                        skill.embedding = embedding
                        updated_count += 1
                        logger.debug(f"Generated embedding for skill: {skill.name}")
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for skill {skill.name}: {e}")
            
            if updated_count > 0:
                await db.commit()
                logger.info(f"Generated embeddings for {updated_count} skills")
        
        return updated_count
    
    def _build_embedding_text(self, skill: LearnedSkill) -> str:
        """
        Build the text representation of a skill for embedding generation.
        Combines name, description, and trigger patterns for rich semantic content.
        """
        parts = [skill.name]
        
        if skill.description:
            parts.append(skill.description)
        
        if skill.trigger_patterns:
            try:
                triggers = json.loads(skill.trigger_patterns)
                parts.extend(triggers)
            except Exception:
                parts.append(skill.trigger_patterns)
        
        return " | ".join(parts)


# Singleton instance
skill_retriever = SkillRetriever()

