# LLM 处理链路统一（重构方案）

### 1.1 问题

当前 AI 消息的入库（`persist(role="ai")`）和推送（`_dispatch_block()` → SSE/WS）依赖于 `DatabaseCallbackHandler.on_llm_end()`，这是一个 **LangChain 回调钩子**，挂在 `inference_engine._stream_llm_response()` 传入的 `lc_config["callbacks"]` 中。

```
inference_engine._stream_llm_response()
  └─ lc_config = {"callbacks": config.get("callbacks"), ...}
  └─ llm.astream(messages, config=lc_config)
       ├─ LangChain 模型: 触发 callbacks → on_llm_end() → handle_ai_message()
       │                                    → persist + _dispatch_block
       └─ LlamaCppChatModel: kwargs.pop("config", None) → callbacks 丢失 ❌
```

两种 LLM 路径：

| LLM 类型 | 模型实现 | 回调行为 | AI 消息入库 |
|----------|---------|----------|------------|
| **LangChain 模型**（cloud, `AdaptiveChatOpenAI`） | LangChain `BaseChatModel` | `lc_config["callbacks"]` 自动触发 | ✅ `handle_ai_message()` 执行 |
| **原生模型**（local, `LlamaCppChatModel`） | 自定义，非 LangChain | `config` 被 pop，callbacks 不触发 | ❌ 不入库、不推送 |

### 1.2 根因

`handle_ai_message()` 挂载在 LangChain 回调钩子上，而不是 LLM 执行结束后的统一后处理步骤。cloud 模型走 LangChain 所以正常，local 模型不走 LangChain 所以断掉。

### 1.3 方案：统一后处理

将 `handle_ai_message()` 从 `DatabaseCallbackHandler.on_llm_end()` 中移出，放到 `InferenceEngine._execute_llm_call()` 的返回值之后，作为 **LLM 执行的固有步骤**，无论模型类型都执行。

```
inference_engine._execute_llm_call()
  └─ response = await _stream_llm_response(...)       ← LLM 调用（任何模型）
  └─ _handle_ai_response(response, config)             ← 新增：统一后处理
       └─ handler.handle_ai_message(content, tool_calls, thinking, ...)
            ├─ persist(role="ai")                      ← 入库
            └─ _dispatch_block() → SSE/WS              ← 推送到前端
```

### 1.4 改动清单

| # | 文件 | 改动 | 职责 |
|---|------|------|------|
| 1 | `callbacks/database_logger.py` | `on_llm_end()` 中移除 `handle_ai_message()` 调用 | 不再负责 AI 消息落库 |
| 2 | `inference_engine.py` | `_execute_llm_call()` 末尾新增 `_handle_ai_response()` | 调用 `handler.handle_ai_message()` |
| 3 | `llamacpp_adapter.py` | 无需改动（`pop("config")` 保留，无影响） | — |
| 4 | `nodes/supervisor.py` | 无需额外改动 | `handle_ai_message` 已在引擎层执行 |

### 1.5 边界情况

| 场景 | 处理 |
|------|------|
| **ReAct 多步** | `run_react_loop()` 每次循环调用 `_execute_llm_call()` → 每次自动执行 `_handle_ai_response()` |
| **Tool calls** | `handle_ai_message(tool_calls=[...])` 正常处理，工具类消息按 `tool_calls` 参数判别 |
| **node_source** | 通过 `current_node_source.get()` 读取，已在 `engine.py:run_node()` 中设置 |
| **message_id 预分配** | 从 `DatabaseCallbackHandler.on_llm_start()` 移入引擎，`_execute_llm_call()` 中预分配 UUID |
| **单次调用 (`run_single_shot`)** | 同样在 `_execute_llm_call()` 后走 `_handle_ai_response()` |

### 1.6 不解决的问题

**Token 流式推送**（`TransparentCallbackHandler.on_llm_new_token()`）同样依赖 LangChain 回调，local 模型也无法触发。本重构只解决消息落库和最终推送的模型统一。实时流式推送需要 local 模型在 `astream()` 中手动触发 SSE 写入或调用 `MessageHandler.stream_token()`，作为独立优化项。

### 1.7 架构变化

```
改前:
  llm.astream() → LangChain 回调 → on_llm_end() → handle_ai_message()
                                                     ├─ persist
                                                     └─ _dispatch_block

改后:
  llm.astream() → response returned
                → _handle_ai_response(response, config)  ← 与模型无关
                  ├─ persist
                  └─ _dispatch_block
```

### 1.8 消息入库流程（重构后）

```
engine.py:run_node()
  └─ current_node_source.set(node_source)
  └─ inference_engine.run_react_loop()
       └─ for each step:
            └─ _execute_llm_call()
                 ├─ _stream_llm_response() → response
                 ├─ handler = config["message_handler"]
                 ├─ _handle_ai_response(response, handler)
                 │    ├─ 提取 content / tool_calls / thinking / metadata
                 │    ├─ handler.handle_ai_message(...)
                 │    │    ├─ persist(role="ai")
                 │    │    └─ _dispatch_block() → SSE/WS
                 │    └─ response.id = result.message_id
                 └─ return response
```

无论 Supervisor、Worker 还是 Finish 节点，无论 cloud 还是 local 模型，均走此统一路径。

---

