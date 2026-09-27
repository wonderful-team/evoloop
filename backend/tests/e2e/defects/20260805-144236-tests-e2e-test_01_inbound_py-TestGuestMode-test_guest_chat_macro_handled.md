# E2E 缺陷报告：test_guest_chat_macro_handled

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestGuestMode::test_guest_chat_macro_handled`
- **发现时间**: 2026-08-05T14:42:36.969669
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:324: in test_guest_chat_macro_handled
    macro_id = await _create_routable_macro(guest_http_client, "ack", "麻烦对对对")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
tests/e2e/test_02_routing.py:44: in _create_routable_macro
    assert create_resp.status_code == 201, create_resp.text
E   AssertionError: {"detail":"Not authenticated"}
E   assert 401 == 201
E    +  where 401 = <Response [401 Unauthorized]>.status_code
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_01_inbound.py::TestGuestMode::test_guest_chat_macro_handled -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
