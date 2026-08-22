"""MCP 微信客服值守渠道（经项目配置的 MCP server 接入商城）。

与 ``wecom/``（本地企微客户端 GUI 轮巡）并行，二者可同时启用：
- callback 渠道只处理商城"微信客服 API"的客户咨询消息（direction=0），
  与 GUI 的本地客户端未读天然不同源，互不冲突。
- 依赖的 MCP server 名由项目配置 ``callback.mcp_server`` 指定，不在代码写死。
"""

from app.core.channel.duty.mcp_kf.mcp_kf_channel import MpcKfChannel

__all__ = ["MpcKfChannel"]
