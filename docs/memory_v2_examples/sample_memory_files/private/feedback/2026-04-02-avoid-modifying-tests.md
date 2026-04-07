---
id: mem_fb_001
type: feedback
privacy: private
title: 避免修改测试文件
created_at: '2026-04-02T10:00:00Z'
updated_at: '2026-04-02T10:00:00Z'
version: 1
tags:
- testing
- feedback
- constraints
source: extracted
confidence: 0.92
source_thread_id: thread_456
source_message_id: msg_789
---

## 用户反馈：不要修改测试文件

在一次代码重构会话中，用户明确指示：

> "请不要修改测试文件，只修改源代码。"

### 背景

在重构 `app/core/engine/tasks.py` 时，AI 尝试同时更新相关的测试文件。用户纠正了这一行为，强调测试文件应该保持独立，修改应该仅针对源代码。

### 指导原则

1. **测试隔离**：测试文件反映了预期的行为契约，不应随意修改
2. **源代码优先**：重构和改进应集中在源代码
3. **例外情况**：只有在明确请求时才协助更新测试

### 相关上下文

- 涉及文件：`tests/unit/core/test_tasks.py`
- 涉及功能：Celery 任务执行
