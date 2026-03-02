import asyncio
import os
import sys

# 将 backend 目录添加到路径
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.infrastructure.database.graph.driver import Neo4jManager

async def query_android_layouts():
    print("🔍 查询 Neo4j 中的 Android 布局概念...")
    
    driver = Neo4jManager.get_driver()
    async with driver.session() as session:
        # 查询所有以 android_layout: 开头的 Concept 节点
        result = await session.run(
            """
            MATCH (c:Concept)
            WHERE c.name STARTS WITH 'android_layout:'
            RETURN c.name as name, c.description as description
            ORDER BY c.name
            """
        )
        
        records = await result.data()
        
        if not records:
            print("❌ 未发现任何 Android 布局概念。")
            return

        print(f"✅ 发现 {len(records)} 个记录:\n")
        for i, r in enumerate(records, 1):
            print(f"{i}. 名称: {r['name']}")
            print(f"   描述: {r['description']}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(query_android_layouts())
