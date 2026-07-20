"""最小化验证原型:AppMap -> 技能工厂 -> 确定性执行链。

不并入 Evoloop 生产代码(用户决策 v0.15)。用一小部分商城地图数据(goods 实体)
+ 模板库实例化出几个技能/宏,验证草案 §7.7-§7.9 的核心主张:

  - 确定性腿(validate_deterministic):无 LLM/无后端,校验 map->模板->技能 正确且安全。
  - agent 腿(validate_agent):经 run_agent_background 走 Agent Loop,验证 agent 消费地图
    + 读-算-写 + 确认门(商城写入用内存 stub,不碰真实库)。

运行(evoloop/backend 下):
  uv run python -m prototype.map_factory.run            # 确定性腿(永远跑)
  uv run python -m prototype.map_factory.run --agent    # 加 agent 腿(需后端 + LLM)
"""
