"""Sample application for editing tests."""

import os
import sys
from typing import Optional, Dict, List


def foo():
    """Old function name."""
    return True


def baz():
    """Another old function."""
    return False


def helper(data: str) -> str:
    """Helper function."""
    if not data:
        return ""
    result = data.strip()
    return result.upper()


class Config:
    """Configuration class."""

    def __init__(self):
        self.debug = True
        self.verbose = False
        self.timeout = 30

    def load(self, path: str) -> Dict:
        """Load configuration from file."""
        return {
            "path": path,
            "debug": self.debug,
            "verbose": self.verbose,
        }

    def validate(self) -> bool:
        """Validate configuration."""
        return self.timeout > 0


def process_items(items: List[str]) -> List[str]:
    """Process a list of items."""
    results = []
    for item in items:
        if item:
            results.append(item.strip())
    return results


def main():
    """Main entry point."""
    config = Config()
    config.load("config.json")

    if config.validate():
        print("Config is valid")
    else:
        print("Config is invalid")

    items = ["  hello  ", "world", "  "]
    processed = process_items(items)
    print(processed)

    foo()
    baz()


if __name__ == "__main__":
    main()
