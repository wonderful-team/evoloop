"""
Apply patch tool for complex structural changes within a single file.

This tool uses a custom patch language for atomic, multi-hunk edits.
Prefer this tool for complex structural changes (multiple related blocks, renames, moves).
"""

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Annotated, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.core.file.editor import EditEngine
from app.core.file import safe_read_with_hash, write_file_with_verification
from app.i18n.service import i18n

from .utils import resolve_and_validate_path

# Keep references to background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


@dataclass
class PatchHunk:
    """Represents a single hunk in a patch."""
    old_lines: List[str]
    new_lines: List[str]


@dataclass
class PatchOperation:
    """Represents a file operation in a patch."""
    operation: str  # 'add', 'delete', 'update'
    path: str
    move_to: Optional[str] = None  # For rename operations
    hunks: Optional[List[PatchHunk]] = None  # For update operations
    content: Optional[str] = None  # For add operations


class PatchParseError(Exception):
    """Raised when patch syntax is invalid."""
    pass


def parse_patch(patch_text: str) -> List[PatchOperation]:
    """
    Parse patch text into a list of PatchOperation objects.
    
    Patch format:
    *** Begin Patch
    [one or more file operations]
    *** End Patch
    
    Operations:
    - *** Add File: <path>
      +<line1>
      +<line2>
    
    - *** Delete File: <path>
    
    - *** Update File: <path>
      @@
      -<old line1>
      -<old line2>
      +<new line1>
      +<new line2>
      @@
      [more hunks...]
    
    - *** Update File: <path>
      *** Move to: <new_path>
    """
    operations = []
    lines = patch_text.split('\n')
    i = 0
    
    # Find patch start
    while i < len(lines) and not lines[i].strip().startswith('*** Begin Patch'):
        i += 1
    
    if i >= len(lines):
        raise PatchParseError("Missing '*** Begin Patch' marker")
    
    i += 1  # Skip Begin Patch line
    
    while i < len(lines):
        line = lines[i].strip()
        
        # End of patch
        if line.startswith('*** End Patch'):
            break
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Add File
        if line.startswith('*** Add File:'):
            path = line[len('*** Add File:'):].strip()
            i += 1
            content_lines = []
            while i < len(lines) and not lines[i].strip().startswith('***'):
                if lines[i].startswith('+'):
                    content_lines.append(lines[i][1:])  # Remove + prefix
                elif lines[i].strip():
                    raise PatchParseError(f"Add File content must start with '+': {lines[i]}")
                i += 1
            operations.append(PatchOperation(
                operation='add',
                path=path,
                content='\n'.join(content_lines)
            ))
        
        # Delete File
        elif line.startswith('*** Delete File:'):
            path = line[len('*** Delete File:'):].strip()
            operations.append(PatchOperation(
                operation='delete',
                path=path
            ))
            i += 1
        
        # Update File
        elif line.startswith('*** Update File:'):
            path = line[len('*** Update File:'):].strip()
            i += 1
            
            # Check for move operation
            if i < len(lines) and lines[i].strip().startswith('*** Move to:'):
                new_path = lines[i].strip()[len('*** Move to:'):].strip()
                operations.append(PatchOperation(
                    operation='update',
                    path=path,
                    move_to=new_path
                ))
                i += 1
                continue
            
            # Parse hunks
            hunks = []
            while i < len(lines) and not lines[i].strip().startswith('***'):
                if lines[i].strip() == '@@':
                    i += 1
                    old_lines = []
                    new_lines = []
                    
                    while i < len(lines) and lines[i].strip() != '@@' and not lines[i].strip().startswith('***'):
                        if lines[i].startswith('-'):
                            old_lines.append(lines[i][1:])  # Remove - prefix
                        elif lines[i].startswith('+'):
                            new_lines.append(lines[i][1:])  # Remove + prefix
                        elif lines[i].strip():
                            # Context line - add to both old and new to preserve it
                            context = lines[i]
                            old_lines.append(context)
                            new_lines.append(context)
                        i += 1
                    
                    if not old_lines and not new_lines:
                        raise PatchParseError("Empty hunk found")
                    
                    hunks.append(PatchHunk(old_lines=old_lines, new_lines=new_lines))
                elif lines[i].strip():
                    raise PatchParseError(f"Expected '@@' to start hunk, got: {lines[i]}")
                else:
                    i += 1
            
            if hunks:
                operations.append(PatchOperation(
                    operation='update',
                    path=path,
                    hunks=hunks
                ))
            else:
                raise PatchParseError(f"Update File '{path}' has no hunks")
        
        else:
            raise PatchParseError(f"Unknown directive: {line}")
    
    if not operations:
        raise PatchParseError("No operations found in patch")
    
    return operations


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=[],
    summary_template="database_logger.tool_summary.apply_patch_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "应用补丁", "en": "Apply Patch File"}
)
async def apply_patch_file(
    patch_text: str | None = None,
    expected_hash: str | None = None,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Apply a patch to perform complex structural changes to files atomically.
    
    This is the PREFERRED tool for complex refactoring within a single file,
    especially when you need to modify multiple related blocks, rename items,
    or restructure code. It provides atomic all-or-nothing guarantees.

    Your patch language is a stripped-down, file-oriented diff format designed
    to be easy to parse and safe to apply. You can think of it as a high-level
    envelope:

    *** Begin Patch
    [one or more file operations]
    *** End Patch

    Within that envelope, you get a sequence of file operations.
    You MUST include a header to specify the action you are taking.
    Each operation starts with one of three headers:

    *** Add File: <path> - create a new file. Every following line is a + line.
    *** Delete File: <path> - remove an existing file.
    *** Update File: <path> - patch an existing file in place (optionally with rename).

    For Update operations, use hunks to specify changes:

    @@
    -old line 1
    -old line 2
    +new line 1
    +new line 2
    @@
    -another old block
    +another new block

    Example patch:
    ```
    *** Begin Patch
    *** Add File: hello.txt
    +Hello world
    *** Update File: src/app.py
    @@
    -def old_func():
    -    pass
    +def new_func():
    +    return True
    @@
    -x = 1
    +x = 2
    *** Delete File: obsolete.txt
    *** End Patch
    ```

    CRITICAL REQUIREMENTS:
    1. The patch is ATOMIC - either all operations succeed, or none are applied
    2. All hunks must match exactly (cascading fuzzy matching is used)
    3. You can include multiple Update operations in one patch
    4. All paths should be absolute

    When to use:
    - Use this for complex multi-block changes within a single file
    - Use this when you need atomic guarantees (all-or-nothing)
    - For simple single-block changes, use edit_file or multiedit_file instead
    - For creating new files, use write_file instead

    Args:
        patch_text: The complete patch text including Begin/End markers. **REQUIRED**
        expected_hash: Optional hash for first file (for concurrent modification detection)
        verify_types: If True (default), perform type check after updates

    Examples:
        # Refactor multiple functions
        apply_patch_file(patch_text="*** Begin Patch\\n*** Update File: src/app.py\\n@@\\n-def helper():\\n-    return 1\\n+def _helper():\\n+    return 42\\n*** End Patch")
    """
    from app.utils import render_template
    from app.domain.codebase.exploration.engine import get_exploration_engine

    # Validation
    if not patch_text:
        return (
            "SYSTEM ERROR: You called 'apply_patch_file' with EMPTY patch_text. "
            "You MUST provide the complete patch text.\n"
            "CORRECT USAGE: apply_patch_file(patch_text='*** Begin Patch...*** End Patch')"
        )

    try:
        operations = parse_patch(patch_text)
    except PatchParseError as e:
        return f"❌ Patch parse error: {str(e)}\nPlease check your patch syntax."

    # Phase 1: Validate and collect all operations
    validated_operations = []
    
    for i, op in enumerate(operations):
        try:
            if op.operation == 'add':
                # For add, just validate path
                target_path = await resolve_and_validate_path(op.path, config)
                if os.path.exists(target_path):
                    return f"❌ Operation #{i+1}: File already exists: {op.path}"
                validated_operations.append(('add', target_path, op.content, op.path))
                
            elif op.operation == 'delete':
                target_path = await resolve_and_validate_path(op.path, config)
                if not os.path.exists(target_path):
                    return f"❌ Operation #{i+1}: File not found: {op.path}"
                validated_operations.append(('delete', target_path, None, op.path))
                
            elif op.operation == 'update':
                target_path = await resolve_and_validate_path(op.path, config)
                if not os.path.exists(target_path):
                    return f"❌ Operation #{i+1}: File not found: {op.path}"
                
                # Read current content
                file_content, _, stats = safe_read_with_hash(target_path)
                
                # Hash check for first operation only (optimization)
                if i == 0 and expected_hash and stats.content_hash != expected_hash:
                    return render_template(
                        "files/edit_result.prompt.j2",
                        success=False,
                        path=op.path,
                        message="File was modified by another process since last read.",
                        details=(
                            f"Current hash: {stats.content_hash[:8]}...\n"
                            f"Expected: {expected_hash[:8]}...\n"
                            f"Please re-read the file and try again."
                        ),
                        labels=i18n.get("domain_tools.files.edit_labels") or {}
                    )
                
                if op.move_to:
                    # Rename operation
                    new_path = await resolve_and_validate_path(op.move_to, config)
                    validated_operations.append(('rename', target_path, new_path, op.path))
                else:
                    # Update with hunks
                    current_content = file_content
                    
                    for j, hunk in enumerate(op.hunks):
                        old_block = '\n'.join(hunk.old_lines)
                        new_block = '\n'.join(hunk.new_lines)
                        
                        # Handle pure insertion (empty old_block)
                        if not old_block:
                            # Insert new content at the end of current_content
                            # or use context-aware insertion if we have previous hunks
                            if current_content and not current_content.endswith('\n'):
                                current_content += '\n'
                            current_content += new_block
                            continue
                        
                        success, new_content, log = EditEngine.apply_replacement(
                            current_content,
                            old_block,
                            new_block,
                            replace_all=False
                        )
                        
                        if not success:
                            return (
                                f"❌ Operation #{i+1} (Update File '{op.path}'), "
                                f"Hunk #{j+1} failed validation. No changes applied.\n"
                                f"   Target block: {old_block[:50]}{'...' if len(old_block) > 50 else ''}\n"
                                f"   Error: {log}\n"
                                f"   (All previous operations were not applied due to atomicity)"
                            )
                        
                        current_content = new_content
                    
                    validated_operations.append(('update', target_path, current_content, op.path))
                    
        except ValueError as e:
            return f"❌ Operation #{i+1}: Path error: {str(e)}"

    # Phase 2: Atomic application with rollback capability
    results = []
    updated_files_for_type_check = []  # Track files for async type checking
    rollback_log = []  # Track operations for rollback on failure
    
    try:
        for op_type, target_path, content_or_new_path, original_path in validated_operations:
            if op_type == 'add':
                # Check if file already exists (shouldn't happen due to validation)
                if os.path.exists(target_path):
                    raise RuntimeError(f"File already exists: {original_path}")
                
                # Create directory if needed
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content_or_new_path)
                
                rollback_log.append(('delete', target_path, None, original_path))
                results.append(f"Added: {original_path}")
                
            elif op_type == 'delete':
                # Backup file content for rollback
                with open(target_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                
                os.remove(target_path)
                
                rollback_log.append(('add_back', target_path, backup_content, original_path))
                results.append(f"Deleted: {original_path}")
                
            elif op_type == 'rename':
                new_path = content_or_new_path
                
                # Create directory if needed
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                os.rename(target_path, new_path)
                
                rollback_log.append(('rename_back', new_path, target_path, original_path))
                results.append(f"Renamed: {original_path} -> {new_path}")
                
                if verify_types:
                    updated_files_for_type_check.append((original_path, new_path))
                
            elif op_type == 'update':
                # Backup original content
                with open(target_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                
                write_result = write_file_with_verification(
                    content_or_new_path,
                    target_path,
                    expected_hash=None  # Already verified in phase 1
                )
                if not write_result["success"]:
                    raise RuntimeError(f"Write failed for {original_path}: {write_result.get('message')}")
                
                rollback_log.append(('restore', target_path, backup_content, original_path))
                results.append(f"Updated: {original_path}")
                
                # Collect files for async type checking
                if verify_types:
                    updated_files_for_type_check.append((original_path, target_path))
    
    except Exception as e:
        # Rollback all completed operations in reverse order
        rollback_errors = []
        for rb_op_type, rb_path, rb_content, rb_original in reversed(rollback_log):
            try:
                if rb_op_type == 'delete':
                    if os.path.exists(rb_path):
                        os.remove(rb_path)
                elif rb_op_type == 'add_back':
                    os.makedirs(os.path.dirname(rb_path), exist_ok=True)
                    with open(rb_path, 'w', encoding='utf-8') as f:
                        f.write(rb_content)
                elif rb_op_type == 'rename_back':
                    os.rename(rb_path, rb_content)  # content is old_path here
                elif rb_op_type == 'restore':
                    with open(rb_path, 'w', encoding='utf-8') as f:
                        f.write(rb_content)
            except Exception as rb_e:
                rollback_errors.append(f"{rb_original}: {str(rb_e)}")
        
        error_msg = f"❌ Patch application failed: {str(e)}\nAll changes have been rolled back."
        if rollback_errors:
            error_msg += f"\n⚠️ Rollback errors occurred: {', '.join(rollback_errors)}"
        return error_msg

    # Async type checking for all updated files
    if verify_types and updated_files_for_type_check:
        async def _async_type_check_files(files_to_check):
            try:
                engine = get_exploration_engine()
                repo_path = get_working_directory(config)
                
                for original_path, target_path in files_to_check:
                    try:
                        diagnostics = await engine.check_types(target_path, repo_path)
                        if diagnostics:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.info(f"[Async Type Check] {original_path}: {len(diagnostics)} diagnostic(s)")
                            for d in diagnostics[:3]:
                                logger.info(f"  - {d.get('severity', 'info')}: {d.get('message', '')[:50]}")
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).debug(f"[Async Type Check] {original_path} failed: {e}")
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"[Async Type Check] Failed: {e}")
        
        # Fire and forget - keep reference to prevent GC
        task = asyncio.create_task(_async_type_check_files(updated_files_for_type_check))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    # Build success response
    result_summary = "\n".join([f"  - {r}" for r in results])
    
    response = f"✅ Successfully applied patch with {len(results)} operation(s):\n{result_summary}"
    
    if verify_types and updated_files_for_type_check:
        response += "\n\nℹ️ Type check running in background for updated files..."
    
    return response
