#!/usr/bin/env python3
"""
Test runner script with options for different test types.

Usage:
    python tests/run_tests.py              # Run all tests
    python tests/run_tests.py --unit       # Run only unit tests
    python tests/run_tests.py --integration # Run integration tests
    python tests/run_tests.py --coverage   # Run with coverage report
    python tests/run_tests.py --parallel   # Run tests in parallel
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list, description: str) -> int:
    """Run a command and return exit code."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('=' * 60 + "\n")

    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run EvoLoop tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--e2e", action="store_true", help="Run e2e tests only")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--tb", default="short", help="Traceback style")
    parser.add_argument("--test-dir", default="tests", help="Test directory")

    args = parser.parse_args()

    # Build pytest command
    cmd = ["pytest"]

    # Add verbosity
    if args.verbose:
        cmd.append("-v")

    # Add traceback style
    cmd.extend(["--tb", args.tb])

    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml"
        ])

    # Add parallel execution if requested
    if args.parallel:
        cmd.extend(["-n", "auto", "--dist=loadfile"])

    # Determine which tests to run
    if args.unit:
        cmd.append(f"{args.test_dir}/unit")
    elif args.integration:
        cmd.extend(["-m", "integration", args.test_dir])
    elif args.e2e:
        cmd.extend(["-m", "e2e", args.test_dir])
    else:
        # Run all tests by default
        cmd.append(args.test_dir)

    # Add markers to exclude slow tests by default (unless explicitly included)
    if not args.integration and not args.e2e:
        cmd.extend(["-m", "not slow"])

    # Run the tests
    exit_code = run_command(cmd, "EvoLoop Test Suite")

    if args.coverage and exit_code == 0:
        print("\n" + "=" * 60)
        print("Coverage report generated in: htmlcov/index.html")
        print("=" * 60)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
