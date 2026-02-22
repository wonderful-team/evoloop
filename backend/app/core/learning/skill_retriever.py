
# SkillRetriever and skill_retriever are DEPRECATED.
# Use SkillDiscovery and skill_discovery from app.core.learning.discovery instead.

import logging

from app.core.learning.discovery import skill_discovery

logger = logging.getLogger(__name__)

# Drop-in compatibility singleton
skill_retriever = skill_discovery
SkillRetriever = skill_discovery.__class__
