import asyncio
import os
import sys

# 将项目根目录添加到系统路径
sys.path.append(os.getcwd())

from app.core.learning.discovery import skill_discovery
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from sqlalchemy import select

async def test_my_semantic_discovery():
    """
    EvoLoop 语义检索测试脚本
    用于验证跨语言（中文指令 -> 英文 SOP）的召回能力
    """
    print("="*50)
    print("🚀 EvoLoop 语义检索测试")
    print("="*50)

    # 1. 检查数据库中已同步的技能
    async with session_scope() as db:
        stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
        result = await db.execute(stmt)
        skills = result.scalars().all()
        
        print(f"📊 数据库统计:")
        print(f"   - 活跃技能总数: {len(skills)}")
        
        if len(skills) == 0:
            print("\n❌ 警告: 数据库中没有发现技能数据，请检查 SOP 所在的文件夹。")
            return

    # 2. 定义测试用例 (涵盖不同领域，使用抽象或间接表达)
    test_queries = [
        # 跨领域 (Cross-App)
        "协助我将网络终端的数据同步到第三方通讯软件", 
        "发现网页报错后立即通过即时通讯工具告知负责人",
        
        # 浏览器 (Browser)
        "在社交媒体平台上抓取最近的动态并整理成简报",
        "帮我处理一下这个网页上的验证码校验",
        "把这个网站上的所有表格数据都导出来",
        
        # 操作系统 (macOS)
        "帮我看看控制面板里有没有什么硬件设置可以开关",
        "在电脑里搜索一份特定的合同文件并把它打开",
        "截取当前屏幕的局部区域并保存到本地",
        "调整一下窗口的大小，把它最大化显示",
        
        # 办公/QA (Office/QA)
        "审计一下这份电子表格，看看格式有没有统一",
        "检查一下这份 PDF 文档的末尾有没有盖章或者签名",
        "帮我从电子邮件的附件里提取有用的信息",
        "验证一下页面加载时的骨架屏显示是否正常",

        "好，同意，请开始吧"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n【测试用例 {i}】")
        print(f"🔍 输入指令: \"{query}\"")
        
        match, relevant, reasoning = await skill_discovery.exact_search(query)
        
        if match:
            print(f"✅ 匹配成功!")
            print(f"   - 匹配名称: {match.skill_name}")
            print(f"   - 置信度: {match.confidence}")
            print(f"   - 推理过程: {reasoning}")
        else:
            print(f"❌ 未能精确匹配到特定意图。")
            print(f"   - 推理过程: {reasoning}")

        if relevant:
            print(f"📚 相关候选技能:")
            for s in relevant[:3]:
                print(f"   - [{s.id}] {s.name} (Namespace: {s.namespace})")

async def test_multi_turn_discovery():
    """
    测试多轮对话下的意图识别表现
    """
    print("\n" + "="*50)
    print("🔄 多轮对话意图识别测试")
    print("="*50)

    # 模拟一个典型的三轮对话
    # 1. 第一轮：明确任务意图
    print("\n【第一轮：明确意图】")
    q1 = "我想从网页抓点数据发飞书"
    print(f"👤 User: {q1}")
    match1, _, reasoning1 = await skill_discovery.exact_search(q1)
    if match1:
        print(f"🤖 Match: {match1.skill_name}\n   - Reasoning: {reasoning1}")
    
    # 模拟助手回复
    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": "好的，我为你找到了 'Browser to IM Bridge' 技能。请问需要现在开始执行吗？"}
    ]

    # 2. 第二轮：模糊确认
    print("\n【第二轮：上下文确认】")
    q2 = "好，同意，请开始吧"
    print(f"👤 User: {q2}")
    match2, _, reasoning2 = await skill_discovery.exact_search(q2, history=history)
    if match2:
        print(f"🤖 Match: {match2.skill_name}\n   - Reasoning: {reasoning2}")
    else:
        print(f"🤖 Match: None\n   - Reasoning: {reasoning2}")

    # 3. 第三轮：在对话中突然切换新任务
    print("\n【第三轮：意图切换】")
    q3 = "算了，先不发了，帮我查查电脑里有没有关于合同的文件"
    print(f"👤 User: {q3}")
    history.append({"role": "user", "content": q2})
    history.append({"role": "assistant", "content": "好的，正在为您准备..."})
    
    match3, _, reasoning3 = await skill_discovery.exact_search(q3, history=history)
    if match3:
        print(f"🤖 Match: {match3.skill_name}\n   - Reasoning: {reasoning3}")
    else:
        print(f"🤖 Match: None\n   - Reasoning: {reasoning3}")
    
    if match3 and "Find and Open File" in match3.skill_name:
        print("✅ 表现理想：即便在对话中，也能通过上下文识别出新的任务切换。")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    if not os.path.exists("app"):
        print("❌ 错误: 请在 backend 根目录下运行此脚本。")
    else:
        async def main():
            await test_my_semantic_discovery()
            await test_multi_turn_discovery()
            
        asyncio.run(main())
