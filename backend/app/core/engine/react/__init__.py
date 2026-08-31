"""React engine package — single-Agent ReAct loop (OpenCode-style).

替代图引擎（supervisor/worker/finish + signals + routers）的执行编排层：
- 主 Agent 一条连续消息流 ReAct 循环
- `task` 工具按需 spawn 子代理（隔离上下文）/ A2A 远程委派
- `skill` / `macro` 工具按需加载一等公民能力
- completion 收尾管线（记忆 / 宏 / skill 学习闭环）

单 Agent ReAct 是唯一执行体；图引擎代码已整体移除，无模式切换。
"""
