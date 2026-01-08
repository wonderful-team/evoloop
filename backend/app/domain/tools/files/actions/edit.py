from typing import Optional
import os
from langchain_core.runnables import RunnableConfig
from app.utils.file import  write_file_contents as utils_write_file
from .utils import resolve_and_validate_path

async def handle_edit(path: str, target: Optional[str] = None, content: Optional[str] = None, config: Optional[RunnableConfig] = None) -> str:
    if not target and not content: return "Error: 'target' and 'content' (replacement) required for update_block."
    
    # Safety Check: Target Uniqueness
    if len(target) < 10 or len(target.splitlines()) < 2:
        return "Error: Target block is too short or ambiguous (must be > 10 chars and > 1 line). Please provide more context(surrounding lines) to ensure unique match."
    
    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return f"Error: File not found: {path}"
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            file_content = f.read()
            
        count = file_content.count(target)
        if count == 0:
            # Fall through to Fuzzy
            pass 
        elif count > 1:
            return f"Error: Target snippet found {count} times. Please include more context to make it unique."
        else:
            # Strict Success
            new_content = file_content.replace(target, content)
            utils_write_file(new_content, target_path)
            return f"Successfully updated {path}"

        # 2. Try Fuzzy Fallback
        from app.domain.tools.utils.fuzzy import apply_fuzzy_patch
        
        success, new_content, log = apply_fuzzy_patch(file_content, target, content)
        if success:
            utils_write_file(new_content, target_path)
            return f"Successfully updated {path}\n(Note: Applied via Fuzzy Match: {log})"
            
        return f"Error: Target snippet not found (Strict). Fuzzy Fallback Failed: {log}"
        
    except Exception as e:
        return f"Error during update: {e}"
