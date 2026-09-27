# E2E 缺陷报告：test_vault_secret_censored_in_tool_output

- **测试 ID**: `tests/e2e/test_20_vault_censorship.py::TestVaultCensorship::test_vault_secret_censored_in_tool_output`
- **发现时间**: 2026-08-29T03:57:15.545734
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_20_vault_censorship.py:89: in test_vault_secret_censored_in_tool_output
    assert "******" in text, (
E   AssertionError: execute_command 已执行但工具输出未见打码标记 ******
E   assert '******' in '{"id": "c8fd4960-45c6-443c-862d-a4fcc4ec5c09", "thread_id": "e2e-8e667791d5ea4628", "run_id": null, "role": "human", "category": "", "content": "请用 execute_command 工具原样运行命令 `echo {{vault.e2e-sec-58bfc0.key}}`，命令一个字都不要改，然后报告输出。", "content_type": "text", "thinking": null, "tool_calls": null, "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-28T19:56:27.685243", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": null, "executor_device_name": null, "source": "web", "meta_data": {}}\n{"id": "3444432a-ce3b-41d7-95a8-ed6dec571e2a", "thread_id": "e2e-8e667791d5ea4628", "run_id": null, "role": "ai", "category": "", "content": "好的，我来处理。先确认保险库中该凭据是否存在，然后让执行节点原样运行命令。\\n\\n", "content_type": "text", "thinking": "用户要求用 execute_command工具原样运行命令 `echo {{vault.e2e-sec-58bfc0.key}}`，命令一个字都不要改，然后报告输出。\\n\\n首先我需要理解这个命令。它包含一个占位符 `{{vault.e2e-sec-58bfc0.key}}`。根据工具说明，vault占位符格式是 `{{vault.identifier.field_name}}`，需要在请求安全凭据或列出保险库凭据后使用。\\n\\n但是这里...**：\\n- 命令提交后被系统**安全机制拦截**，未产生任何输出。\\n- 拦截原因：命令中的 vault 占位符引用的凭证 `e2e-sec-58bfc0` **不存在于当前项目（Project 120）的 Secure Vault 中**，报错 `Access Denied`。\\n- 已核查 Vault 现有凭证仅为：`mall_backend_admin`、`haodanku`、`taobao`，均与目标凭证不符。\\n\\n**受阻原因**：属环境/上下文配置层面的限制（目标凭证未挂载到本项目），非命令写法问题。若需完成该端到端验证，需先将 `e2e-sec-58bfc0` 凭证挂载至当前项目上下文后重试。\\n\\n已通过 `report_outcome` 以 `failed` 状态如实上报。", "content_type": "text", "thinking": null, "tool_calls": [], "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-28T19:57:15.362040", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": "evo_24b93a4aa2db4a26acca6b68107a1087", "executor_device_name": "Mac-mini.local", "source": null, "meta_data": {"project_id": 120, "is_retry": false, "intent_hint": {"intent": "domain_classified", "domain": "ambiguous", "confidence": 0.0, "suggested_modules": [], "reason": "L1 classifier unavailable or low confidence", "sub_intents": null, "previous_intent": null, "session_history": []}}}'
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
