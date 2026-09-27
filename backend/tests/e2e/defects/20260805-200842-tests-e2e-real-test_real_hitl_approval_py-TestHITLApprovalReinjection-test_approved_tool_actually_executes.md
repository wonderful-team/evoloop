# E2E 缺陷报告：test_approved_tool_actually_executes

- **测试 ID**: `tests/e2e/real/test_real_hitl_approval.py::TestHITLApprovalReinjection::test_approved_tool_actually_executes`
- **发现时间**: 2026-08-05T20:08:42.972452
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
E   AssertionError: write_file 调用后未发现任何文件（原始+工作目录重定向均无）: ['/tmp/e2e-hitl-65d197f6.txt', '/tmp/e2e-hitl-65d197f6.txt', '/Users/huangjinhuan/Projects/e2e-real-5034e684/tmp/e2e-hitl-65d197f6.txt', '/Users/huangjinhuan/Projects/e2e-real-5034e684/tmp/e2e-hitl-65d197f6.txt']
    assert []
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_hitl_approval.py::TestHITLApprovalReinjection::test_approved_tool_actually_executes -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
