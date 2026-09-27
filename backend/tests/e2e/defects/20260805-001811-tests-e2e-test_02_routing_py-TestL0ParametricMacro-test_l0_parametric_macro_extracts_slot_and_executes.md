# E2E 缺陷报告：test_l0_parametric_macro_extracts_slot_and_executes

- **测试 ID**: `tests/e2e/test_02_routing.py::TestL0ParametricMacro::test_l0_parametric_macro_extracts_slot_and_executes`
- **发现时间**: 2026-08-05T00:18:11.478118
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_02_routing.py:361: in test_l0_parametric_macro_extracts_slot_and_executes
    assert body["status"] == "done", f"参数化宏未正常完成: {body}"
E   AssertionError: 参数化宏未正常完成: {'status': 'queued', 'thread_id': 'e2e-d420ab97f8d8426f', 'message_id': 'da9a15b4-cf63-4741-8d9f-3a1c82c20422'}
E   assert 'queued' == 'done'
E     
E     - done
E     + queued
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestL0ParametricMacro::test_l0_parametric_macro_extracts_slot_and_executes -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
