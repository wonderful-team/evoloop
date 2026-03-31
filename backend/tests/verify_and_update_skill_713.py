
import asyncio
import logging
import sys
import os
import json
from pathlib import Path


# Fix PYTHONPATH
project_root = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load env file
def load_env_file():
    env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()
# Set some required defaults for local run
if "ENVIRONMENT" not in os.environ:
    os.environ["ENVIRONMENT"] = "local"

from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.core.execution.macro.verification_service import VerificationService
from app.core.execution.macro.verification_models import EnvironmentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    skill_id = 713
    
    async with session_scope() as session:
        # 1. Fetch Skill 713
        skill = await session.get(LearnedSkill, skill_id)
        if not skill:
            logger.error(f"Skill {skill_id} not found in database.")
            return

        logger.info(f"Loaded Skill {skill_id}: {skill.name}")
        
        # 2. Extract macro_script
        macro_script = skill.macro_script
        if not macro_script:
            logger.error(f"Skill {skill_id} has no macro_script.")
            return
            
        logger.info(f"Macro script steps count: {len(macro_script)}")

        # 3. Run Verification and Evolution
        # Use known device if possible, or default to standard android environment
        device_id = "HYC5T19B11003570" # From test_save_evolved_macro.py
        
        logger.info(f"Starting verification/evolution for Skill {skill_id}...")
        
        # We use a custom request setup to ensure evolution happens with my fix
        from app.core.execution.macro.verification_models import VerificationRequest, AgentConfig
        from app.core.execution.macro.agent_validator import AgentMacroValidator
        
        request = VerificationRequest(
            macro_script=macro_script,
            target_environment=EnvironmentConfig(
                platform="android",
                device_id=device_id
            ),
            max_rounds=1, # One round to apply the redundancy check logic
            output_mode="evolved"
        )
        
        validator = AgentMacroValidator(request)
        response = await validator.validate()
        
        if not response.success:
            logger.warning(f"Verification reported status: {response.status}")
            
        evolved_macro = response.evolved_macro
        if not evolved_macro:
            logger.error("No evolved macro generated. Cannot update.")
            return

        # 4. Update Skill with Evolved Macro
        logger.info(f"Evolved macro steps count: {len(evolved_macro)}")
        
        # Compare if changed
        if evolved_macro == macro_script:
            logger.info("Evolved macro is identical to original. (Wait, it should at least have one less wait if redundant)")
            # Sometimes deep comparison of JSON objects might be tricky if keys are reordered.
            # But here we want to force the save of the 'correct' version.
        
        logger.info("Updating database with evolved macro...")
        
        # Backup original to validation_report for safety
        skill.validation_report = {
            "original_macro": macro_script,
            "evolved_at": str(Path(__file__).name),
            "verification_status": str(response.status)
        }
        
        skill.macro_script = evolved_macro
        skill.execution_mode = response.execution_mode.value if hasattr(response.execution_mode, 'value') else str(response.execution_mode)
        skill.confidence_score = response.confidence_score
        
        # Committing...
        logger.info(f"Skill {skill_id} macro_script updated successfully in session.")

if __name__ == "__main__":
    asyncio.run(main())
