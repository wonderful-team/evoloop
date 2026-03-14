#!/usr/bin/env python3
"""
Quick test script for Sidecar Protocol

Usage:
    python scripts/test_sidecar.py [ping|status|file_read|file_write|shell]

Examples:
    python scripts/test_sidecar.py ping
    python scripts/test_sidecar.py file_read --path /tmp/test.txt
    python scripts/test_sidecar.py shell --command "ls -la"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_sidecar_e2e import SidecarTestClient


async def test_ping():
    """Quick ping test."""
    client = SidecarTestClient()

    try:
        print("Starting Client...")
        started = await client.start()

        if not started:
            print("✗ Failed to start Client")
            return False

        print("✓ Client started, sending ping...")

        response = await client.request({
            'type': 'ping',
            'id': 'quick-test'
        })

        print(f"Response: {json.dumps(response, indent=2)}")
        return response.get('pong') == True

    finally:
        await client.stop()


async def test_status():
    """Quick status test."""
    client = SidecarTestClient()

    try:
        await client.start()

        response = await client.request({
            'type': 'status',
            'id': 'status-test'
        })

        print(f"Status: {json.dumps(response, indent=2)}")
        return True

    finally:
        await client.stop()


async def test_file_read(path: str):
    """Test file read."""
    client = SidecarTestClient()

    try:
        await client.start()

        response = await client.request({
            'type': 'execute',
            'id': 'file-read-test',
            'tool': 'file_read',
            'params': {'path': path}
        })

        if response.get('error'):
            print(f"✗ Error: {response['error']}")
            return False

        print(f"Content:\n{response['result']}")
        return True

    finally:
        await client.stop()


async def test_file_write(path: str, content: str):
    """Test file write."""
    client = SidecarTestClient()

    try:
        await client.start()

        response = await client.request({
            'type': 'execute',
            'id': 'file-write-test',
            'tool': 'file_write',
            'params': {'path': path, 'content': content}
        })

        if response.get('error'):
            print(f"✗ Error: {response['error']}")
            return False

        print(f"✓ Written: {json.dumps(response['result'], indent=2)}")
        return True

    finally:
        await client.stop()


async def test_shell(command: str, cwd: str = None):
    """Test shell execution."""
    client = SidecarTestClient()

    try:
        await client.start()

        params = {'command': command}
        if cwd:
            params['cwd'] = cwd

        response = await client.request({
            'type': 'execute',
            'id': 'shell-test',
            'tool': 'shell',
            'params': params
        })

        if response.get('error'):
            print(f"✗ Error: {response['error']}")
            return False

        result = response['result']
        print(f"Exit code: {result.get('exit_code')}")
        print(f"Stdout:\n{result.get('stdout', '')}")
        if result.get('stderr'):
            print(f"Stderr:\n{result.get('stderr', '')}")
        return True

    finally:
        await client.stop()


async def main():
    parser = argparse.ArgumentParser(description='Quick Sidecar tests')
    parser.add_argument('command', choices=['ping', 'status', 'file_read', 'file_write', 'shell'])
    parser.add_argument('--path', help='File path for file operations')
    parser.add_argument('--content', help='Content for file_write')
    parser.add_argument('--command-str', dest='command_str', help='Command string for shell')
    parser.add_argument('--cwd', help='Working directory for shell')

    args = parser.parse_args()

    if args.command == 'ping':
        success = await test_ping()
    elif args.command == 'status':
        success = await test_status()
    elif args.command == 'file_read':
        if not args.path:
            print("Error: --path required")
            return 1
        success = await test_file_read(args.path)
    elif args.command == 'file_write':
        if not args.path or not args.content:
            print("Error: --path and --content required")
            return 1
        success = await test_file_write(args.path, args.content)
    elif args.command == 'shell':
        if not args.command_str:
            print("Error: --command-str required")
            return 1
        success = await test_shell(args.command_str, args.cwd)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
