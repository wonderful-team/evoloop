# E2E 缺陷报告：test_voice_route_inbound_contract

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract`
- **发现时间**: 2026-09-24T05:37:15.828992
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:137: in test_voice_route_inbound_contract
    assert body["summary"] == "完成"
E   AssertionError: assert '执行失败了——宏库中并没...），我来帮你运行对应的宏。' == '完成'
E     - 完成
E     + 执行失败了——宏库中并没有名为「宏#」的宏。
E     + 当前可用宏（部分）：
E     + 音量/媒体类：静音、音量增大/减小、播放暂停、下一曲、上一曲、快进/快退
E     + 系统类：锁屏、息屏、深色模式、清空废纸篓
E     + 截屏类：截屏、区域截屏、截屏到剪贴板、定时截屏
E     + 窗口类：隐藏窗口、最小化、全屏、关闭窗口...
E     
E     ...Full output truncated (4 lines hidden), use '-vv' to show
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
