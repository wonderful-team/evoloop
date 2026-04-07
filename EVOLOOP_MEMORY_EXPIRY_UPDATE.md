# EvoLoop 记忆系统 - 过期与更新机制分析

**分析日期**: 2026-04-02  
**分析范围**: `app/core/memory/` 全模块

---

## 一、概述

EvoLoop 记忆系统具有**多层次**的过期和更新机制，涵盖：

1. **记忆条目更新** (Update) - 修改现有记忆
2. **新鲜度衰减** (Freshness Decay) - 基于时间的质量下降
3. **清理建议** (Cleanup Recommendations) - 自动识别过期记忆
4. **状态追踪过期** (State Tracking TTL) - 短期呈现状态过期
5. **两层级再生** (Two-Tier Regeneration) - 热记忆自动刷新
6. **对话剪枝** (Conversation Pruning) - 短期记忆清理

---

## 二、详细机制

### 2.1 记忆条目更新机制

#### 数据模型 (`models.py`)

```python
@dataclass
class MemoryEntry:
    version: int = 1                    # 乐观锁版本号
    created_at: datetime = ...          # 创建时间
    updated_at: datetime = ...          # 最后更新时间
```

**更新行为**:
- 每次调用 `save()` 时自动更新 `updated_at = datetime.utcnow()`
- 支持通过 `version` 字段实现乐观锁（当前为基础实现）

**代码位置**:
- `file_backend.py:138` - File 存储自动更新时间戳
- `neo4j_backend.py:196` - Neo4j 存储自动更新时间戳

#### 更新操作示例

```python
# 获取现有记忆
entry = await storage.get(entry_id)

# 修改内容
entry.content = "新的内容"
entry.version += 1  # 手动版本递增

# 保存（自动更新 updated_at）
await storage.save(entry)
```

**实现状态**: ✅ **完整**

---

### 2.2 新鲜度衰减机制

#### Two-Tier 新鲜度计算 (`two_tier.py:320-339`)

```python
def _calculate_freshness(self, mem_type: MemoryType, age_days: int) -> float:
    """Calculate freshness based on type-specific lifespan."""
    lifespans = {
        MemoryType.USER: None,       # 永久 - 不衰减
        MemoryType.FEEDBACK: 30,     # 30天
        MemoryType.PROJECT: None,    # 永久 - 不衰减
        MemoryType.REFERENCE: 7,     # 7天
    }
    
    lifespan = lifespans.get(mem_type)
    if lifespan is None:
        return 1.0  # 无衰减
    
    # 线性衰减到0
    return max(0.0, 1.0 - (age_days / lifespan))
```

**不同类型衰减策略**:

| 记忆类型 | 生命周期 | 说明 |
|---------|---------|------|
| `USER` | 永久 | 用户画像不随时间衰减 |
| `PROJECT` | 永久 | 项目架构知识长期有效 |
| `FEEDBACK` | 30天 | 反馈类记忆较快过时 |
| `REFERENCE` | 7天 | 参考信息最快过时 |

#### Quality 新鲜度评分 (`quality.py:127-134`)

```python
FRESHNESS_HALF_LIFE = 30  # 30天半衰期

def _score_freshness(self, entry: MemoryEntry) -> float:
    """使用指数衰减计算新鲜度 (0-1)"""
    age_days = (datetime.utcnow() - entry.updated_at).days
    return math.exp(-age_days / self.FRESHNESS_HALF_LIFE)
```

**半衰期公式**: `freshness = e^(-age_days / 30)`

| 年龄 | 新鲜度评分 |
|------|-----------|
| 0天 | 1.0 |
| 30天 | 0.5 |
| 60天 | 0.25 |
| 90天 | 0.125 |

**实现状态**: ✅ **完整**

---

### 2.3 清理建议机制

#### QualityAnalyzer 清理分析 (`quality.py:210-298`)

```python
async def get_cleanup_recommendations(
    self,
    project_id: Optional[int] = None,
    min_quality: float = 0.3,
) -> List[CleanupRecommendation]:
    """获取需要清理的记忆建议"""
```

**建议动作类型**:

| 动作 | 触发条件 | 说明 |
|------|---------|------|
| `archive` | 90天+ 项目记忆 | 归档过时项目记忆 |
| `update` | 新鲜度 < 0.2 | 建议更新内容 |
| `delete` | 质量分 < 0.2 | 建议删除 |
| `improve` | 其他低质量 | 建议改进 |

**质量评分维度**:

```python
@dataclass
class QualityScores:
    freshness: float      # 新鲜度 (25%)
    usage: float          # 使用频率 (30%)
    specificity: float    # 具体程度 (25%)
    actionability: float  # 可操作性 (20%)
    overall: float        # 加权总分
```

**使用示例**:

```python
from app.core.memory.quality import MemoryQualityAnalyzer

analyzer = MemoryQualityAnalyzer(storage)
recommendations = await analyzer.get_cleanup_recommendations(min_quality=0.3)

for rec in recommendations:
    print(f"{rec.action}: {rec.entry.title}")
    print(f"  原因: {rec.reason}")
    print(f"  建议: {rec.suggestions}")
```

**实现状态**: ✅ **完整**（分析）/ ⚠️ **需手动执行**（未自动运行）

---

### 2.4 状态追踪过期机制

#### MemoryStateTracker (`state_tracking.py:31-149`)

**用途**: 防止在同一会话中重复呈现相同记忆

```python
class MemoryStateTracker:
    DEFAULT_SURFACE_TTL = 3600  # 1小时过期
    
    def get_surfaced_ids(self, thread_id: str, max_age: Optional[float] = None) -> Set[str]:
        """获取已呈现的记忆ID，过滤掉过期的"""
        valid_ids = {
            mem_id for mem_id, timestamp in surfaced.items()
            if (now - timestamp) < max_age  # 过期检查
        }
```

**工作机制**:

1. **标记呈现**: `mark_surfaced(thread_id, memory_ids)` - 记录呈现时间戳
2. **过期检查**: `get_surfaced_ids()` - 过滤超过 TTL 的记录
3. **定期清理**: `_maybe_cleanup()` - 每5分钟清理过期条目

**配置**:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_SURFACE_TTL` | 3600秒 | 记忆呈现后1小时内不再重复 |
| `_cleanup_interval` | 300秒 | 每5分钟清理一次过期条目 |

**实现状态**: ✅ **完整**（自动运行）

---

### 2.5 两层级记忆再生机制

#### TwoTierMemoryManager (`two_tier.py:98-575`)

**架构**:

```
Tier 1 (Hot Memory): MEMORY.md - 会话开始时始终加载
├── Architecture (25行) - 系统设计
├── Decisions (25行) - 关键决策  
├── Patterns (25行) - 模式与约定
├── Gotchas (20行) - 注意事项
├── Progress (30行) - 最近进展
└── Context (15行) - 临时上下文

Tier 2 (Cold Memory): 完整存储 - 按需搜索
├── private/ - 私有记忆
└── team/ - 团队共享记忆
```

**再生算法** (`regenerate_memory_md()`):

```python
async def regenerate_memory_md(self) -> None:
    """
    从 Cold Memory 再生 Hot Memory:
    1. 收集所有 Cold Memory
    2. 按 confidence × access_count × freshness 评分
    3. 按类型分配到不同 section
    4. 应用预算限制并重新分配
    5. 写入 MEMORY.md
    """
```

**评分公式**: `score = confidence × (1 + access_count) × freshness`

**预算限制**:

| Section | 预算(行) | 类型映射 |
|---------|---------|---------|
| Architecture | 25 | PROJECT |
| Decisions | 25 | - |
| Patterns | 25 | USER |
| Gotchas | 20 | FEEDBACK |
| Progress | 30 | - |
| Context | 15 | - |
| **总计** | **140** | Max: 200行 / 25KB |

**实现状态**: ✅ **完整**（需手动或定时触发）

---

### 2.6 对话剪枝机制

#### SQL Short-Term Memory (`sql_short_term.py:173-209`)

```python
async def prune(self, thread_id: str) -> None:
    """
    应用剪枝策略减少 Token 压力。
    当前实现: 保留最近100条消息，删除更早的。
    """
    MAX_MESSAGES = 100
    
    # 删除最旧的消息
    to_delete = total_count - MAX_MESSAGES
    # ... 删除逻辑
```

**剪枝策略**:

| 层级 | 策略 | 触发条件 |
|------|------|---------|
| 短期记忆 | 删除旧消息 | 超过100条 |
| 消息层级 | 标记为不可见 | 业务逻辑触发 |

**实现状态**: ✅ **完整**（基于计数）

---

### 2.7 日誌合并机制

#### Daily Log Consolidation (`daily_log.py`)

**流程**:

```
1. 每日追加写入 logs/YYYY/MM/YYYY-MM-DD.md
2. 夜间定时任务读取日誌
3. 聚类相似记忆
4. 生成/更新 consolidated memories
5. 可选: 清理已合并的日誌条目
```

**相关配置**:

```python
# config.py
auto_cleanup_enabled: bool = False  # 自动清理低质量记忆（默认关闭）
pruning_threshold: int = 100        # 剪枝阈值
```

**实现状态**: ⚠️ **基础实现**（合并逻辑存在但未完全集成定时任务）

---

## 三、机制对比表

| 机制 | 类型 | 触发方式 | 自动化程度 | 用途 |
|------|------|---------|-----------|------|
| **条目更新** | 更新 | 手动 save() | 100% | 修改记忆内容 |
| **新鲜度衰减** | 过期 | 实时计算 | 100% | 排序和评分 |
| **状态追踪 TTL** | 过期 | 时间检查 | 100% | 防止重复呈现 |
| **清理建议** | 分析 | 手动调用 | 0% | 识别过期记忆 |
| **两层级再生** | 更新 | 手动/定时 | 50% | 热记忆刷新 |
| **对话剪枝** | 清理 | 计数触发 | 100% | 控制上下文长度 |
| **日誌合并** | 更新 | 定时任务 | 30% | 聚合每日记忆 |

---

## 四、使用示例

### 4.1 手动更新记忆

```python
from app.core.memory.lifespan import get_memory_manager

manager = get_memory_manager()

# 获取记忆
entry = await manager.get_memory("memory-id")

# 更新
entry.content = "更新的内容"
entry.version += 1
await manager.save_memory(entry)
```

### 4.2 获取清理建议

```python
from app.core.memory.quality import MemoryQualityAnalyzer
from app.core.memory.lifespan import get_memory_container

container = get_memory_container()
analyzer = MemoryQualityAnalyzer(container.storage)

# 获取低质量记忆建议
recommendations = await analyzer.get_cleanup_recommendations(min_quality=0.3)

for rec in recommendations:
    if rec.action == "delete":
        await container.storage.delete(rec.entry.id)
    elif rec.action == "archive":
        # 归档逻辑
        pass
```

### 4.3 再生热记忆

```python
from app.core.memory.two_tier import TwoTierMemoryManager
from app.core.memory.lifespan import get_memory_container

container = get_memory_container()
manager = TwoTierMemoryManager(container.storage)

# 从 Cold Memory 再生 MEMORY.md
await manager.regenerate_memory_md()

# 查看统计
stats = await manager.get_section_stats()
```

### 4.4 检查记忆新鲜度

```python
from datetime import datetime
from app.core.memory.models import MemoryEntry

entry = await storage.get(entry_id)
age_days = (datetime.utcnow() - entry.updated_at).days

# 类型特定衰减
if entry.type == MemoryType.FEEDBACK and age_days > 30:
    print("反馈记忆已过时")
elif entry.type == MemoryType.REFERENCE and age_days > 7:
    print("参考记忆已过时")
```

---

## 五、改进建议

### 高优先级

1. **自动清理任务**
   - 添加定时任务自动执行清理建议
   - 配置阈值自动删除/归档低质量记忆

2. **自动再生热记忆**
   - 定时任务每日再生 MEMORY.md
   - 或基于事件触发（如记忆数量变化>10%）

### 中优先级

3. **版本冲突处理**
   - 完善乐观锁机制，检测并发修改
   - 添加冲突解决策略

4. **过期通知**
   - 向用户提示即将过期的关键记忆
   - 提供一键更新选项

### 低优先级

5. **自定义衰减策略**
   - 允许用户配置不同类型记忆的生命周期
   - 基于项目阶段调整衰减速度

---

## 六、总结

EvoLoop 记忆系统具有**完整但分散**的过期和更新机制：

| 能力 | 状态 |
|------|------|
| 手动更新记忆 | ✅ 完整 |
| 自动时间衰减 | ✅ 完整 |
| 呈现状态过期 | ✅ 完整（自动） |
| 低质量识别 | ✅ 完整（需手动执行） |
| 热记忆刷新 | ✅ 完整（需手动触发） |
| 自动清理 | ⚠️ 框架存在，需集成定时任务 |

**核心优势**: 多种机制覆盖不同场景，从短期状态到长期质量都有考虑。

**主要缺口**: 自动化程度不一，部分机制需要手动触发或集成到定时任务中。

---

*报告生成: EvoLoop Memory Expiry Analysis*  
*生成时间: 2026-04-02*
