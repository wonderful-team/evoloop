#!/usr/bin/env python3
"""
Test runner for Phase 3 Memory Retrieval improvements.

Usage:
    python tests/run_phase3_tests.py          # Run all Phase 3 tests
    python tests/run_phase3_tests.py -v       # Verbose mode
    python tests/run_phase3_tests.py --unit   # Unit tests only
    python tests/run_phase3_tests.py --int    # Integration tests only
"""

import sys
import subprocess
import argparse


def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description='Run Phase 3 memory tests')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--unit', action='store_true', help='Unit tests only')
    parser.add_argument('--int', action='store_true', help='Integration tests only')
    parser.add_argument('--syntax-only', action='store_true', help='Only check syntax')
    
    args = parser.parse_args()
    
    verbose_flag = ['-v'] if args.verbose else []
    failed = []
    
    # Check syntax first
    if args.syntax_only:
        print("Checking syntax of Phase 3 modules...")
        modules = [
            'app.core.memory.smart_retrieval',
            'app.core.memory.quality',
            'app.core.memory.state_tracking',
        ]
        for module in modules:
            cmd = [sys.executable, '-c', f'import {module}']
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                print(f"  ✓ {module}")
            else:
                print(f"  ✗ {module}")
                print(result.stderr.decode())
                failed.append(module)
        
        return len(failed)
    
    # Unit tests
    if not args.int:
        unit_tests = [
            ('tests/unit/memory/test_smart_retrieval.py', 'Smart Retrieval Unit Tests'),
            ('tests/unit/memory/test_quality.py', 'Quality Analysis Unit Tests'),
            ('tests/unit/memory/test_state_tracking.py', 'State Tracking Unit Tests'),
            ('tests/unit/memory/test_auto_extraction.py', 'Auto Extraction Unit Tests'),
        ]
        
        for test_path, description in unit_tests:
            cmd = [sys.executable, '-m', 'pytest', test_path] + verbose_flag + ['--tb=short']
            returncode = run_command(cmd, description)
            if returncode != 0:
                failed.append(description)
    
    # Integration tests
    if not args.unit:
        int_tests = [
            ('tests/integration/test_memory_tools.py', 'Memory Tools Integration Tests'),
            ('tests/integration/test_smart_retrieval_integration.py', 'Smart Retrieval Integration Tests'),
        ]
        
        for test_path, description in int_tests:
            cmd = [sys.executable, '-m', 'pytest', test_path, '-m', 'integration'] + verbose_flag + ['--tb=short']
            returncode = run_command(cmd, description)
            if returncode != 0:
                failed.append(description)
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    
    if not failed:
        print("✅ All Phase 3 tests passed!")
        return 0
    else:
        print(f"❌ {len(failed)} test suite(s) failed:")
        for f in failed:
            print(f"  - {f}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
