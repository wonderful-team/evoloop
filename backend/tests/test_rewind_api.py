#!/usr/bin/env python3
"""
API Test Script for Rewind System

Tests the rewind API endpoint with real HTTP requests.

Usage:
    # Start the server first
    ./bin/evo dev
    
    # Then run this script
    python scripts/test_rewind_api.py
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

# Configuration
BASE_URL = "http://127.0.0.1:20160/api/v1"
THREAD_ID = "test-rewind-thread-001"

# Test message IDs (from setup script)
MSG_1 = 43  # First human message
MSG_3 = 45  # Second human message
MSG_5 = 47  # Third human message


async def test_health():
    """Test server health."""
    print("=" * 60)
    print("Test 1: Server Health Check")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/healthz", timeout=5) as resp:
                if resp.status == 200:
                    print(f"✓ Server is healthy: {resp.status}")
                    return True
                else:
                    print(f"✗ Server returned: {resp.status}")
                    return False
        except Exception as e:
            print(f"✗ Cannot connect to server: {e}")
            print("\nPlease start the server first:")
            print("  ./bin/evo dev")
            return False


async def test_get_messages():
    """Test getting conversation messages."""
    print("\n" + "=" * 60)
    print("Test 2: Get Conversation Messages")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/conversations/{THREAD_ID}/messages"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ Got messages: {len(data.get('items', []))} items")
                    for item in data.get('items', []):
                        print(f"  - ID {item['id']}: role={item['role']}")
                    return True
                else:
                    text = await resp.text()
                    print(f"✗ Failed: {resp.status} - {text[:200]}")
                    return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def test_rewind_to_message():
    """Test rewind API."""
    print("\n" + "=" * 60)
    print("Test 3: Rewind API")
    print("=" * 60)
    print(f"\nThread ID: {THREAD_ID}")
    print(f"Target Message ID: {MSG_3}")
    print("This should delete messages 46, 47, 48 and revert file operations\n")
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/conversations/{THREAD_ID}/rewind"
            payload = {
                "message_id": str(MSG_3),
                "revert_files": True
            }
            
            print(f"Request: POST {url}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            async with session.post(
                url, 
                json=payload,
                timeout=30
            ) as resp:
                text = await resp.text()
                print(f"\nResponse Status: {resp.status}")
                print(f"Response Body: {text[:500]}")
                
                if resp.status == 200:
                    data = json.loads(text)
                    print(f"\n✓ Rewind successful!")
                    print(f"  Status: {data.get('status')}")
                    print(f"  Removed: {data.get('removed_count')} messages")
                    print(f"  Files reverted: {data.get('files_reverted')}")
                    return True
                elif resp.status == 404:
                    print(f"\n⚠️ Thread or message not found")
                    return False
                else:
                    print(f"\n✗ Failed: {resp.status}")
                    return False
                    
        except asyncio.TimeoutError:
            print(f"✗ Request timeout")
            return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def test_rewind_no_target():
    """Test rewind to last human message."""
    print("\n" + "=" * 60)
    print("Test 4: Rewind to Last Human Message")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/conversations/{THREAD_ID}/rewind"
            payload = {
                "revert_files": True
            }
            
            print(f"Request: POST {url}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            
            async with session.post(
                url, 
                json=payload,
                timeout=30
            ) as resp:
                text = await resp.text()
                print(f"\nResponse Status: {resp.status}")
                
                if resp.status == 200:
                    data = json.loads(text)
                    print(f"\n✓ Rewind successful!")
                    print(f"  Status: {data.get('status')}")
                    print(f"  Removed: {data.get('removed_count')} messages")
                    return True
                else:
                    print(f"\n⚠️ Response: {text[:300]}")
                    return False
                    
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def verify_rewind_result():
    """Verify that rewind actually deleted messages."""
    print("\n" + "=" * 60)
    print("Test 5: Verify Rewind Result")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/conversations/{THREAD_ID}/messages"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    remaining = len(data.get('items', []))
                    print(f"✓ Remaining messages: {remaining}")
                    
                    for item in data.get('items', []):
                        print(f"  - ID {item['id']}: role={item['role']}")
                    
                    # After rewind to message 3, should have messages 43, 44, 45
                    if remaining <= 3:
                        print(f"\n✅ Rewind verified! Messages were deleted.")
                        return True
                    else:
                        print(f"\n⚠️ Expected 3 or fewer messages, got {remaining}")
                        return False
                else:
                    print(f"✗ Failed to get messages: {resp.status}")
                    return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def test_changeset():
    """Test changeset API."""
    print("\n" + "=" * 60)
    print("Test 6: Get Changeset")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{BASE_URL}/conversations/{THREAD_ID}/changeset"
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ Got changeset: {len(data)} items")
                    for item in data:
                        print(f"  - {item.get('path')}: {item.get('operation')}")
                    return True
                else:
                    text = await resp.text()
                    print(f"⚠️ Changeset: {resp.status} - {text[:200]}")
                    return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def run_all_tests():
    """Run all API tests."""
    print("\n" + "=" * 60)
    print("REWIND API TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Thread ID: {THREAD_ID}")
    print("=" * 60)
    
    # Check server first
    if not await test_health():
        print("\n❌ Server not available. Aborting tests.")
        return 1
    
    # Run tests
    results = []
    
    # Test 1: Get messages before rewind
    results.append(await test_get_messages())
    
    # Test 2: Get changeset
    results.append(await test_changeset())
    
    # Test 3: Rewind to specific message
    rewind_result = await test_rewind_to_message()
    results.append(rewind_result)
    
    # Test 4: Verify result
    if rewind_result:
        results.append(await verify_rewind_result())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ ALL API TESTS PASSED!")
        return 0
    else:
        print("\n⚠️ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    # Check if aiohttp is available
    try:
        import aiohttp
    except ImportError:
        print("Installing aiohttp...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
        import aiohttp
    
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
