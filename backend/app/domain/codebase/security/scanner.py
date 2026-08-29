"""General-purpose AST/text-based security scanner.

The scanner uses deterministic regex/keyword heuristics so it works offline,
requires no LLM, and stays fast. It deliberately avoids common safe patterns
(parameterized queries, hardcoded examples, list arguments to subprocess, etc.)
to keep false positives low.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityFindingCreate:
    finding_type: str
    severity: str
    description: str
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str | None = None


class SecurityScanner:
    """Regex/keyword security scanner for any language."""

    SEVERITIES: ClassVar[dict[str, str]] = {
        "sql_injection": "high",
        "path_traversal": "high",
        "command_injection": "critical",
        "hardcoded_secret": "high",
        "ssrf": "medium",
    }

    # SQL injection: string concatenation/formatting inside execute/query calls.
    # Avoids parameterized placeholders like ? or %s used alone, and ORM/Session.query.
    # SQL injection: string concatenation/formatting inside execute/query calls.
    # Avoids parameterized placeholders like ? or %s used alone, and ORM/Session.query.
    SQL_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"""(execute|query|cursor|exec|sql)\s*\([^)]*?(?:\+\s*[a-zA-Z_]|%\s*[a-zA-Z_]|%\s*\(|f["']|['\"]\s*\+\s*[a-zA-Z_])""",
            re.IGNORECASE,
        ),
        re.compile(
            r"""(SELECT|INSERT|UPDATE|DELETE)\s+[^\"']*?(?:\+\s*[a-zA-Z_]|%\s*[a-zA-Z_]|%\s*\(|f["']|['\"]\s*\+\s*[a-zA-Z_])""",
            re.IGNORECASE,
        ),
    ]

    # Path traversal: user-controlled paths opened/joined without sanitization.
    PATH_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"""(open|file|readFile|writeFile|createReadStream|os\.path\.join|Path\(\))\s*\([^)]*?(?:\+\s*[a-zA-Z_]|%\s*[a-zA-Z_]|%\s*\(|f["']|['\"]\s*\+\s*[a-zA-Z_])""",
            re.IGNORECASE,
        ),
    ]

    # Command injection: shell execution with string concatenation/formatting.
    CMD_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"""(os\.system|subprocess\.run|subprocess\.call|subprocess\.Popen|exec|eval)\s*\([^)]*?(?:\+\s*[a-zA-Z_]|%\s*[a-zA-Z_]|%\s*\(|f["']|['\"]\s*\+\s*[a-zA-Z_])""",
            re.IGNORECASE,
        ),
        re.compile(
            r"""(subprocess\.run|subprocess\.call|subprocess\.Popen)\s*\([^)]*shell\s*=\s*True""",
            re.IGNORECASE,
        ),
    ]

    # SSRF: network requests with user-controlled URLs.
    SSRF_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"""(requests\.(get|post|put|delete|patch)|httpx\.(get|post|put|delete|patch)|urlopen|fetch)\s*\(\s*[a-zA-Z_][a-zA-Z0-9_]*""",
            re.IGNORECASE,
        ),
    ]

    # Hardcoded secrets: common secret-like variable names with non-trivial values.
    SECRET_KEY_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key|password|passwd|pwd)\s*[:=]\s*[\"']([^\"']{8,})[\"']"
    )
    # Ignore obvious placeholder/example values.
    SECRET_IGNORE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?i)(example|sample|placeholder|test|dummy|your_|xxx+|password123|123456|secret|token|key)"
    )

    # Safe patterns that should suppress a finding in the same line.
    SAFE_HINTS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r"(?i)\?\s*%s|\bparams\s*=\s*\{|\bparams\s*=\s*\[|bind_param|sqlalchemy|session\.query|prisma\.|orm\."
        ),
        re.compile(r"(?i)\bshell\s*=\s*False|\bargs\s*=\s*\["),
        re.compile(
            r"(?i)__file__|\.json|\.txt|\.md|\.csv|\.yaml|\.yml|\.xml|config|settings|env|fixture"
        ),
    ]

    def __init__(self) -> None:
        self._compiled: dict[str, list[re.Pattern[str]]] = {
            "sql_injection": self.SQL_PATTERNS,
            "path_traversal": self.PATH_PATTERNS,
            "command_injection": self.CMD_PATTERNS,
            "ssrf": self.SSRF_PATTERNS,
        }

    def _is_safe_line(self, line: str) -> bool:
        return any(hint.search(line) for hint in self.SAFE_HINTS)

    def _extract_snippet(self, lines: list[str], line_idx: int) -> str:
        start = max(0, line_idx - 1)
        end = min(len(lines), line_idx + 4)
        return "\n".join(lines[start:end])

    def _match_finding(
        self,
        finding_type: str,
        line: str,
        line_idx: int,
        lines: list[str],
    ) -> SecurityFindingCreate | None:
        if self._is_safe_line(line):
            return None
        return SecurityFindingCreate(
            finding_type=finding_type,
            severity=self.SEVERITIES[finding_type],
            description=f"Potential {finding_type.replace('_', ' ')} detected.",
            line_start=line_idx + 1,
            line_end=line_idx + 1,
            code_snippet=self._extract_snippet(lines, line_idx),
        )

    def scan(self, file_path: str, content: str) -> list[SecurityFindingCreate]:
        """Scan file content and return a list of findings."""
        findings: list[SecurityFindingCreate] = []
        lines = content.splitlines()

        for line_idx, line in enumerate(lines):
            for finding_type, patterns in self._compiled.items():
                for pattern in patterns:
                    if pattern.search(line):
                        finding = self._match_finding(
                            finding_type, line, line_idx, lines
                        )
                        if finding:
                            findings.append(finding)
                            break

        for line_idx, line in enumerate(lines):
            match = self.SECRET_KEY_RE.search(line)
            if not match:
                continue
            value = match.group(2)
            if self.SECRET_IGNORE_RE.search(value):
                continue
            findings.append(
                SecurityFindingCreate(
                    finding_type="hardcoded_secret",
                    severity=self.SEVERITIES["hardcoded_secret"],
                    description="Hardcoded secret or token-like value detected.",
                    line_start=line_idx + 1,
                    line_end=line_idx + 1,
                    code_snippet=self._extract_snippet(lines, line_idx),
                )
            )

        return findings


def scan_file(file_path: str, content: str) -> list[SecurityFindingCreate]:
    """Convenience entry point matching the design-doc signature."""
    return SecurityScanner().scan(file_path, content)
