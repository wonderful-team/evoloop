import os

import pathspec


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
            self.spec = pathspec.PathSpec.from_lines('gitwildmatch', content.splitlines())
        except Exception:
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
        except Exception:
            return False

    @classmethod
    def from_file(cls, root_path: str, ignore_file: str = ".gitignore") -> 'GitignoreMatcher':
        """Create matcher from a .gitignore file in the root path."""
        file_path = os.path.join(root_path, ignore_file)
        content = ""
        if os.path.exists(file_path):
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass
        return cls(root_path, content)
