
from app.utils.process import CommandResult, run_command


def git_command(args: list[str], cwd: str | None = None) -> CommandResult:
    """Run a git command."""
    # Ensure 'git' is the command. Input args should be the arguments.
    full_cmd = ["git"] + args
    return run_command(full_cmd, cwd=cwd, check=False)

def get_current_branch(cwd: str | None = None) -> str:
    """Get current git branch name."""
    res = git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if res.success:
        return res.stdout.strip()
    return ""

def get_git_root(cwd: str | None = None) -> str:
    """Get the root directory of the git repo."""
    res = git_command(["rev-parse", "--show-toplevel"], cwd=cwd)
    if res.success:
        return res.stdout.strip()
    return ""

def is_git_repo(cwd: str | None = None) -> bool:
    """Check if directory is inside a git repo."""
    res = git_command(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    return res.success and res.stdout.strip() == "true"
