# E2E 缺陷报告：test_evolved_macro_runs_on_web_and_voice

- **测试 ID**: `tests/e2e/test_14_learning.py::TestEvolvedMacroChannels::test_evolved_macro_runs_on_web_and_voice`
- **发现时间**: 2026-08-29T05:08:42.530502
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_14_learning.py:100: in test_evolved_macro_runs_on_web_and_voice
    assert web_body["status"] == "done", f"Web 宏触发未返回 done: {web_body}"
E   AssertionError: Web 宏触发未返回 done: {'status': 'queued', 'thread_id': 'e2e-891d0b0e90ab4f61', 'message_id': 'ad3988a7-2d75-4f8c-b5bd-882d1c6732f2'}
E   assert 'queued' == 'done'
E     - done
E     + queued
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_14_learning.py::TestEvolvedMacroChannels::test_evolved_macro_runs_on_web_and_voice -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
