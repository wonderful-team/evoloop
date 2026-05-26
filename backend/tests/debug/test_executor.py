"""
真实对话测试执行与监控系统

功能：
1. 执行真实话术测试，调用后端 API
2. 实时监控 Agent + LLM 行为
3. 异常检测与自动切断
4. 详细记录测试过程
5. 支持修正后重试

使用：
    python test_executor.py --scenario code_generation --max-rounds 5 --watch
"""

import asyncio
import json
import time
import sys
import os
import signal
import argparse
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import httpx
import traceback

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from test_dialogue_scenarios import ALL_SCENARIOS


class TestStatus(Enum):
    """测试状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"  # 被切断


class AnomalyType(Enum):
    """异常类型"""
    NONE = "none"
    TIMEOUT = "timeout"  # 响应超时
    ERROR_RESPONSE = "error_response"  # 返回错误
    EMPTY_RESPONSE = "empty_response"  # 空响应
    REPETITION = "repetition"  # 重复输出
    INFINITE_LOOP = "infinite_loop"  # 无限循环
    HALLUCINATION = "hallucination"  # 幻觉/编造
    TOOL_FAILURE = "tool_failure"  # 工具调用失败
    CONTEXT_LOSS = "context_loss"  # 上下文丢失
    COST_ANOMALY = "cost_anomaly"  # 成本异常（token 过多）


@dataclass
class RoundRecord:
    """单轮对话记录"""
    round_num: int
    user_input: str
    timestamp: float
    
    # 响应信息
    response_content: str = ""
    response_time_ms: float = 0.0
    tokens_used: int = 0
    
    # Agent 状态
    agent_steps: List[Dict] = field(default_factory=list)
    tools_called: List[str] = field(default_factory=list)
    
    # 异常信息
    anomaly: AnomalyType = AnomalyType.NONE
    anomaly_detail: str = ""
    
    # 原始数据（用于调试）
    raw_response: Dict = field(default_factory=dict)


@dataclass
class TestSession:
    """测试会话"""
    session_id: str
    scenario_name: str
    scenario_desc: str
    start_time: float
    
    thread_id: Optional[str] = None
    status: TestStatus = TestStatus.PENDING
    rounds: List[RoundRecord] = field(default_factory=list)
    
    # 统计
    total_tokens: int = 0
    total_cost: float = 0.0
    
    # 异常汇总
    anomalies: List[Dict] = field(default_factory=list)
    
    # 中断信息
    interrupted_at: Optional[int] = None  # 第几轮被中断
    interrupt_reason: str = ""


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self):
        self.response_history: List[str] = []
        self.max_similarity_threshold = 0.9  # 重复检测阈值
        
    def check(self, record: RoundRecord) -> Optional[Tuple[AnomalyType, str]]:
        """
        检查是否存在异常
        返回: (异常类型, 详细描述) 或 None
        """
        content = record.response_content
        
        # 1. 检查空响应
        if not content or len(content.strip()) < 10:
            return AnomalyType.EMPTY_RESPONSE, f"响应内容过短: {len(content) if content else 0} 字符"
        
        # 2. 检查错误响应
        error_keywords = ["error", "exception", "failed", "timeout", "internal server error"]
        if any(kw in content.lower() for kw in error_keywords[:3]):
            if len(content) < 200:  # 短错误消息
                return AnomalyType.ERROR_RESPONSE, f"可能返回错误: {content[:100]}"
        
        # 3. 检查重复（与历史响应比较）
        for i, hist_content in enumerate(self.response_history[-3:]):  # 只比较最近3轮
            similarity = self._calculate_similarity(content, hist_content)
            if similarity > self.max_similarity_threshold:
                return AnomalyType.REPETITION, f"与第 {len(self.response_history)-3+i} 轮重复度 {similarity:.2%}"
        
        # 4. 检查工具调用失败
        if record.tools_called:
            for step in record.agent_steps:
                if step.get("status") == "error":
                    return AnomalyType.TOOL_FAILURE, f"工具调用失败: {step.get('tool', 'unknown')}"
        
        # 5. 检查 Token 异常
        if record.tokens_used > 4000:  # 单次超过 4000 token
            return AnomalyType.COST_ANOMALY, f"Token 使用量异常: {record.tokens_used}"
        
        # 6. 检查响应时间异常
        if record.response_time_ms > 30000:  # 超过 30 秒
            return AnomalyType.TIMEOUT, f"响应时间过长: {record.response_time_ms/1000:.1f}s"
        
        # 记录到历史
        self.response_history.append(content)
        if len(self.response_history) > 10:
            self.response_history.pop(0)
        
        return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """简单计算文本相似度"""
        if not text1 or not text2:
            return 0.0
        
        # 使用简单的 Jaccard 相似度
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0


class TestMonitor:
    """测试监控器 - 实时观察 Agent + LLM 行为"""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.detector = AnomalyDetector()
        self.should_stop = False
        
    def on_round_start(self, session: TestSession, round_num: int, user_input: str):
        """轮次开始"""
        msg = f"\n[第 {round_num} 轮] 用户: {user_input[:60]}..."
        print(msg)
        self._notify("round_start", {"session": session, "round": round_num, "input": user_input})
        
    def on_round_complete(self, session: TestSession, record: RoundRecord) -> bool:
        """
        轮次完成，返回是否继续
        返回 False 表示应该切断测试
        """
        # 检测异常
        anomaly = self.detector.check(record)
        
        if anomaly:
            anomaly_type, detail = anomaly
            record.anomaly = anomaly_type
            record.anomaly_detail = detail
            
            msg = f"⚠️  检测到异常 [{anomaly_type.value}]: {detail}"
            print(msg)
            
            session.anomalies.append({
                "round": record.round_num,
                "type": anomaly_type.value,
                "detail": detail,
                "timestamp": time.time()
            })
            
            self._notify("anomaly_detected", {
                "session": session,
                "record": record,
                "anomaly": anomaly_type,
                "detail": detail
            })
            
            # 关键异常：切断测试
            if anomaly_type in [
                AnomalyType.INFINITE_LOOP,
                AnomalyType.ERROR_RESPONSE,
                AnomalyType.TOOL_FAILURE,
            ]:
                print(f"🛑 关键异常，切断测试！")
                return False
        
        # 显示结果
        print(f"   AI ({record.response_time_ms/1000:.1f}s, {record.tokens_used}tokens): {record.response_content[:100]}...")
        
        if record.tools_called:
            print(f"   工具调用: {', '.join(record.tools_called)}")
        
        self._notify("round_complete", {"session": session, "record": record})
        
        return not self.should_stop
    
    def on_test_complete(self, session: TestSession):
        """测试完成"""
        print(f"\n{'='*60}")
        print(f"测试完成: {session.session_id}")
        print(f"状态: {session.status.value}")
        print(f"轮次: {len(session.rounds)}")
        print(f"总 Token: {session.total_tokens}")
        print(f"异常数: {len(session.anomalies)}")
        
        if session.interrupted_at:
            print(f"⚠️  在第 {session.interrupted_at} 轮被切断")
            print(f"原因: {session.interrupt_reason}")
        
        self._notify("test_complete", {"session": session})
    
    def request_stop(self):
        """请求停止测试"""
        self.should_stop = True
        print("\n🛑 收到停止信号，将在当前轮次后停止...")
    
    def _notify(self, event: str, data: Dict):
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                print(f"回调错误: {e}")


class DialogueTestExecutor:
    """对话测试执行器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self.monitor = TestMonitor()
        
    async def execute_scenario(
        self,
        scenario_name: str,
        utterances: List[str],
        max_rounds: int = 10,
        auto_continue: bool = False
    ) -> TestSession:
        """
        执行一个测试场景
        
        Args:
            scenario_name: 场景名称
            utterances: 话术列表
            max_rounds: 最大轮次
            auto_continue: 是否自动继续（不等待人工确认）
        """
        session_id = f"{scenario_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        session = TestSession(
            session_id=session_id,
            scenario_name=scenario_name,
            scenario_desc=f"测试场景: {scenario_name}",
            start_time=time.time()
        )
        
        print(f"\n{'='*60}")
        print(f"开始测试: {scenario_name}")
        print(f"会话 ID: {session_id}")
        print(f"话术数: {len(utterances)}")
        print(f"{'='*60}")
        
        session.status = TestStatus.RUNNING
        
        try:
            # 1. 创建对话
            conv_resp = await self.client.post("/api/conversations/", json={
                "title": f"Test_{scenario_name}"
            })
            session.thread_id = conv_resp.json()["thread_id"]
            print(f"创建对话: {session.thread_id}")
            
            # 2. 逐轮执行
            for i, utterance in enumerate(utterances[:max_rounds], 1):
                if self.monitor.should_stop:
                    session.status = TestStatus.INTERRUPTED
                    session.interrupted_at = i
                    session.interrupt_reason = "人工停止"
                    break
                
                # 开始轮次
                self.monitor.on_round_start(session, i, utterance)
                
                # 执行对话
                record = await self._execute_round(session, i, utterance)
                session.rounds.append(record)
                
                # 监控检查
                should_continue = self.monitor.on_round_complete(session, record)
                
                if not should_continue:
                    session.status = TestStatus.INTERRUPTED
                    session.interrupted_at = i
                    session.interrupt_reason = f"检测到异常: {record.anomaly.value}"
                    
                    if not auto_continue:
                        # 等待人工确认
                        print(f"\n⚠️  测试被切断")
                        print(f"选项: [c]继续 [r]重试当前轮 [s]跳过 [q]退出")
                        choice = input("选择: ").strip().lower()
                        
                        if choice == 'c':
                            print("继续测试...")
                            session.status = TestStatus.RUNNING
                            continue
                        elif choice == 'r':
                            print("重试当前轮...")
                            # 移除当前记录，重试
                            session.rounds.pop()
                            record = await self._execute_round(session, i, utterance)
                            session.rounds.append(record)
                            should_continue = self.monitor.on_round_complete(session, record)
                            if should_continue:
                                session.status = TestStatus.RUNNING
                                continue
                        elif choice == 's':
                            print("跳过剩余测试...")
                            break
                        else:
                            print("退出测试...")
                            break
                    else:
                        break
                
                # 累计统计
                session.total_tokens += record.tokens_used
                
            else:
                # 正常完成所有轮次
                session.status = TestStatus.SUCCESS
                
        except Exception as e:
            session.status = TestStatus.ERROR
            print(f"\n❌ 测试异常: {e}")
            traceback.print_exc()
            
        finally:
            session.total_cost = session.total_tokens * 0.00015  # gpt-4o-mini 约 $0.15/1M
            self.monitor.on_test_complete(session)
            await self._save_report(session)
            
        return session
    
    async def _execute_round(
        self,
        session: TestSession,
        round_num: int,
        user_input: str
    ) -> RoundRecord:
        """执行单轮对话"""
        record = RoundRecord(
            round_num=round_num,
            user_input=user_input,
            timestamp=time.time()
        )
        
        try:
            # 发送消息
            start_time = time.time()
            
            msg_resp = await self.client.post(
                f"/api/conversations/{session.thread_id}/messages",
                json={"content": user_input}
            )
            
            # 等待处理（轮询获取结果）
            await asyncio.sleep(1)  # 等待 LLM 开始处理
            
            # 获取消息历史
            messages_resp = await self.client.get(
                f"/api/conversations/{session.thread_id}/messages",
                params={"limit": 5}
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # 解析响应
            messages = messages_resp.json().get("items", [])
            ai_messages = [m for m in messages if m.get("role") == "ai"]
            
            if ai_messages:
                latest = ai_messages[-1]
                record.response_content = latest.get("content", "")
                record.raw_response = latest
                
                # 提取工具调用
                if latest.get("steps"):
                    record.agent_steps = latest["steps"]
                    record.tools_called = [s.get("tool") for s in latest["steps"] if s.get("tool")]
            
            record.response_time_ms = elapsed_ms
            
            # 估算 Token（实际应从 API 返回获取）
            record.tokens_used = len(user_input) + len(record.response_content)
            
        except httpx.TimeoutException:
            record.anomaly = AnomalyType.TIMEOUT
            record.anomaly_detail = "请求超时"
            record.response_content = "[TIMEOUT]"
            
        except Exception as e:
            record.anomaly = AnomalyType.ERROR_RESPONSE
            record.anomaly_detail = str(e)
            record.response_content = f"[ERROR: {e}]"
            
        return record
    
    async def _save_report(self, session: TestSession):
        """保存测试报告"""
        report = {
            "session_id": session.session_id,
            "scenario_name": session.scenario_name,
            "status": session.status.value,
            "start_time": session.start_time,
            "duration": time.time() - session.start_time,
            "thread_id": session.thread_id,
            "total_tokens": session.total_tokens,
            "total_cost": session.total_cost,
            "anomalies": session.anomalies,
            "interrupted_at": session.interrupted_at,
            "interrupt_reason": session.interrupt_reason,
            "rounds": [
                {
                    "round": r.round_num,
                    "user_input": r.user_input,
                    "response": r.response_content[:500],  # 截断
                    "response_time_ms": r.response_time_ms,
                    "tokens": r.tokens_used,
                    "tools": r.tools_called,
                    "anomaly": r.anomaly.value,
                    "anomaly_detail": r.anomaly_detail,
                }
                for r in session.rounds
            ]
        }
        
        # 保存到文件
        filename = f"tests/monitoring/reports/{session.session_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 报告已保存: {filename}")
        
    async def close(self):
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description='对话测试执行器')
    parser.add_argument('--scenario', type=str, default='code_generation',
                       help='测试场景名称')
    parser.add_argument('--max-rounds', type=int, default=5,
                       help='最大测试轮次')
    parser.add_argument('--auto', action='store_true',
                       help='自动模式（不询问确认）')
    parser.add_argument('--base-url', type=str, default='http://localhost:8000',
                       help='后端 API 地址')
    
    args = parser.parse_args()
    
    # 获取话术
    scenarios = ALL_SCENARIOS.get(args.scenario, [])
    if not scenarios:
        print(f"未知场景: {args.scenario}")
        print(f"可用场景: {list(ALL_SCENARIOS.keys())}")
        return
    
    # 提取话术（处理多轮场景的特殊结构）
    if args.scenario == 'multi_turn':
        utterances = [s["cn"] for s in scenarios[0]]  # 取第一个多轮场景
    else:
        utterances = [s["cn"] for s in scenarios]
    
    # 执行测试
    executor = DialogueTestExecutor(base_url=args.base_url)
    
    # 设置信号处理
    def signal_handler(sig, frame):
        print("\n\n收到中断信号...")
        executor.monitor.request_stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        session = await executor.execute_scenario(
            scenario_name=args.scenario,
            utterances=utterances,
            max_rounds=args.max_rounds,
            auto_continue=args.auto
        )
        
        print(f"\n{'='*60}")
        print(f"最终状态: {session.status.value}")
        print(f"发现问题: {len(session.anomalies)} 个")
        
    finally:
        await executor.close()


if __name__ == "__main__":
    asyncio.run(main())
