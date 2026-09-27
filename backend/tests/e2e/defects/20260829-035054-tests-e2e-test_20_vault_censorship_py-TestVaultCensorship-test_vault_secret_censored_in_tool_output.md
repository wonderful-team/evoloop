# E2E 缺陷报告：test_vault_secret_censored_in_tool_output

- **测试 ID**: `tests/e2e/test_20_vault_censorship.py::TestVaultCensorship::test_vault_secret_censored_in_tool_output`
- **发现时间**: 2026-08-29T03:50:54.182552
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
E   assert '******' in '{"id": "c4cebf0f-c94c-4cba-869e-b1441601367d", "thread_id": "e2e-f84cf2d0894d48c9", "run_id": null, "role": "human", "category": "", "content": "请用 execute_command 工具原样运行命令 `echo {{vault.e2e-sec-e3ae62.key}}`，命令一个字都不要改，然后报告输出。", "content_type": "text", "thinking": null, "tool_calls": null, "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-28T19:50:02.838112", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": null, "executor_device_name": null, "source": "web", "meta_data": {}}\n{"id": "d4d53ae8-3d8a-4ea0-8e34-16146fa3f214", "thread_id": "e2e-f84cf2d0894d48c9", "run_id": null, "role": "ai", "category": "", "content": "好的，我先确认一下该凭据在安全库中是否存在，然后安排执行。\\n\\n", "content_type": "text", "thinking": "用户要求用 execute_command工具原样运行命令 `echo {{vault.e2e-sec-e3ae62.key}}`，命令一个字都不要改，然后报告输出。\\n\\n我需要理解这个请求。用户提到了 vault凭据的占位符格式 `{{vault.e2e-sec-e3ae62.key}}`。这是一个凭据占位符，系统应该会自动替换成真实凭据值。\\n\\n但是作为 Supervisor，我没有 execute_command工具——这是执行工具（shell...aodanku`、`taobao`，**确实不存在** `e2e-sec-e3ae62`。\\n- 因此，此结果属于验收标准中明确的\\"**占位符未替换/报错**\\"情形，非命令本身语法错误，已如实上报，无编造。\\n\\n### 验收标准对照\\n\\n| 验收项 | 状态 |\\n|---|---|\\n| 命令用 execute_command 原样运行、一字未改 | ✅ 已原样提交 |\\n| 如实报告实际输出（含未替换/报错，不编造） | ✅ 已报告安全拦截错误及核实依据 |\\n\\n> 附注：任务执行中首次尝试调用结果上报工具时，因摘要文本中包含字面 `{{vault...}}` 占位符模式被系统误当作占位符再次拦截；调整措辞（避免字面占位符文本）后上报成功。此属工具层行为，不影响上述结论。", "content_type": "text", "thinking": null, "tool_calls": [], "tool_name": null, "tool_call_id": null, "input": null, "tool_meta": null, "references": [], "has_file_operations": false, "changeset_count": 0, "changeset_files": null, "status": "completed", "is_visible": true, "created_at": "2026-08-28T19:50:53.558265", "updated_at": null, "sequence_number": 0, "parent_id": null, "checkpoint_id": null, "is_complete": null, "executor_device_key": "evo_24b93a4aa2db4a26acca6b68107a1087", "executor_device_name": "Mac-mini.local", "source": null, "meta_data": {"project_id": 120, "is_retry": false, "intent_hint": {"intent": "domain_classified", "domain": "ambiguous", "confidence": 0.0, "suggested_modules": [], "reason": "L1 classifier unavailable or low confidence", "sub_intents": null, "previous_intent": null, "session_history": []}}}'
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
