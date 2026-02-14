
import logging
import asyncio
import json
from typing import List

from app.domain.environment.explorers.base import BaseExplorer
from app.core.memory import memory_manager
from app.core.memory.interfaces.long_term import Concept
from app.domain.tools.environment.drivers.adb import adb_driver
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.core.config import settings
from sqlalchemy import select

logger = logging.getLogger(__name__)


class AndroidExplorer(BaseExplorer):
    """
    Android-specific discovery and probing logic.
    """

    async def scout(self, device_id: str) -> dict:
        discovery = {
            "new_apps_found": [],
            "missing_sops": [],
            "verified_concepts": 0
        }

        try:
            # 1. Get live apps
            live_packages = adb_driver.list_installed_apps(device_id=device_id)
            
            # 2. Sync with Brain
            await memory_manager.initialize()
            concepts_text = await memory_manager.long_term.get_project_concepts(0)
            
            known_pkg_map = {}
            for line in concepts_text:
                if "android_package:" in line:
                    try:
                        name_part, pkg_part = line.split(":", 1)
                        name = name_part.replace("android_package:", "").strip()
                        known_pkg_map[pkg_part.strip()] = name
                    except: continue

            for pkg in live_packages:
                if pkg not in known_pkg_map:
                    discovery["new_apps_found"].append(pkg)
                    await memory_manager.long_term.store_concept(Concept(
                        name=f"android_package:Discovered_{pkg.split('.')[-1]}",
                        description=pkg,
                        project_id=0,
                        related_files=[]
                    ))
                else:
                    discovery["verified_concepts"] += 1

            # 3. Intelligent Triage
            potentials = discovery["new_apps_found"][:20]
            llm_apps_data = {}
            if potentials:
                llm_apps_data = await self.identify_high_value_apps(potentials, platform="android")
                logger.info(f"🧠 [AndroidExplorer] LLM identified: {list(llm_apps_data.keys())}")

            # Merge core apps and LLM selected apps
            target_apps = set(settings.AWAKENING_CORE_APPS) | set(llm_apps_data.keys())
            
            missing_core = []
            name_to_pkg = {v: k for k, v in known_pkg_map.items()}
            # Map app names to package IDs
            for name, data in llm_apps_data.items():
                name_to_pkg[name] = data.get("id")

            async with session_scope() as db:
                for app_name in target_apps:
                    pkg_json = json.dumps(app_name).strip('"')
                    stmt = select(LearnedSkill).where(
                        (LearnedSkill.trigger_patterns.contains(app_name)) | 
                        (LearnedSkill.trigger_patterns.contains(pkg_json))
                    )
                    skill = (await db.execute(stmt)).scalars().first()
                    if not skill:
                        discovery["missing_sops"].append(app_name)
                        missing_core.append(app_name)
            
            # 4. Silent Probing
            if missing_core:
                to_probe = [n for n in missing_core if n in name_to_pkg]
                for app_name in to_probe[:2]:
                    pkg = name_to_pkg[app_name]
                    # Check if already probed
                    exists = False
                    for line in concepts_text:
                        if f"android_layout:{pkg}" in line:
                            exists = True
                            break
                    
                    if not exists:
                        # Store reasoning if available before probing
                        reason = llm_apps_data.get(app_name, {}).get("reason", "No reason provided")
                        logger.info(f"🧪 [AndroidExplorer] Probing layout for: {app_name} (Reason: {reason})")
                        await self._probe_app_layout(device_id, app_name, pkg, reason)
                    else:
                        logger.info(f"✅ [AndroidExplorer] Layout already known for {app_name}.")

        except Exception as e:
            logger.error(f"Android scout failed for {device_id}: {e}")
            discovery["error"] = str(e)

        return discovery

    async def _probe_app_layout(self, device_id: str, app_name: str, package_name: str, reason: str = ""):
        # P2: Sensitive Blacklist
        PROBE_BLACKLIST = [
            "com.eg.android.AlipayGphone", # Alipay
            "com.tencent.mm",              # WeChat
            "com.icbc",                    # ICBC
            "com.citiccard.mobilebank",    # CITIC
            "com.android.settings"         # Settings
        ]
        
        if package_name in PROBE_BLACKLIST:
            logger.warning(f"  - [Safety] Skipping automatic probe for sensitive app: {app_name} ({package_name})")
            return

        try:
            logger.info(f"  - Probing {app_name} ({package_name})...")
            adb_driver.launch_app(package_name, device_id=device_id)
            await asyncio.sleep(6)
            
            xml = adb_driver.dump_ui(device_id=device_id)
            summary = f"UI Layout baseline for {app_name}.\n"
            summary += f"Triage Reason: {reason}\n\n"
            summary += f"Detected Elements: {xml.count('<node')} nodes found.\n"
            summary += f"Layout Sample: {xml[:3000]}..."
            
            concept = Concept(
                name=f"android_layout:{app_name} ({package_name})",
                description=summary,
                project_id=0,
                related_files=[]
            )
            await memory_manager.long_term.store_concept(concept)
            
            async with session_scope() as db:
                draft_sop = LearnedSkill(
                    name=f"Draft_{app_name}_SOP",
                    description=f"# DRAFT SOP for {app_name}\n\n*This SOP was automatically generated via Active Discovery probing.*\n\n## Triage Reason\n{reason}\n\n## UI Context\nFound {xml.count('<node')} interactive nodes.\n\n## Guidelines\n1. Use `desktop_control(action='open_app', text='{package_name}')` to start.\n2. Verification required based on latest UI dump.",
                    trigger_patterns=json.dumps([app_name, package_name]),
                    parameters="[]",
                    steps="[]",
                    is_active=True
                )
                db.add(draft_sop)
                logger.info(f"  - Created Draft SOP for {app_name}.")

            adb_driver.press_key("home", device_id=device_id)
        except Exception as e:
            logger.warning(f"Failed to probe app layout for {package_name}: {e}")
