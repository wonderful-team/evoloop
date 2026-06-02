#!/usr/bin/env python3
"""
Test script for Retry API with new RewindOrchestrator.

Usage:
    python scripts/test_retry_api.py
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:20160/api/v1"
THREAD_ID = "test-rewind-thread-001"


async def test_retry_api():
    """Test retry API endpoint."""
    print("=" * 60)
    print("Testing Retry API")
    print("=" * 60)
    print(f"Thread ID: {THREAD_ID}")
    print()
    
    headers = {"x-guest-id": "test-guest-123"}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # Test 1: Retry without message_id (should use last human message)
        print("Test 1: Retry without message_id")
        url = f"{BASE_URL}/chat/retry"
        payload = {
            "thread_id": THREAD_ID,
            "message": "",  # Required but not used for retry
            "project_id": 1,
            "revert_files": False
        }
        
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                text = await resp.text()
                print(f"\nResponse Status: {resp.status}")
                print(f"Response Body: {text[:500]}")
                
                if resp.status == 200:
                    print("\n✅ Retry request accepted")
                    return True
                else:
                    print(f"\n❌ Failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return False


async def test_retry_with_message_id():
    """Test retry with specific message_id."""
    print("\n" + "=" * 60)
    print("Test 2: Retry with message_id")
    print("=" * 60)
    
    headers = {"x-guest-id": "test-guest-123"}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        url = f"{BASE_URL}/chat/retry"
        # Use message 43 (first human message)
        payload = {
            "thread_id": THREAD_ID,
            "message": "",  # Required but not used for retry
            "project_id": 1,
            "message_id": 43,
            "revert_files": True
        }
        
        print(f"Request: POST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with session.post(url, json=payload, timeout=30) as resp:
                text = await resp.text()
                print(f"\nResponse Status: {resp.status}")
                print(f"Response Body: {text[:500]}")
                
                if resp.status == 200:
                    print("\n✅ Retry with message_id accepted")
                    return True
                else:
                    print(f"\n❌ Failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return False


async def verify_messages_after_retry():
    """Verify message count after retry."""
    print("\n" + "=" * 60)
    print("Verifying Messages After Retry")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/conversations/{THREAD_ID}/messages"
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    count = len(data.get('items', []))
                    print(f"✓ Remaining messages: {count}")
                    for item in data.get('items', []):
                        print(f"  - ID {item['id']}: role={item['role']}")
                    return True
                else:
                    print(f"✗ Failed to get messages: {resp.status}")
                    return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def run_all_tests():
    """Run all retry tests."""
    print("\n" + "=" * 60)
    print("RETRY API TEST SUITE")
    print("=" * 60)
    
    results = []
    results.append(await test_retry_api())
    results.append(await test_retry_with_message_id())
    results.append(await verify_messages_after_retry())
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ ALL RETRY TESTS PASSED!")
        return 0
    else:
        print("\n⚠️ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    try:
        import aiohttp
    except ImportError:
        print("Installing aiohttp...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
        import aiohttp
    
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
