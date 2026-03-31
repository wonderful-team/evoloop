#!/bin/bash
# Agent 直接测试启动脚本
# 自动设置环境并调用 Agent 内部方法

cd "$(dirname "$0")/../../"

echo "═══════════════════════════════════════════════════════════════"
echo "  EvoLoop Agent 直接测试"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 未找到虚拟环境 .venv"
    exit 1
fi

# 激活环境
source .venv/bin/activate

# 加载 .env
export $(grep -v '^#' .env | xargs)

echo "配置信息:"
echo "  API Key: ${OPENAI_API_KEY:0:10}..."
echo "  Base URL: $OPENAI_BASE_URL"
echo "  Model: $OPENAI_MODEL_NAME"
echo ""

# 测试话术
TEST_INPUTS=(
    "帮我写一个 Python 函数，计算斐波那契数列"
    "生成一个 React 组件，显示用户头像和名称"
    "解释一下什么是依赖注入"
)

echo "═══════════════════════════════════════════════════════════════"
echo "  测试话术:"
echo "═══════════════════════════════════════════════════════════════"
for i in "${!TEST_INPUTS[@]}"; do
    echo "  $((i+1)). ${TEST_INPUTS[$i]}"
done
echo ""

# 创建测试脚本
cat > /tmp/agent_test.py << 'PYTHON_EOF'
import asyncio
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

async def main():
    print("🚀 开始测试...")
    print("-" * 60)
    
    try:
        # 导入必要的模块
        print("1. 导入核心模块...")
        from app.core.engine.background_agent import run_agent_background
        from app.core.globals import get_graph, set_graph
        from app.core.engine.graph_builder import GraphBuilder
        from app.core.persistence import get_checkpointer
        from app.infrastructure.database.sql.database import engine, AsyncSessionLocal
        from app.core.monitoring.activity import activity_monitor
        print("   ✅ 导入成功")
        
        # 检查 Graph 是否已初始化
        print("2. 检查 Graph 状态...")
        graph = get_graph()
        if graph is None:
            print("   ⚠️  Graph 未初始化，尝试初始化...")
            
            # 创建 Graph
            from app.core.config import settings
            config_path = settings.AGENT_CONFIG_PATH
            
            print(f"   配置文件: {config_path}")
            
            # 获取 checkpointer
            checkpointer = get_checkpointer()
            
            # 构建 Graph
            builder = GraphBuilder()
            graph = builder.build(config_path, checkpointer=checkpointer)
            
            # 设置全局 Graph
            set_graph(graph, config_path=config_path, checkpointer=checkpointer)
            print("   ✅ Graph 初始化完成")
        else:
            print("   ✅ Graph 已就绪")
        
        # 执行测试
        test_inputs = [
            "帮我写一个 Python 函数，计算斐波那契数列",
            "生成一个 React 组件，显示用户头像和名称",
        ]
        
        for i, user_input in enumerate(test_inputs, 1):
            print(f"\n{'-'*60}")
            print(f"📌 [测试 {i}] {user_input[:50]}...")
            print(f"{'-'*60}")
            
            thread_id = f"test-{datetime.now().strftime('%H%M%S')}-{i}"
            
            # 构建输入
            inputs = {
                "messages": [{"type": "human", "content": user_input}],
                "project_id": 1,
                "goal": user_input[:50],
                "is_retry": False
            }
            
            print(f"Thread: {thread_id}")
            print("⏳ 执行 Agent...")
            
            start = asyncio.get_event_loop().time()
            
            try:
                # 执行 Agent（带超时）
                await asyncio.wait_for(
                    run_agent_background(thread_id, inputs),
                    timeout=30.0
                )
                
                elapsed = asyncio.get_event_loop().time() - start
                print(f"✅ 完成! 耗时: {elapsed:.2f}s")
                
            except asyncio.TimeoutError:
                print("⚠️  执行超时 (30s)")
                print("   Agent 可能还在后台运行")
                
            except Exception as e:
                print(f"❌ 执行错误: {e}")
        
        print(f"\n{'='*60}")
        print("测试完成!")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ 初始化错误: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(main())
PYTHON_EOF

# 运行测试
.venv/bin/python /tmp/agent_test.py

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  测试结束"
echo "═══════════════════════════════════════════════════════════════"
