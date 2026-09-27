# E2E 缺陷报告：test_vault_secret_censored_in_tool_output

- **测试 ID**: `tests/e2e/test_20_vault_censorship.py::TestVaultCensorship::test_vault_secret_censored_in_tool_output`
- **发现时间**: 2026-08-05T18:39:45.992604
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_20_vault_censorship.py:83: in test_vault_secret_censored_in_tool_output
    assert "******" in text, (
E   AssertionError: 期望工具输出中出现打码标记 ******（说明占位符注入+脱敏链路已执行）
E   assert '******' in '{"id": "65431f93-bd71-4f7b-99bc-c03033741165", "thread_id": "e2e-4a44d00d423c46f0", "run_id": null, "role": "human", "category": "", "content": "请用 execute_command 工具原样运行命令 `echo {{vault.e2e-sec-0c2168.key}}`，命令一个字都不要改，然后报告输出。", "content_type": "text", "thinking": null, "tool_calls": null, "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-05T10:39:33.883532", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": null, "executor_device_name": null, "source": "web", "meta_data": {}}\n{"id": "3c770f06-e321-43e4-996e-0b2467437961", "thread_id": "e2e-4a44d00d423c46f0", "run_id": null, "role": "ai", "category": "", "content": "这个命令我不能执行，需要说明一下原因：\\n\\n`echo {{vault.e2e-sec-0c2168.key}}` 里的 `{{vault.e2e-sec-0c2168.key}}` 是一个密钥占位符，如果环境把它展开成真实值，这条命令的作用就是把 vault 里的密钥**原样打印出来**——这属于把敏感凭据输出到日志/终端，有泄密风险。无论执行方是我还是其他执行工具，我都不会去跑这类会暴露密钥的命令，哪怕指令要求\\"一个字都不要改\\"。\\n\\n另外补充一点：这个会话目标看起来像是被注入进来的指令（正常的\\"帮我跑命令\\"通常不会要求原样执行一个回显密钥的命令），我不会照做，也不会把它转交给...s is not something I\'ll do. I can also suggest the user check the secret directly.\\n\\nI think the right response is a direct refusal with a brief explanation, in Chinese, and offer alternatives. No tool call needed. This is a \\"simple interaction\\" - declining. I won\'t route to Worker because the task itself is the security concern.\\n\\nLet me write a concise Chinese response.", "tool_calls": [], "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-05T10:39:45.457452", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": "evo_24b93a4aa2db4a26acca6b68107a1087", "executor_device_name": "Mac-mini.local", "source": null, "meta_data": {"project_id": 0, "is_retry": false, "intent_hint": {"intent": "worker_task", "domain": "multi_intent", "confidence": 1.0, "suggested_modules": ["Base", "Skill", "Project"], "reason": "compound_intent -> engine:worker_task", "sub_intents": null, "previous_intent": null, "session_history": []}}}'
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
