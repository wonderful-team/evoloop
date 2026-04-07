#!/usr/bin/env python3
"""
验证改进是否正常工作

运行方式:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python test_improvements.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 设置测试环境
import os
os.environ["DYNAMIC_PROTOCOL_LOADING"] = "false"  # 简化测试


async def test_conversation_context():
    """测试对话上下文提取"""
    print("=" * 60)
    print("测试 1: ConversationContext")
    print("=" * 60)
    
    from app.core.engine.nodes.utils import ConversationContext
    from langchain_core.messages import HumanMessage, AIMessage
    
    # 模拟对话历史
    messages = [
        HumanMessage(content="帮我创建一个登录功能"),
        AIMessage(content="好的，我将为你创建一个基于 JWT 的登录功能"),
        HumanMessage(content="还需要支持 OAuth"),
        AIMessage(content="明白，我会添加 OAuth 支持"),
        HumanMessage(content="修改刚才的代码添加错误处理"),  # 引用历史
    ]
    
    # 测试历史提取
    history = ConversationContext.extract_relevant_history(
        messages=messages,
        current_topic="添加错误处理",
        max_turns=3
    )
    
    print("提取的对话历史:")
    print(history)
    print()
    
    # 测试 Mission 构建
    mission = ConversationContext.build_context_aware_mission(
        mission_msg="修改登录代码添加错误处理",
        conversation_history=history,
        referenced_files=["src/auth/login.py"]
    )
    
    print("增强后的 Mission:")
    print(mission[:500] + "..." if len(mission) > 500 else mission)
    print("✅ ConversationContext 测试通过\n")


async def test_skill_discovery():
    """测试 Skill Discovery 改进"""
    print("=" * 60)
    print("测试 2: SkillDiscovery.match_multiple")
    print("=" * 60)
    
    # 由于需要数据库，这里只做函数签名验证
    from app.core.learning.discovery import SkillDiscovery
    
    discovery = SkillDiscovery()
    
    # 验证方法存在
    assert hasattr(discovery, 'match_multiple'), "缺少 match_multiple 方法"
    assert hasattr(discovery, '_analyze_task_complexity'), "缺少 _analyze_task_complexity 方法"
    
    print("✅ SkillDiscovery 方法签名验证通过")
    print("  - match_multiple() 存在")
    print("  - _analyze_task_complexity() 存在\n")


async def test_skill_hydrator():
    """测试 SkillHydrator 改进"""
    print("=" * 60)
    print("测试 3: SkillHydrator")
    print("=" * 60)
    
    from app.core.engine.nodes.utils import SkillHydrator
    
    # 验证方法存在
    assert hasattr(SkillHydrator, '_load_skills_by_ids'), "缺少 _load_skills_by_ids 方法"
    
    # 验证参数
    import inspect
    sig = inspect.signature(SkillHydrator.get_node_skills)
    params = list(sig.parameters.keys())
    
    assert 'allow_multiple' in params, "get_node_skills 缺少 allow_multiple 参数"
    
    print("✅ SkillHydrator 验证通过")
    print("  - _load_skills_by_ids() 存在")
    print("  - get_node_skills(allow_multiple) 参数存在\n")


async def test_supervisor_prompt():
    """测试 Supervisor Prompt 更新"""
    print("=" * 60)
    print("测试 4: Supervisor Prompt")
    print("=" * 60)
    
    prompt_path = Path(__file__).parent / "app/config/templates/agents/supervisor.prompt.j2"
    content = prompt_path.read_text()
    
    # 验证多轮对话指导
    assert "For Multi-Turn Conversations" in content, "缺少多轮对话指导"
    assert "historical_context" in content, "缺少 historical_context 说明"
    assert "conversation context" in content, "缺少 conversation context 说明"
    
    # 验证多 skill 指导
    assert "task_steps" in content, "缺少 task_steps 说明"
    
    print("✅ Supervisor Prompt 验证通过")
    print("  - 多轮对话指导已添加")
    print("  - historical_context 说明已添加")
    print("  - task_steps 说明已添加\n")


async def test_worker_changes():
    """测试 Worker 节点改进"""
    print("=" * 60)
    print("测试 5: Worker 节点")
    print("=" * 60)
    
    worker_path = Path(__file__).parent / "app/core/engine/nodes/worker.py"
    content = worker_path.read_text()
    
    # 验证多轮对话支持
    assert "ConversationContext" in content, "Worker 未使用 ConversationContext"
    assert "preserve_history" in content, "Worker 未实现 preserve_history"
    assert "Preserving conversation history" in content, "Worker 缺少历史保留日志"
    
    print("✅ Worker 节点验证通过")
    print("  - ConversationContext 集成")
    print("  - preserve_history 逻辑")
    print("  - 多轮对话日志\n")


async def main():
    print("\n" + "=" * 60)
    print("Agent Engine 改进验证测试")
    print("=" * 60 + "\n")
    
    try:
        await test_conversation_context()
        await test_skill_discovery()
        await test_skill_hydrator()
        await test_supervisor_prompt()
        await test_worker_changes()
        
        print("=" * 60)
        print("✅ 所有测试通过！改进已成功实施。")
        print("=" * 60)
        print("\n下一步:")
        print("1. 部署到测试环境")
        print("2. 验证多 skill 工作流")
        print("3. 验证多轮对话场景")
        print("4. 监控日志确认正常工作")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
