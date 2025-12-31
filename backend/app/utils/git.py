from typing import List, Optional
from app.utils.process import run_command, CommandResult

def git_command(args: List[str], cwd: Optional[str] = None) -> CommandResult:
    """Run a git command."""
    # Ensure 'git' is the command. Input args should be the arguments.
    full_cmd = ["git"] + args
    return run_command(full_cmd, cwd=cwd, check=False)

def get_current_branch(cwd: Optional[str] = None) -> str:
    """Get current git branch name."""
    res = git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if res.success:
        return res.stdout.strip()
    return ""

def get_git_root(cwd: Optional[str] = None) -> str:
    """Get the root directory of the git repo."""
    res = git_command(["rev-parse", "--show-toplevel"], cwd=cwd)
    if res.success:
        return res.stdout.strip()
    return ""

def is_git_repo(cwd: Optional[str] = None) -> bool:
    """Check if directory is inside a git repo."""
    res = git_command(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    return res.success and res.stdout.strip() == "true"
