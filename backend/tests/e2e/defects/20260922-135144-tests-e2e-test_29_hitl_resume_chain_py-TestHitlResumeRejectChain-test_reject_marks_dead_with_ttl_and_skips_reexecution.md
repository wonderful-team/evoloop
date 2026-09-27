# E2E 缺陷报告：test_reject_marks_dead_with_ttl_and_skips_reexecution

- **测试 ID**: `tests/e2e/test_29_hitl_resume_chain.py::TestHitlResumeRejectChain::test_reject_marks_dead_with_ttl_and_skips_reexecution`
- **发现时间**: 2026-09-22T13:51:44.341289
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_29_hitl_resume_chain.py:219: in test_reject_marks_dead_with_ttl_and_skips_reexecution
    assert resp.status_code == 200, f"resume 失败: {resp.status_code} {resp.text}"
E   AssertionError: resume 失败: 500 {"success":false,"code":"INTERNAL_ERROR","message":"Internal server error","detail":"Internal server error"}
E   assert 500 == 200
E    +  where 500 = <Response [500 Internal Server Error]>.status_code
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_29_hitl_resume_chain.py::TestHitlResumeRejectChain::test_reject_marks_dead_with_ttl_and_skips_reexecution -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
