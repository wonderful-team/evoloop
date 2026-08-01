import asyncio
import json
import os
import sys
import time
from collections import Counter
from typing import Any

import httpx

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:20160/api/v1")
USER = os.environ["EVOCLOUD_USER"]
PASS = os.environ["EVOCLOUD_PASS"]
MAX_EVENTS = 200

# Question bank: (category, question)
QUESTIONS = [
    # 闲聊
    ("chitchat", "你好"),
    ("chitchat", "早上好"),
    ("chitchat", "你是谁"),
    ("chitchat", "你能做什么"),
    ("chitchat", "讲个笑话"),
    ("chitchat", "谢谢"),
    ("chitchat", "再见"),
    ("chitchat", "What can you do?"),
    ("chitchat", "How are you today?"),
    ("chitchat", "Nice to meet you"),
    # 简单任务
    ("simple_task", "计算 123 乘以 456"),
    ("simple_task", "100 美元等于多少人民币"),
    ("simple_task", "提醒我喝水"),
    ("simple_task", "打开计算器"),
    ("simple_task", "打开 Safari"),
    ("simple_task", "帮我截图"),
    ("simple_task", "搜索一下 Python 的官方文档"),
    ("simple_task", "现在几点"),
    ("simple_task", "今天是星期几"),
    ("simple_task", "设置一个 5 分钟后的提醒"),
    # 复杂任务
    ("complex_task", "帮我写一个爬取知乎热榜的 Python 爬虫"),
    ("complex_task", "写一个完整的 TODO List 网页应用"),
    ("complex_task", "帮我重构一个 legacy Python 项目"),
    ("complex_task", "设计一个用户认证系统"),
    ("complex_task", "帮我搭建一个 CI/CD 流水线"),
    ("complex_task", "分析这个目录下所有 Python 文件的质量"),
    ("complex_task", "帮我写一个自动化备份脚本"),
    ("complex_task", "创建一个股票数据分析看板"),
    ("complex_task", "实现一个 Redis 缓存中间件"),
    ("complex_task", "帮我写一个 Docker Compose 配置来跑 Postgres 和 Redis"),
    # 通用查询
    ("query", "法国首都是哪里"),
    ("query", "谁写了《1984》"),
    ("query", "月球离地球多远"),
    ("query", "光速是多少"),
    ("query", "水的沸点是多少"),
    ("query", "秦始皇是谁"),
    ("query", "什么是机器学习"),
    ("query", "解释一下区块链"),
    ("query", "推荐几本好书"),
    ("query", "如何学好英语"),
    # 个人/记忆
    ("memory", "我之前问过你什么"),
    ("memory", "总结一下我的上一个项目"),
    ("memory", "我叫什么名字"),
    ("memory", "第 3 轮我们聊了什么"),
    ("memory", "我常用的编程语言是什么"),
    # 医疗
    ("medical", "感冒有哪些症状"),
    ("medical", "头痛应该怎么缓解"),
    ("medical", "糖尿病是什么"),
    ("medical", "高血压要注意什么"),
    ("medical", "布洛芬有什么副作用"),
    ("medical", "健康饮食建议"),
    ("medical", "失眠怎么办"),
    ("medical", "What are symptoms of flu?"),
    ("medical", "如何提高免疫力"),
    ("medical", "儿童发烧怎么处理"),
    # 金融
    ("finance", "什么是复利"),
    ("finance", "股票期权是什么"),
    ("finance", "等额本息和等额本金有什么区别"),
    ("finance", "通货膨胀是什么意思"),
    ("finance", "如何计算房贷月供"),
    ("finance", "加密货币是什么"),
    ("finance", "个人理财建议"),
    ("finance", "What is compound interest?"),
    ("finance", "如何看股票 K 线图"),
    ("finance", "有哪些省税的方法"),
    # 科研
    ("research", "最新的人工智能研究进展"),
    ("research", "CRISPR 是什么"),
    ("research", "量子计算原理"),
    ("research", "暗物质是什么"),
    ("research", "气候变化的主要原因"),
    ("research", "解释相对论"),
    ("research", "什么是大语言模型"),
    ("research", "基因编辑的伦理问题"),
    ("research", "核能的优缺点"),
    ("research", "最新有哪些论文值得关注"),
    # 编码
    ("coding", "写一个 Python 函数反转字符串"),
    ("coding", "解释一下递归"),
    ("coding", "如何 debug 一段 Python 代码"),
    ("coding", "Git 如何撤销上一次提交"),
    ("coding", "写一个正则表达式匹配手机号"),
    ("coding", "SQL 如何查询重复记录"),
    ("coding", "REST API 设计最佳实践"),
    ("coding", "时间复杂度 O(n log n) 是什么意思"),
    ("coding", "Python 的 decorator 怎么用"),
    ("coding", "写一个快速排序"),
    ("coding", "如何处理并发请求"),
    ("coding", "Docker 和 Kubernetes 的区别"),
    ("coding", "解释一下微服务架构"),
    ("coding", "前端如何调用后端 API"),
    ("coding", "写一个二分查找"),
    ("coding", "如何优化数据库查询"),
    ("coding", "Python 的 GIL 是什么"),
    ("coding", "TypeScript 相比 JavaScript 的优势"),
    ("coding", "什么是 CI/CD"),
    ("coding", "如何写一个单元测试"),
    # 运维
    ("ops", "如何查看磁盘空间"),
    ("ops", "如何重启 Nginx"),
    ("ops", "Docker 常用命令有哪些"),
    ("ops", "如何查看系统进程"),
    ("ops", "SSH 怎么免密登录"),
    ("ops", "如何监控 CPU 使用率"),
    ("ops", "备份 MySQL 数据库的方法"),
    ("ops", "Kubernetes 的 Pod 是什么"),
    ("ops", "如何排查网络连接问题"),
    ("ops", "Linux 如何查看端口占用"),
    # 教育
    ("education", "光合作用是什么"),
    ("education", "教我几个常用汉字"),
    ("education", "如何高效学习一门语言"),
    ("education", "解方程 2x + 5 = 15"),
    ("education", "唐朝历史简介"),
    ("education", "牛顿三大定律"),
    ("education", "如何准备考研"),
    ("education", "What is photosynthesis?"),
    ("education", "三角函数 sin/cos/tan 的含义"),
    ("education", "编程入门推荐学什么语言"),
    # 新闻
    ("news", "今天有什么科技新闻"),
    ("news", "最近 AI 领域有什么突破"),
    ("news", "今天股市怎么样"),
    ("news", "最新的国际新闻"),
    ("news", "国内今天发生了什么大事"),
    ("news", "最近的体育新闻"),
    ("news", "特斯拉最近有什么新闻"),
    ("news", "苹果最新发布会信息"),
    ("news", "有哪些值得关注的创业动态"),
    ("news", "今天天气相关新闻"),
    # 天气
    ("weather", "今天天气怎么样"),
    ("weather", "明天会下雨吗"),
    ("weather", "未来一周天气预报"),
    ("weather", "北京现在多少度"),
    ("weather", "上海明天天气如何"),
    ("weather", "What's the weather like today?"),
    ("weather", "今天适合出门吗"),
    ("weather", "气温多少度"),
    ("weather", "紫外线强吗"),
    ("weather", "空气质量怎么样"),
    # 环境/主机
    ("environment", "我用的是什么系统"),
    ("environment", "现在有哪些程序在运行"),
    ("environment", "我的电脑型号是什么"),
    ("environment", "磁盘空间还剩多少"),
    ("environment", "有哪些设备连接了"),
    ("environment", "网络连接正常吗"),
    ("environment", "Docker 有哪些容器在跑"),
    ("environment", "后台有哪些任务"),
    ("environment", "我安装了哪些应用"),
    ("environment", "浏览器打开了哪些标签"),
    # 模糊/歧义
    ("ambiguous", "帮我"),
    ("ambiguous", "做点什么"),
    ("ambiguous", "我不知道该干嘛"),
    ("ambiguous", "修一下"),
    ("ambiguous", "让它更好"),
    ("ambiguous", "你看着办"),
    ("ambiguous", "怎么办"),
    ("ambiguous", "开始吧"),
    ("ambiguous", "继续"),
    ("ambiguous", " ??? "),
    # 多意图
    ("multi_intent", "打开 Chrome 然后搜索今天的新闻"),
    ("multi_intent", "写一个 Python 脚本，同时告诉我天气"),
    ("multi_intent", "查一下股票行情，然后总结一下"),
    ("multi_intent", "微信怎么发消息给联系人"),
    ("multi_intent", "帮我找文件并列出重复项"),
    ("multi_intent", "计算房贷并给出理财建议"),
    ("multi_intent", "写代码并运行测试"),
    ("multi_intent", "搜索资料并整理成文档"),
    ("multi_intent", "打开应用然后截图"),
    ("multi_intent", "查天气和路况"),
    # 边界
    ("edge", "a"),
    ("edge", "1+1=?"),
    ("edge", "用 500 字详细解释 Python 的 GIL 是什么，为什么存在，对多线程有什么影响，如何避免"),
    ("edge", "Write a Python function and explain it in Chinese."),
    ("edge", "用英文告诉我你叫什么"),
    ("edge", "把这个代码改对：def foo(): return x + 1"),
    ("edge", "你能控制我的电脑吗"),
    ("edge", "你能访问互联网吗"),
    ("edge", "你能记住我们的对话吗"),
    ("edge", "如何安全地删除重复文件"),
]


async def login():
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/login/access-token",
            data={"username": USER, "password": PASS, "grant_type": "password", "scope": ""},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def evaluate_question(
    token: str,
    category: str,
    question: str,
    model: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    chat_payload = {"message": question, "project_id": 0}
    if model:
        chat_payload["model"] = model
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
            r = await client.post(
                f"{BASE_URL}/chat",
                json=chat_payload,
                headers=headers,
            )
            r.raise_for_status()
            chat_resp = r.json()
    except Exception as e:
        return {
            "category": category,
            "question": question,
            "thread_id": None,
            "error": f"chat request failed: {e}",
            "elapsed": time.time() - start,
        }

    thread_id = chat_resp["thread_id"]
    events: list[dict] = []
    first_action = None
    first_action_time = None
    first_tool_calls = None
    route_to_task = None
    direct_text = ""
    session_done = False
    last_agent_state = None
    supervisor_task_name = "Supervisor Decision"

    async def stream_loop():
        nonlocal direct_text, first_action, first_action_time, first_tool_calls, session_done, route_to_task, last_agent_state
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout + 5)) as stream_client:
            async with stream_client.stream(
                "GET",
                f"{BASE_URL}/stream/chat/{thread_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if time.time() - start > timeout:
                        break
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    events.append(payload)
                    if len(events) > MAX_EVENTS:
                        break

                    etype = payload.get("type")
                    data = payload.get("data", {})

                    if etype == "agent_state":
                        task_name = payload.get("task_name")
                        mode = payload.get("mode")
                        last_agent_state = (mode, task_name, payload.get("task_status"))
                        # If the engine has transitioned to a Worker task, the Supervisor
                        # already decided to route to Worker. Capture this as the first action
                        # and stop watching — we don't want to evaluate Worker execution here.
                        if task_name and task_name != supervisor_task_name and not first_action:
                            first_action = "route_to_worker"
                            route_to_task = task_name
                            first_action_time = time.time() - start
                            return

                    if etype == "message" and data.get("role") == "ai":
                        content = data.get("content") or ""
                        tool_calls = data.get("tool_calls") or []
                        if tool_calls and not first_action:
                            if last_agent_state and last_agent_state[1] != supervisor_task_name:
                                # First visible tool call is from a Worker node
                                first_action = "route_to_worker"
                                route_to_task = last_agent_state[1]
                            else:
                                first_action = classify_tool_calls(tool_calls)
                            first_action_time = time.time() - start
                            first_tool_calls = tool_calls
                            return
                        if content and not first_action:
                            direct_text += content
                    elif etype == "token":
                        direct_text += payload.get("content", "")
                    elif etype in ("session_completed", "run_end"):
                        session_done = True
                        if not first_action:
                            first_action = "direct_answer"
                            first_action_time = time.time() - start
                            return

    try:
        await asyncio.wait_for(stream_loop(), timeout=timeout + 5)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        return {
            "category": category,
            "question": question,
            "thread_id": thread_id,
            "error": f"stream failed: {e}",
            "elapsed": time.time() - start,
        }
    finally:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as stop_client:
                await stop_client.post(
                    f"{BASE_URL}/chat/stop",
                    json={"thread_id": thread_id},
                    headers=headers,
                )
        except Exception:
            pass

    if not first_action:
        first_action = "no_action_timeout"
        first_action_time = time.time() - start

    return {
        "category": category,
        "question": question,
        "thread_id": thread_id,
        "first_action": first_action,
        "first_action_time": first_action_time,
        "direct_text": direct_text[:500],
        "tool_calls": first_tool_calls,
        "route_to_task": route_to_task,
        "session_done": session_done,
        "elapsed": time.time() - start,
        "event_count": len(events),
    }


def classify_tool_calls(tool_calls: list[dict]) -> str:
    if not tool_calls:
        return "direct_answer"
    names = [tc.get("name") or tc.get("function", {}).get("name", "") for tc in tool_calls]
    if any(n == "route_to" for n in names):
        for tc in tool_calls:
            if tc.get("name") == "route_to":
                args = tc.get("args", tc.get("arguments", {}))
                target = args.get("target") if isinstance(args, dict) else None
                return f"route_to_{target}" if target else "route_to"
    if any(n == "run_macro" for n in names):
        return "run_macro"
    if any(n == "list_macros" for n in names):
        return "list_macros"
    if any(n == "decompose_task" for n in names):
        return "decompose_task"
    if any(n in {"search_history", "recall", "query_concepts"} for n in names):
        return "memory_tool"
    if any(n in {"ask_human", "request_human_input"} for n in names):
        return "ask_human"
    # Any other tool call means the Supervisor tried to execute directly
    return f"direct_tool:{names[0]}"


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        r = await client.post(
            f"{BASE_URL}/login/access-token",
            data={"username": USER, "password": PASS, "grant_type": "password", "scope": ""},
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    model = os.getenv("MODEL", "deepseek-v4-flash")
    per_q_timeout = float(os.getenv("TIMEOUT", "30"))
    out_path = os.getenv("RESULT_PATH", "/tmp/opencode/supervisor_eval_results.json")
    progress_path = f"{out_path}.progress.jsonl"

    # Resume from existing progress file, if any
    normalized: list[dict] = []
    done_keys: set[tuple[str, str]] = set()
    if os.path.exists(progress_path):
        with open(progress_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                normalized.append(rec)
                done_keys.add((rec.get("category", ""), rec.get("question", "")))
        print(f"Resuming {len(normalized)} completed questions from {progress_path}", flush=True)

    print(f"Logged in, token prefix: {token[:6]}..., model={model}, timeout={per_q_timeout}s", flush=True)

    semaphore = asyncio.Semaphore(1)

    async def run_one(category, question):
        async with semaphore:
            try:
                result = await evaluate_question(
                    token, category, question, model=model, timeout=per_q_timeout
                )
            except Exception as e:
                result = {
                    "category": category,
                    "question": question,
                    "thread_id": None,
                    "error": f"uncaught exception: {e}",
                    "first_action": "error",
                    "elapsed": 0,
                }
            if "error" in result:
                print(
                    f"[{result['category']}] ERROR: {result['error']}", flush=True
                )
            else:
                print(
                    f"[{result['category']}] {result['question'][:40]:<40} -> "
                    f"{result['first_action']:<20} in {result['first_action_time']:.1f}s",
                    flush=True,
                )
            if "error" in result and result.get("first_action") is None:
                result["first_action"] = "error"
            normalized.append(result)
            with open(progress_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
            await asyncio.sleep(1)
            return result

    limit = int(os.getenv("LIMIT", "0"))
    question_slice = QUESTIONS[:limit] if limit > 0 else QUESTIONS
    question_slice = [item for item in question_slice if (item[0], item[1]) not in done_keys]
    if not question_slice:
        print("No remaining questions to evaluate.", flush=True)
    tasks = [run_one(cat, q) for cat, q in question_slice]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate
    action_counts = Counter(r.get("first_action", "unknown") for r in normalized)
    category_action_counts = Counter(
        (r.get("category", "unknown"), r.get("first_action", "unknown")) for r in normalized
    )

    print("\n=== Action distribution ===", flush=True)
    for action, count in action_counts.most_common():
        print(f"  {action}: {count}", flush=True)

    print("\n=== Category distribution ===", flush=True)
    for (cat, action), count in sorted(category_action_counts.items()):
        print(f"  {cat} -> {action}: {count}", flush=True)

    # Save results
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": dict(action_counts),
            "category_summary": {f"{cat}::{action}": count for (cat, action), count in category_action_counts.items()},
            "results": normalized,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {out_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
