# E2E 缺陷报告：test_voice_route_empty_text

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceRouteEdgeCases::test_voice_route_empty_text`
- **发现时间**: 2026-08-05T14:09:51.416402
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:953: in transfer_data
    message = await self.read_message()
              ^^^^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:1023: in read_message
    frame = await self.read_data_frame(max_size=self.max_size)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:1098: in read_data_frame
    frame = await self.read_frame(max_size)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:1155: in read_frame
    frame = await Frame.read(
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/framing.py:70: in read
    data = await reader(2)
           ^^^^^^^^^^^^^^^
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/asyncio/streams.py:748: in readexactly
    raise exceptions.IncompleteReadError(incomplete, n)
E   asyncio.exceptions.IncompleteReadError: 0 bytes read on a total of 2 expected bytes

The above exception was the direct cause of the following exception:
tests/e2e/test_04_voice_output.py:115: in test_voice_route_empty_text
    await voice_conn.send_route("再见")
tests/e2e/conftest.py:413: in send_route
    await self.ws.send(json.dumps(make_envelope("voice.route", body)))
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:628: in send
    await self.ensure_open()
/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/websockets/legacy/protocol.py:929: in ensure_open
    raise self.connection_closed_exc()
E   websockets.exceptions.ConnectionClosedError: no close frame received or sent
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceRouteEdgeCases::test_voice_route_empty_text -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
