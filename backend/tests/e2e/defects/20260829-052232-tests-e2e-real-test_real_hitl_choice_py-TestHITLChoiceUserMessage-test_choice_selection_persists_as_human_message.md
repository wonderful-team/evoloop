# E2E 缺陷报告：test_choice_selection_persists_as_human_message

- **测试 ID**: `tests/e2e/real/test_real_hitl_choice.py::TestHITLChoiceUserMessage::test_choice_selection_persists_as_human_message`
- **发现时间**: 2026-08-29T05:22:32.967592
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/real/test_real_hitl_choice.py:152: in test_choice_selection_persists_as_human_message
    assert (
E   AssertionError: 未收到 choice 型 human_request（LLM 未调用 ask_human 带 options）
E   assert False
E    +  where False = ChoiceState(hitl_seen=False, resumed=False, chosen='', thread_id='e2e-4668d577b52d492a').hitl_seen
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_hitl_choice.py::TestHITLChoiceUserMessage::test_choice_selection_persists_as_human_message -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
