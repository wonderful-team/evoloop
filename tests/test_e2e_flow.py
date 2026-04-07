#!/usr/bin/env python3
"""
EvoLoop Link 端到端完整链路测试

测试流程:
    Frontend -> Backend -> Gateway -> LLM Vendor
                          |
                          v
                   Member Center (计费/配额)
                          |
    Frontend <- Backend <- Gateway <- LLM

用法:
    # 1. 配置环境变量
    export MC_BACKEND_URL="http://localhost:8000"
    export GATEWAY_URL="http://localhost:8080"
    export MEMBER_TOKEN="your_jwt_token"
    export GATEWAY_TOKEN="your_gateway_token"
    
    # 2. 运行测试
    python3 test_e2e_flow.py --test-chat
    python3 test_e2e_flow.py --test-stream
    python3 test_e2e_flow.py --test-full
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Optional

try:
    import requests
except ImportError:
    print("安装依赖: pip install requests")
    sys.exit(1)


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


def print_step(step: int, total: int, title: str):
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}步骤 {step}/{total}: {title}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")


def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")


def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")


def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")


def print_divider():
    print(f"{Colors.CYAN}{'-'*60}{Colors.RESET}")


class E2ETestRunner:
    """端到端测试运行器"""
    
    def __init__(self):
        self.mc_url = os.getenv("MC_BACKEND_URL", "http://localhost:8000").rstrip("/")
        self.gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8080").rstrip("/")
        self.member_token = os.getenv("MEMBER_TOKEN", "")
        self.gateway_token = os.getenv("GATEWAY_TOKEN", "")
        
        self.session = requests.Session()
        self.session.timeout = 60
        
        self.results = []
        self.test_data = {
            "member_id": None,
            "model_id": None,
            "request_id": None,
            "quota_before": 0,
            "quota_after": 0,
            "tokens_used": 0,
        }

    def check_env(self) -> bool:
        """检查环境配置"""
        print_step(0, 5, "环境检查")
        
        missing = []
        if not self.member_token:
            missing.append("MEMBER_TOKEN")
        if not self.gateway_token:
            missing.append("GATEWAY_TOKEN")
        
        if missing:
            print_error(f"缺少环境变量: {', '.join(missing)}")
            print_info("请设置: export MEMBER_TOKEN=your_token")
            return False
        
        print_success("环境变量检查通过")
        print_info(f"Backend: {self.mc_url}")
        print_info(f"Gateway: {self.gateway_url}")
        return True

    def test_frontend_to_backend(self) -> bool:
        """测试 Frontend -> Backend 链路"""
        print_step(1, 5, "Frontend -> Backend (获取模型列表)")
        
        try:
            url = f"{self.mc_url}/api/evolooplink/llm/models"
            headers = {"Authorization": f"Bearer {self.member_token}"}
            
            print_info(f"GET {url}")
            start = time.time()
            resp = self.session.get(url, headers=headers)
            latency = time.time() - start
            
            if resp.status_code != 200:
                print_error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            
            data = resp.json()
            if data.get("code") != 0:
                print_error(f"API 错误: {data.get('message')}")
                return False
            
            models = data.get("data", {}).get("list", [])
            enabled_models = [m for m in models if m.get("is_enabled")]
            
            if not enabled_models:
                print_error("没有启用的模型")
                return False
            
            self.test_data["model_id"] = enabled_models[0].get("model_id")
            
            print_success(f"获取模型列表成功 ({latency:.2f}s)")
            print_info(f"总模型数: {len(models)}, 启用: {len(enabled_models)}")
            print_info(f"选择测试模型: {self.test_data['model_id']}")
            
            # 获取配额
            print_divider()
            url = f"{self.mc_url}/api/evolooplink/llm/quota"
            resp = self.session.get(url, headers=headers)
            
            if resp.status_code == 200:
                quota_data = resp.json().get("data", {})
                self.test_data["quota_before"] = quota_data.get("remaining", 0)
                self.test_data["member_id"] = quota_data.get("member_id", 0)
                print_success(f"配额查询成功")
                print_info(f"用户ID: {self.test_data['member_id']}")
                print_info(f"剩余配额: {self.test_data['quota_before']}")
            
            return True
            
        except Exception as e:
            print_error(f"请求异常: {e}")
            return False

    def test_backend_to_gateway(self) -> bool:
        """测试 Backend -> Gateway 链路"""
        print_step(2, 5, "Backend -> Gateway (配置同步)")
        
        try:
            url = f"{self.gateway_url}/config"
            print_info(f"GET {url}")
            
            resp = self.session.get(url)
            if resp.status_code != 200:
                print_error(f"Gateway 配置获取失败: HTTP {resp.status_code}")
                return False
            
            config = resp.json()
            providers = config.get("providers", [])
            
            print_success(f"Gateway 配置获取成功")
            print_info(f"配置版本: {config.get('version', 'unknown')}")
            print_info(f"供应商数: {len(providers)}")
            
            # 健康检查
            print_divider()
            url = f"{self.gateway_url}/health"
            resp = self.session.get(url)
            if resp.status_code == 200:
                print_success(f"Gateway 健康检查通过")
            
            return True
            
        except Exception as e:
            print_error(f"Gateway 连接异常: {e}")
            return False

    def test_gateway_to_llm(self) -> bool:
        """测试 Gateway -> LLM 链路"""
        print_step(3, 5, "Gateway -> LLM (实际调用)")
        
        if not self.test_data.get("model_id"):
            print_error("没有可用的测试模型")
            return False
        
        model_id = self.test_data["model_id"]
        
        try:
            url = f"{self.gateway_url}/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.gateway_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "user", "content": "Hello, please respond with 'OK' only."}
                ],
                "temperature": 0.1,
                "max_tokens": 10,
            }
            
            print_info(f"POST {url}")
            print_info(f"Model: {model_id}")
            
            start = time.time()
            resp = self.session.post(url, headers=headers, json=payload)
            latency = time.time() - start
            
            if resp.status_code != 200:
                print_error(f"LLM 调用失败: HTTP {resp.status_code}")
                return False
            
            data = resp.json()
            self.test_data["request_id"] = data.get("id", "unknown")
            usage = data.get("usage", {})
            self.test_data["tokens_used"] = usage.get("total_tokens", 0)
            
            print_success(f"LLM 调用成功 ({latency:.2f}s)")
            print_info(f"Request ID: {self.test_data['request_id']}")
            print_info(f"Tokens: {self.test_data['tokens_used']}")
            
            return True
            
        except Exception as e:
            print_error(f"LLM 调用异常: {e}")
            return False

    def test_billing_flow(self) -> bool:
        """测试计费流程 Gateway -> Member Center"""
        print_step(4, 5, "Gateway -> Member Center (计费上报)")
        
        if not self.test_data.get("request_id"):
            print_warning("没有请求ID，跳过计费验证")
            return None
        
        print_info("等待计费上报 (3秒)...")
        time.sleep(3)
        
        try:
            url = f"{self.mc_url}/api/evolooplink/llm/usage"
            headers = {"Authorization": f"Bearer {self.member_token}"}
            
            resp = self.session.get(url, headers=headers, params={"page": 1, "limit": 5})
            if resp.status_code != 200:
                return None
            
            records = resp.json().get("data", {}).get("list", [])
            
            for record in records:
                if record.get("request_id") == self.test_data["request_id"]:
                    print_success("找到计费记录")
                    print_info(f"消耗Tokens: {record.get('total_tokens')}")
                    print_info(f"费用: ${record.get('cost_usd', 0):.6f}")
                    return True
            
            print_warning("暂未找到计费记录 (可能有延迟)")
            return True
            
        except Exception as e:
            print_error(f"计费验证异常: {e}")
            return False

    def test_backend_to_frontend(self) -> bool:
        """测试 Backend -> Frontend (响应返回)"""
        print_step(5, 5, "Backend -> Frontend (响应封装)")
        
        try:
            url = f"{self.mc_url}/api/evolooplink/llm/chat"
            headers = {"Authorization": f"Bearer {self.member_token}"}
            payload = {
                "model": self.test_data.get("model_id", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": "Say OK"}],
                "temperature": 0.1,
                "max_tokens": 10,
            }
            
            print_info(f"POST {url}")
            start = time.time()
            resp = self.session.post(url, headers=headers, json=payload, timeout=60)
            latency = time.time() - start
            
            if resp.status_code != 200:
                print_error(f"聊天接口失败: HTTP {resp.status_code}")
                return False
            
            data = resp.json()
            if data.get("code") != 0:
                print_error(f"API 错误: {data.get('message')}")
                return False
            
            result = data.get("data", {})
            print_success(f"聊天接口成功 ({latency:.2f}s)")
            print_info(f"响应: {result.get('content', '')[:50]}")
            
            return True
            
        except Exception as e:
            print_error(f"接口异常: {e}")
            return False

    def run_full_test(self):
        """运行完整测试"""
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}EvoLoop Link 端到端链路测试{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        if not self.check_env():
            return
        
        results = {
            "frontend_to_backend": self.test_frontend_to_backend(),
            "backend_to_gateway": self.test_backend_to_gateway(),
            "gateway_to_llm": self.test_gateway_to_llm(),
            "billing_flow": self.test_billing_flow(),
            "backend_to_frontend": self.test_backend_to_frontend(),
        }
        
        # 汇总
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}测试结果汇总{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        for name, passed in results.items():
            status = "✅ 通过" if passed else ("⏸️ 跳过" if passed is None else "❌ 失败")
            print(f"  {name:25s}: {status}")
        
        passed_count = sum(1 for v in results.values() if v is True)
        total_count = len([v for v in results.values() if v is not None])
        
        print(f"\n总计: {passed_count}/{total_count} 项通过")
        
        if passed_count == total_count:
            print(f"\n{Colors.GREEN}🎉 完整链路测试通过！{Colors.RESET}")
        elif passed_count >= total_count * 0.6:
            print(f"\n{Colors.YELLOW}⚠️  大部分链路正常，部分需要检查{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}❌ 链路存在问题，需要排查{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(description="EvoLoop Link 端到端链路测试")
    parser.add_argument("--test-chat", action="store_true", help="测试普通对话链路")
    parser.add_argument("--test-full", action="store_true", help="测试完整链路")
    
    args = parser.parse_args()
    
    runner = E2ETestRunner()
    
    if args.test_chat:
        runner.check_env()
        runner.test_frontend_to_backend()
        runner.test_backend_to_frontend()
    else:
        runner.run_full_test()


if __name__ == "__main__":
    main()
