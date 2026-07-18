import os

import pathspec

from app.core.file import FileStatus, read_file


class GitignoreMatcher:
    """
    A gitignore matcher that uses the 'pathspec' library for robust pattern matching.
    """

    def __init__(self, root_path: str, content: str = ""):
        self.root_path = root_path
        self.spec = None
        if content:
            self.parse(content)

    def parse(self, content: str):
        """Parse gitignore content into a PathSpec."""
        try:
            self.spec = pathspec.PathSpec.from_lines("gitwildmatch", content.splitlines())
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            # Fallback or log? For now just silent fail or empty spec
            pass

    def should_ignore(self, abs_path: str, is_dir: bool = False) -> bool:
        """
        Check if the path should be ignored.
        Returns True if ignored, False otherwise.
        """
        if not self.spec:
            return False

        rel_path = os.path.relpath(abs_path, self.root_path)
        if rel_path == ".":
            return False

        # PathSpec expects paths relative to the root (where .gitignore is)
        # It handles OS separators, but usually prefers forward slash internally or handles it.
        # pathspec check_match / match_file logic:
        # returns True if included? No, check_match returns True if it matches the pattern.
        # If it matches a gitignore pattern, it is IGNORED.

        # However, pathspec checks against file names?
        # We should append '/' if it's a directory?
        # pathspec 'gitwildmatch' handles directory detection if path ends with separator?

        check_path = rel_path
        if is_dir and not check_path.endswith(os.sep):
            check_path += os.sep

        try:
            return self.spec.match_file(check_path)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            return False

    @classmethod
    def from_file(cls, root_path: str, ignore_file: str = ".gitignore") -> "GitignoreMatcher":
        """Create matcher from a .gitignore file in the root path."""
        file_path = os.path.join(root_path, ignore_file)
        content = ""
        result = read_file(file_path)
        if result.status == FileStatus.SUCCESS:
            content = result.content
        return cls(root_path, content)


class NestedGitignoreMatcher:
    """
    A gitignore matcher that supports nested .gitignore files.

    Lazily loads and caches .gitignore matchers per directory,
    then checks from the repo root down to the file's directory
    — matching git's actual behavior.
    """

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._matcher_cache: dict[str, GitignoreMatcher | None] = {}

    def _get_matcher(self, dir_path: str) -> GitignoreMatcher | None:
        """Lazy-load and cache the .gitignore matcher for a directory."""
        if dir_path not in self._matcher_cache:
            gitignore_path = os.path.join(dir_path, ".gitignore")
            if os.path.isfile(gitignore_path):
                self._matcher_cache[dir_path] = GitignoreMatcher.from_file(dir_path, ".gitignore")
            else:
                self._matcher_cache[dir_path] = None
        return self._matcher_cache[dir_path]

    def should_ignore(self, abs_path: str, is_dir: bool = False) -> bool:
        """
        Check if the path should be ignored by any .gitignore from root to leaf.
        Returns True if ignored, False otherwise.
        """
        rel_path = os.path.relpath(abs_path, self.repo_path)
        if rel_path == ".":
            return False

        parts = rel_path.split(os.sep)
        # Walk from repo root down to the file's parent directory
        # (for directories, include the directory itself)
        max_depth = len(parts) if is_dir else len(parts) - 1
        for i in range(max_depth + 1):
            dir_path = os.path.join(self.repo_path, *parts[:i]) if i > 0 else self.repo_path
            matcher = self._get_matcher(dir_path)
            if matcher and matcher.should_ignore(abs_path, is_dir=is_dir):
                return True

        return False
