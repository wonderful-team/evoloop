from typing import Optional
import os
from langchain_core.runnables import RunnableConfig
from app.utils.file import  write_file_contents as utils_write_file
from .utils import resolve_and_validate_path

async def handle_edit(path: str, target: Optional[str] = None, content: Optional[str] = None, allow_multiple: bool = False, config: Optional[RunnableConfig] = None) -> str:
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
        elif count > 1 and not allow_multiple:
            return f"Error: Target snippet found {count} times. Please include more context to make it unique."
        else:
            # Strict Success
            if allow_multiple:
                new_content = file_content.replace(target, content)
            else:
                new_content = file_content.replace(target, content, 1)
                
            utils_write_file(new_content, target_path)
            return f"Successfully updated {path}"

        # 2. Try Fuzzy Fallback (Robust Edit Engine)
        from app.domain.tools.utils.editing.engine import EditEngine
        
        success, new_content, log = EditEngine.apply_replacement(file_content, target, content, replace_all=allow_multiple)
        if success:
            utils_write_file(new_content, target_path)
            return f"Successfully updated {path}\n(Note: {log})"
            
        return f"Error: Target snippet not found (Strict). Robust Fallback Failed: {log}"
        
    except Exception as e:
        return f"Error during update: {e}"
