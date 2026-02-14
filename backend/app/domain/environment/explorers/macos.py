
import logging
import json
from typing import List

from app.domain.environment.explorers.base import BaseExplorer
from app.domain.environment.models import MacOSEnvironment
from app.core.memory import memory_manager
from app.core.memory.interfaces.long_term import Concept
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from sqlalchemy import select

logger = logging.getLogger(__name__)


class MacOSExplorer(BaseExplorer):
    """
    MacOS-specific discovery logic.
    """

    async def scout(self, macos: MacOSEnvironment) -> dict:
        discovery = {
            "new_apps_found": [],
            "missing_sops": [],
            "verified_concepts": 0
        }

        try:
            await memory_manager.initialize()
            concepts_text = await memory_manager.long_term.get_project_concepts(0)
            
            known_apps = set()
            for line in concepts_text:
                if "macos_app:" in line:
                    try:
                        name = line.split("macos_app:", 1)[1].split(":", 1)[0].strip()
                        known_apps.add(name)
                    except: continue

            for app in macos.installed_apps:
                app_name = app.replace(".app", "")
                if app_name not in known_apps:
                    discovery["new_apps_found"].append(app_name)
                    await memory_manager.long_term.store_concept(Concept(
                        name=f"macos_app:{app_name}",
                        description=f"MacOS Application: {app}",
                        project_id=0,
                        related_files=[]
                    ))
                else:
                    discovery["verified_concepts"] += 1

            potentials = discovery["new_apps_found"][:20]
            if potentials:
                llm_apps_data = await self.identify_high_value_apps(potentials, platform="macos")
                logger.info(f"🧠 [MacOSExplorer] LLM identified: {list(llm_apps_data.keys())}")

                async with session_scope() as db:
                    for app_display_name, data in llm_apps_data.items():
                        identifier = data.get("id")
                        reason = data.get("reason", "No reason provided")
                        
                        stmt = select(LearnedSkill).where(LearnedSkill.name == f"Draft_{app_display_name}_SOP")
                        existing = (await db.execute(stmt)).scalars().first()
                        
                        if not existing:
                            logger.info(f"🧪 [MacOSExplorer] Creating Draft SOP for: {app_display_name} (Reason: {reason})")
                            draft_sop = LearnedSkill(
                                name=f"Draft_{app_display_name}_SOP",
                                description=f"# DRAFT SOP for {app_display_name}\n\n*This SOP was automatically generated via MacOS Active Discovery.*\n\n## Triage Reason\n{reason}\n\n## Guidelines\n1. Use `keyboard_shortcut('command', 'space')` and type '{app_display_name}' to launch.\n2. Verification required based on screen content.",
                                trigger_patterns=json.dumps([app_display_name, identifier]),
                                parameters="[]",
                                steps="[]",
                                is_active=True
                            )
                            db.add(draft_sop)
                            discovery["missing_sops"].append(app_display_name)

        except Exception as e:
            logger.error(f"MacOS scout failed: {e}")
            discovery["error"] = str(e)

        return discovery
