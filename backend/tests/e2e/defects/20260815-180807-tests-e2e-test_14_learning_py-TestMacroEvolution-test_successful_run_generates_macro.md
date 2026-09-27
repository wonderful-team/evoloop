# E2E 缺陷报告：test_successful_run_generates_macro

- **测试 ID**: `tests/e2e/test_14_learning.py::TestMacroEvolution::test_successful_run_generates_macro`
- **发现时间**: 2026-08-15T18:08:07.304173
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_14_learning.py:259: in test_successful_run_generates_macro
    assert activity.get("macro_creation_eligible") == 1, (
E   AssertionError: 运行未被标记为 macro_creation_eligible: {'final_outcome': 'completed', 'macro_creation_eligible': 0}
E   assert 0 == 1
E    +  where 0 = <built-in method get of dict object at 0x103dd2200>('macro_creation_eligible')
E    +    where <built-in method get of dict object at 0x103dd2200> = {'final_outcome': 'completed', 'macro_creation_eligible': 0}.get
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_14_learning.py::TestMacroEvolution::test_successful_run_generates_macro -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
