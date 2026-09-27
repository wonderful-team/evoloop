# E2E 缺陷报告：test_failing_web_macro_falls_back

- **测试 ID**: `tests/e2e/test_27_macro_self_heal.py::TestWebMacroSelfHeal::test_failing_web_macro_falls_back`
- **发现时间**: 2026-08-05T21:19:12.194353
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
E   AssertionError: 宏失败后 web 源应返回 done（自愈），实际: {'status': 'failed', 'action_type': 'macro', 'summary': 'Exit code 1\nSTDOUT:\n\nSTDERR:', 'fell_back': True, 'thread_id': 'e2e-920ea45593bd413f'}
    assert 'failed' in ('done', 'queued')
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_27_macro_self_heal.py::TestWebMacroSelfHeal::test_failing_web_macro_falls_back -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
