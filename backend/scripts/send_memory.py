#!/usr/bin/env python3
"""模拟 Mobile 通过 Gateway 触发记忆操作（WS 命令下发到 Desktop Agent）."""

import argparse
import time

import requests


def login_mc(mc_url: str, username: str, password: str) -> str:
    url = f"{mc_url.rstrip('/')}/api/login/login"
    resp = requests.post(url, json={"username": username, "password": password}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in (200, 0, "200", "0"):
        raise RuntimeError(f"MC 登录失败: {data}")
    token = data.get("data", {}).get("token") or data.get("token")
    if not token:
        raise RuntimeError(f"MC 登录响应中无 token: {data}")
    return token


def main():
    parser = argparse.ArgumentParser(description="通过 Gateway 触发记忆操作（WS 命令下发到 Desktop Agent）")
    parser.add_argument("--gateway", default="http://192.168.3.21:9001")
    parser.add_argument("--mc-url", default="http://192.168.3.21:9002")
    parser.add_argument("--username", default="preterchan")
    parser.add_argument("--password", default="hellomylife")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--device-key", default="evo_0b080f3dc88f40d3b68b64d2fc0fac03")
    parser.add_argument("--action", choices=["add", "update", "delete", "list"], default="add")
    parser.add_argument("--name", default="从对话学习")
    parser.add_argument("--text", default="请记住这条消息")
    parser.add_argument("--thread-id", default="thread_test")
    parser.add_argument("--message-id", default="msg_test")
    args = parser.parse_args()

    token = login_mc(args.mc_url, args.username, args.password)
    headers = {"Authorization": f"Bearer {token}"}

    if args.action == "list":
        resp = requests.get(
            f"{args.gateway.rstrip('/')}/api/v1/memory/concepts",
            params={"project_id": args.project_id},
            headers=headers,
            timeout=10,
        )
    elif args.action == "delete":
        resp = requests.post(
            f"{args.gateway.rstrip('/')}/api/v1/command/send",
            json={
                "device_key": args.device_key,
                "command_type": "memory_delete",
                "thread_id": f"memory_{int(time.time() * 1000)}",
                "project_id": args.project_id,
                "content": {"name": args.name},
            },
            headers=headers,
            timeout=10,
        )
    elif args.action == "update":
        resp = requests.post(
            f"{args.gateway.rstrip('/')}/api/v1/command/send",
            json={
                "device_key": args.device_key,
                "command_type": "memory_update",
                "thread_id": f"memory_{int(time.time() * 1000)}",
                "project_id": args.project_id,
                "content": {
                    "name": args.name,
                    "description": args.text,
                    "related_files": [],
                },
            },
            headers=headers,
            timeout=10,
        )
    else:  # add
        resp = requests.post(
            f"{args.gateway.rstrip('/')}/api/v1/command/send",
            json={
                "device_key": args.device_key,
                "command_type": "memory_add",
                "thread_id": f"memory_{int(time.time() * 1000)}",
                "project_id": args.project_id,
                "content": {
                    "name": args.name,
                    "description": args.text,
                    "related_files": [],
                    "source_message_id": args.message_id,
                    "source_thread_id": args.thread_id,
                },
            },
            headers=headers,
            timeout=10,
        )

    print(f"status={resp.status_code}")
    print(resp.text)

    if args.action != "list":
        print("\n等待 Agent 执行并同步回 Gateway...")
        time.sleep(2)
        list_resp = requests.get(
            f"{args.gateway.rstrip('/')}/api/v1/memory/concepts",
            params={"project_id": args.project_id},
            headers=headers,
            timeout=10,
        )
        print("list after action:")
        print(list_resp.text)


if __name__ == "__main__":
    main()
