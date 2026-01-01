from typing import Optional, Literal
from langchain_core.runnables import RunnableConfig
from app.core.tools import evoloop_tool

# Imports for delegation
# Imports for delegation
from app.infrastructure.filesystem.tool import grep_files
from app.domain.tools.document_reader import read_document
from app.domain.codebase.retrieval.tools import search_codebase
from app.domain.codebase.analysis.tools import find_definition
from app.domain.tools.git import git_status, git_diff, git_commit, git_history, git_create_branch
from app.domain.tools.memory import save_preference, get_user_preferences, search_concepts, add_concept

@evoloop_tool
def manage_file(
    action: Literal['read', 'create', 'update_block', 'overwrite', 'list', 'create_directory', 'delete', 'move'],
    path: str,
    content: Optional[str] = None,
    target: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    config: Optional[RunnableConfig] = None
) -> str:
    """
    Unified File Management Tool.
    
    Args:
        action: Operation to perform.
        path: Target file path (or source for move).
        content: Content for 'create', 'overwrite', or replacement for 'update_block'. Alternatively, destination path for 'move'.
        target: Target block to replace (for 'update_block').
        start_line/end_line: For 'read' (limit range).
    """
    from app.core.tools import get_working_directory
    from app.utils.file import resolve_path, read_file_content as utils_read_file, write_file_contents as utils_write_file
    import os
    
    # Handle Agent Hallucinations (treating system root dependencies)
    if path.strip() == "/" or path.strip() == "":
        path = "."
        
    root = get_working_directory(config)
    target_path = resolve_path(path, base_path=root)
    
    if not target_path: # Could not resolve
         return f"Error: Could not resolve path: {path}"
         
    # Security Check: Prevent breaking out of working directory
    # If path is absolute (e.g. /), user might be confused. We enforce confinement.
    if not str(target_path).startswith(str(root)):
        # If the user tried using an absolute path that is OUTSIDE root, deny it.
        # But if they passed an absolute path INSIDE root, it's fine.
        
        # NOTE: resolve_path already returns absolute path.
        # If target_path doesn't start with root, it's outside.
        return f"Error: Security Violation. Path '{path}' is outside the working directory '{root}'. Please use relative paths."
         
    # Route by action
    if action == 'read':
        # Smart routing: if it looks like a doc, use read_document logic (still via tool or direct?)
        if path.lower().endswith(('.pdf', '.docx', '.doc')):
            return read_document.invoke({"file_path": path}, config=config)
            
        if not os.path.exists(target_path):
             # Smart Error Handling: Suggest sibling files
             parent_dir = os.path.dirname(target_path)
             if os.path.exists(parent_dir):
                 try:
                     siblings = os.listdir(parent_dir)
                     siblings_str = ", ".join(siblings[:20]) # Limit to 20
                     return f"Error: File '{path}' not found. Did you mean one of these in the same directory? [{siblings_str}]"
                 except:
                     pass
             return f"Error: File not found: {path}"
             
        file_content, _ = utils_read_file(target_path, start_line, end_line)
        return file_content

    elif action in ['create', 'overwrite']:
        if content is None: return f"Error: 'content' required for {action} action."
        try:
            utils_write_file(content, target_path)
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    elif action == 'update_block':
        if not target and not content: return "Error: 'target' and 'content' (replacement) required for update_block."
        
        # Safety Check: Target Uniqueness
        if len(target) < 10 or len(target.splitlines()) < 2:
            return "Error: Target block is too short or ambiguous (must be > 10 chars and > 1 line). Please provide more context(surrounding lines) to ensure unique match."
        
        # Inlining edit_file logic
        if not os.path.exists(target_path):
            return f"Error: File not found: {path}"
            
        with open(target_path, "r", encoding="utf-8") as f:
            file_content = f.read()
            
        count = file_content.count(target)
        if count == 0:
            # Fallback Logic
            pass # Fall through to Fuzzy
        elif count > 1:
            return f"Error: Target snippet found {count} times. Please include more context to make it unique."
        else:
            # Strict Success
            new_content = file_content.replace(target, content)
            utils_write_file(new_content, target_path)
            return f"Successfully updated {path}"

        # 2. Try Fuzzy Fallback
        try:
            from app.domain.tools.utils.fuzzy import apply_fuzzy_patch
            
            success, new_content, log = apply_fuzzy_patch(file_content, target, content)
            if success:
                utils_write_file(new_content, target_path)
                return f"Successfully updated {path}\n(Note: Applied via Fuzzy Match: {log})"
                
            return f"Error: Target snippet not found (Strict). Fuzzy Fallback Failed: {log}"
            
        except Exception as e:
            return f"Error during update: {e}"
        
    elif action == 'list':
        # Inlining list logic
        from app.utils.process import run_command as utils_run_cmd
        if not os.path.exists(target_path):
             return f"Error: Directory does not exist: {path}"
        
        # ls logic
        cmd = ["ls", target_path]
        res = utils_run_cmd(cmd)
        if not res.success:
            return f"Error: {res.stderr}"
        return res.stdout[:2000]
        
    elif action == 'create_directory':
        try:
            os.makedirs(target_path, exist_ok=True)
            return f"Successfully created directory: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"

    elif action == 'delete':
        if not os.path.exists(target_path):
            return f"Error: Path not found: {path}"
        try:
            if os.path.isdir(target_path):
                import shutil
                shutil.rmtree(target_path)
                return f"Successfully deleted directory: {path}"
            else:
                os.remove(target_path)
                return f"Successfully deleted file: {path}"
        except Exception as e:
            return f"Error deleting path: {e}"

    elif action == 'move':
        # content is treated as destination path here
        if not content: return "Error: 'content' (destination path) required for move action."
        
        dest_path = resolve_path(content, base_path=root)
        if not dest_path: return f"Error: Could not resolve destination: {content}"
        
        # Security Check for Destination
        if not str(dest_path).startswith(str(root)):
             return f"Error: Security Violation. Destination '{content}' is outside working directory."

        if not os.path.exists(target_path):
            return f"Error: Source path not found: {path}"
            
        try:
            import shutil
            shutil.move(target_path, dest_path)
            return f"Successfully moved '{path}' to '{content}'"
        except Exception as e:
            return f"Error moving path: {e}"

    return f"Error: Unknown action '{action}'"


@evoloop_tool
async def explore_codebase(
    action: Literal['search_symbol', 'search_text', 'search_concept'],
    query: str,
    scope_path: Optional[str] = None, # Optional file pattern or path
    config: Optional[RunnableConfig] = None
) -> str:
    """
    Unified Codebase Exploration Tool.
    
    Args:
        action:
            - 'search_symbol': Find definition of class/function (AST).
            - 'search_text': Grep for string literal (Regex).
            - 'search_concept': Semantic search for "How does X work?".
        query: The symbol name, regex pattern, or question.
        scope_path: Optional glob pattern or path to limit search.
    """
    if action == 'search_symbol':
        # Delegate to find_definition
        return find_definition.invoke({"symbol_name": query, "file_pattern": scope_path}, config=config)
        
    elif action == 'search_text':
        # Delegate to grep
        # If scope_path is provided, use it as 'path' or 'pattern'? grep tool usually takes 'path' as dir.
        # We might need to handle args mapping carefully.
        # grep_files signature: (pattern, path, extensions, case_sensitive, is_regex)
        args = {"pattern": query, "is_regex": True}
        if scope_path: args["path"] = scope_path
        return grep_files.invoke(args, config=config)
        
    elif action == 'search_concept':
        # Delegate to search_codebase (async)
        # Assuming project_id is handled by context inside search_codebase
        return await search_codebase.ainvoke({"query": query}, config=config)
        
    return f"Error: Unknown action '{action}'"


@evoloop_tool
def manage_git(
    action: Literal['status', 'diff', 'commit', 'log', 'create_branch'],
    argument: Optional[str] = None, # message for commit, branch name, etc.
    config: Optional[RunnableConfig] = None
) -> str:
    """
    Unified Git Operations.
    
    Args:
        action: Git command.
        argument: Contextual argument (commit message, branch name).
    """
    if action == 'status':
        return git_status.invoke({}, config=config)
    elif action == 'diff':
        return git_diff.invoke({}, config=config)
    elif action == 'commit':
        if not argument: return "Error: 'argument' (message) required for commit."
        return git_commit.invoke({"message": argument}, config=config)
    elif action == 'log':
        return git_history.invoke({}, config=config)
    elif action == 'create_branch':
        if not argument: return "Error: 'argument' (branch_name) required."
        return git_create_branch.invoke({"branch_name": argument}, config=config)
        
    return f"Error: Unknown action '{action}'"


@evoloop_tool
async def manage_memory(
    action: Literal['save_preference', 'retrieve_preferences', 'add_concept', 'search_concepts'],
    key: Optional[str] = None, # concept name or pref key
    value: Optional[str] = None, # description or pref value
    config: Optional[RunnableConfig] = None
) -> str:
    """
    Unified Memory Management.
    """
    # Assuming user_id is handled implicitly or 'user_default'
    user_id = "user_default" 
    
    if action == 'save_preference':
        if not key or not value: return "Error: key/value required."
        return await save_preference.ainvoke({"key": key, "value": value}, config=config)
        
    elif action == 'retrieve_preferences':
        return await get_user_preferences.ainvoke({"user_id": user_id}, config=config)
        
    elif action == 'add_concept':
        if not key or not value: return "Error: key (name) and value (description) required."
        return await add_concept.ainvoke({"name": key, "description": value}, config=config)
        
    elif action == 'search_concepts':
        if not key: return "Error: key (query) required."
        return await search_concepts.ainvoke({"query": key}, config=config)

    return f"Error: Unknown action '{action}'"
