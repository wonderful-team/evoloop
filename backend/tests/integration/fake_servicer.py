"""进程内假客服 MCP servicer（stdio），用于集成测试模拟收/发消息与断连。

状态存共享 JSON（消息队列 + 已发回复），由测试进程写入/读取。

用法：python fake_servicer.py <state.json>
"""

import json
import os
import sys
import threading
import time

from mcp.server.fastmcp import FastMCP

STATE_FILE = sys.argv[1]

mcp = FastMCP("fake-kf-servicer")


def _load():
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


@mcp.tool()
async def kf_list_new_messages(site_id: int = 1, limit: int = 20) -> dict:
    """模拟企微客服拉取未处理消息。"""
    del site_id
    st = _load()
    msgs = [m for m in st["messages"] if not m.get("processed")]
    return {"count": len(msgs), "messages": msgs[:limit]}


@mcp.tool()
async def kf_mark_processed(ids: str) -> dict:
    """模拟标记已处理。"""
    id_set = {int(x) for x in ids.split(",") if x.strip()}
    st = _load()
    for m in st["messages"]:
        if m["id"] in id_set:
            m["processed"] = 1
    _save(st)
    return {"success": True, "marked": len(id_set)}


@mcp.tool()
async def kf_send_text(external_userid: str, open_kfid: str, content: str, site_id: int = 1) -> dict:
    """模拟发送客服回复。"""
    del open_kfid, site_id
    st = _load()
    st["sent"].append({"external_userid": external_userid, "content": content})
    _save(st)
    return {"success": True, "msgid": f"out-{len(st['sent'])}"}


@mcp.tool()
async def kf_die() -> str:
    """模拟远程进程崩溃/关闭连接（供测试杀服务）。"""

    def _exit_later():
        time.sleep(0.1)
        os._exit(0)

    threading.Thread(target=_exit_later, daemon=True).start()
    return "dying"


if __name__ == "__main__":
    mcp.run()
