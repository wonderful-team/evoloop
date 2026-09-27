# E2E 缺陷报告：test_voice_done_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope`
- **发现时间**: 2026-09-23T22:17:28.785909
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:50: in test_voice_done_envelope
    assert body["summary"] == "完成"
E   AssertionError: assert '宏列表里没有名为「宏#」...或想做的事），我直接执行。' == '完成'
E     - 完成
E     + 宏列表里没有名为「宏#」的宏——这个名字像是占位符或识别出错。请问你想执行哪个宏？我可以帮你确认：
E     + 常用：静音、截屏、深色模式、锁屏、音量调节
E     + 窗口：关闭窗口、最小化、全屏、强制退出
E     + 编辑：复制、粘贴、剪切、撤销、全选
E     + 浏览器：刷新、新建/关闭标签页、后退、前进
E     + 其他：打开/关闭 WiFi、蓝牙、清空废纸篓
E     + 告诉我宏名（或想做的事），我直接执行。
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
