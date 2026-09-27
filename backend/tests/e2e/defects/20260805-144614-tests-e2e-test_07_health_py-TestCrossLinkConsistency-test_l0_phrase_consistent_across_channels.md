# E2E 缺陷报告：test_l0_phrase_consistent_across_channels

- **测试 ID**: `tests/e2e/test_07_health.py::TestCrossLinkConsistency::test_l0_phrase_consistent_across_channels`
- **发现时间**: 2026-08-05T14:46:14.177683
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_07_health.py:95: in test_l0_phrase_consistent_across_channels
    assert voice_env["body"]["summary"] == "完成", (
E   AssertionError: 跨通道话术不一致: web='完成' voice='好的，请问您想让我"对"什么呢？比如对账、校对文件、核对数据，还是其他？您说清楚一点，我马上帮您处理。'
E   assert '好的，请问您想让我"对"...清楚一点，我马上帮您处理。' == '完成'
E     - 完成
E     + 好的，请问您想让我"对"什么呢？比如对账、校对文件、核对数据，还是其他？您说清楚一点，我马上帮您处理。
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_07_health.py::TestCrossLinkConsistency::test_l0_phrase_consistent_across_channels -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
