# EvoLoop 前端功能补充完整实施计划

> 制定时间：2025-04-04  
> 目标：补充缺失的项目管理功能（子任务、甘特图、工时表）

---

## 一、实施路线图

```
Phase 1 (Week 1-2): 子任务管理功能 [高优先级]
├── Task 1.1: 子任务 Store 和服务层
├── Task 1.2: 任务树形展示组件
├── Task 1.3: 子任务 CRUD 操作
└── Task 1.4: 任务进度更新

Phase 2 (Week 3-4): 甘特图可视化 [中优先级]
├── Task 2.1: 甘特图组件选型/开发
├── Task 2.2: 任务时间轴数据集成
└── Task 2.3: 交互功能（拖拽、依赖）

Phase 3 (Week 5-6): 工时表功能 [中优先级]
├── Task 3.1: 时间记录组件
├── Task 3.2: 统计报表
└── Task 3.3: 数据导出

Phase 4 (Week 7): 集成与优化
├── 功能联调
├── UI/UX 统一
└── 性能优化
```

---

## 二、Phase 1: 子任务管理功能（高优先级）

### 2.1 技术方案

**架构设计：**
```
stores/taskStore.ts          # 新增：任务状态管理
components/Tasks/
├── TaskTree/               # 新增：树形任务组件
│   ├── TaskTree.tsx        # 树形结构展示
│   ├── TaskTreeNode.tsx    # 单个节点
│   └── TaskTreeHeader.tsx  # 树形头部操作
├── Subtask/
│   ├── SubtaskList.tsx     # 子任务列表
│   ├── CreateSubtaskDialog.tsx
│   └── EditSubtaskDialog.tsx
├── TaskDetail/
│   ├── TaskDetail.tsx      # 扩展现有
│   ├── TaskProgress.tsx    # 进度更新
│   └── SubtaskSection.tsx  # 子任务区域
└── TaskActions/
    └── QuickAddSubtask.tsx # 快速添加
```

### 2.2 详细任务

#### Task 1.1: 子任务 Store 和服务层（2天）

**目标：** 创建任务状态管理，封装 API 调用

**文件：** `src/stores/taskStore.ts`（新建）

```typescript
// 核心接口定义
interface TaskTreeNode {
  id: number
  title: string
  description?: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
  progress: number
  priority: 'low' | 'medium' | 'high' | 'critical'
  estimated_hours?: number
  actual_hours?: number
  parent_id?: number
  children: TaskTreeNode[]
  created_at: string
  updated_at: string
}

interface TaskState {
  // 状态
  taskTree: TaskTreeNode[]
  currentTask: TaskTreeNode | null
  isLoading: boolean
  
  // 操作
  fetchTaskTree: (projectId: number, rootTaskId?: number) => Promise<void>
  createTask: (projectId: number, data: CreateTaskData) => Promise<void>
  createSubtask: (projectId: number, parentId: number, data: CreateSubtaskData) => Promise<void>
  updateTask: (projectId: number, taskId: number, data: UpdateTaskData) => Promise<void>
  updateProgress: (projectId: number, taskId: number, progress: number, status?: string) => Promise<void>
  deleteTask: (projectId: number, taskId: number) => Promise<void>
  getNextExecutable: (projectId: number) => Promise<TaskTreeNode | null>
  flattenTaskTree: (projectId: number, taskId: number) => Promise<TaskTreeNode[]>
}
```

**实现步骤：**
1. 创建 `taskStore.ts` 文件
2. 使用 `SubtasksService` 封装 API 调用
3. 实现树形数据转换（扁平 → 树形）
4. 添加错误处理和 Toast 提示
5. 添加乐观更新支持

**验收标准：**
- [ ] Store 能正确获取和缓存任务树
- [ ] 所有 CRUD 操作正常工作
- [ ] 错误处理完善

---

#### Task 1.2: 任务树形展示组件（3天）

**目标：** 创建可交互的树形任务展示组件

**依赖：** Task 1.1

**文件：**
- `src/components/Projects/Modules/Tasks/TaskTree/TaskTree.tsx`
- `src/components/Projects/Modules/Tasks/TaskTree/TaskTreeNode.tsx`
- `src/components/Projects/Modules/Tasks/TaskTree/index.ts`

**组件设计：**
```typescript
interface TaskTreeProps {
  projectId: number
  rootTaskId?: number          // 可选，不传则显示所有根任务
  selectable?: boolean         // 是否可选择
  onSelect?: (task: TaskTreeNode) => void
  onExpand?: (taskId: number) => void
  expandedKeys?: Set<number>   // 受控展开状态
  showActions?: boolean        // 是否显示操作按钮
  showProgress?: boolean       // 是否显示进度条
  maxDepth?: number            // 最大展开深度
}
```

**功能特性：**
1. **树形展示**
   - 支持无限层级嵌套
   - 展开/折叠动画
   - 缩进线可视化层级

2. **节点内容**
   ```
   [图标] 任务标题 [优先级徽章] [进度条] [状态徽章] [操作按钮]
   ```

3. **交互功能**
   - 点击展开/折叠
   - 右键菜单（编辑/删除/添加子任务）
   - 拖拽排序（可选）

4. **视觉设计**
   - 当前选中高亮
   - 完成状态样式（删除线、灰色）
   - 进度条颜色根据状态变化

**伪代码实现：**
```tsx
function TaskTree({ projectId, onSelect }: TaskTreeProps) {
  const { taskTree, fetchTaskTree, isLoading } = useTaskStore()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  
  useEffect(() => {
    fetchTaskTree(projectId)
  }, [projectId])
  
  const renderNode = (node: TaskTreeNode, level: number) => (
    <div key={node.id} style={{ paddingLeft: level * 24 }}>
      <TaskTreeNode
        node={node}
        isExpanded={expanded.has(node.id)}
        onToggle={() => toggleExpand(node.id)}
        onSelect={() => onSelect?.(node)}
      />
      {expanded.has(node.id) && node.children?.map(child => 
        renderNode(child, level + 1)
      )}
    </div>
  )
  
  return (
    <div className="task-tree">
      {taskTree.map(node => renderNode(node, 0))}
    </div>
  )
}
```

**验收标准：**
- [ ] 能正确展示多层嵌套任务
- [ ] 展开/折叠功能正常
- [ ] 选中状态正确传递
- [ ] 响应式设计

---

#### Task 1.3: 子任务 CRUD 操作（3天）

**目标：** 实现子任务的创建、编辑、删除功能

**依赖：** Task 1.1, Task 1.2

**文件：**
- `src/components/Projects/Modules/Tasks/Subtask/CreateSubtaskDialog.tsx`
- `src/components/Projects/Modules/Tasks/Subtask/EditSubtaskDialog.tsx`
- `src/components/Projects/Modules/Tasks/Subtask/SubtaskList.tsx`

**1. 创建子任务弹窗**

```typescript
interface CreateSubtaskDialogProps {
  projectId: number
  parentTaskId: number           // 父任务ID
  isOpen: boolean
  onClose: () => void
  onSuccess?: () => void
}

// 表单字段
interface SubtaskFormData {
  title: string                  // 必填
  description?: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  estimated_hours?: number       // 预计工时
  assignee?: string              // 负责人
  due_date?: string              // 截止日期
}
```

**2. 编辑子任务弹窗**

```typescript
interface EditSubtaskDialogProps {
  projectId: number
  task: TaskTreeNode              // 编辑的任务
  isOpen: boolean
  onClose: () => void
  onSuccess?: () => void
}
```

**3. 快速添加组件**

在任务行内快速添加子任务：
```tsx
// QuickAddSubtask.tsx
function QuickAddSubtask({ parentId, onAdd }: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [title, setTitle] = useState('')
  
  if (!isEditing) {
    return <Button variant="ghost" size="sm" onClick={() => setIsEditing(true)}>+ 添加子任务</Button>
  }
  
  return (
    <div className="flex gap-2">
      <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="子任务标题" />
      <Button size="sm" onClick={() => { onAdd(title); setIsEditing(false) }}>保存</Button>
    </div>
  )
}
```

**验收标准：**
- [ ] 创建子任务表单验证完整
- [ ] 编辑功能能正确回显数据
- [ ] 删除有确认弹窗
- [ ] 操作后有成功提示

---

#### Task 1.4: 任务进度更新（2天）

**目标：** 实现任务进度更新和状态流转

**依赖：** Task 1.1

**文件：**
- `src/components/Projects/Modules/Tasks/TaskDetail/TaskProgress.tsx`
- `src/components/Projects/Modules/Tasks/TaskDetail/SubtaskSection.tsx`

**功能设计：**

1. **进度滑块组件**
```tsx
function TaskProgress({ task, onUpdate }: Props) {
  const [progress, setProgress] = useState(task.progress)
  
  const handleChange = (value: number) => {
    setProgress(value)
    // 自动推断状态
    const status = value === 0 ? 'pending' : value === 100 ? 'completed' : 'in_progress'
    onUpdate(task.id, value, status)
  }
  
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span>进度</span>
        <span>{progress}%</span>
      </div>
      <Slider value={[progress]} onValueChange={([v]) => handleChange(v)} max={100} step={5} />
      <div className="flex gap-2">
        <Button size="sm" variant={task.status === 'pending' ? 'default' : 'outline'}>待开始</Button>
        <Button size="sm" variant={task.status === 'in_progress' ? 'default' : 'outline'}>进行中</Button>
        <Button size="sm" variant={task.status === 'completed' ? 'default' : 'outline'}>已完成</Button>
      </div>
    </div>
  )
}
```

2. **子任务进度汇总**
- 自动计算父任务进度 = 子任务进度平均值（加权）
- 显示子任务完成数/总数

**验收标准：**
- [ ] 进度滑块拖拽流畅
- [ ] 状态按钮切换正常
- [ ] 子任务进度正确汇总到父任务
- [ ] 更新后有视觉反馈

---

#### Task 1.5: 集成到现有页面（2天）

**目标：** 将子任务功能集成到现有任务列表和详情页

**修改文件：**
- `src/routes/_layout/projects.$projectId.tasks.tsx` - 添加任务树入口
- `src/components/Projects/Modules/Tasks/TaskList.tsx` - 添加树形/列表切换
- `src/components/Projects/Modules/Tasks/TaskDetail.tsx` - 添加子任务区域

**集成点：**

1. **任务列表页添加视图切换**
```tsx
// TaskList.tsx 添加
const [viewMode, setViewMode] = useState<'list' | 'tree'>('list')

// 在 Header 添加切换按钮
<ButtonGroup>
  <Button variant={viewMode === 'list' ? 'default' : 'outline'} onClick={() => setViewMode('list')}>
    <ListIcon className="h-4 w-4" />
  </Button>
  <Button variant={viewMode === 'tree' ? 'default' : 'outline'} onClick={() => setViewMode('tree')}>
    <TreeIcon className="h-4 w-4" />
  </Button>
</ButtonGroup>

// 根据模式渲染不同组件
{viewMode === 'list' ? <DataTable ... /> : <TaskTree ... />}
```

2. **任务详情页添加子任务区域**
```tsx
// TaskDetail.tsx 添加
<Tabs>
  <TabsList>
    <TabsTrigger value="details">详情</TabsTrigger>
    <TabsTrigger value="subtasks">
      子任务 {task.children?.length > 0 && `(${task.children.length})`}
    </TabsTrigger>
    <TabsTrigger value="progress">进度</TabsTrigger>
  </TabsList>
  
  <TabsContent value="subtasks">
    <SubtaskSection parentTask={task} />
  </TabsContent>
</Tabs>
```

**验收标准：**
- [ ] 任务列表能切换树形/列表视图
- [ ] 任务详情有子任务标签页
- [ ] 从需求生成的任务能正确显示层级

---

## 三、Phase 2: 甘特图可视化（中优先级）

### 3.1 技术方案选型

**方案对比：**

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **@mermaid-js/gantt** | 已在项目使用 | 交互性弱 | ⭐⭐⭐ |
| **frappe-gantt** | 轻量、易用 | 功能较简单 | ⭐⭐⭐⭐ |
| **dhtmlx-gantt** | 功能强大 | 商业软件 | ⭐⭐ |
| **自研 SVG** | 完全可控 | 开发成本高 | ⭐⭐⭐ |

**推荐方案：frappe-gantt**（轻量、开源、足够使用）

安装：
```bash
npm install frappe-gantt
npm install -D @types/frappe-gantt
```

### 3.2 详细任务

#### Task 2.1: 甘特图组件封装（3天）

**目标：** 封装 frappe-gantt 为 React 组件

**文件：**
- `src/components/Projects/Modules/Gantt/GanttChart.tsx`
- `src/components/Projects/Modules/Gantt/GanttToolbar.tsx`
- `src/components/Projects/Modules/Gantt/index.ts`

**组件设计：**
```typescript
interface GanttTask {
  id: string
  name: string
  start: string        // YYYY-MM-DD
  end: string          // YYYY-MM-DD
  progress: number     // 0-100
  dependencies?: string[]  // 依赖任务ID列表
  custom_class?: string    // 自定义样式
}

interface GanttChartProps {
  projectId: number
  tasks: GanttTask[]
  viewMode?: 'Day' | 'Week' | 'Month' | 'Year'
  onTaskClick?: (task: GanttTask) => void
  onTaskUpdate?: (task: GanttTask, newStart: string, newEnd: string) => void
  onProgressChange?: (task: GanttTask, progress: number) => void
  readonly?: boolean
}
```

**实现要点：**
1. 使用 `useRef` 获取 DOM 节点
2. 监听任务数据变化，更新图表
3. 事件转发到 React 层
4. 中文本地化

**伪代码：**
```tsx
function GanttChart({ tasks, onTaskClick }: GanttChartProps) {
  const ganttRef = useRef<HTMLDivElement>(null)
  const ganttInstance = useRef<any>(null)
  
  useEffect(() => {
    if (ganttRef.current) {
      ganttInstance.current = new Gantt(ganttRef.current, tasks, {
        on_click: onTaskClick,
        on_date_change: handleDateChange,
        on_progress_change: handleProgressChange,
        custom_popup_html: customPopup,
      })
    }
    
    return () => {
      ganttInstance.current?.destroy()
    }
  }, [])
  
  // 数据更新时刷新
  useEffect(() => {
    ganttInstance.current?.refresh(tasks)
  }, [tasks])
  
  return <div ref={ganttRef} className="gantt-container" />
}
```

---

#### Task 2.2: 任务时间数据集成（2天）

**目标：** 将后端任务数据转换为甘特图格式

**文件：** `src/stores/ganttStore.ts`（新建或扩展 taskStore）

**数据转换：**
```typescript
// 将 TaskTreeNode 转换为 GanttTask
function convertToGanttTask(task: TaskTreeNode): GanttTask {
  // 如果没有时间，根据工期和优先级推算
  const start = task.start_date || estimateStartDate(task)
  const end = task.end_date || calculateEndDate(start, task.estimated_hours)
  
  return {
    id: String(task.id),
    name: task.title,
    start,
    end,
    progress: task.progress,
    dependencies: task.dependencies?.map(String),
    custom_class: getTaskClass(task),
  }
}

// 估算开始时间（根据优先级排序）
function estimateStartDate(task: TaskTreeNode): string {
  // 逻辑：高优先级先开始，考虑依赖关系
}
```

---

#### Task 2.3: 甘特图页面（2天）

**目标：** 实现甘特图页面路由

**修改文件：** `src/routes/_layout/projects.$projectId.gantt.tsx`

**页面结构：**
```tsx
export default function GanttPage() {
  const { projectId } = useParams()
  const { tasks, fetchTasks } = useGanttStore()
  const [viewMode, setViewMode] = useState<'Day' | 'Week' | 'Month'>('Week')
  
  useEffect(() => {
    fetchTasks(Number(projectId))
  }, [projectId])
  
  return (
    <div className="h-full flex flex-col">
      <GanttToolbar 
        viewMode={viewMode} 
        onViewModeChange={setViewMode}
        onExport={() => exportToPDF()}
      />
      <div className="flex-1 overflow-auto">
        <GanttChart
          projectId={Number(projectId)}
          tasks={tasks}
          viewMode={viewMode}
          onTaskClick={handleTaskClick}
          onTaskUpdate={handleTaskUpdate}
        />
      </div>
    </div>
  )
}
```

---

## 四、Phase 3: 工时表功能（中优先级）

### 4.1 技术方案

**数据模型：**
```typescript
interface TimesheetEntry {
  id: number
  task_id: number
  project_id: number
  user_id: string
  date: string              // YYYY-MM-DD
  hours: number             // 工时（支持小数）
  description?: string      // 工作内容描述
  created_at: string
  updated_at: string
}

interface TimesheetSummary {
  total_hours: number
  billable_hours: number
  by_project: Record<number, number>
  by_date: Record<string, number>
}
```

### 4.2 详细任务

#### Task 3.1: 时间记录组件（3天）

**目标：** 创建工时录入界面

**文件：**
- `src/components/Projects/Modules/Timesheet/TimesheetForm.tsx`
- `src/components/Projects/Modules/Timesheet/TimesheetCalendar.tsx`
- `src/components/Projects/Modules/Timesheet/TimesheetList.tsx`

**组件设计：**

1. **工时录入表单**
```tsx
function TimesheetForm({ projectId, onSubmit }: Props) {
  const [entries, setEntries] = useState<Partial<TimesheetEntry>[]>([])
  
  return (
    <div className="space-y-4">
      {entries.map((entry, idx) => (
        <div key={idx} className="flex gap-2">
          <TaskSelector 
            projectId={projectId} 
            value={entry.task_id}
            onChange={(taskId) => updateEntry(idx, { task_id: taskId })}
          />
          <Input 
            type="number" 
            placeholder="工时" 
            value={entry.hours}
            onChange={(e) => updateEntry(idx, { hours: Number(e.target.value) })}
          />
          <Textarea 
            placeholder="工作内容"
            value={entry.description}
            onChange={(e) => updateEntry(idx, { description: e.target.value })}
          />
          <Button variant="ghost" onClick={() => removeEntry(idx)}>
            <TrashIcon />
          </Button>
        </div>
      ))}
      <Button onClick={addEntry}>+ 添加一行</Button>
    </div>
  )
}
```

2. **日历视图**
- 展示每日工时分布
- 支持点击日期快速录入
- 颜色标识工时饱和度

---

#### Task 3.2: 统计报表（2天）

**目标：** 创建工时统计可视化

**文件：**
- `src/components/Projects/Modules/Timesheet/TimesheetStats.tsx`
- `src/components/Projects/Modules/Timesheet/TimesheetCharts.tsx`

**报表内容：**
1. **概览卡片**
   - 本周总工时
   - 本月总工时
   - 平均每日工时
   - 项目分布

2. **图表展示**
   - 柱状图：每日工时趋势
   - 饼图：项目工时占比
   - 热力图：年度工时分布

---

#### Task 3.3: 工时表页面（2天）

**目标：** 实现工时表页面路由

**修改文件：** `src/routes/_layout/projects.$projectId.timesheet.tsx`

**页面结构：**
```tsx
export default function TimesheetPage() {
  return (
    <div className="p-6 space-y-6">
      <TimesheetStats />
      <Tabs defaultValue="calendar">
        <TabsList>
          <TabsTrigger value="calendar">日历视图</TabsTrigger>
          <TabsTrigger value="list">列表视图</TabsTrigger>
          <TabsTrigger value="charts">统计图表</TabsTrigger>
        </TabsList>
        <TabsContent value="calendar"><TimesheetCalendar /></TabsContent>
        <TabsContent value="list"><TimesheetList /></TabsContent>
        <TabsContent value="charts"><TimesheetCharts /></TabsContent>
      </Tabs>
    </div>
  )
}
```

---

## 五、Phase 4: 集成与优化（Week 7）

### 5.1 功能联调（2天）

**检查清单：**
- [ ] 子任务创建后甘特图自动更新
- [ ] 任务进度更新同步到甘特图
- [ ] 工时录入后任务实际工时更新
- [ ] 所有操作有 loading 和错误处理

### 5.2 UI/UX 统一（2天）

**优化项：**
1. **空状态统一**
   - 所有列表页面统一空状态样式
   - 添加引导操作

2. **加载状态**
   - Skeleton 屏占位
   - Loading 按钮状态

3. **错误处理**
   - 全局错误边界
   - API 错误统一提示

4. **动画效果**
   - 页面切换过渡
   - 列表项添加/删除动画

### 5.3 性能优化（2天）

**优化策略：**
1. **虚拟列表**
   - 任务树大数据量时使用虚拟滚动
   - 甘特图大量任务时优化

2. **数据缓存**
   - React Query 缓存策略优化
   - 树形数据本地缓存

3. **懒加载**
   - 子任务按需加载
   - 甘特图分片渲染

---

## 六、依赖关系图

```
Phase 1: 子任务管理
├── Task 1.1 (Store) ──┬──> Task 1.2 (树形组件)
│                      ├──> Task 1.3 (CRUD)
│                      └──> Task 1.4 (进度更新)
└── Task 1.5 (集成) <──┴──┴──┘
         │
         v
Phase 2: 甘特图
├── Task 2.1 (组件封装) <──┐
├── Task 2.2 (数据集成) <──┤── 依赖 Task 1.1 (Store)
└── Task 2.3 (页面) <──────┘
         │
         v
Phase 3: 工时表
├── Task 3.1 (录入组件)
├── Task 3.2 (统计报表)
└── Task 3.3 (页面)
         │
         v
Phase 4: 集成优化
├── 功能联调
├── UI/UX 统一
└── 性能优化
```

---

## 七、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| frappe-gantt 不满足需求 | 甘特图延期 | 提前原型验证，备选自研 SVG |
| 后端 API 调整 | 子任务功能阻塞 | 及时沟通，使用 mock 数据并行开发 |
| 性能问题（大数据量） | 用户体验差 | 预留虚拟滚动优化时间 |
| 第三方库兼容性 | 构建失败 | 使用 TypeScript 类型检查 |

---

## 八、验收标准

### 8.1 子任务功能
- [ ] 能创建多级子任务（至少 5 层）
- [ ] 子任务进度正确汇总到父任务
- [ ] 树形组件支持 1000+ 节点流畅渲染
- [ ] 所有操作有视觉反馈

### 8.2 甘特图功能
- [ ] 支持日/周/月视图切换
- [ ] 拖拽更新任务时间
- [ ] 点击任务显示详情
- [ ] 正确显示任务依赖关系

### 8.3 工时表功能
- [ ] 支持批量录入工时
- [ ] 统计图表正确展示
- [ ] 支持数据导出（CSV/PDF）
- [ ] 移动端可正常使用

---

## 九、附录

### 9.1 相关后端 API

```
# 子任务
POST   /api/v1/projects/{project_id}/subtasks/              # 创建任务树
GET    /api/v1/projects/{project_id}/subtasks/tree/{task_id} # 获取任务树
PUT    /api/v1/projects/{project_id}/subtasks/progress/{task_id} # 更新进度
GET    /api/v1/projects/{project_id}/subtasks/next          # 获取下一个可执行任务
GET    /api/v1/projects/{project_id}/subtasks/flat/{task_id} # 扁平化任务树
GET    /api/v1/projects/{project_id}/subtasks/list          # 列出根任务

# 工时表（需后端补充）
POST   /api/v1/projects/{project_id}/timesheets             # 创建工时记录
GET    /api/v1/projects/{project_id}/timesheets             # 获取工时列表
PUT    /api/v1/timesheets/{id}                              # 更新工时记录
DELETE /api/v1/timesheets/{id}                              # 删除工时记录
GET    /api/v1/projects/{project_id}/timesheets/stats       # 获取工时统计
```

### 9.2 开发顺序建议

**第 1 周：**
- Day 1-2: Task 1.1 (Store)
- Day 3-5: Task 1.2 (树形组件)

**第 2 周：**
- Day 1-3: Task 1.3 (CRUD)
- Day 4-5: Task 1.4-1.5 (进度+集成)

**第 3-4 周：** 甘特图
**第 5-6 周：** 工时表
**第 7 周：** 集成优化

---

**计划制定时间：** 2025-04-04  
**预计完成时间：** 7 周（含测试和优化）
