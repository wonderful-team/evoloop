# E2E 缺陷报告：test_l0_navigation_macro_trigger_returns_navigate

- **测试 ID**: `tests/e2e/test_02_routing.py::TestL0NavigationMacro::test_l0_navigation_macro_trigger_returns_navigate`
- **发现时间**: 2026-08-15T01:05:57.413746
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_02_routing.py:386: in test_l0_navigation_macro_trigger_returns_navigate
    macro_id = await _create_navigation_macro(
tests/e2e/test_02_routing.py:327: in _create_navigation_macro
    assert update_resp.status_code == 200, update_resp.text
E   AssertionError: Internal Server Error
E   assert 500 == 200
E    +  where 500 = <Response [500 Internal Server Error]>.status_code
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestL0NavigationMacro::test_l0_navigation_macro_trigger_returns_navigate -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
