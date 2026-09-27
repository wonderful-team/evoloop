# E2E 缺陷报告：test_vault_secret_censored_in_tool_output

- **测试 ID**: `tests/e2e/test_20_vault_censorship.py::TestVaultCensorship::test_vault_secret_censored_in_tool_output`
- **发现时间**: 2026-08-05T18:34:13.474646
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_20_vault_censorship.py:80: in test_vault_secret_censored_in_tool_output
    assert secret not in text, (
E   AssertionError: Vault 密文在工具输出中泄露！thread=e2e-c3efc38956f945dd secret=e2e-vault-se...
E   assert 'e2e-vault-secret-3e99a11a' not in '{"id": "a8c...tory": []}}}'
E     'e2e-vault-secret-3e99a11a' is contained here:
E       {"id": "a8c0b66e-a6bb-499a-9e3e-11fb98483156", "thread_id": "e2e-c3efc38956f945dd", "run_id": null, "role": "human", "category": "", "content": "请用 execute_command 工具原样运行命令 `echo {{vault.e2e-sec-d0450e.key}}`，命令一个字都不要改，然后报告输出。", "content_type": "text", "thinking": null, "tool_calls": null, "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-05...
E     
E     ...Full output truncated (6 lines hidden), use '-vv' to show
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_20_vault_censorship.py::TestVaultCensorship::test_vault_secret_censored_in_tool_output -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
