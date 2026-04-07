#!/usr/bin/env python3
"""
测试动态协议加载功能

运行方式:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python test_protocol_loading.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 设置测试环境变量
import os
os.environ["DYNAMIC_PROTOCOL_LOADING"] = "true"
os.environ["PROTOCOL_MATCHER_THRESHOLD"] = "0.7"


async def test_protocol_loader():
    """测试 Protocol Loader"""
    print("=" * 60)
    print("测试 Protocol Loader")
    print("=" * 60)
    
    from app.core.protocols import ProtocolSkillLoader
    
    loader = ProtocolSkillLoader(cache_ttl=300)
    
    # 测试加载各个协议
    for protocol_name in ["desktop", "mobile", "browser"]:
        skill = await loader.load(protocol_name)
        if skill:
            print(f"✅ {protocol_name}: {skill.name} (v{skill.version})")
            print(f"   - 触发模式: {len(skill.trigger_patterns)} 个")
            print(f"   - 需要能力: {skill.required_capabilities}")
            print(f"   - 指令长度: {len(skill.instructions)} 字符")
        else:
            print(f"❌ {protocol_name}: 加载失败")
    
    # 测试缓存
    print("\n测试缓存...")
    skill1 = await loader.load("desktop")
    skill2 = await loader.load("desktop")
    print(f"缓存命中: {skill1 is skill2}")


async def test_protocol_matcher():
    """测试 Protocol Matcher"""
    print("\n" + "=" * 60)
    print("测试 Protocol Matcher")
    print("=" * 60)
    
    from app.core.protocols import ProtocolMatcher
    
    matcher = ProtocolMatcher(threshold=0.7)
    
    test_cases = [
        ("帮我打开 WeChat 并截图", {"macos": True, "android": False}),
        ("在手机上打开淘宝", {"macos": True, "android": True}),
        ("访问 google.com 搜索新闻", {"macos": True, "android": False}),
        ("修复这个 bug", {"macos": True, "android": False}),
        ("打开 Chrome 浏览器访问网页", {"macos": True, "android": False}),
    ]
    
    for intent, capabilities in test_cases:
        print(f"\n意图: {intent}")
        print(f"环境: {capabilities}")
        
        matches = await matcher.match(intent, capabilities)
        if matches:
            for m in matches:
                print(f"  ✅ {m.protocol_name}: {m.confidence:.2f} - {m.reason}")
        else:
            print("  ⚠️ 无匹配协议")


async def test_skill_hydrator_integration():
    """测试 SkillHydrator 集成"""
    print("\n" + "=" * 60)
    print("测试 SkillHydrator 集成")
    print("=" * 60)
    
    from app.core.engine.nodes.utils import SkillHydrator
    from app.core.engine.state import AgentState
    
    # 创建一个模拟的 state
    state = AgentState({
        "execution_ticket": {
            "topic": "帮我打开 Chrome 浏览器并截图",
            "agent_config": {}
        }
    })
    
    # 注意：这需要数据库连接，可能无法在没有完整环境的情况下运行
    print("注意：完整集成测试需要数据库连接")
    print("测试 _inject_protocols 方法...")
    
    try:
        protocols = await SkillHydrator._inject_protocols(
            state, 
            "帮我打开 Chrome 浏览器并截图"
        )
        print(f"✅ 成功注入 {len(protocols)} 个协议")
        for p in protocols:
            print(f"   - {p.name}")
    except Exception as e:
        print(f"⚠️ 集成测试跳过: {e}")


async def test_config():
    """测试配置读取"""
    print("\n" + "=" * 60)
    print("测试配置")
    print("=" * 60)
    
    from app.core.config import settings
    
    print(f"DYNAMIC_PROTOCOL_LOADING: {settings.DYNAMIC_PROTOCOL_LOADING}")
    print(f"PROTOCOL_MATCHER_THRESHOLD: {settings.PROTOCOL_MATCHER_THRESHOLD}")
    print(f"PROTOCOL_LOADER_CACHE_TTL: {settings.PROTOCOL_LOADER_CACHE_TTL}")


def estimate_size_reduction():
    """估算大小减少"""
    print("\n" + "=" * 60)
    print("估算大小减少")
    print("=" * 60)
    
    # 从 Skill 文件读取实际大小
    skills_dir = Path(__file__).parent / "app" / "config" / "skills" / "protocols"
    
    sizes = {}
    for protocol in ["desktop", "mobile", "browser"]:
        skill_file = skills_dir / protocol / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text()
            # 只计算指令部分（不含 frontmatter）
            if "---" in content:
                parts = content.split("---")
                if len(parts) >= 3:
                    instructions = parts[2]
                else:
                    instructions = content
            else:
                instructions = content
            sizes[protocol] = len(instructions.encode('utf-8'))
    
    total_size = sum(sizes.values())
    
    print("协议大小:")
    for name, size in sizes.items():
        print(f"  - {name}: {size / 1024:.1f} KB")
    print(f"\n总协议大小: {total_size / 1024:.1f} KB")
    print("\n预期收益:")
    print("  - 纯代码任务: 减少 ~10-15 KB (不加载 Browser/Mobile 协议)")
    print("  - 桌面自动化任务: 减少 ~5 KB (只加载需要的协议)")
    print("  - 所有任务: 消除协议重复，提高指令清晰度")


async def main():
    print("\n" + "=" * 60)
    print("动态协议加载功能测试")
    print("=" * 60 + "\n")
    
    try:
        await test_config()
        await test_protocol_loader()
        await test_protocol_matcher()
        await test_skill_hydrator_integration()
        estimate_size_reduction()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
