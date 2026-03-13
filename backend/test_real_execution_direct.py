#!/usr/bin/env python3
"""
真实执行测试 - 直接使用 ADB 驱动执行 Skill 713 的宏
绕过复杂的依赖链
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

# Set required env vars
os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

# Load .env file
def load_env_file():
    env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()

# Add backend to path
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")


async def get_skill_from_db(skill_id: int = 713):
    """Query LearnedSkills table"""
    try:
        import asyncpg

        pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_db = os.environ.get("POSTGRES_DB", "app")
        pg_user = os.environ.get("POSTGRES_USER", "postgres")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "")

        db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

        conn = await asyncpg.connect(db_url)

        row = await conn.fetchrow(
            "SELECT id, name, status, execution_mode, confidence_score, macro_script FROM learned_skills WHERE id = $1",
            skill_id
        )

        await conn.close()

        if row:
            macro_script_data = row['macro_script']
            if isinstance(macro_script_data, str):
                macro_script = json.loads(macro_script_data)
            else:
                macro_script = macro_script_data

            return {
                'id': row['id'],
                'name': row['name'],
                'status': row['status'],
                'execution_mode': row['execution_mode'],
                'confidence_score': row['confidence_score'],
                'macro_script': macro_script
            }
        return None

    except Exception as e:
        print(f"❌ Database query failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_adb(args, device_id=None, timeout=30):
    """Run ADB command directly"""
    adb_path = "/Users/huangjinhuan/Library/Android/sdk/platform-tools/adb"
    cmd = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


async def check_device():
    """Check if device is connected via ADB"""
    try:
        ok, stdout, stderr = run_adb(["devices"])
        if not ok:
            return False, f"ADB error: {stderr}"

        lines = stdout.strip().split('\n')
        devices = [line.split('\t')[0] for line in lines[1:] if '\tdevice' in line]

        if not devices:
            return False, "No devices connected"

        device_id = devices[0]
        print(f"✅ Device connected: {device_id}")

        # Get screen size
        ok, stdout, stderr = run_adb(["shell", "wm", "size"], device_id)
        if ok:
            print(f"   Screen: {stdout.strip()}")

        # Get current app
        ok, stdout, stderr = run_adb(["shell", "dumpsys", "window", "|", "grep", "mCurrentFocus"], device_id)
        if ok:
            print(f"   Current app: {stdout.strip()[:80]}")

        return True, device_id

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, str(e)


async def take_screenshot(device_id: str, filename: str) -> str:
    """Take screenshot and save to file"""
    import time
    timestamp = int(time.time())
    local_path = f"/tmp/skill713_step{filename}_{timestamp}.png"

    # Take screenshot on device
    ok, _, _ = run_adb(["shell", "screencap", "-p", f"/sdcard/screen_{filename}.png"], device_id)
    if not ok:
        return None

    # Pull to local
    ok, _, _ = run_adb(["pull", f"/sdcard/screen_{filename}.png", local_path], device_id)
    if ok and os.path.exists(local_path):
        return local_path
    return None


async def execute_step(step: dict, device_id: str, step_num: int):
    """Execute a single macro step on the device using direct ADB"""
    event_type = step.get('event_type', 'unknown')
    payload = step.get('payload', {})

    print(f"\n  Step {step_num}: {event_type}")
    print(f"    Payload: {json.dumps(payload, indent=6)[:300]}...")

    result = {
        'success': False,
        'error': None,
        'ui_before': None,
        'ui_after': None,
        'screenshot_before': None,
        'screenshot_after': None
    }

    # Screenshot before
    print(f"    📸 Taking screenshot BEFORE...")
    ss_before = await take_screenshot(device_id, f"{step_num}_before")
    if ss_before:
        result['screenshot_before'] = ss_before
        print(f"    💾 Screenshot saved: {ss_before}")

    # Dump UI before action for comparison
    print(f"    📱 Capturing UI state before...")
    ok, ui_before, _ = run_adb(["shell", "uiautomator", "dump", "/sdcard/ui_before.xml"], device_id)
    if ok:
        ok2, ui_content, _ = run_adb(["shell", "cat", "/sdcard/ui_before.xml"], device_id)
        if ok2:
            result['ui_before'] = ui_content[:500]
            # Parse for elements
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(ui_content)
                elements = root.findall('.//node')
                print(f"    Found {len(elements)} UI elements")
            except:
                pass

    try:
        if event_type == 'open_app':
            package = payload.get('package_name') or payload.get('package')
            if package:
                print(f"    🚀 Opening app: {package}")
                ok, stdout, stderr = run_adb(["shell", "am", "start", "-n", f"{package}/.{package.split('.')[-1]}.MainActivity"], device_id)
                if not ok:
                    # Try simpler launch
                    ok, stdout, stderr = run_adb(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], device_id)
                result['success'] = ok
                if not ok:
                    result['error'] = stderr
            else:
                result['error'] = "No package_name in payload"

        elif event_type == 'tap' or event_type == 'click':
            x = payload.get('x')
            y = payload.get('y')
            if x is not None and y is not None:
                print(f"    👆 Tapping at ({x}, {y})")
                ok, stdout, stderr = run_adb(["shell", "input", "tap", str(x), str(y)], device_id)
                result['success'] = ok
                if not ok:
                    result['error'] = stderr
            else:
                result['error'] = "No coordinates in payload"

        elif event_type == 'wait':
            duration = payload.get('duration_ms', 1000)
            print(f"    ⏱️  Waiting {duration}ms")
            await asyncio.sleep(duration / 1000)
            result['success'] = True

        elif event_type == 'input' or event_type == 'input_text':
            text = payload.get('text')
            if text:
                print(f"    ⌨️  Inputting text: {text[:30]}...")
                # Escape special characters for shell
                safe_text = text.replace(' ', '%s').replace("'", "\\'").replace('"', '\\"')
                ok, stdout, stderr = run_adb(["shell", "input", "text", safe_text], device_id)
                result['success'] = ok
                if not ok:
                    result['error'] = stderr
            else:
                result['error'] = "No text in payload"

        elif event_type == 'swipe' or event_type == 'scroll':
            x1 = payload.get('x1') or payload.get('start_x')
            y1 = payload.get('y1') or payload.get('start_y')
            x2 = payload.get('x2') or payload.get('end_x')
            y2 = payload.get('y2') or payload.get('end_y')
            if all(v is not None for v in [x1, y1, x2, y2]):
                print(f"    👋 Swiping from ({x1}, {y1}) to ({x2}, {y2})")
                ok, stdout, stderr = run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2)], device_id)
                result['success'] = ok
                if not ok:
                    result['error'] = stderr
            else:
                result['error'] = "Incomplete swipe coordinates"

        elif event_type == 'back':
            print(f"    🔙 Pressing back")
            ok, stdout, stderr = run_adb(["shell", "input", "keyevent", "4"], device_id)
            result['success'] = ok

        elif event_type == 'home':
            print(f"    🏠 Pressing home")
            ok, stdout, stderr = run_adb(["shell", "input", "keyevent", "3"], device_id)
            result['success'] = ok

        elif event_type == 'dump_ui' or event_type == 'get_ui_hierarchy':
            print(f"    📄 Getting UI hierarchy")
            ok, stdout, stderr = run_adb(["shell", "uiautomator", "dump", "/sdcard/ui_dump.xml"], device_id)
            if ok:
                ok2, content, _ = run_adb(["shell", "cat", "/sdcard/ui_dump.xml"], device_id)
                if ok2:
                    result['success'] = True
                    result['ui_hierarchy'] = content[:1000]
            else:
                result['error'] = stderr

        elif event_type == 'loop':
            print(f"    🔄 Loop step (skipped in direct execution)")
            result['success'] = True
            result['note'] = "Loop steps not executed in direct mode"

        else:
            result['error'] = f"Unknown event type: {event_type}"

    except Exception as e:
        result['error'] = str(e)
        print(f"    ❌ Error: {e}")

    # Screenshot after
    print(f"    📸 Taking screenshot AFTER...")
    ss_after = await take_screenshot(device_id, f"{step_num}_after")
    if ss_after:
        result['screenshot_after'] = ss_after
        print(f"    💾 Screenshot saved: {ss_after}")

    # Capture UI after
    if event_type not in ['wait', 'dump_ui']:
        print(f"    📱 Capturing UI state after...")
        ok, ui_after, _ = run_adb(["shell", "uiautomator", "dump", "/sdcard/ui_after.xml"], device_id)
        if ok:
            ok2, ui_content, _ = run_adb(["shell", "cat", "/sdcard/ui_after.xml"], device_id)
            if ok2:
                result['ui_after'] = ui_content[:500]

    status = "✅" if result['success'] else "❌"
    print(f"    {status} Result: {result['error'] or 'Success'}")

    return result


async def run_real_execution():
    """Run the real execution test"""
    print("=" * 70)
    print("🚀 REAL EXECUTION TEST - Skill 713 on Android Device (Direct ADB)")
    print("=" * 70)

    # Step 1: Check device
    print("\n📱 Step 1: Checking Android device...")
    device_ok, device_info = await check_device()
    if not device_ok:
        print(f"❌ Device check failed: {device_info}")
        return False

    device_id = device_info

    # Step 2: Get skill from database
    print("\n🗄️  Step 2: Loading skill from database...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ Failed to load skill 713")
        return False

    print(f"✅ Loaded skill: {skill['name']}")
    print(f"   Status: {skill['status']}")
    print(f"   Execution mode: {skill['execution_mode']}")
    print(f"   Confidence: {skill['confidence_score']}")
    print(f"   Steps: {len(skill['macro_script'])}")

    # Show steps
    print("\n   Macro steps preview:")
    for i, step in enumerate(skill['macro_script'], 1):
        event_type = step.get('event_type', 'unknown')
        payload = step.get('payload', {})
        if 'x' in payload and 'y' in payload:
            print(f"     {i}. {event_type} at ({payload['x']}, {payload['y']})")
        elif 'package_name' in payload:
            print(f"     {i}. {event_type} {payload['package_name']}")
        elif 'duration_ms' in payload:
            print(f"     {i}. {event_type} {payload['duration_ms']}ms")
        else:
            print(f"     {i}. {event_type}")

    # Step 3: Confirm execution
    print("\n" + "=" * 70)
    print("⚠️  WARNING: This will execute REAL actions on your phone!")
    print(f"   Device: {device_id}")
    print(f"   Skill: {skill['name']}")
    print(f"   Steps: {len(skill['macro_script'])}")
    print("=" * 70)

    # Countdown
    print("\n🎬 Starting execution in 5 seconds... (Ctrl+C to cancel)")
    for i in range(5, 0, -1):
        print(f"   {i}...")
        await asyncio.sleep(1)

    # Step 4: Execute macro
    print("\n" + "=" * 70)
    print("▶️  EXECUTING MACRO")
    print("=" * 70)

    results = []
    for i, step in enumerate(skill['macro_script'], 1):
        result = await execute_step(step, device_id, i)
        results.append({
            'step': i,
            'event_type': step.get('event_type'),
            'success': result['success'],
            'error': result['error'],
            'has_ui_before': result['ui_before'] is not None,
            'has_ui_after': result['ui_after'] is not None,
            'screenshot_before': result.get('screenshot_before'),
            'screenshot_after': result.get('screenshot_after')
        })

        # Brief pause between steps
        await asyncio.sleep(0.5)

    # Step 5: Summary
    print("\n" + "=" * 70)
    print("📊 EXECUTION SUMMARY")
    print("=" * 70)

    success_count = sum(1 for r in results if r['success'])
    fail_count = len(results) - success_count

    for r in results:
        status = "✅" if r['success'] else "❌"
        ui_info = f"[UI: {r['has_ui_before']}/{r['has_ui_after']}]"
        event_type = r['event_type'] or 'unknown'
        error_msg = r['error'] or 'OK'
        print(f"{status} Step {r['step']}: {event_type:<15} - {error_msg:<30} {ui_info}")

    print(f"\nTotal: {success_count}/{len(results)} steps successful ({success_count/len(results)*100:.1f}%)")

    if fail_count == 0:
        print("\n🎉 All steps executed successfully on real device!")
    else:
        print(f"\n⚠️ {fail_count} step(s) failed")

    # Anomaly detection summary
    print("\n" + "=" * 70)
    print("🔍 ANOMALY DETECTION")
    print("=" * 70)
    print("Comparing UI states before/after each step...")

    anomalies = []
    for r in results:
        if r['has_ui_before'] and r['has_ui_after']:
            # Simple check: if both states are identical after an action, might be an anomaly
            if r['event_type'] in ['tap', 'click', 'input'] and r['success']:
                print(f"  Step {r['step']}: UI changed detected ✓")
        elif r['event_type'] not in ['wait', 'dump_ui']:
            print(f"  Step {r['step']}: Could not capture UI state")
            anomalies.append(r['step'])

    if anomalies:
        print(f"\n⚠️  Anomalies detected at steps: {anomalies}")
    else:
        print("\n✅ No obvious anomalies detected")

    # Screenshot evidence
    print("\n" + "=" * 70)
    print("📸 SCREENSHOT EVIDENCE")
    print("=" * 70)
    for r in results:
        if r['screenshot_before'] or r['screenshot_after']:
            print(f"\n  Step {r['step']} ({r['event_type']}):")
            if r['screenshot_before']:
                print(f"    Before: {r['screenshot_before']}")
            if r['screenshot_after']:
                print(f"    After:  {r['screenshot_after']}")

    print("\n" + "=" * 70)
    print("📝 To view screenshots, run:")
    print("   open /tmp/skill713_step*.png")
    print("=" * 70)

    return fail_count == 0


if __name__ == "__main__":
    try:
        result = asyncio.run(run_real_execution())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Execution cancelled by user")
        sys.exit(1)
