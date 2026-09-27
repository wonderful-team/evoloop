# E2E 缺陷报告：test_voice_route_result_is_canonical_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_route_result_is_canonical_envelope`
- **发现时间**: 2026-08-05T14:46:47.981408
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:95: in test_voice_route_result_is_canonical_envelope
    assert env["body"]["summary"] == "完成"
E   AssertionError: assert '好的，我在这里。不过我还...认某个任务，还是其他事情？' == '完成'
E     - 完成
E     + 好的，我在这里。不过我还没听清楚您具体需要我做什么，方便再说一下吗？比如是要核对某个文件、确认某个任务，还是其他事情？
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_route_result_is_canonical_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
