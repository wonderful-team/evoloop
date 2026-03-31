#!/bin/bash
# Run all optimization tests with reporting

set -e

echo "=========================================="
echo "EvoLoop Optimization Test Suite"
echo "=========================================="
echo ""

cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend

# Create test report directory
mkdir -p test_reports

echo "1. Running Tool Cache Tests..."
python -m pytest tests/test_tool_cache.py -v --tb=short 2>&1 | tee test_reports/tool_cache_test.log
echo "   ✓ Tool Cache tests complete"
echo ""

echo "2. Running Context Cache Tests..."
python -m pytest tests/test_context_cache.py -v --tb=short 2>&1 | tee test_reports/context_cache_test.log
echo "   ✓ Context Cache tests complete"
echo ""

echo "3. Running Finish Auditor Tests..."
python -m pytest tests/test_finish_auditor.py -v --tb=short 2>&1 | tee test_reports/finish_auditor_test.log
echo "   ✓ Finish Auditor tests complete"
echo ""

echo "4. Running Integration Tests..."
python -m pytest tests/test_optimization_integration.py -v --tb=short 2>&1 | tee test_reports/integration_test.log
echo "   ✓ Integration tests complete"
echo ""

echo "5. Running Performance Benchmarks..."
python -m pytest tests/test_optimization_integration.py -v -m benchmark --tb=short 2>&1 | tee test_reports/benchmark_test.log
echo "   ✓ Performance benchmarks complete"
echo ""

# Generate summary report
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""

echo "Tool Cache:"
grep -E "(PASSED|FAILED|ERROR)" test_reports/tool_cache_test.log | tail -5

echo ""
echo "Context Cache:"
grep -E "(PASSED|FAILED|ERROR)" test_reports/context_cache_test.log | tail -5

echo ""
echo "Finish Auditor:"
grep -E "(PASSED|FAILED|ERROR)" test_reports/finish_auditor_test.log | tail -5

echo ""
echo "Integration:"
grep -E "(PASSED|FAILED|ERROR)" test_reports/integration_test.log | tail -5

echo ""
echo "All test reports saved to: test_reports/"
echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="
