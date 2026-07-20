#!/usr/bin/env python3
"""模拟 Mobile 通过 Gateway 发送 conversation_delete 命令到 Desktop Agent."""

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://192.168.3.21:9001")
    parser.add_argument("--mc-url", default="http://192.168.3.21:9002")
    parser.add_argument("--username", default="preterchan")
    parser.add_argument("--password", default="hellomylife")
    parser.add_argument("--device-key", default="evo_0b080f3dc88f40d3b68b64d2fc0fac03")
    parser.add_argument("--thread-id", default="test-lifecycle12-1783042467")
    args = parser.parse_args()

    token = login_mc(args.mc_url, args.username, args.password)

    payload = {
        "device_key": args.device_key,
        "command_type": "conversation_delete",
        "thread_id": args.thread_id,
        "content": {},
    }

    resp = requests.post(
        f"{args.gateway.rstrip('/')}/api/v1/command/send",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print(f"status={resp.status_code}")
    print(resp.text)


if __name__ == "__main__":
    main()
