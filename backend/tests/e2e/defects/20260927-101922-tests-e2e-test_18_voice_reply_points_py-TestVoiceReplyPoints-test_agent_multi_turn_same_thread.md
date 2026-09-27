# E2E 缺陷报告：test_agent_multi_turn_same_thread

- **测试 ID**: `tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_agent_multi_turn_same_thread`
- **发现时间**: 2026-09-27T10:19:22.041857
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_18_voice_reply_points.py:250: in test_agent_multi_turn_same_thread
    assert (body.get("summary") or "").strip(), (
E   AssertionError: 第 2 轮 done 终态 summary 不应为空: {'thread_id': 'e2e-1b547ab0d4b349b7', 'status': 'done', 'summary': '', 'skip_tts': True}
E   assert ''
E    +  where '' = <built-in method strip of str object at 0x1074892b0>()
E    +    where <built-in method strip of str object at 0x1074892b0> = ('' or '').strip
E    +      where '' = <built-in method get of dict object at 0x16b33dcc0>('summary')
E    +        where <built-in method get of dict object at 0x16b33dcc0> = {'skip_tts': True, 'status': 'done', 'summary': '', 'thread_id': 'e2e-1b547ab0d4b349b7'}.get
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_agent_multi_turn_same_thread -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
