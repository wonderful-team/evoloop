# E2E 缺陷报告：test_human_mobile_echo_suppressed

- **测试 ID**: `tests/e2e/test_22_channel_policy.py::TestToolAndHumanBlocks::test_human_mobile_echo_suppressed`
- **发现时间**: 2026-08-05T18:54:09.783627
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_22_channel_policy.py:71: in test_human_mobile_echo_suppressed
    assert OutputChannelPolicy.resolve(_block("human", "completed"), "mobile", "supervisor") == {"sse"}
tests/e2e/test_22_channel_policy.py:20: in _block
    return MessageBlock(role=role, content="x", status=status, thread_id="t")
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for MessageBlock
E   id
E     Field required [type=missing, input_value={'role': 'human', 'conten...eted', 'thread_id': 't'}, input_type=dict]
E       For further information visit https://errors.pydantic.dev/2.12/v/missing
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_22_channel_policy.py::TestToolAndHumanBlocks::test_human_mobile_echo_suppressed -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
