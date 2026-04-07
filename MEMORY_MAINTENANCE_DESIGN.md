# EvoLoop 记忆系统自动维护机制设计

**设计日期**: 2026-04-02  
**状态**: 已实现  
**版本**: 1.0

---

## 一、概述

### 1.1 目标

建立全自动化的记忆维护系统，确保：
1. **质量保持** - 自动识别并清理低质量记忆
2. **存储优化** - 归档过期记忆，释放空间
3. **热记忆刷新** - 每日更新 MEMORY.md
4. **可追溯性** - 生成维护报告供审查

### 1.2 设计原则

- **保守删除** - 默认只归档，不自动删除
- **可配置** - 所有参数可调
- **可观察** - 生成详细报告
- **可回滚** - 归档而非永久删除

---

## 二、架构设计

### 2.1 组件架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Queue (Huey/Celery)                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │ Daily Maintenance   │    │ Hourly Stats Collection     │ │
│  │ Cron: 0 2 * * *     │    │ Cron: 0 * * * *             │ │
│  └──────────┬──────────┘    └─────────────────────────────┘ │
│             │                                                │
│             ▼                                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │            MemoryMaintenanceTask                      │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │  │
│  │  │  Cleanup    │ │ Regenerate  │ │   Consolidate   │  │  │
│  │  │  Service    │ │ Hot Memory  │ │   Daily Logs    │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘  │  │
│  └─────────────────────────┬─────────────────────────────┘  │
│                            │                                 │
│                            ▼                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │               Maintenance Report                      │  │
│  │         (Saved as MemoryEntry for history)            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
1. Daily Maintenance Trigger (2:00 AM)
   │
   ├─▶ Analyze Quality
   │   ├─ Score all memories (freshness, usage, specificity, actionability)
   │   ├─ Identify low quality (< 0.3)
   │   └─ Generate recommendations
   │
   ├─▶ Execute Cleanup (if auto_archive=True)
   │   ├─ Archive: 90+ days old project memories → tag "archived"
   │   ├─ Tag: stale memories → tag "needs_update"
   │   └─ Delete: very low quality (optional, default off)
   │
   ├─▶ Regenerate Hot Memory
   │   ├─ Collect all cold memories
   │   ├─ Score: confidence × access_count × freshness
   │   ├─ Apply budgets per section
   │   └─ Write MEMORY.md
   │
   ├─▶ Consolidate Daily Logs
   │   ├─ Read yesterday's log
   │   ├─ Cluster similar entries
   │   └─ Create/update consolidated memories
   │
   └─▶ Save Report
       └─ Create MemoryEntry with full report
```

---

## 三、核心组件

### 3.1 Maintenance Tasks (`tasks.py`)

| 组件 | 职责 | 调度 |
|------|------|------|
| `daily_memory_maintenance` | 完整维护流程 | 每日 2:00 AM |
| `hourly_memory_stats` | 轻量级统计收集 | 每小时 |
| `run_memory_maintenance` | 手动触发入口 | 按需 |

**报告结构** (`MaintenanceReport`):

```python
@dataclass
class MaintenanceReport:
    timestamp: datetime
    duration_seconds: float
    
    # Cleanup stats
    memories_analyzed: int
    memories_archived: int
    memories_deleted: int
    memories_updated: int
    
    # Quality stats
    low_quality_found: int
    avg_quality_score: float
    
    # Two-tier stats
    hot_memory_regenerated: bool
    hot_memory_entries: int
    
    # Logs
    logs_consolidated: int
    
    # Errors
    errors: List[str]
```

### 3.2 清理策略

#### 质量评分维度

| 维度 | 权重 | 计算方式 |
|------|------|---------|
| 新鲜度 | 25% | 指数衰减，30天半衰期 |
| 使用频率 | 30% | 访问计数归一化 |
| 具体程度 | 25% | 正则匹配代码/日期/版本 |
| 可操作性 | 20% | 关键词匹配指令性语言 |

#### 自动动作

| 条件 | 动作 | 默认启用 |
|------|------|---------|
| 质量分 < 0.2 | 标记 "needs_update" | ✅ |
| 90+ 天项目记忆 | 归档 (tag "archived") | ✅ |
| 质量分 < 0.2 + 30+ 天 | 删除 | ❌ (需 --auto-delete) |

### 3.3 热记忆再生

**评分公式**: `score = confidence × (1 + access_count) × freshness`

**预算分配**:

| Section | 行数预算 | 内容类型 |
|---------|---------|---------|
| Architecture | 25 | PROJECT 类型 |
| Decisions | 25 | 关键决策 |
| Patterns | 25 | USER 类型 |
| Gotchas | 20 | FEEDBACK 类型 |
| Progress | 30 | 最近更新 |
| Context | 15 | 临时上下文 |

---

## 四、配置

### 4.1 环境变量

```bash
# 维护配置
MEMORY_AUTO_CLEANUP=true          # 启用自动清理
MEMORY_QUALITY_THRESHOLD=0.3      # 低质量阈值
MEMORY_ARCHIVE_DAYS=90            # 归档天数阈值
MEMORY_MAINTENANCE_HOUR=2         # 维护执行小时 (0-23)

# 任务队列配置
TASK_QUEUE_BACKEND=huey           # huey 或 celery
```

### 4.2 代码配置 (`config.py`)

```python
@dataclass
class MemoryConfig:
    auto_cleanup_enabled: bool = False
    quality_threshold: float = 0.3
    archive_days: int = 90
    hot_memory_max_chars: int = 8000
    cold_memory_results: int = 5
```

---

## 五、使用方式

### 5.1 自动运行

任务通过装饰器自动注册到任务队列：

```python
@periodic_task(cron="0 2 * * *", name="memory_daily_maintenance")
def daily_memory_maintenance():
    """每天 2:00 AM 自动运行"""
    ...
```

**启用调度**:

```bash
# Embedded Mode (Huey)
python -m app.infrastructure.queue.huey_queue

# Full Mode (Celery)
celery -A app.infrastructure.queue.celery worker -B
```

### 5.2 手动触发

```python
# 方法1: 异步调用
from app.core.memory import run_memory_maintenance_async

report = await run_memory_maintenance_async(
    auto_archive=True,
    auto_delete=False,
)

print(f"Analyzed: {report.memories_analyzed}")
print(f"Archived: {report.memories_archived}")
```

```python
# 方法2: 任务队列
from app.core.memory import trigger_maintenance_now

result = trigger_maintenance_now()
report = await result.get(timeout=60)
```

### 5.3 CLI 工具

```bash
# 运行维护
python -m app.core.memory.maintenance_cli run

# 干运行 (分析但不修改)
python -m app.core.memory.maintenance_cli run --dry-run

# 查看统计
python -m app.core.memory.maintenance_cli stats

# 查看上次报告
python -m app.core.memory.maintenance_cli report

# 输出 JSON 报告
python -m app.core.memory.maintenance_cli run --output report.json
```

---

## 六、监控与观察

### 6.1 日志输出

```
[MemoryMaintenance] Starting daily maintenance...
[MemoryMaintenance] Step 1/4: Analyzing memory quality...
[MemoryMaintenance] Step 2/4: Regenerating hot memory...
[MemoryMaintenance] Step 3/4: Consolidating daily logs...
[MemoryMaintenance] Step 4/4: Saving maintenance report...
[MemoryMaintenance] Maintenance complete (SUCCESS): 12.34s, 156 analyzed, 3 archived, 0 errors
```

### 6.2 报告历史

每次维护自动生成报告记忆：

```yaml
---
id: "maintenance-report-20260402-020015"
type: "reference"
privacy: "private"
title: "Daily Memory Maintenance Report - 2026-04-02"
tags: ["maintenance", "report", "auto-generated"]
source: "maintenance_task"
---

# Memory Maintenance Report

**Date**: 2026-04-02 02:00 UTC
**Duration**: 12.34 seconds

## Summary
- **Memories Analyzed**: 156
- **Low Quality Found**: 5
- **Average Quality Score**: 0.72

## Actions Taken
- **Archived**: 3 memories
- **Deleted**: 0 memories
- **Tagged for Update**: 2 memories
- **Hot Memory Regenerated**: Yes (45 entries)
```

### 6.3 指标收集

```python
# 获取上次报告
from app.core.memory import get_last_maintenance_report

report = await get_last_maintenance_report()
print(f"Last run: {report.timestamp}")
print(f"Avg quality: {report.avg_quality_score}")
```

---

## 七、故障处理

### 7.1 错误恢复

| 场景 | 处理策略 |
|------|---------|
| 单个记忆处理失败 | 记录错误，继续处理其他 |
| 存储连接失败 | 终止任务，记录错误 |
| 热记忆再生失败 | 记录错误，不影响清理 |
| 报告保存失败 | 记录到日志，不终止 |

### 7.2 重试机制

- 任务通过任务队列的重试机制
- 默认重试3次，指数退避

---

## 八、扩展性

### 8.1 添加新的清理规则

```python
async def _custom_cleanup_rule(report: MaintenanceReport):
    """自定义清理规则示例"""
    container = await _get_memory_container()
    memories = await container.storage.list_all()
    
    for mem in memories:
        if should_delete_custom(mem):
            await container.storage.delete(mem.id)
            report.memories_deleted += 1
```

### 8.2 自定义报告格式

```python
class CustomMaintenanceReport(MaintenanceReport):
    custom_field: str
    
    def to_dict(self):
        base = super().to_dict()
        base["custom"] = self.custom_field
        return base
```

---

## 九、实施清单

- [x] 创建 `tasks.py` - 维护任务实现
- [x] 创建 `maintenance_cli.py` - 命令行工具
- [x] 更新 `__init__.py` - 导出公共 API
- [x] 编写设计文档
- [ ] 添加单元测试
- [ ] 集成到部署流程
- [ ] 添加监控告警

---

## 十、参考

- [Huey Periodic Tasks](https://huey.readthedocs.io/en/latest/guide.html#periodic-tasks)
- [Celery Beat](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
- [EvoLoop Memory System Assessment](./EVOLOOP_MEMORY_SYSTEM_ASSESSMENT_REPORT.md)

---

*设计: EvoLoop Architecture Team*  
*最后更新: 2026-04-02*
