import os
import sys
import json
import urllib.request
import urllib.error

def test_dashscope_urllib(api_key, base_url, model):
    """
    使用 Python 标准库 urllib 进行测试（无需安装任何第三方库，如 openai 或 httpx）
    """
    print(f"\n--- 正在使用 Python 标准库 (urllib) 进行测试 ---")
    
    # 拼接 Chat Completions API 路径
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好，这是一次测试连接的请求。如果收到了请回复：'连接成功！'"}
        ],
        "temperature": 0.1
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        print(f"发送请求至: {url}")
        print(f"使用模型: {model}")
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            content = res_json["choices"][0]["message"]["content"]
            print("\n[测试成功！] 接口返回内容:")
            print(content)
            return True
    except urllib.error.HTTPError as e:
        print(f"\n[测试失败] 发生 HTTP 错误，状态码: {e.code}")
        try:
            error_detail = e.read().decode("utf-8")
            print(f"错误详情: {error_detail}")
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"\n[测试失败] 发生异常: {e}")
        return False

def test_dashscope_openai(api_key, base_url, model):
    """
    尝试使用 openai 官方库进行测试（如果已安装）
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("\n未检测到 `openai` 库，跳过 OpenAI SDK 测试。")
        return None

    print(f"\n--- 正在使用 openai 官方 SDK 进行测试 ---")
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        print(f"发送请求至: {base_url}/chat/completions")
        print(f"使用模型: {model}")
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "你好，这是一次测试连接的请求"}
            ],
            temperature=0.1
        )
        print("\n[测试成功！] 接口返回内容:")
        print(completion.choices[0].message.content)
        return True
    except Exception as e:
        print(f"\n[测试失败] SDK 调用发生异常: {e}")
        return False

if __name__ == "__main__":
    # 1. 尝试从环境变量或 .env 读取
    api_key = "sk-sp-D.HYHDL.MlVv.MEUCIQD4lQoovJZ/Cdt3x7X8p3TOVZEFCl89kxeVbEYH97gVagIgLTIKbq60MSRIec27mM8qfOs4WMYSAouA4086HP2vplc="
    base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    model = "deepseek-v4-flash"

    print("==================================================")
    print("      DashScope Token Plan 团队版连接测试工具     ")
    print("==================================================")

    # 如果没有读取到，提示输入
    if not api_key:
        print("\n未在环境变量中检测到 API Key，请手动输入：")
        api_key = input("请输入您的 API Key (以 sk-sp- 开头): ").strip()

    if not api_key:
        print("错误: API Key 不能为空，退出测试。")
        sys.exit(1)

    print(f"\n当前配置:")
    print(f"  - API Key:  {api_key[:8]}...{api_key[-6:] if len(api_key) > 14 else ''}")
    print(f"  - Base URL: {base_url}")
    print(f"  - Model:    {model}")

    # 优先执行标准库测试，确保 100% 可运行
    success = test_dashscope_urllib(api_key, base_url, model)
    
    # 尝试使用 OpenAI 库测试（若有）
    test_dashscope_openai(api_key, base_url, model)
    
    print("\n==================================================")
    if success:
        print("【结论】您的 Token Plan 团队版接口可以正常连通！")
    else:
        print("【结论】接口测试失败，请检查 API Key、Base URL 或网络连接。")
    print("==================================================")
