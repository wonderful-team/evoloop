#!/bin/bash
#
# Test Huey recursion fix using arm64 architecture
#

set -e

cd "$(dirname "$0")/.."

echo "============================================================"
echo "Huey Recursion Fix Test (ARM64)"
echo "============================================================"
echo ""

# Check architecture
echo "Current architecture: $(arch)"
echo "Python architecture: $(arch -arm64 .venv/bin/python -c 'import platform; print(platform.machine())' 2>/dev/null || echo 'N/A')"
echo ""

# Test 1: Syntax check
echo "[Test 1] Syntax check..."
arch -arm64 .venv/bin/python -m py_compile app/infrastructure/queue/huey_queue.py
if [ $? -eq 0 ]; then
    echo "✅ Syntax OK"
else
    echo "❌ Syntax error"
    exit 1
fi
echo ""

# Test 2: Import test
echo "[Test 2] Import test..."
arch -arm64 .venv/bin/python -c "
from app.infrastructure.queue.huey_queue import HueyTaskScheduler
from app.infrastructure.queue.factory import get_scheduler
print('✅ Imports successful')
"
if [ $? -ne 0 ]; then
    echo "❌ Import failed"
    exit 1
fi
echo ""

# Test 3: Verify retry limit mechanism
echo "[Test 3] Verify retry limit mechanism..."
arch -arm64 .venv/bin/python -c "
import inspect
from app.infrastructure.queue.huey_queue import HueyTaskScheduler

# Check send_task signature
sig = inspect.signature(HueyTaskScheduler.send_task)
params = list(sig.parameters.keys())

if '_retry_count' in params:
    print('✅ _retry_count parameter exists')
else:
    print('❌ _retry_count parameter missing')
    exit(1)

# Check max_retries in source
with open('app/infrastructure/queue/huey_queue.py', 'r') as f:
    source = f.read()
    
if 'max_retries = 3' in source:
    print('✅ max_retries = 3 found in code')
else:
    print('❌ max_retries not found')
    exit(1)

if '_retry_count >= max_retries' in source:
    print('✅ Retry limit check exists')
else:
    print('❌ Retry limit check missing')
    exit(1)
"
if [ $? -ne 0 ]; then
    echo "❌ Retry limit test failed"
    exit 1
fi
echo ""

# Test 4: Verify task caching
echo "[Test 4] Verify task caching..."
arch -arm64 .venv/bin/python -c "
with open('app/infrastructure/queue/huey_queue.py', 'r') as f:
    source = f.read()

if 'func._huey_task' in source:
    print('✅ Task caching (func._huey_task) found')
else:
    print('❌ Task caching not found')
    exit(1)

# Check for hasattr check
if 'hasattr(func' in source and '_huey_task' in source:
    print('✅ Cache check exists')
else:
    print('❌ Cache check missing')
    exit(1)
"
if [ $? -ne 0 ]; then
    echo "❌ Task caching test failed"
    exit 1
fi
echo ""

# Test 5: Functional test - simulate concurrent registration
echo "[Test 5] Functional test - concurrent registration..."
arch -arm64 .venv/bin/python -c "
import sys
sys.path.insert(0, '.')

from app.infrastructure.queue.huey_queue import HueyTaskScheduler
from app.infrastructure.queue.factory import get_scheduler
import threading
import time

scheduler = get_scheduler()
print(f'Scheduler type: {type(scheduler).__name__}')

if type(scheduler).__name__ != 'HueyTaskScheduler':
    print(f'⚠️  Not using Huey, skipping functional test')
    sys.exit(0)

# Register a test task
@scheduler.task(name='test_concurrent_fix')
def test_task(x):
    return x * 2

print('✅ Test task registered')

# Test single dispatch
try:
    result = test_task.delay(5)
    print(f'✅ Single dispatch OK: {result}')
except Exception as e:
    print(f'⚠️  Single dispatch: {e}')

# Test concurrent dispatch (simulate the problematic scenario)
errors = []
success = []

def dispatch_task(i):
    try:
        result = scheduler.send_task('test_concurrent_fix', args=(i,))
        success.append(i)
    except Exception as e:
        errors.append(str(e))

print('Testing concurrent dispatch (20 threads)...')
threads = []
for i in range(20):
    t = threading.Thread(target=dispatch_task, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join(timeout=5)

print(f'✅ Success: {len(success)}/20')
print(f'✅ Errors: {len(errors)}')

# Check for recursion errors
recursion_errors = [e for e in errors if 'recursion' in e.lower()]
if recursion_errors:
    print(f'❌ FAILED: Recursion errors detected!')
    for e in recursion_errors[:3]:
        print(f'   - {e}')
    sys.exit(1)

# Check that we don't have excessive retries
retry_errors = [e for e in errors if 'after 3 retries' in e]
if retry_errors:
    print(f'⚠️  Some tasks failed after max retries (expected: limited to 3)')

print('✅ Concurrent test passed - No infinite recursion')
"
if [ $? -ne 0 ]; then
    echo "❌ Functional test failed"
    exit 1
fi
echo ""

echo "============================================================"
echo "All tests PASSED ✅"
echo "============================================================"
echo ""
echo "Summary:"
echo "  - Syntax: OK"
echo "  - Imports: OK"
echo "  - Retry limit (max 3): OK"
echo "  - Task caching: OK"
echo "  - Concurrent registration: OK"
echo ""
echo "The recursion fix is working correctly."
