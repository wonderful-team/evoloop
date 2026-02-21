class SkillExecutionInterruptedException(Exception):
    """
    Exception raised when a skill execution fails and requires 
    upstream cognitive reasoning (AgentEngine) to recover.
    """
    def __init__(self, skill_name: str, step_index: int, error_details: str):
        self.skill_name = skill_name
        self.step_index = step_index
        self.error_details = error_details
        super().__init__(f"Skill '{skill_name}' interrupted at step {step_index}: {error_details}")
