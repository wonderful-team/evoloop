# E2E 缺陷报告：test_l0_duplicate_trigger_newest_macro_wins

- **测试 ID**: `tests/e2e/test_02_routing.py::TestL0MacroRoute::test_l0_duplicate_trigger_newest_macro_wins`
- **发现时间**: 2026-08-15T18:05:22.652952
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_02_routing.py:241: in test_l0_duplicate_trigger_newest_macro_wins
    assert all(
E   AssertionError: 重复 trigger 应只绑定最新宏 macro:3336，实际: [{'action': 'macro:3336', 'patterns': ['麻烦对对对'], 'slots': {}, 'args': {}, 'project_id': None}, {'action': 'macro:2924', 'patterns': ['麻烦对对对'], 'slots': {}, 'args': {}, 'project_id': 0}]
E   assert False
E    +  where False = all(<generator object TestL0MacroRoute.test_l0_duplicate_trigger_newest_macro_wins.<locals>.<genexpr> at 0x31ff30900>)
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestL0MacroRoute::test_l0_duplicate_trigger_newest_macro_wins -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
