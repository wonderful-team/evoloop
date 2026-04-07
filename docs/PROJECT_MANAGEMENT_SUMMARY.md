# 项目管理系统梳理总结

## 📊 核心问题

### 1. 数据分散（最大问题）

```
EvoCloud (远程)          SQLite (本地)              Memory
├── Projects             ├── Repositories           ├── Tree Cache
├── Tasks                ├── Todos                  └── Context
├── Budget/Timesheet     ├── Plans/PlanSteps
└── Statistics           ├── Conversations
                         ├── AutonomousTasks
                         └── Requirements
```

**影响：**
- 无法离线完整使用项目管理
- 备份需要多处操作
- 数据一致性难以保证
- 搜索需要跨多个数据源

### 2. 任务模型混乱

| 模型 | 用途 | 存储 | 问题 |
|------|------|------|------|
| `TodoItem` | 快速待办 | SQLite | 与项目任务割裂 |
| `PlanStep` | 执行计划步骤 | SQLite | 与项目任务无关联 |
| `AutonomousTask` | 定时自主任务 | SQLite | 独立于项目任务 |
| `ProjectRequirementTask` | 需求拆解任务 | SQLite→EvoCloud | 同步复杂 |
| EvoCloud Tasks | 正式项目任务 | EvoCloud | 离线不可用 |

**实际场景：** 用户无法在一个视图看到所有待办事项。

### 3. 需求流程过重

```
当前流程:
文档上传 → 内容提取 → AI分析 → 人工确认 → 任务拆解 → 同步到EvoCloud

耗时: 5-10分钟
问题: 想快速创建个任务太麻烦
```

## 🔴 缺失的关键功能

### 通用项目管理必备

1. **项目治理**
   - ❌ 项目阶段/里程碑
   - ❌ 项目模板
   - ❌ 项目标签/分类

2. **任务管理**
   - ❌ 子任务（层级结构）
   - ❌ 任务依赖
   - ❌ 看板视图
   - ❌ 任务分配

3. **可视化**
   - ❌ 甘特图/时间线
   - ❌ 燃尽图
   - ❌ 项目统计仪表板

4. **协作**
   - ❌ 任务评论
   - ❌ 成员管理
   - ❌ 通知中心

## 🟢 冗余/可简化

1. **队列系统过度设计**
   - 已支持 Celery/Huey/Local 三种
   - 实际 Huey 已满足所有场景
   - Celery 仅用于服务器分布式场景

2. **AutonomousTask 与 EvoCloud Tasks 重叠**
   - 都是定时/周期任务
   - 可以统一模型

3. **同步逻辑分散**
   - 多处实现同步代码
   - 应统一同步层

## 💡 改进建议（优先级排序）

### P0 - 立即修复

1. **统一任务视图**
   ```python
   # 统一查询所有待办
   GET /api/v1/unified-todos?project_id=123
   # 返回: Todos + PlanSteps + AutonomousTasks + EvoCloud Tasks
   ```

2. **快速创建任务**
   ```python
   POST /api/v1/projects/{id}/tasks/quick
   {"title": "修复 bug", "priority": "high"}
   # 跳过需求流程
   ```

### P1 - 短期（1-2周）

1. **本地项目模型**
   - 创建 `LocalProject` 表
   - 可选同步到 EvoCloud
   - 支持离线完整使用

2. **任务关联增强**
   - 任务 ↔ 代码提交
   - 任务 ↔ 会话
   - 任务 ↔ Wiki 页面

### P2 - 中期（1月）

1. **看板视图**
2. **项目统计仪表板**
3. **任务标签系统**

### P3 - 长期（可选）

1. 甘特图
2. 多成员协作
3. 项目模板

## 🎯 决策建议

### 推荐方案：混合模式

```
┌─────────────────────────────────────────┐
│           本地优先 (SQLite)              │
├─────────────────────────────────────────┤
│  • Projects (LocalProject)              │
│  • Tasks (统一模型)                      │
│  • Plans/Steps (关联到 Tasks)            │
│  • Repositories                         │
│  • Wiki                                 │
│  • Documents                            │
├─────────────────────────────────────────┤
│  可选同步 ↕                              │
├─────────────────────────────────────────┤
│           EvoCloud (云端)                │
│  • 跨设备同步                            │
│  • 团队协作                              │
│  • 高级功能 (Budget/Timesheet)           │
└─────────────────────────────────────────┘
```

**好处：**
- 离线完全可用
- 云端作为增强而非依赖
- 简化架构

## 📋 立即行动清单

- [ ] 创建 `unified_tasks` 视图 API
- [ ] 添加快速任务创建接口
- [ ] 评估 LocalProject 模型设计
- [ ] 统一任务模型设计文档
