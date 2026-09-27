# E2E 缺陷报告：test_retry_reverts_file_and_db

- **测试 ID**: `tests/e2e/test_11_rollback.py::TestRetryFileRollback::test_retry_reverts_file_and_db`
- **发现时间**: 2026-08-27T03:41:38.787332
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_11_rollback.py:127: in test_retry_reverts_file_and_db
    assert (
E   AssertionError: 第一次运行后文件内容应为 'after'，实际: 'before'
E   assert 'before' == 'after'
E     - after
E     + before
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_11_rollback.py::TestRetryFileRollback::test_retry_reverts_file_and_db -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
