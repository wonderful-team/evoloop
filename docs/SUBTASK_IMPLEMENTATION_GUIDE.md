# 子任务功能实施完成

## 📁 新增文件

| 文件 | 描述 | 行数 |
|------|------|------|
| `app/domain/project/requirements/models.py` | 更新：添加 parent_id, status, progress 字段 | +30 |
| `app/domain/project/subtask_service.py` | 新建：子任务服务层 | 350 |
| `app/api/routes/subtasks.py` | 新建：子任务 API 路由 | 220 |
| `app/domain/tools/project/subtask_tools.py` | 新建：Agent 工具函数 | 360 |
| `app/alembic/versions/20250403_add_subtask_support.py` | 新建：数据库迁移 | 100 |
| `app/api/main.py` | 更新：注册子任务路由 | +2 |

## 🗄️ 数据库变更

```sql
-- 新增字段
ALTER TABLE project_requirement_tasks ADD COLUMN parent_id VARCHAR(36) NULL;
ALTER TABLE project_requirement_tasks ADD COLUMN status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE project_requirement_tasks ADD COLUMN progress INTEGER DEFAULT 0;
ALTER TABLE project_requirement_tasks ADD COLUMN updated_at TIMESTAMP NULL;

-- 新增索引
CREATE INDEX ix_project_requirement_tasks_parent_id ON project_requirement_tasks(parent_id);
CREATE INDEX ix_project_requirement_tasks_status ON project_requirement_tasks(status);
CREATE INDEX ix_project_requirement_tasks_project_status ON project_requirement_tasks(project_id, status);

-- 自引用外键
ALTER TABLE project_requirement_tasks 
ADD CONSTRAINT fk_project_requirement_tasks_parent 
FOREIGN KEY (parent_id) REFERENCES project_requirement_tasks(id) ON DELETE CASCADE;
```

## 🔧 API 接口

### 创建任务（带子任务）
```http
POST /projects/{project_id}/subtasks/
Content-Type: application/json

{
    "title": "实现用户登录模块",
    "description": "完整的用户登录功能",
    "priority": "high",
    "estimated_hours": 8,
    "subtasks": [
        {"title": "设计数据库表", "description": "用户表结构", "estimated_hours": 2},
        {"title": "实现登录API", "description": "POST /api/login", "estimated_hours": 3},
        {"title": "前端登录页面", "description": "登录表单", "estimated_hours": 3}
    ]
}
```

### 获取任务树
```http
GET /projects/{project_id}/subtasks/tree/{task_id}?max_depth=5
```

### 更新任务进度
```http
PUT /projects/{project_id}/subtasks/progress/{task_id}
Content-Type: application/json

{
    "status": "completed",
    "progress": 100,
    "result": "Implemented JWT authentication"
}
```

### 获取下一个可执行任务
```http
GET /projects/{project_id}/subtasks/next
```

### 扁平化任务列表
```http
GET /projects/{project_id}/subtasks/flat/{task_id}
```

### 列出根任务
```http
GET /projects/{project_id}/subtasks/list?status_filter=pending&limit=20
```

## 🤖 Agent 工具

### 1. 创建层级任务
```python
@evoloop_tool(name_map={"zh": "创建层级任务", "en": "Create Hierarchical Task"})
async def create_task_with_subtasks(
    title: str,
    description: str = "",
    subtasks_json: str = "[]",
    priority: str = "medium",
    estimated_hours: int = 0
) -> str:
    """
    使用场景：用户要求复杂功能时，Agent 自动拆解为子任务
    
    示例：
    用户："帮我开发一个电商网站"
    Agent 调用：create_task_with_subtasks(
        title="电商网站开发",
        subtasks_json='[
            {"title": "用户模块", "subtasks": [...]},
            {"title": "商品模块", "subtasks": [...]},
            ...
        ]'
    )
    """
```

### 2. 获取任务树摘要
```python
@evoloop_tool(name_map={"zh": "获取任务树", "en": "Get Task Tree"})
async def get_task_tree_summary(task_id: str) -> str:
    """
    返回格式化的任务树，带进度指示器
    
    示例输出：
    📋 Task Tree: 实现用户登录模块
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Overall Progress: 66%
    
    └── ✅ 设计数据库表 (100%)
    └── 🔄 实现登录API (50%)
    └── ⏳ 前端登录页面 (0%)
    """
```

### 3. 更新任务完成状态
```python
@evoloop_tool(name_map={"zh": "更新任务进度", "en": "Update Task Progress"})
async def update_task_completion(
    task_id: str,
    status: str,  # pending/in_progress/completed/failed
    result_summary: str = "",
    progress: Optional[int] = None
) -> str:
    """
    更新任务状态，自动计算父任务进度
    
    特性：
    - 子任务完成时，自动更新父任务进度
    - 支持部分完成（progress 0-100）
    - 记录执行结果
    """
```

### 4. 获取下一个可执行任务
```python
@evoloop_tool(name_map={"zh": "获取待执行任务", "en": "Get Next Executable Task"})
async def get_next_executable_task() -> str:
    """
    返回下一个待执行的子任务
    
    使用场景：
    Agent: "接下来我要做什么？"
    → 调用此工具获取下一个任务
    """
```

### 5. 列出项目任务
```python
@evoloop_tool(name_map={"zh": "列出项目任务", "en": "List Project Tasks"})
async def list_project_tasks(status_filter: str = "all", limit: int = 20) -> str:
    """
    列出项目的根任务（父任务）
    
    返回：
    ⏳ 实现用户登录模块 (66%) - ID: abc12345
    ✅ 完成数据库设计 (100%) - ID: def67890
    """
```

## 🎯 使用示例

### Agent 对话示例

**用户**：帮我规划这个电商网站开发

**Agent**：
```
我来为您规划电商网站的开发任务。

调用 create_task_with_subtasks:
- title: "电商网站开发"
- subtasks:
  1. 用户模块 [登录, 注册, 个人中心]
  2. 商品模块 [商品列表, 详情, 搜索]
  3. 订单模块 [购物车, 下单, 支付]
  4. 后台管理 [商品管理, 订单管理]

✅ 已创建任务 "电商网站开发" 及 12 个子任务
任务 ID: xxxx-xxxx
```

**用户**：现在进度如何？

**Agent**：
```
调用 get_task_tree_summary("xxxx")

📋 Task Tree: 电商网站开发
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall Progress: 25%

└── ✅ 用户模块 (100%)
    ├── ✅ 登录功能 (100%)
    ├── ✅ 注册功能 (100%)
    └── ✅ 个人中心 (100%)
└── 🔄 商品模块 (50%)
    ├── ✅ 商品列表 (100%)
    ├── 🔄 商品详情 (50%)
    └── ⏳ 搜索功能 (0%)
└── ⏳ 订单模块 (0%)
└── ⏳ 后台管理 (0%)
```

**用户**：完成商品详情

**Agent**：
```
调用 update_task_completion(
    task_id="商品详情ID",
    status="completed",
    result_summary="实现了商品详情页面，包含图片轮播、规格选择、库存显示"
)

✅ 已更新任务状态为 completed (100%)
父任务 "商品模块" 整体进度: 66%
```

## 📊 特性

### 自动进度计算
```
父任务进度 = Σ(子任务进度 × 子任务工时权重)

示例：
- 子任务1: 进度 100%, 工时 2h
- 子任务2: 进度 50%, 工时 4h
- 子任务3: 进度 0%, 工时 2h
- 总工时: 8h

父任务进度 = (100×2 + 50×4 + 0×2) / 8 = 400/8 = 50%
```

### 状态自动传播
```
所有子任务完成 → 父任务自动标记为 completed
任一子任务失败 → 父任务标记为 failed
任一子任务进行中 → 父任务标记为 in_progress
```

### 深度支持
- 最大支持 5 层嵌套（可配置）
- 支持无限宽度（同级子任务数量）

## 🔧 部署步骤

1. **运行数据库迁移**
```bash
cd evoloop/backend
alembic upgrade 20250403_add_subtask_support
```

2. **验证安装**
```bash
# 检查 API
curl http://localhost:8000/api/v1/projects/1/subtasks/list

# 应该返回空列表或现有任务
```

3. **测试 Agent 工具**
在 Agent 对话中测试：
- "创建一个任务：实现登录功能，包含数据库设计、API实现、前端页面三个子任务"
- "显示任务树 xxx"
- "更新任务 xxx 为已完成"

## ✅ 完成检查清单

- [x] 数据库模型更新
- [x] 数据库迁移脚本
- [x] 服务层实现
- [x] API 路由实现
- [x] Agent 工具实现
- [x] API 路由注册
- [ ] 运行迁移脚本
- [ ] 功能测试
