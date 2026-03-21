import os

from langchain_core.runnables import RunnableConfig

from app.i18n.service import i18n
from app.utils.file import (
    apply_edit_with_verification,
    safe_read_with_hash,
    get_file_stats
)

from .utils import resolve_and_validate_path


async def handle_edit(
    path: str,
    target: str | None = None,
    content: str | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """
    Edit file with optional hash verification for concurrent modification detection.

    Args:
        path: File path
        target: Text to find and replace
        content: Replacement text
        allow_multiple: Replace all occurrences
        expected_hash: Expected hash of file before modification (for verification)
        config: RunnableConfig
    """
    if not target and not content:
        return i18n.get("domain_tools.files.edit_args_required")

    # Safety Check: Target Uniqueness
    if len(target.strip()) < 3:
        return i18n.get("domain_tools.files.edit_target_short")

    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return i18n.get("domain_tools.files.edit_not_found", path=path)

    try:
        # Use new verification-based edit
        result = apply_edit_with_verification(
            file_path=target_path,
            old_string=target,
            new_string=content,
            expected_hash=expected_hash,
            allow_multiple=allow_multiple
        )

        if result["success"]:
            replaced = result.get("replaced_count", 1)
            new_hash = result.get("new_hash", "")[:8]
            return (
                f"✅ Successfully edited {path}\n"
                f"   Replaced {replaced} occurrence(s)\n"
                f"   New hash: {new_hash}..."
            )
        else:
            error = result.get("error", "UNKNOWN")
            message = result.get("message", "Edit failed")

            if error == "HASH_MISMATCH":
                return (
                    f"⚠️ {message}\n"
                    f"   Current hash: {result.get('current_hash', 'unknown')[:8]}...\n"
                    f"   Expected: {result.get('expected_hash', 'unknown')[:8]}...\n"
                    f"   Please re-read the file and try again."
                )
            elif error == "STRING_NOT_FOUND":
                # Try fuzzy fallback
                from app.domain.tools.utils.editing.engine import EditEngine

                file_content, _, stats = safe_read_with_hash(target_path)
                success, new_content, log = EditEngine.apply_replacement(
                    file_content, target, content, replace_all=allow_multiple
                )
                if success:
                    # Write with verification
                    from app.utils.file import write_file_with_verification
                    write_result = write_file_with_verification(
                        new_content, target_path, expected_hash=stats.content_hash
                    )
                    if write_result["success"]:
                        return f"✅ Successfully edited {path} (fuzzy match)\n   {log}"
                    else:
                        return f"⚠️ Fuzzy match succeeded but write failed: {write_result.get('message')}"

                return f"❌ {message}\n   Fuzzy match also failed: {log}"
            elif error == "MULTIPLE_OCCURRENCES":
                return (
                    f"⚠️ Found {result.get('count', 'multiple')} occurrences of target text.\n"
                    f"   Set allow_multiple=True to replace all."
                )
            else:
                return f"❌ Edit failed: {message}"

    except Exception as e:
        return i18n.get("domain_tools.files.edit_error", error=str(e))
