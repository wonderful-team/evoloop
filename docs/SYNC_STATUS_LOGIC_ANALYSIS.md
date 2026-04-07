# EvoLoop 项目管理 sync_status 字段逻辑深度分析

## 📋 概述

`sync_status` 是 EvoLoop 项目管理系统的核心状态字段，用于管理本地项目与云端 (EvoCloud/Member Center) 的同步状态。该字段位于 `repositories` 表中，控制项目的整个生命周期。

---

## 🎯 状态定义

### 2.1 状态枚举值

| 状态值 | 含义 | 说明 |
|--------|------|------|
| `DETECTED` | 已检测到 | 文件系统检测到新项目，等待用户确认导入 |
| `IGNORED` | 已忽略 | 用户选择不导入的项目 |
| `PENDING_CREATION` | 等待创建 | 用户确认导入，正在同步到云端 |
| `SYNCED` | 已同步 | 项目已成功同步到云端，可正常使用 |
| `DISCONNECTED` | 已断开 | 本地目录被删除，与云端断开连接 |

### 2.2 数据库模型定义

```python
# app/models/codebase.py
class Repository(Base):
    __tablename__ = "repositories"
    
    # Sync Status:
    # - "DETECTED": Newly detected, awaiting user confirmation
    # - "IGNORED": User chose to ignore
    # - "PENDING_CREATION": User confirmed, awaiting cloud sync
    # - "SYNCED": Successfully synced with cloud
    # - "DISCONNECTED": Local directory deleted
    sync_status: Mapped[str] = mapped_column(String(50), default="DETECTED")
    
    # 关联字段
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

---

## 🔄 状态流转图

```
                          用户点击"导入"
    文件系统检测              ↓
         │            ┌─────────────┐
         ↓            │   IMPORT    │
    ┌─────────┐       │   确认导入   │
    │DETECTED │──────→│             │
    │ (检测到) │       └──────┬──────┘
    └────┬────┘              │
         │                   ↓
         │ 用户点击"忽略"  ┌─────────────┐
         │                │   PENDING   │
         ↓                │  _CREATION  │
    ┌─────────┐           │ (等待创建)  │
    │ IGNORED │           └──────┬──────┘
    │ (已忽略) │                  │
    └────┬────┘                  │ Celery任务
         │                       │ 同步到云端
         │                       ↓
         │                ┌─────────────┐
         │                │   SYNCED    │
         │                │   (已同步)   │←────── 云端已存在
         │                └──────┬──────┘        自动关联
         │                       │
         │                       │ 本地目录
         │                       │ 被删除
         │                       ↓
         │                ┌─────────────┐
         │                │ DISCONNECTED│
         │                │  (已断开)   │
         │                └──────┬──────┘
         │                       │
         │                       │ 目录恢复/
         │                       │ 移动重命名
         └──────────────────────→│
                                 ↓
                          ┌─────────────┐
                          │   SYNCED    │
                          │ (重新连接)  │
                          └─────────────┘
```

---

## 📝 状态流转详细逻辑

### 3.1 DETECTED → 初始检测

**触发条件：** 文件系统监控检测到新目录

```python
# app/domain/project/sync_service.py::handle_project_created()
async def handle_project_created(self, path: str):
    # 1. 检查是否应自动忽略（系统目录）
    if self._should_auto_ignore(path):
        return
    
    # 2. 检查是否已存在记录
    existing = await self._indexing_service.get_repo_by_path(path)
    if existing:
        if existing.sync_status == "IGNORED":
            return  # 尊重用户选择
    
    # 3. 检查云端是否已存在同名项目
    cloud_project = await self._find_matching_cloud_project(repo_name, abs_path)
    
    if cloud_project:
        # 云端存在 → 直接 SYNCED
        repo = Repository(
            sync_status="SYNCED",
            project_id=cloud_project_id,
            ...
        )
        await self._trigger_auto_indexing(repo, path)
    else:
        # 云端不存在 → DETECTED，等待用户确认
        repo = Repository(
            sync_status="DETECTED",
            project_id=None,
            ...
        )
        # 发布 NewProjectDetectedEvent 通知前端
        await system_bus.publish(NewProjectDetectedEvent(...))
```

**关键点：**
- 如果云端已存在同名项目，自动关联并设为 `SYNCED`
- 如果云端不存在，设为 `DETECTED` 并通知前端显示导入提示

---

### 3.2 DETECTED → PENDING_CREATION → SYNCED

**触发条件：** 用户点击"导入项目"

```python
# app/domain/project/sync_service.py::import_project()
async def import_project(self, repo_id: int) -> Repository:
    repo = await session.get(Repository, repo_id)
    
    # 状态校验
    if repo.sync_status not in ["DETECTED", "IGNORED"]:
        logger.warning(f"Project already imported (status: {repo.sync_status})")
        return repo
    
    # 更新状态
    repo.sync_status = "PENDING_CREATION"
    repo.indexing_status = "pending"
    repo.imported_at = utcnow()
    
    # 发布事件触发索引
    await system_bus.publish(ProjectCreatedEvent(...))
    
    # 派发云端同步任务
    sync_project_to_cloud_task.delay(repo.id)
```

**Celery 任务执行：**

```python
# app/domain/project/sync_tasks.py::sync_project_to_cloud_task()
@celery_app.task(name="sync_project_to_cloud", max_retries=5)
def sync_project_to_cloud_task(_self, repo_id: int):
    # 调用 EvoCloud API 创建项目
    res = await evocloud_manager.api.create_project(...)
    
    if res.get("code") == 0:
        new_pid = res["data"]["project_id"]
        repo.project_id = new_pid
        repo.sync_status = "SYNCED"  # ← 状态变更
        await session.commit()
    else:
        raise Exception(f"Cloud API Failed")
```

---

### 3.3 DETECTED → IGNORED

**触发条件：** 用户点击"忽略项目"

```python
# app/domain/project/sync_service.py::ignore_project()
async def ignore_project(self, repo_id: int):
    repo = await session.get(Repository, repo_id)
    
    if repo.sync_status != "DETECTED":
        logger.warning(f"Cannot ignore project with status: {repo.sync_status}")
        return
    
    repo.sync_status = "IGNORED"
    repo.indexing_status = "not_needed"
    
    # 更新缓存，排除在树形视图外
    await project_cache.add_ignored_path(repo.local_path)
```

---

### 3.4 IGNORED → DETECTED (恢复)

**触发条件：** 用户从"已忽略"列表中恢复项目

```python
# app/domain/project/sync_service.py::unignore_project()
async def unignore_project(self, repo_id: int) -> Repository:
    repo = await session.get(Repository, repo_id)
    
    if repo.sync_status != "IGNORED":
        return repo
    
    repo.sync_status = "DETECTED"
    repo.indexing_status = "not_needed"
    
    # 从缓存中移除
    await project_cache.remove_ignored_path(repo.local_path)
```

---

### 3.5 SYNCED → DISCONNECTED

**触发条件：** 本地项目目录被删除

```python
# app/domain/project/sync_service.py::handle_project_deleted()
async def handle_project_deleted(self, path: str):
    repo = await self._indexing_service.get_repo_by_path(path)
    
    if repo:
        async with self._indexing_service.session_factory() as session:
            r = await session.get(type(repo), repo.id)
            if r:
                r.sync_status = "DISCONNECTED"  # ← 状态变更
                await session.commit()
    
    # 发布删除事件，清理资源
    await system_bus.publish(ProjectDeletedEvent(...))
```

**注意：** 项目删除不会删除云端项目，只是断开本地关联。

---

### 3.6 DISCONNECTED → SYNCED (重新连接)

**触发条件1：** 被删除的目录恢复

```python
# app/domain/project/sync_service.py::reconcile_projects()
# 在协调过程中检测
for p in known_paths & fs_paths:  # DB中有且文件系统存在
    repo = known_projects_map[p]
    if repo.sync_status == "DISCONNECTED":
        if r.project_id:
            r.sync_status = "SYNCED"
        else:
            r.sync_status = "DETECTED"
```

**触发条件2：** 项目移动/重命名

```python
# app/domain/project/sync_service.py::handle_project_moved()
async def handle_project_moved(self, src_path: str, dest_path: str):
    repo = await self._indexing_service.get_repo_by_path(src_path)
    
    # 更新云端项目路径
    if repo.project_id:
        await evocloud_manager.api.update_project(
            project_id=repo.project_id,
            name=new_name,
            path=dest_path
        )
    
    # 更新本地记录
    async with self._indexing_service.session_factory() as session:
        r = await session.get(type(repo), repo.id)
        r.local_path = dest_path
        r.name = new_name
        if r.sync_status == "DISCONNECTED":
            r.sync_status = "SYNCED"  # ← 重新连接
```

---

## 🔍 API 筛选逻辑

### 4.1 项目列表筛选

```python
# app/api/routes/projects.py::get_projects()
async def get_projects(
    filter_type: str | None = None,  # switchable | cloud_only | disconnected
    ...
):
    # 1. 获取云端项目列表
    cloud_projects = await evocloud_manager.api.get_projects(...)
    
    # 2. 扫描本地工作区
    workspace_projects = _scan_workspace_projects()
    
    # 3. 匹配云端与本地项目，构建 local_status_map
    for cloud_project in projects:
        if project_name in workspace_projects:
            # 匹配成功
            if repo.project_id == project_id:
                local_status_map[pid] = {
                    "status": "SYNCED",
                    "exists_locally": True,
                    ...
                }
    
    # 4. 应用 filter_type 筛选
    if filter_type == "switchable":
        # 云端和本地都存在的项目
        valid_local_ids = {
            pid for pid, info in local_status_map.items()
            if info.get("exists_locally") and info.get("status") != "DISCONNECTED"
        }
        switchable_ids = cloud_project_ids & valid_local_ids
        projects = [p for p in projects if pid in switchable_ids]
    
    elif filter_type == "cloud_only":
        # 仅在云端存在，未关联本地
        cloud_only_ids = cloud_project_ids - local_linked_ids
        projects = [p for p in projects if pid in cloud_only_ids]
    
    elif filter_type == "disconnected":
        # 已断开连接的项目
        disconnected_ids = {
            pid for pid, info in local_status_map.items()
            if info.get("status") == "DISCONNECTED"
        }
        projects = [p for p in projects if pid in disconnected_ids]
```

### 4.2 检测到的项目列表

```python
# GET /projects/detected
async def get_detected_projects():
    # 查询 sync_status="DETECTED" 的项目
    stmt = select(Repository).where(
        Repository.sync_status == "DETECTED"
    ).order_by(Repository.detected_at.desc())
```

### 4.3 忽略的项目列表

```python
# GET /projects/ignored
async def get_ignored_projects():
    # 查询 sync_status="IGNORED" 的项目
    stmt = select(Repository).where(
        Repository.sync_status == "IGNORED"
    )
```

---

## 📊 与 indexing_status 的关系

| sync_status | indexing_status | 说明 |
|-------------|-----------------|------|
| DETECTED | not_needed | 未导入，不需要索引 |
| IGNORED | not_needed | 已忽略，不需要索引 |
| PENDING_CREATION | pending | 等待索引 |
| SYNCED | pending/in_progress/completed/failed | 正常索引流程 |
| DISCONNECTED | (保持原值) | 断开前状态 |

**索引状态流转：**

```
                    项目导入/自动关联
                          │
                          ↓
                    ┌─────────────┐
         ┌─────────│   pending   │
         │         │  (等待索引)  │
         │         └──────┬──────┘
         │                │
         │                ▼
         │         ┌─────────────┐
         │    ┌───→│in_progress  │
         │    │    │ (索引中)    │
         │    │    └──────┬──────┘
         │    │           │
         │    │     ┌─────┴─────┐
         │    │     ▼           ▼
         │    │  ┌───────┐  ┌────────┐
         │    └──│ failed│  │completed│
         │       │(失败) │  │(完成)  │
         │       └───┬───┘  └────┬───┘
         │           │           │
         └───────────┘           │
              失败重试            │
                                 ▼
                          ┌─────────────┐
                          │  可被搜索    │
                          └─────────────┘
```

---

## 🖥️ 前端状态管理

### 6.1 ProjectStore (主项目列表)

```typescript
// stores/projectStore.ts
export interface Project {
  // ...
  local_status?: string | null  // SYNCED, PENDING_CREATION, DISCONNECTED
  exists_locally?: boolean      // 本地是否存在
  db_indexing_status?: string   // 索引状态
}

// 获取项目列表（带筛选）
fetchProjects: async (filterType?: 'switchable' | 'cloud_only' | 'disconnected') => {
  const resp = await ProjectsService.getProjects({ filterType })
  // 映射到前端类型
  const list: Project[] = rawList.map((item: any) => ({
    ...item,
    local_status: item.local_status || null,
    exists_locally: item.exists_locally === true,
  }))
}
```

### 6.2 ProjectImportStore (导入管理)

```typescript
// stores/projectImportStore.ts
interface ProjectImportState {
  detectedProjects: DetectedProject[]  // DETECTED 状态项目
  ignoredProjects: DetectedProject[]   // IGNORED 状态项目
  hasNewDetected: boolean
}

// 获取检测到的项目
fetchDetected: async () => {
  const res = await ProjectsService.getDetectedProjects()
  // 检查是否有新的、未处理的项目
  const hasNewUnprocessed = items.some(
    (item) => !dismissedProjectIds.has(item.id)
  )
}

// 导入项目
importProject: async (id: number) => {
  await ProjectsService.importDetectedProject({ repoId: id })
  // DETECTED → PENDING_CREATION → SYNCED
}

// 忽略项目
ignoreProject: async (id: number) => {
  await ProjectsService.ignoreDetectedProject({ repoId: id })
  // DETECTED → IGNORED
}
```

---

## 🔧 关键工具函数

### 7.1 自动忽略检测

```python
# app/domain/project/sync_service.py
def _should_auto_ignore(self, path: str) -> bool:
    name = os.path.basename(path)
    
    # 隐藏目录
    if name.startswith("."):
        return True
    
    # 系统/构建目录
    ignored_names = {
        "node_modules", "__pycache__", ".git", ".svn", "dist", "build",
        "target", "vendor", "tmp", "temp", ".venv", "venv", ".idea"
    }
    
    if name in ignored_names:
        return True
    
    return False
```

### 7.2 检查是否曾被忽略

```python
async def _check_if_previously_ignored(self, repo_name: str) -> bool:
    """检查同名项目是否曾被忽略（处理删除后重建的情况）"""
    stmt = select(Repository).where(
        Repository.name == repo_name,
        Repository.sync_status == "IGNORED"
    )
    ignored_repo = result.scalar_one_or_none()
    return ignored_repo is not None
```

### 7.3 协调项目状态

```python
async def reconcile_projects(self, root_path: str):
    """
    协调本地文件系统与数据库状态
    处理服务离线期间发生的创建/删除
    """
    # 1. 扫描文件系统
    fs_projects = set()
    for entry in os.scandir(root_path):
        if entry.is_dir() and not entry.name.startswith("."):
            fs_projects.add(os.path.abspath(entry.path))
    
    # 2. 获取已知项目
    known_projects_map = {}
    repos = await self._indexing_service.get_all_repos()
    
    # 3. 检测变更
    new_paths = fs_paths - known_paths        # 新建
    missing_paths = known_paths - fs_paths    # 删除
    
    # 处理新建项目
    for p in new_paths:
        if self._is_ignored_path(p, ignored_paths):
            await self._create_ignored_project(p)
        else:
            await self.handle_project_created(p)
    
    # 处理已删除项目
    for p in missing_paths:
        await self.handle_project_deleted(p)
```

---

## 📈 性能优化

### 8.1 数据库索引

```sql
--  Migration: j4c9d2e71a03_add_project_import_status.py
CREATE INDEX ix_repositories_sync_status ON repositories(sync_status);
CREATE INDEX ix_repositories_detected_at ON repositories(detected_at);
```

### 8.2 缓存策略

```python
# app/domain/project/cache.py
# 忽略的项目路径缓存（避免频繁查询数据库）

async def add_ignored_path(path: str) -> bool:
    key = _key(project_id, "ignored_paths")
    await cache.sadd(key, path)
    await cache.expire(key, DEFAULT_TTL)  # 1小时过期

async def is_path_ignored(path: str) -> bool:
    return await cache.sismember(_key(project_id, "ignored_paths"), path)
```

---

## ⚠️ 边界情况处理

### 9.1 删除后重建同名项目

```
用户操作: 删除项目文件夹 → 创建同名文件夹
系统行为:
1. 检测到新目录（同名）
2. 检查发现曾被忽略（_check_if_previously_ignored）
3. 自动创建为 IGNORED 状态（尊重用户选择）
4. 用户可手动从"已忽略"列表恢复
```

### 9.2 云端已存在同名项目

```
场景: 用户在另一台电脑上创建了项目并同步到云端
       然后在本地创建同名项目

系统行为:
1. 检测到本地新项目
2. 扫描云端发现同名项目
3. 自动关联（auto-link）
4. 设为 SYNCED 状态
5. 自动触发索引
```

### 9.3 网络中断处理

```
场景: 用户导入项目时网络中断

系统行为:
1. 状态设为 PENDING_CREATION
2. Celery 任务失败，触发重试（最多5次，指数退避）
3. 下次协调时检查 PENDING_CREATION 项目
4. 重新派发同步任务
```

---

## 🐛 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 项目重复出现 | 云端和本地 ID 不匹配 | 检查 project_id 关联 |
| 导入后状态不对 | Celery 任务未执行 | 检查任务队列状态 |
| 已删除项目仍显示 | 未收到删除事件 | 手动触发协调 |
| 忽略的项目又出现了 | 同名目录重建 | 这是预期行为，需再次忽略 |

---

## 📚 相关文件清单

| 文件 | 职责 |
|------|------|
| `app/models/codebase.py` | Repository 模型定义 |
| `app/domain/project/sync_service.py` | 核心同步逻辑 |
| `app/domain/project/sync_tasks.py` | Celery 同步任务 |
| `app/api/routes/projects.py` | API 端点 |
| `app/domain/project/cache.py` | 缓存工具 |
| `app/domain/project/events.py` | 领域事件 |
| `stores/projectStore.ts` | 前端项目状态 |
| `stores/projectImportStore.ts` | 前端导入管理 |

---

**文档版本**: v1.0  
**最后更新**: 2026-04-03  
**相关组件**: EvoLoop Backend, EvoLoop Desktop
