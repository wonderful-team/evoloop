# E2E 缺陷报告：test_a2a_delegate_and_callback_resume

- **测试 ID**: `tests/e2e/test_12_a2a.py::TestA2AHITLCallback::test_a2a_delegate_and_callback_resume`
- **发现时间**: 2026-08-29T02:08:38.448536
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_12_a2a.py:372: in test_a2a_delegate_and_callback_resume
    assert task.get("target_device_key") == A2A_TARGET_DEVICE
E   AssertionError: assert 'evo_24b93a4a...a6b68107a1087' == 'child-device'
E     - child-device
E     + evo_24b93a4aa2db4a26acca6b68107a1087
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_12_a2a.py::TestA2AHITLCallback::test_a2a_delegate_and_callback_resume -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
