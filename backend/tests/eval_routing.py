"""Standalone evaluation of CommandRouter L0 decisions without running the Agent.

Like ``tests/eval_supervisor.py`` but observes routing decisions (status,
target_type, intent_hint) instead of Supervisor behavior.

Modes:
- Default (fast, isolated): uses fixture templates, mocks DB macros, and uses an
  empty context probe. No DB / macOS driver / ONNX model / Agent required.
- ``USE_DB=1``: uses the real ``build_and_enrich_spec()`` and ``MacroResolver``
  so DB macros participate in matching. The BERT ONNX classifier is used if it
  is available locally. The Agent is still never invoked — only the routing
  decision is observed.

Environment variables:
- ``USE_DB=1``              use real DB macros and enriched RouteCatalog
- ``USE_REAL_CONTEXT=1``    use real macOS/phone context probe (default fake)
- ``RESULT_PATH=...``       JSON output path (default ``/tmp/opencode/routing_eval_results.json``)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter
from typing import Any

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

from app.core.routing.command_router import CommandRouter
from app.core.routing.conversation_state import clear_thread_intent_state
from app.core.routing.init_spec import build_and_enrich_spec, build_init_spec
from app.core.routing.intent_classifier import initialize as init_classifier
from app.core.routing.intent_resolution import IntentResolver
from app.core.routing.local_matcher import LocalMatcher
from app.core.routing.macro_resolver import MacroResolver
from app.core.routing.schemas import RouteDecision
from app.infrastructure.database.resource_manager import db_resource_manager
from tests.unit.core.routing import fixtures as routing_fixtures

RESULT_PATH = os.getenv("RESULT_PATH", "/tmp/opencode/routing_eval_results.json")
PROGRESS_PATH = f"{RESULT_PATH}.progress.jsonl"

USE_DB = os.getenv("USE_DB", "").lower() in ("1", "true", "yes")
USE_REAL_CONTEXT = os.getenv("USE_REAL_CONTEXT", "").lower() in ("1", "true", "yes")

# When a question does not provide its own expected label, use this per-domain
# default to compute accuracy / leakage metrics.  L0/builtin questions are checked
# by status/target_type only; domain questions are checked by domain.
DEFAULT_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "builtin": {"status": "routed", "target_type": "builtin"},
    # Session control maps to builtin actions (end/cancel/ack/rename etc.)
    "session_control": {"status": "routed", "target_type": "builtin"},
    # Media / app / device control are deterministic local actions
    "media_control": {"status": "routed", "target_type": "local"},
    "app_control": {"status": "routed", "target_type": "local"},
    "device_control": {"status": "routed", "target_type": "local"},
    "greeting": {"status": "delegate", "target_type": "agent", "domain": "greeting"},
    "chitchat": {"status": "delegate", "target_type": "agent", "domain": "chitchat"},
    "system_info": {"status": "delegate", "target_type": "agent", "domain": "system_info"},
    "memory": {"status": "delegate", "target_type": "agent", "domain": "memory"},
    "ambiguous": {"status": "delegate", "target_type": "agent", "domain": "ambiguous"},
    "multi_intent": {"status": "delegate", "target_type": "agent", "domain": "multi_intent"},
    "edge": {"status": "delegate", "target_type": "agent"},
    # Knowledge / task domains
    "daily_life": {"status": "delegate", "target_type": "agent", "domain": "daily_life"},
    "coding_dev": {"status": "delegate", "target_type": "agent", "domain": "coding_dev"},
    "coding_test": {"status": "delegate", "target_type": "agent", "domain": "coding_test"},
    "coding_ops": {"status": "delegate", "target_type": "agent", "domain": "coding_ops"},
    "ecommerce": {"status": "delegate", "target_type": "agent", "domain": "ecommerce"},
    "research": {"status": "delegate", "target_type": "agent", "domain": "research"},
    "finance": {"status": "delegate", "target_type": "agent", "domain": "finance"},
    "education": {"status": "delegate", "target_type": "agent", "domain": "education"},
    "industry": {"status": "delegate", "target_type": "agent", "domain": "industry"},
    "business": {"status": "delegate", "target_type": "agent", "domain": "business"},
    "legal": {"status": "delegate", "target_type": "agent", "domain": "legal"},
    "medical": {"status": "delegate", "target_type": "agent", "domain": "medical"},
    "marketing": {"status": "delegate", "target_type": "agent", "domain": "marketing"},
    "travel": {"status": "delegate", "target_type": "agent", "domain": "travel"},
    "food": {"status": "delegate", "target_type": "agent", "domain": "food"},
    "shopping": {"status": "delegate", "target_type": "agent", "domain": "shopping"},
    "sports": {"status": "delegate", "target_type": "agent", "domain": "sports"},
    "entertainment": {"status": "delegate", "target_type": "agent", "domain": "entertainment"},
    "news": {"status": "delegate", "target_type": "agent", "domain": "news"},
    "weather": {"status": "delegate", "target_type": "agent", "domain": "weather"},
    "multi_turn": {"status": "delegate", "target_type": "agent"},
}


QUESTIONS: list[dict[str, Any]] = []


def q(
    domain: str,
    text: str,
    *,
    expected: dict[str, str | None] | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Create a question entry."""
    return {
        "domain": domain,
        "text": text,
        "expected": expected,
        "thread_id": thread_id,
    }


def add(domain: str, texts: list[str], **kwargs: Any) -> None:
    """Bulk add questions for a domain."""
    for text in texts:
        QUESTIONS.append(q(domain, text, **kwargs))


# Conversation / session control
add(
    "session_control",
    [
        "再见", "拜拜", "结束", "取消", "算了", "对的", "没错", "重说",
        "再说一遍", "你以后叫小爱", "你的名字是旺财", "不用了", "不要",
        "是的", "可以", "就这个",
    ],
)

# Media / system actions
add(
    "media_control",
    [
        "暂停", "继续播放", "下一首", "上一首", "切歌", "静音", "取消静音",
        "音量大一点", "音量小一点", "音量最大", "截图", "截屏", "锁屏",
        "锁定屏幕", "播放音乐", "音量调到一半", "调大音量", "按 Esc",
        "按 Command+C", "调低音量", "声音大一点", "声音小一点", "静音一下",
        "继续", "停止播放",
    ],
)

# App control
add(
    "app_control",
    [
        "打开微信", "启动 Safari", "切换到 Chrome", "退出网易云音乐", "打开终端",
        "打开 VS Code", "关闭 QQ", "打开浏览器", "打开音乐", "打开计算器",
        "关闭当前应用", "切换到 Safari", "请打开微信", "启动 Chrome", "打开QQ",
        "打开飞书", "打开Chrome", "打开Safari", "关闭微信", "打开网易云音乐",
    ],
)

# Device control
add(
    "device_control",
    [
        "打开 WiFi", "关闭 WiFi", "打开蓝牙", "关闭蓝牙", "打开信息",
        "关闭 WiFi", "打开蓝牙", "关闭蓝牙", "打开WiFi", "关闭WiFi",
    ],
)

# Greetings
add(
    "greeting",
    [
        "你好", "早上好", "hello", "晚上好", "hi", "您好",
        "Good morning", "Hello",
    ],
)

# Chitchat
add(
    "chitchat",
    [
        "讲个笑话", "谢谢", "What can you do?", "How are you today?",
        "Nice to meet you", "你能做什么", "你能控制我的电脑吗",
        "你能访问互联网吗", "你能记住我们的对话吗", "你叫什么名字", "你是谁",
    ],
)

# System / host queries
add(
    "system_info",
    [
        "当前 CPU 是什么型号", "内存占用多少", "磁盘空间还剩多少", "现在几点",
        "今天是星期几", "有哪些程序在运行", "Docker 有哪些容器在跑", "当前内存",
        "网络连接正常吗", "我安装了哪些应用", "后台有哪些任务",
        "浏览器打开了哪些标签", "我的电脑型号是什么", "磁盘空间", "现在时间",
        "CPU 温度多少", "网络速度", "电池电量",
    ],
)

# News
add(
    "news",
    [
        "今天有什么科技新闻", "最近 AI 领域有什么突破", "今天股市怎么样",
        "最新的国际新闻", "国内今天发生了什么大事", "最近的体育新闻",
        "特斯拉最近有什么新闻", "苹果最新发布会信息", "有哪些值得关注的创业动态",
        "今天有什么热点", "新闻摘要", "最新的人工智能研究进展", "头条新闻",
    ],
)

# Weather
add(
    "weather",
    [
        "今天天气怎么样", "明天会下雨吗", "未来一周天气预报", "今天适合洗车吗",
        "查一下天气", "明天天气如何", "北京今天多少度", "上海明天天气如何",
        "今天适合出门吗", "气温多少度", "空气质量怎么样", "紫外线强吗",
    ],
)

# Memory / personal context
add(
    "memory",
    [
        "我之前问过你什么", "我叫什么名字", "第 3 轮我们聊了什么",
        "总结我的上一个项目", "我的上一封邮件", "上次我们聊了什么",
        "我说过什么", "我之前问过的问题", "我的上一个任务", "记住我叫小明",
    ],
)

# Ambiguous / vague
add(
    "ambiguous",
    [
        "帮我", "你看着办", "怎么办", "继续", "我要出门了", "随便", "开始吧",
        "帮我一下", "做点什么", "修一下",
    ],
)

# Multi-intent (should fall through to agent)
add(
    "multi_intent",
    [
        "打开微信再截图", "暂停然后锁屏", "查天气和路况",
        "打开 Chrome 然后搜索今天的新闻", "打开微信然后退出", "天气和新闻",
        "打开微信给张三发消息", "写代码并运行测试", "搜索资料并整理成文档",
        "打开应用然后截图",
    ],
)

# Edge cases
add(
    "edge",
    [
        "", "a", "1+1=?", "用 500 字详细解释 Python 的 GIL",
        "你能记住我们的对话吗", "如何安全地删除重复文件",
        "Write a Python function and explain it in Chinese.",
        "用英文告诉我你叫什么", "把这个代码改对：def foo(): return x + 1", " ??? ",
    ],
)

# Daily life
add(
    "daily_life",
    [
        "今天天气怎么样", "明天会下雨吗", "提醒我记得喝水", "帮我查一下航班",
        "订一张电影票", "附近有什么好吃的", "帮我叫个外卖", "设置明天早上7点的闹钟",
        "给家里打电话", "查询快递进度", "今天有什么新闻", "推荐一部好看的电影",
        "帮我规划周末出行", "怎么养猫", "如何健身", "附近健身房", "今天适合洗车吗",
        "帮我想个生日礼物的建议", "如何快速入睡", "记账", "怎么做饭",
    ],
)

# Coding / software development — split into dev, test, ops
add(
    "coding_dev",
    [
        "写一个 Python 函数反转字符串", "解释一下递归", "如何 debug 一段 Python 代码",
        "Git 如何撤销上一次提交", "写一个正则表达式匹配手机号",
        "SQL 如何查询重复记录", "REST API 设计最佳实践",
        "时间复杂度 O(n log n) 是什么意思", "Python 的 decorator 怎么用",
        "写一个快速排序", "如何处理并发请求",
        "前端如何调用后端 API", "如何优化数据库查询",
        "Python 的 GIL 是什么", "TypeScript 相比 JavaScript 的优势",
        "帮我重构一个 legacy Python 项目", "写一个 React 组件示例",
        "JavaScript 闭包是什么", "Python 的生成器怎么用",
        "Git 分支管理最佳实践", "帮我写个知乎爬虫",
        "前端用 Vue 还是 React 好", "这个接口怎么设计",
    ],
)

add(
    "coding_test",
    [
        "如何写一个单元测试", "帮我写 Jest 测试用例",
        "这个函数的边界条件怎么测", "测试覆盖率怎么提高",
        "帮我写 API 集成测试", "Selenium 自动化测试脚本",
        "帮我写 pytest 测试", "Cypress 怎么测这个表单",
        "帮我写验收标准", "如何设计回归测试用例",
        "帮我复现这个 bug", "这个 bug 的复现步骤是什么",
        "性能测试工具推荐", "帮我写压测脚本",
        "Postman 集合怎么写", "测试数据怎么构造",
        "Mock 第三方 API", "快照测试适合什么场景",
        "契约测试怎么落地", "帮我写测试报告",
    ],
)

add(
    "coding_ops",
    [
        "什么是 CI/CD", "帮我写一个 GitHub Actions 工作流",
        "Dockerfile 怎么优化", "Kubernetes 部署 yaml",
        "Nginx 配置反向代理", "如何配置 Redis 集群",
        "Prometheus 怎么监控服务", "日志收集方案 ELK",
        "服务器磁盘满了怎么办", "如何优雅地上线",
        "发布失败怎么回滚", "帮我写 Terraform 配置",
        "Ansible 批量部署脚本", "服务限流怎么配",
        "证书过期怎么处理", "MySQL 主从同步配置",
        "如何排查线上故障", "帮我写 Helm Chart",
        "链路追踪 SkyWalking 配置", "环境变量放哪里安全",
    ],
)

# E-commerce / store operations
add(
    "ecommerce",
    [
        "淘宝店铺怎么提升流量", "帮我写一段直播带货脚本",
        "详情页主图怎么设计", "直通车怎么出价",
        "抖音小店如何运营", "拼多多商品标题怎么写",
        "如何提高加购转化率", "售后退货率怎么降低",
        "电商运营每天看什么数据", "帮我制定一个促销方案",
        "跨境电商选品建议", "SKU 规划怎么做",
        "私域社群怎么维护", "直播间中控需要做哪些事",
        "评价管理有什么技巧", "如何应对职业打假",
        "平台降权怎么申诉", "电商财务报表怎么做",
        "客服快捷回复话术", "一件代发模式怎么选品",
    ],
)

# Research / science
add(
    "research",
    [
        "最新的人工智能研究进展", "CRISPR 是什么", "量子计算原理", "暗物质是什么",
        "气候变化的主要原因", "解释相对论", "什么是大语言模型",
        "基因编辑的伦理问题", "核能的优缺点", "最新有哪些论文值得关注",
        "可控核聚变进展", "脑机接口最新研究", "室温超导是真的吗", "神经网络为什么有效",
        "Transformer 架构详解", "强化学习基础", "因果推断方法", "科学实验设计",
        "论文润色", "学术写作规范",
    ],
)

# Finance / investment
add(
    "finance",
    [
        "什么是复利", "股票期权是什么", "等额本息和等额本金有什么区别",
        "通货膨胀是什么意思", "如何计算房贷月供", "加密货币是什么", "个人理财建议",
        "如何看股票 K 线图", "有哪些省税的方法", "什么是 ETF", "资产配置原则",
        "风险管理", "财务报表分析", "量化交易入门", "保险怎么买", "退休金规划",
        "外汇交易", "宏观经济指标", "公司估值方法", "投资组合优化",
    ],
)

# Education / learning
add(
    "education",
    [
        "光合作用是什么", "教我几个常用汉字", "如何高效学习一门语言",
        "解方程 2x + 5 = 15", "唐朝历史简介", "牛顿三大定律", "如何准备考研",
        "What is photosynthesis?", "三角函数 sin/cos/tan 的含义",
        "编程入门推荐学什么语言", "小学数学辅导", "英语语法讲解", "物理力学基础",
        "化学元素周期表", "地理知识", "历史事件时间线", "考试复习计划",
        "在线课程推荐", "教育心理学", "学习方法论",
    ],
)

# Industry / manufacturing
add(
    "industry",
    [
        "智能制造是什么", "工业 4.0 概念", "PLC 编程入门", "供应链优化",
        "物联网应用", "预测性维护", "工厂自动化", "工业机器人", "MES 系统介绍",
        "质量控制方法", "精益生产", "六西格玛", "能源管理", "安全生产规范",
        "设备故障诊断",
    ],
)

# Business / management
add(
    "business",
    [
        "商业计划书怎么写", "市场调研方法", "竞品分析", "SWOT 分析", "客户画像",
        "销售策略", "定价策略", "商业模式画布", "增长黑客", "用户留存",
        "转化率优化", "品牌建设", "CRM 系统", "项目管理", "OKR 制定",
        "团队协作工具", "企业文化", "融资路演", "合同审查", "商务谈判技巧",
    ],
)

# Legal / compliance
add(
    "legal",
    [
        "合同法基本原则", "劳动合同注意事项", "知识产权保护", "隐私权相关法律",
        "数据合规要求", "公司注册流程", "股权协议要点", "侵权责任",
        "消费者权益保护法", "GDPR 简介", "合规审查", "法律风险识别",
        "诉讼流程", "仲裁与调解", "法律顾问", "数据安全法", "网络安全法",
        "反垄断法", "劳动法", "公司章程",
    ],
)

# Medical / health
add(
    "medical",
    [
        "感冒有哪些症状", "头痛应该怎么缓解", "糖尿病是什么", "高血压要注意什么",
        "布洛芬有什么副作用", "健康饮食建议", "失眠怎么办", "What are symptoms of flu?",
        "如何提高免疫力", "儿童发烧怎么处理", "急救常识", "心肺复苏步骤",
        "常见药物相互作用", "体检项目选择", "慢性病管理", "疫苗接种", "心理健康",
        "运动损伤", "营养学基础", "医患沟通",
    ],
)

# Marketing / growth
add(
    "marketing",
    [
        "内容营销怎么做", "SEO 优化技巧", "社交媒体运营", "广告投放策略", "品牌定位",
        "用户增长", "邮件营销", "KOL 合作", "社群运营", "转化漏斗", "A/B 测试",
        "数据分析", "竞品营销", "短视频营销", "直播带货", "私域流量", "公域流量",
        "营销自动化", "口碑营销", "危机公关",
    ],
)

# Travel / tourism
add(
    "travel",
    [
        "北京有什么景点", "帮我规划日本自由行", "签证怎么办理",
        "cheapest flight to Tokyo", "酒店推荐", "旅游攻略", "当地美食", "交通指南",
        "旅行保险", "行李清单", "汇率换算", "时差", "自驾游路线", "签证材料",
        "护照办理", "旅行摄影", "文化禁忌", "安全提示", "景点预约", "退税流程",
    ],
)

# Food / cooking
add(
    "food",
    [
        "红烧肉怎么做", "推荐一道家常菜", "低卡路里食谱", "如何煮咖啡", "烘焙入门",
        "川菜做法", "粤菜推荐", "素食菜单", "营养早餐", "健康饮食计划",
        "食材保存", "调酒配方", "节日美食", "火锅底料", "食材搭配", "食品安全",
        "减肥餐", "儿童食谱", "宴会菜单", "地方特产",
    ],
)

# E-commerce / store operations
add(
    "ecommerce",
    [
        "电商运营", "库存管理", "SKU 分析", "促销策略", "会员体系",
        "支付集成", "物流跟踪", "跨境电商", "直播购物", "团购",
        "秒杀", "预售", "淘宝店铺怎么提升流量", "帮我写一段直播带货脚本",
        "详情页主图怎么设计", "直通车怎么出价", "抖音小店如何运营",
        "拼多多商品标题怎么写", "如何提高加购转化率", "售后退货率怎么降低",
    ],
)

# Shopping / consumer purchase decisions
add(
    "shopping",
    [
        "帮我挑一款笔记本电脑", "iPhone 和 Android 怎么选", "性价比高的耳机",
        "购物比价", "优惠券", "二手平台", "商品评价", "退换货政策",
        "哪个型号的手机适合拍照", "这款耳机降噪怎么样", "帮我对比几款平板",
        "智能手表选哪个好", "机械键盘推荐", "显示器怎么选", "扫地机器人推荐",
        "空气净化器推荐", "床垫哪个品牌好", "护肤品怎么选", "跑鞋推荐",
    ],
)

# Sports / fitness
add(
    "sports",
    [
        "世界杯赛程", "NBA 最新战况", "跑步训练计划", "健身房训练计划", "瑜伽入门",
        "游泳技巧", "羽毛球规则", "网球发球", "足球战术", "马拉松训练",
        "运动恢复", "损伤预防", "营养学", "体育新闻", "赛事预测", "球队历史",
        "球员数据", "健身饮食", "增肌计划", "减脂计划",
    ],
)

# Entertainment / media
add(
    "entertainment",
    [
        "推荐几部电影", "最新电视剧", "流行音乐", "游戏推荐", "动漫推荐",
        "小说推荐", "综艺节目", "演唱会信息", "明星八卦", "影评", "游戏攻略",
        "剧本创作", "音乐制作", "短视频创作", "直播技巧", "娱乐新闻", "影评写作",
        "粉丝运营", "IP 授权", "流媒体推荐",
    ],
)

# Multi-turn anaphora (fixed thread)
QUESTIONS.extend(
    [
        q("multi_turn", "当前 CPU 是什么型号", thread_id="t-eval", expected={"status": "delegate", "target_type": "agent", "domain": "system_info"}),
        q("multi_turn", "那它的内存呢", thread_id="t-eval", expected={"status": "delegate", "target_type": "agent", "domain": "system_info"}),
        q("multi_turn", "帮我写个周报", thread_id="t-eval", expected={"status": "delegate", "target_type": "agent", "domain": "business"}),
        q("multi_turn", "把它改成日报", thread_id="t-eval", expected={"status": "delegate", "target_type": "agent", "domain": "business"}),
    ]
)


async def fake_probe() -> dict[str, Any]:
    """Empty context probe so the script does not depend on macOS driver."""
    return {"app": "", "phone_connected": False}


class NoMacroResolver(MacroResolver):
    """Macro resolver that never finds a DB macro, isolating classification."""

    async def _load_macro_by_name(self, name: str, project_id: int) -> Any:
        return None


# Fallback app entries so the eval is deterministic even on non-macOS hosts.
_FALLBACK_APPS = [
    {"name": "微信", "pinyin": "weixin", "aliases": []},
    {"name": "QQ", "aliases": []},
    {"name": "网易云音乐", "pinyin": "wangyiyunyinyue", "aliases": []},
    {"name": "音乐", "aliases": []},
    {"name": "Safari", "aliases": []},
    {"name": "Chrome", "aliases": []},
    {"name": "VS Code", "aliases": []},
    {"name": "终端", "pinyin": "zhongduan", "aliases": []},
    {"name": "计算器", "pinyin": "jisuanqi", "aliases": []},
    {"name": "飞书", "pinyin": "feishu", "aliases": []},
]


async def build_router() -> CommandRouter:
    """Build a CommandRouter according to USE_DB / USE_REAL_CONTEXT flags."""
    if USE_DB:
        try:
            spec = await build_and_enrich_spec()
            print("[eval_routing] Using REAL DB macros + enriched RouteCatalog", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[eval_routing] build_and_enrich_spec failed ({exc}); falling back to init_spec",
                flush=True,
            )
            spec = await asyncio.to_thread(build_init_spec)
    else:
        spec = await asyncio.to_thread(build_init_spec)
        print("[eval_routing] Using fixture templates (DB macros mocked)", flush=True)

    slot_dictionaries = dict(spec.slot_dictionaries)
    slot_dictionaries.setdefault("delta", routing_fixtures._DELTA_DICT)
    slot_dictionaries.setdefault("key", routing_fixtures._KEY_DICT)
    if not slot_dictionaries.get("app"):
        slot_dictionaries["app"] = _FALLBACK_APPS

    aliases = dict(routing_fixtures._ALIASES)
    aliases.update(spec.aliases)

    app_usage_rank = spec.app_usage_rank or [e["name"] for e in _FALLBACK_APPS]

    if USE_DB:
        # In DB mode we trust the real enriched templates.  Still inject the fixture
        # builtin templates in case the DB has no routable macros yet.
        templates = list(spec.templates)
        seen_actions = {t.get("action") for t in templates if isinstance(t, dict)}
        for fixture_template in routing_fixtures._TEMPLATES:
            if fixture_template.get("action") not in seen_actions:
                templates.append(fixture_template)
    else:
        templates = routing_fixtures._TEMPLATES

    local_matcher = LocalMatcher(
        templates=templates,
        slot_dictionaries=slot_dictionaries,
        aliases=aliases,
        app_usage_rank=app_usage_rank,
    )

    if USE_REAL_CONTEXT:
        from app.core.routing.context_probe import resolve_context

        context_probe = resolve_context
    else:
        context_probe = fake_probe

    macro_resolver = MacroResolver() if USE_DB else NoMacroResolver()
    intent_resolver = IntentResolver(
        context_probe=context_probe,
        macro_resolver=macro_resolver,
    )
    return CommandRouter(local_matcher=local_matcher, intent_resolver=intent_resolver)


async def evaluate_one(
    router: CommandRouter,
    domain: str,
    text: str,
    thread_id: str,
    expected: dict[str, str | None] | None,
) -> dict[str, Any]:
    start = time.time()
    try:
        decision: RouteDecision = await router.resolve(
            text,
            thread_id=thread_id,
            project_id=0,
            source="chat",
        )
    except Exception as e:
        return {
            "domain": domain,
            "question": text,
            "thread_id": thread_id,
            "expected": expected,
            "error": f"{type(e).__name__}: {e}",
            "elapsed": time.time() - start,
        }

    elapsed = time.time() - start
    hint = decision.intent_hint.model_dump() if decision.intent_hint else {}
    return {
        "domain": domain,
        "question": text,
        "thread_id": thread_id,
        "expected": expected,
        "status": decision.status,
        "target_type": decision.target_type,
        "target": decision.target,
        "params": decision.params,
        "confidence": decision.confidence,
        "l1_domain": hint.get("domain"),
        "intent": hint.get("intent"),
        "suggested_modules": hint.get("suggested_modules"),
        "reason": hint.get("reason"),
        "previous_intent": hint.get("previous_intent"),
        "session_history": hint.get("session_history"),
        "elapsed": elapsed,
    }


def _effective_expected(record: dict[str, Any]) -> dict[str, str | None] | None:
    """Return the question's expected label, falling back to the domain default."""
    if record.get("expected"):
        return record["expected"]
    return DEFAULT_EXPECTATIONS.get(record["domain"])


def analyze(results: list[dict[str, Any]]) -> None:
    """Print detailed routing analysis and save a JSON summary."""
    ok_results = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    total = len(results)

    print(f"\n=== Detailed Analysis ({total} questions, {len(errors)} errors) ===", flush=True)

    # 1. Global distributions
    status_counts = Counter(r["status"] for r in ok_results)
    print("\n--- Global Status Distribution ---", flush=True)
    for k, v in status_counts.most_common():
        print(f"  {k}: {v} ({v / len(ok_results) * 100:.1f}%)", flush=True)

    target_counts = Counter(r["target_type"] for r in ok_results)
    print("\n--- Global Target Type Distribution ---", flush=True)
    for k, v in target_counts.most_common():
        print(f"  {k}: {v}", flush=True)

    l1_domain_counts = Counter(r.get("l1_domain") for r in ok_results)
    print("\n--- Global L1 Domain Distribution ---", flush=True)
    for k, v in l1_domain_counts.most_common():
        print(f"  {k}: {v}", flush=True)

    # 2. BERT usage
    bert_hits = [r for r in ok_results if r["confidence"] >= 0.08]
    print("\n--- BERT Usage ---", flush=True)
    print(f"  BERT predictions above threshold: {len(bert_hits)}/{len(ok_results)}", flush=True)
    if bert_hits:
        confs = [r["confidence"] for r in bert_hits]
        print(f"  avg confidence (BERT hits): {sum(confs) / len(confs):.3f}", flush=True)
        print(f"  max confidence: {max(confs):.3f}", flush=True)

    # 3. Per-domain routing table with accuracy
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for r in ok_results:
        by_domain.setdefault(r["domain"], []).append(r)

    rows: list[tuple[str, int, int, int, str, float, int, int, int, int]] = []
    for domain, recs in sorted(by_domain.items()):
        n = len(recs)
        routed = sum(1 for r in recs if r["status"] == "routed")
        delegate = n - routed
        top_domains = Counter(r.get("l1_domain") for r in recs).most_common(3)
        top_domain_str = ", ".join(f"{d}:{c}" for d, c in top_domains)
        avg_conf = sum(r["confidence"] for r in recs) / n if n else 0.0

        has_expected = [r for r in recs if _effective_expected(r)]
        status_correct = 0
        domain_correct = 0
        domain_total = 0
        for r in has_expected:
            exp = _effective_expected(r)
            if exp is None:
                continue
            if exp.get("status") and exp["status"] == r["status"]:
                status_correct += 1
            if exp.get("domain"):
                domain_total += 1
                if r.get("l1_domain") == exp["domain"]:
                    domain_correct += 1

        rows.append(
            (
                domain,
                n,
                routed,
                delegate,
                top_domain_str,
                avg_conf,
                status_correct,
                len(has_expected),
                domain_correct,
                domain_total,
            )
        )

    print(
        f"\n  {'domain':<16} {'count':>5} {'routed':>6} {'delegate':>8} "
        f"{'top_l1_domains':<30} {'avg_conf':>8} {'status_acc':>10} {'domain_acc':>10}",
        flush=True,
    )
    for row in rows:
        (
            domain,
            n,
            routed,
            delegate,
            top_domain_str,
            avg_conf,
            status_correct,
            status_total,
            domain_correct,
            domain_total,
        ) = row
        status_acc = f"{status_correct}/{status_total}" if status_total else "-"
        domain_acc = f"{domain_correct}/{domain_total}" if domain_total else "-"
        print(
            f"  {domain:<16} {n:>5} {routed:>6} {delegate:>8} "
            f"{top_domain_str:<30} {avg_conf:>8.2f} {status_acc:>10} {domain_acc:>10}",
            flush=True,
        )

    # 4. Domain questions incorrectly routed to local (local leakage)
    local_leak_domains = {
        "coding_dev",
        "coding_test",
        "coding_ops",
        "research",
        "finance",
        "education",
        "industry",
        "business",
        "ecommerce",
        "legal",
        "medical",
        "marketing",
        "travel",
        "food",
        "shopping",
        "sports",
        "entertainment",
        "daily_life",
        "chitchat",
        "news",
        "weather",
        "system_info",
        "memory",
        "greeting",
        "ambiguous",
        "multi_intent",
    }
    leaked = [
        r
        for r in ok_results
        if r["status"] == "routed" and r["domain"] in local_leak_domains
    ]
    print(
        f"\n--- Domain Questions Incorrectly Routed to Local ({len(leaked)}) ---",
        flush=True,
    )
    for r in leaked:
        print(
            f"  [{r['domain']}] {r['question']!r} -> {r['target_type']}/{r['intent']}",
            flush=True,
        )

    # 5. Local/Builtin questions incorrectly delegated
    local_domains = {"session_control", "media_control", "app_control", "device_control"}
    missed = [
        r
        for r in ok_results
        if r["status"] == "delegate" and r["domain"] in local_domains
    ]
    print(
        f"\n--- Local/Builtin Questions Incorrectly Delegated ({len(missed)}) ---",
        flush=True,
    )
    for r in missed:
        print(
            f"  [{r['domain']}] {r['question']!r} -> {r['intent']}",
            flush=True,
        )

    # 6. Multi-turn anaphora
    anaphora_results = [r for r in ok_results if r["domain"] == "multi_turn"]
    print("\n--- Multi-turn Anaphora ---", flush=True)
    for r in anaphora_results:
        modules = r.get("suggested_modules") or []
        has_memory = "Memory" in modules
        print(
            f"  [{r['domain']}] {r['question']!r} -> l1_domain={r.get('l1_domain')} "
            f"intent={r.get('intent')} Memory={has_memory} prev={r.get('previous_intent')}",
            flush=True,
        )

    # 7. Domain vs L1 Domain confusion matrix
    cat_domain = Counter((r["domain"], r.get("l1_domain")) for r in ok_results)
    domains = sorted({r["domain"] for r in ok_results})
    l1_domains = sorted({d for _, d in cat_domain.keys() if d})
    print("\n--- Domain vs L1 Domain Matrix ---", flush=True)
    header = "domain".ljust(16) + " " + " ".join(f"{d:>10}" for d in l1_domains)
    print(header, flush=True)
    for d in domains:
        row = [d.ljust(16)]
        for l1d in l1_domains:
            row.append(f"{cat_domain[(d, l1d)]:>10}")
        print("".join(row), flush=True)

    # 8. Save analysis JSON
    analysis_path = f"{RESULT_PATH}.analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(
            {
            "global": {
                "total": total,
                "errors": len(errors),
                "status": dict(status_counts),
                "target_type": dict(target_counts),
                "l1_domain": dict(l1_domain_counts),
                "bert_hits": len(bert_hits),
                "avg_bert_confidence": (
                    sum(r["confidence"] for r in bert_hits) / len(bert_hits)
                    if bert_hits
                    else 0.0
                ),
            },
            "per_domain": {
                d: {
                    "count": len(recs),
                    "status": dict(Counter(r["status"] for r in recs)),
                    "target_type": dict(Counter(r["target_type"] for r in recs)),
                    "l1_domain": dict(Counter(r.get("l1_domain") for r in recs)),
                }
                for d, recs in by_domain.items()
            },
                "local_leakage": [
                    {
                        "domain": r["domain"],
                        "question": r["question"],
                        "target_type": r["target_type"],
                        "intent": r["intent"],
                    }
                    for r in leaked
                ],
                "missed_local": [
                    {
                        "domain": r["domain"],
                        "question": r["question"],
                        "intent": r["intent"],
                    }
                    for r in missed
                ],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nAnalysis saved to {analysis_path}", flush=True)


async def main() -> None:
    # Start fresh progress file.
    try:
        os.remove(PROGRESS_PATH)
    except FileNotFoundError:
        pass

    global USE_DB
    if USE_DB:
        try:
            await db_resource_manager.initialize(create_tables=True, seed_data=False)
            print("[eval_routing] Database initialized", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[eval_routing] DB initialization failed ({exc}); falling back to mock mode",
                flush=True,
            )
            USE_DB = False

    bert_available = init_classifier()
    print(
        f"[eval_routing] BERT ONNX classifier available: {bert_available}",
        flush=True,
    )
    print(
        "[eval_routing] Agent execution DISABLED — only routing decisions are observed",
        flush=True,
    )

    router = await build_router()
    results: list[dict[str, Any]] = []
    seen_threads: set[str] = set()

    for i, item in enumerate(QUESTIONS):
        domain = item["domain"]
        text = item["text"]
        expected = item.get("expected")
        thread_id = item.get("thread_id") or f"{domain}-{i}"

        if thread_id not in seen_threads:
            clear_thread_intent_state(thread_id)
            seen_threads.add(thread_id)

        rec = await evaluate_one(router, domain, text, thread_id, expected)
        results.append(rec)

        if "error" in rec:
            print(f"[{rec['domain']}] ERROR: {rec['error']}", flush=True)
        else:
            modules = ",".join(rec.get("suggested_modules") or [])
            extra = f" modules={modules}" if modules else ""
            print(
                f"[{rec['domain']}] {rec['question']!r:40} -> "
                f"{rec['status']}/{rec['target_type']:<10} "
                f"l1_domain={(rec['l1_domain'] or ''):<18} intent={(rec.get('intent') or ''):<18} conf={rec['confidence']:.2f}"
                f"{extra} ({rec['elapsed'] * 1000:.1f}ms)",
                flush=True,
            )

        with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

    analyze(results)

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nRaw results saved to {RESULT_PATH}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
