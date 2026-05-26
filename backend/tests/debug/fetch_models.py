#!/usr/bin/env python3
"""
查询各 LLM 供应商实际可用的模型列表
支持: OpenAI, Anthropic, Google Gemini, DeepSeek, Moonshot/Kimi, Qwen, SiliconFlow

用法:
    python fetch_models.py --provider openai --api-key sk-xxx
    python fetch_models.py --provider gemini --api-key xxx
    python fetch_models.py --all  # 从环境变量读取所有配置

环境变量:
    OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY,
    MOONSHOT_API_KEY, QWEN_API_KEY, SILICONFLOW_API_KEY
"""

import argparse
import os
import sys
from typing import Optional
import json

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)


class ModelFetcher:
    """模型列表获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30

    def fetch_openai_compatible(self, base_url: str, api_key: str, provider_name: str) -> list:
        """获取 OpenAI 兼容格式的模型列表"""
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        try:
            resp = self.session.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for m in data.get("data", []):
                models.append({
                    "id": m.get("id"),
                    "object": m.get("object"),
                    "created": m.get("created"),
                    "owned_by": m.get("owned_by"),
                })
            return models
        except Exception as e:
            print(f"❌ {provider_name} 获取失败: {e}")
            return []

    def fetch_gemini(self, api_key: str) -> list:
        """获取 Google Gemini 模型列表"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            models = []
            for m in data.get("models", []):
                models.append({
                    "id": m.get("name", "").replace("models/", ""),
                    "display_name": m.get("displayName"),
                    "description": m.get("description"),
                    "version": m.get("version"),
                    "supported_actions": m.get("supportedGenerationMethods", []),
                    "input_token_limit": m.get("inputTokenLimit"),
                    "output_token_limit": m.get("outputTokenLimit"),
                })
            return models
        except Exception as e:
            print(f"❌ Gemini 获取失败: {e}")
            return []

    def fetch_anthropic(self, api_key: str) -> list:
        """获取 Anthropic Claude 模型列表
        Anthropic 没有公开的 /models 接口，返回已知模型
        """
        # Anthropic 没有模型列表 API，使用已知的模型 ID
        known_models = [
            {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus", "context": 200000},
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet", "context": 200000},
            {"id": "claude-3-5-sonnet-20240620", "display_name": "Claude 3.5 Sonnet (Old)", "context": 200000},
            {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku", "context": 200000},
            {"id": "claude-3-sonnet-20240229", "display_name": "Claude 3 Sonnet", "context": 200000},
        ]
        
        # 尝试验证 API Key 是否有效
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            # 只验证 key，不真正调用
            resp = self.session.post(url, headers=headers, json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}]
            })
            if resp.status_code == 401:
                print(f"❌ Anthropic API Key 无效")
                return []
        except Exception as e:
            print(f"⚠️ Anthropic API Key 验证失败: {e}")
        
        print(f"ℹ️ Anthropic 没有公开的模型列表 API，返回已知模型")
        return known_models

    def print_models(self, provider: str, models: list):
        """打印模型列表"""
        if not models:
            return
        
        print(f"\n{'='*60}")
        print(f"📦 {provider} - 共 {len(models)} 个模型")
        print(f"{'='*60}")
        
        for i, m in enumerate(models[:50], 1):  # 最多显示50个
            model_id = m.get("id", "unknown")
            display = m.get("display_name", "")
            owned = m.get("owned_by", "")
            
            info_parts = []
            if display and display != model_id:
                info_parts.append(f"display: {display}")
            if owned:
                info_parts.append(f"owner: {owned}")
            if m.get("context"):
                info_parts.append(f"context: {m['context']}")
            if m.get("input_token_limit"):
                info_parts.append(f"input: {m['input_token_limit']}")
            
            info = " | ".join(info_parts)
            if info:
                print(f"  {i:2}. {model_id} ({info})")
            else:
                print(f"  {i:2}. {model_id}")
        
        if len(models) > 50:
            print(f"  ... 还有 {len(models) - 50} 个模型")


def main():
    parser = argparse.ArgumentParser(description="查询 LLM 供应商的可用模型")
    parser.add_argument("--provider", choices=[
        "openai", "anthropic", "gemini", "deepseek", 
        "moonshot", "kimi", "qwen", "siliconflow"
    ], help="供应商名称")
    parser.add_argument("--api-key", help="API Key")
    parser.add_argument("--base-url", help="自定义 Base URL")
    parser.add_argument("--all", action="store_true", help="查询所有配置的环境变量")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    
    args = parser.parse_args()
    
    fetcher = ModelFetcher()
    
    # 查询所有
    if args.all:
        configs = [
            ("OpenAI", "openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
            ("Anthropic", "anthropic", None, "ANTHROPIC_API_KEY"),
            ("Gemini", "gemini", None, "GEMINI_API_KEY"),
            ("DeepSeek", "deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
            ("Moonshot/Kimi", "kimi", "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"),
            ("Qwen", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY"),
            ("SiliconFlow", "siliconflow", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"),
        ]
        
        all_results = {}
        for name, key, default_url, env_var in configs:
            api_key = os.getenv(env_var)
            if not api_key:
                print(f"\n⚠️ {name}: 未设置环境变量 {env_var}")
                continue
            
            print(f"\n🔍 正在查询 {name}...")
            
            if key == "gemini":
                models = fetcher.fetch_gemini(api_key)
            elif key == "anthropic":
                models = fetcher.fetch_anthropic(api_key)
            else:
                base_url = args.base_url or default_url
                models = fetcher.fetch_openai_compatible(base_url, api_key, name)
            
            all_results[name] = models
            fetcher.print_models(name, models)
        
        if args.json:
            print("\n" + json.dumps(all_results, indent=2, ensure_ascii=False))
        
        return
    
    # 查询单个
    if not args.provider:
        parser.print_help()
        return
    
    # 获取 API Key
    api_key = args.api_key
    if not api_key:
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "kimi": "MOONSHOT_API_KEY",
            "qwen": "QWEN_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
        }
        api_key = os.getenv(env_map.get(args.provider, ""))
    
    if not api_key:
        print(f"❌ 请提供 --api-key 或设置环境变量")
        sys.exit(1)
    
    # 获取模型列表
    if args.provider == "gemini":
        models = fetcher.fetch_gemini(api_key)
    elif args.provider == "anthropic":
        models = fetcher.fetch_anthropic(api_key)
    elif args.provider in ["openai", "deepseek", "moonshot", "kimi", "qwen", "siliconflow"]:
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "moonshot": "https://api.moonshot.cn/v1",
            "kimi": "https://api.moonshot.cn/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "siliconflow": "https://api.siliconflow.cn/v1",
        }
        base_url = args.base_url or default_urls.get(args.provider)
        models = fetcher.fetch_openai_compatible(base_url, api_key, args.provider)
    else:
        print(f"❌ 不支持的供应商: {args.provider}")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(models, indent=2, ensure_ascii=False))
    else:
        fetcher.print_models(args.provider.upper(), models)


if __name__ == "__main__":
    main()
