# Agent 主动宏验证机制实施文档

## 1. 背景与目标

### 1.1 问题背景

当前系统的宏脚本验证采用静态 Dry-Run 机制，存在以下致命缺陷：

- **环境敏感**：录制环境与执行环境差异（广告弹窗、布局变化、网络延迟）导致验证失效
- **被动检测**：遇到问题即失败，无法自我修复
- **静态比对**：仅比对坐标/选择器是否匹配，无法处理动态变化

### 1.2 目标

建立**Agent 主动验证机制**，实现：

1. **实战化验证**：Agent 在真实环境中执行宏，遇到异常主动处理
2. **自我修复**：发现问题时根据心法自主决策，修正执行策略
3. **宏进化**：将验证过程中的修正沉淀为增强版宏，提升鲁棒性
4. **分级输出**：根据验证结果自动判定执行模式（Deterministic/Hybrid/Agentic）

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Agent 主动验证架构                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐              │
│  │   输入层     │─────▶│   验证引擎   │─────▶│   输出层     │              │
│  └──────────────┘      └──────────────┘      └──────────────┘              │
│         │                     │                     │                       │
│         ▼                     ▼                     ▼                       │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐              │
│  │ • 初版宏     │      │ • Agent 执行 │      │ • 增强宏     │              │
│  │ • 心法指南   │      │ • 异常处理   │      │ • 验证报告   │              │
│  │ • 原始录制   │      │ • 策略修正   │      │ • 执行模式   │              │
│  │ • 目标环境   │      │ • 多轮迭代   │      │ • 置信度     │              │
│  └──────────────┘      └──────────────┘      └──────────────┘              │
│                               │                                             │
│                               ▼                                             │
│                        ┌──────────────┐                                    │
│                        │  知识库      │                                    │
│                        │ • 历史验证   │                                    │
│                        │ • 常见异常   │                                    │
│                        │ • 修复策略   │                                    │
│                        └──────────────┘                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 位置 |
|------|------|------|
| `AgentMacroValidator` | 验证入口，管理验证生命周期 | `app/core/execution/macro/agent_validator.py` |
| `VerificationWorker` | Agent 执行器，负责单步验证 | `app/core/execution/macro/verification_worker.py` |
| `AnomalyDetector` | 异常检测器，识别环境变化 | `app/core/execution/macro/anomaly_detector.py` |
| `StrategyAdapter` | 策略适配器，生成修正方案 | `app/core/execution/macro/strategy_adapter.py` |
| `MacroEvolver` | 宏进化器，合并修正到宏脚本 | `app/core/execution/macro/macro_evolver.py` |
| `VerificationReporter` | 报告生成器，输出验证结果 | `app/core/execution/macro/verification_reporter.py` |

---

## 3. 核心流程

### 3.1 主流程

```
开始验证
    │
    ▼
┌─────────────────┐
│ 1. 初始化环境   │  连接目标设备/浏览器，确保环境就绪
│    加载输入     │  解析宏脚本 + 心法 + 原始录制
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 预分析       │  分析宏脚本结构，识别高风险步骤
│    (静态分析)   │  如：坐标依赖、固定等待、硬编码值
└────────┬────────┘
         │
         ▼
┌─────────────────┐     失败
│ 3. 第一轮验证   │──────────────▶ 尝试修复 ──▶ 无法修复 ──▶ 人工介入
│    (基准环境)   │
└────────┬────────┘
         │ 成功
         ▼
┌─────────────────┐     失败
│ 4. 第二轮验证   │──────────────▶ 尝试修复 ──▶ 记录问题
│    (干扰环境)   │
└────────┬────────┘
         │ 成功
         ▼
┌─────────────────┐
│ 5. 宏进化       │  合并所有修正策略到增强版宏
│    生成增强版   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. 输出结果     │  增强宏 + 验证报告 + 执行模式建议
└────────┬────────┘
         │
         ▼
      结束
```

### 3.2 单步验证流程

```
执行宏步骤
    │
    ▼
┌─────────────────┐
│ 观察当前状态    │  dump_ui / screenshot
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 评估执行策略    │
│                 │
│ • 宏步骤是否    │
│   适合当前状态？│
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
  适合      不适合
    │         │
    ▼         ▼
┌────────┐  ┌─────────────────┐
│ 直接执行│  │ 异常处理流程    │
│        │  │                 │
└───┬────┘  │ 1. 诊断异常类型 │
    │       │ 2. 查询修复策略 │
    │       │ 3. 生成修正方案 │
    │       │ 4. 执行修正     │
    │       │ 5. 验证修正效果 │
    │       └────────┬────────┘
    │                │
    │           ┌────┴────┐
    │           ▼         ▼
    │        成功      失败
    │           │         │
    │           ▼         ▼
    │      记录修正    再次尝试/跳过
    │      继续下一步  标记风险
    │                │
    └────────────────┘
         │
         ▼
┌─────────────────┐
│ 记录执行结果    │
│ • 实际参数      │
│ • 耗时          │
│ • 修正策略      │
└─────────────────┘
```

---

## 4. 异常处理策略库

### 4.1 异常类型与处理

| 异常类型 | 检测特征 | 处理策略 | 示例 |
|---------|---------|---------|------|
| **坐标漂移** | 目标位置偏差 > 10% | 重新定位 + 坐标修正 | 按钮换了位置 |
| **元素未找到** | selector 匹配失败 | 模糊匹配 + 备用选择器 | ID 变化 |
| **遮挡弹窗** | 目标元素 covered | 关闭弹窗 + 重试 | 广告弹窗 |
| **状态错位** | 当前页非预期 | 导航回正 + 分支处理 | 意外跳转 |
| **加载超时** | 元素未按时出现 | 动态等待 + 超时处理 | 网络慢 |
| **流程分叉** | 出现预期外分支 | 条件分支 + 递归验证 | 新手引导 |
| **数据变化** | 内容不匹配 | 参数化 + 动态提取 | 列表变化 |

### 4.2 策略适配决策树

```
执行失败
    │
    ▼
┌─────────────────┐
│ 能否获取        │
│ 当前 UI 状态？  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
   否        是
    │         │
    ▼         ▼
┌────────┐  ┌─────────────────┐
│ 致命错误│  │ 分析当前状态    │
│ 标记    │  │ 与预期差异      │
└────────┘  └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ 差异类型？      │
            └────────┬────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
      位置        状态          遮挡
        │          │            │
        ▼          ▼            ▼
   ┌────────┐  ┌────────┐   ┌────────┐
   │ 重定位 │  │ 状态机 │   │ 关闭   │
   │ 修正   │  │ 转移   │   │ 重试   │
   └────────┘  └────────┘   └────────┘
```

---

## 5. 接口设计

### 5.1 验证请求接口

```python
# POST /api/v1/learning/skills/verify-with-agent

class AgentVerificationRequest(BaseModel):
    """Agent 验证请求"""

    # 输入
    macro_script: List[dict]           # 初版宏脚本
    instructions: str                  # 心法指南
    session_id: Optional[str]          # 原始录制会话（参考用）

    # 环境配置
    target_environment: EnvironmentConfig  # 目标验证环境

    # 验证配置
    max_rounds: int = 2                # 最大验证轮数
    round_configs: List[RoundConfig]   # 每轮环境配置

    # Agent 配置
    agent_config: Optional[AgentConfig] = None

    # 输出配置
    output_mode: str = "evolved"       # evolved / report_only


class EnvironmentConfig(BaseModel):
    """验证环境配置"""
    platform: str                      # web / android / desktop
    device_id: Optional[str]           # 设备标识
    browser_config: Optional[dict]     # 浏览器配置
    resolution: Optional[tuple]        # 目标分辨率


class RoundConfig(BaseModel):
    """单轮验证配置"""
    round_name: str                    # 轮次名称（如"基准环境"）
    environment_overrides: dict        # 环境覆盖参数
    inject_anomalies: List[str]        # 注入的异常类型（测试用）
    timeout_per_step: int = 30         # 单步超时（秒）


class AgentConfig(BaseModel):
    """Agent 行为配置"""
    llm_model: str = "gpt-4o"          # 使用模型
    max_retries_per_step: int = 3      # 单步最大重试
    allow_strategy_adaptation: bool = True  # 允许策略自适应
    conservative_mode: bool = False    # 保守模式（更谨慎）
```

### 5.2 验证响应接口

```python
class AgentVerificationResponse(BaseModel):
    """Agent 验证响应"""

    # 状态
    success: bool                      # 验证流程是否完成
    status: str                        # completed / partial_failed / failed

    # 增强输出
    evolved_macro: Optional[MacroScript]   # 增强版宏
    execution_mode: str                # deterministic / hybrid / agentic
    confidence_score: float            # 置信度 0-1

    # 详细报告
    verification_report: VerificationReport

    # 元数据
    processing_time_seconds: float
    rounds_completed: int


class VerificationReport(BaseModel):
    """详细验证报告"""

    # 汇总
    summary: ReportSummary

    # 逐轮详情
    rounds: List[RoundReport]

    # 问题清单
    issues: List[VerificationIssue]

    # 优化建议
    recommendations: List[str]


class RoundReport(BaseModel):
    """单轮验证报告"""
    round_number: int
    round_name: str
    status: str                        # success / partial / failed

    # 执行统计
    total_steps: int
    passed_steps: int
    failed_steps: int
    adapted_steps: int                 # 被修正的步骤数

    # 逐步骤详情
    step_results: List[StepResult]

    # 环境快照
    environment_snapshot: dict


class StepResult(BaseModel):
    """单步执行结果"""
    step_number: int
    original_step: dict                # 原始步骤

    # 执行状态
    status: str                        # passed / adapted / failed / skipped

    # 执行详情
    execution: ExecutionDetail

    # 修正记录（如有）
    adaptations: List[AdaptationRecord]

    # 耗时
    execution_time_ms: int


class ExecutionDetail(BaseModel):
    """执行详情"""
    pre_state: dict                    # 执行前 UI 状态
    action_taken: dict                 # 实际执行的动作
    post_state: dict                   # 执行后 UI 状态
    screenshot_path: Optional[str]     # 截图路径


class AdaptationRecord(BaseModel):
    """修正记录"""
    anomaly_type: str                  # 异常类型
    original_strategy: dict            # 原始策略
    adapted_strategy: dict             # 修正后策略
    reasoning: str                     # 修正原因
    success: bool                      # 修正是否成功
```

### 5.3 异步验证接口（长时间验证）

```python
# POST /api/v1/learning/skills/verify-with-agent/async
# 返回 job_id，支持轮询和 WebSocket 进度推送

class AsyncVerificationRequest(AgentVerificationRequest):
    webhook_url: Optional[str]         # 完成回调
    websocket_channel: Optional[str]   # WebSocket 频道


# GET /api/v1/learning/skills/verification-jobs/{job_id}
class VerificationJobStatus(BaseModel):
    job_id: str
    status: str                        # pending / running / completed / failed
    progress_percent: int
    current_round: int
    current_step: int
    current_phase: str                 # 当前阶段描述

    # 中间结果（流式更新）
    partial_results: Optional[RoundReport]

    # 最终结果（完成后）
    final_result: Optional[AgentVerificationResponse]
```

---

## 6. 宏进化规则

### 6.1 修正合并策略

```
单步修正 ──→ 策略分类 ──→ 合并到宏

坐标修正    ──→ 更新坐标值 + 增加选择器备用
等待优化    ──→ fixed_wait ──→ wait_for_element
分支添加    ──→ 插入 if/else 控制流
异常处理    ──→ 包装 try/catch 或前置检查
选择器增强  ──→ 单选择器 ──→ 多选择器 fallback
```

### 6.2 进化示例

**原始宏：**
```yaml
steps:
  - type: action
    event_type: tap
    source: mobile
    payload:
      x: 0.5
      y: 0.3

  - type: wait
    payload:
      seconds: 3

  - type: action
    event_type: input
    payload:
      text: "hardcoded_value"
```

**验证发现问题：**
1. 第一轮：坐标 (0.5, 0.3) 实际按钮在 (0.55, 0.32)
2. 第二轮：出现弹窗遮挡，需先关闭
3. 第二轮：等待 3s 后元素仍未加载，实际需要 5s

**增强宏：**
```yaml
steps:
  - type: if                    # 新增：异常前置处理
    condition:
      type: element_exists
      target_selector: "广告弹窗关闭按钮"
    then_steps:
      - type: action
        event_type: tap
        target_selector: "广告弹窗关闭按钮"

  - type: action
    event_type: tap
    source: mobile
    payload:
      x: 0.55                   # 修正：从 0.5 → 0.55
      y: 0.32                   # 修正：从 0.3 → 0.32
    target_selector:            # 增强：增加文本备选
      - "登录按钮"               # 新增
      - "button_login"          # 新增

  - type: wait_for              # 优化：从固定等待 → 智能等待
    payload:
      selector: "输入框"
      timeout_ms: 5000          # 修正：从 3s → 5s

  - type: extract               # 增强：从硬编码 → 动态提取
    extract_type: gui_extract
    key: input_value
    payload:
      relative_position: {x: 0.55, y: 0.5}
    # 原始硬编码值作为 fallback
```

---

## 7. 执行模式判定

### 7.1 判定规则

```python
def determine_execution_mode(report: VerificationReport) -> str:
    """根据验证报告判定执行模式"""

    # 提取关键指标
    success_rate = report.summary.overall_success_rate
    adaptation_rate = report.summary.adaptation_rate
    max_round_variance = report.summary.max_round_variance

    # Deterministic: 高成功率 + 低修正率 + 跨轮一致
    if (success_rate >= 0.95 and
        adaptation_rate <= 0.1 and
        max_round_variance <= 0.05):
        return "deterministic"

    # Hybrid: 中高成功率 + 有修正但可沉淀
    if (success_rate >= 0.80 and
        adaptation_rate <= 0.3):
        return "hybrid"

    # Agentic: 低成功率 或 高方差（环境敏感）
    return "agentic"
```

### 7.2 模式含义

| 模式 | 含义 | 执行策略 |
|------|------|---------|
| **Deterministic** | 宏可靠 | 完全按增强宏执行，Agent 仅监控 |
| **Hybrid** | 宏基本可靠 | 大部分步骤用宏，高风险步骤转 Agent |
| **Agentic** | 宏不可靠 | 完全由 Agent 按心法自主执行 |

---

## 8. 错误处理与降级

### 8.1 验证流程失败处理

```
验证中断（如环境崩溃）
    │
    ▼
┌─────────────────┐
│ 保存中间状态    │
│ • 已完成的轮次  │
│ • 已验证的步骤  │
│ • 已发现的修正  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 决策            │
└────────┬────────┘
         │
    ┌────┴────┬────────┐
    ▼         ▼        ▼
  可恢复    部分结果  完全失败
    │         │        │
    ▼         ▼        ▼
  断点续验   降级输出   人工介入
  （从断点   （基于已    或
   继续）    完成部分）  放弃
```

### 8.2 降级输出策略

| 失败阶段 | 可用输出 | 处理方式 |
|---------|---------|---------|
| 初始化失败 | 无 | 返回错误，建议检查环境 |
| 第一轮失败 | 原始宏 + 问题分析 | 标记为 Agentic 模式 |
| 第二轮失败 | 第一轮增强宏 + 部分报告 | Hybrid 模式 + 风险提示 |
| 进化阶段失败 | 各轮独立结果 | 人工选择使用哪个版本 |

---

## 9. 实施步骤

### Phase 1: 核心框架（Week 1-2）

**目标**：基础验证流程跑通

- [ ] 1.1 创建 `AgentMacroValidator` 主类
- [ ] 1.2 实现 `VerificationWorker` 单步执行
- [ ] 1.3 实现 `AnomalyDetector` 基础异常检测
- [ ] 1.4 集成现有 MacroEngine，支持 dry-run 模式开关
- [ ] 1.5 基础报告生成

**验收标准**：能完成一轮基础验证，输出通过/失败结果

### Phase 2: 智能修正（Week 3-4）

**目标**：支持自我修复

- [ ] 2.1 实现 `StrategyAdapter`，支持 5+ 种修正策略
- [ ] 2.2 集成 LLM 决策（选择修正策略）
- [ ] 2.3 实现单步重试机制
- [ ] 2.4 异常类型识别优化

**验收标准**：遇到常见异常（弹窗、坐标偏移）能自动修复

### Phase 3: 宏进化（Week 5-6）

**目标**：生成增强宏

- [ ] 3.1 实现 `MacroEvolver` 修正合并
- [ ] 3.2 定义进化规则库
- [ ] 3.3 支持多轮验证
- [ ] 3.4 执行模式自动判定

**验收标准**：输入原始宏，输出增强宏，且增强宏鲁棒性可验证

### Phase 4: 集成优化（Week 7-8）

**目标**：生产可用

- [ ] 4.1 替换现有 `verify_macro_script`
- [ ] 4.2 实现异步验证 API
- [ ] 4.3 WebSocket 进度推送
- [ ] 4.4 性能优化（验证耗时 < 5 分钟）
- [ ] 4.5 完整测试覆盖

**验收标准**：集成到合成流程，端到端可用

### Phase 5: 高级功能（Week 9+）

- [ ] 5.1 历史验证数据学习
- [ ] 5.2 常见异常模式库
- [ ] 5.3 多设备并行验证
- [ ] 5.4 验证可视化回放

---

## 10. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Agent 决策不可靠 | 生成错误修正 | 保守模式开关 + 人工审核阈值 |
| 验证耗时过长 | 用户体验差 | 异步化 + 流式进度 + 超时机制 |
| 环境依赖复杂 | 难以维护 | 环境抽象层 + 容器化测试 |
| LLM 成本过高 | 运营成本高 | 缓存策略 + 分级模型（简单用轻量模型）|

---

## 11. 附录

### 11.1 相关文件位置

```
backend/app/core/execution/macro/
├── __init__.py
├── engine.py                    # 现有宏引擎
├── service.py                   # 现有服务
├── schema.py                    # 现有模型
├── agent_validator.py           # 新增：主验证器
├── verification_worker.py       # 新增：Agent 执行器
├── anomaly_detector.py          # 新增：异常检测
├── strategy_adapter.py          # 新增：策略适配
├── macro_evolver.py             # 新增：宏进化
└── verification_reporter.py     # 新增：报告生成

backend/app/api/routes/learning.py
# 新增端点：verify-with-agent
# 新增端点：verification-jobs
```

### 11.2 关键依赖

```python
# 核心依赖（已有）
- langchain / langgraph          # Agent 框架
- openai / anthropic            # LLM API
- pydantic                      # 模型验证

# 可能需要新增
- jsonschema                    # 宏脚本校验增强
- deepdiff                      # 状态比对
```

### 11.3 术语表

| 术语 | 定义 |
|------|------|
| 心法 | 专家指南（instructions），描述任务逻辑和策略 |
| 初版宏 | LLM 或录制直接生成的原始宏脚本 |
| 增强宏 | 经过验证和修正后的鲁棒版宏脚本 |
| 异常 | 执行时遇到的环境与预期不符的情况 |
| 修正 | 针对异常采取的替代执行策略 |
| 进化 | 将修正沉淀回宏脚本的过程 |
| 验证轮 | 在特定环境下的完整验证执行 |

---

**文档版本**: 1.0
**创建日期**: 2024-01-XX
**作者**: EvoLoop Team
**状态**: 待评审
