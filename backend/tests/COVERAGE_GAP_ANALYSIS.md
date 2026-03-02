# EvoLoop V5 测试覆盖率缺口分析

## 总体覆盖率
- **总行数**: 27,937 lines
- **已覆盖**: 14,997 lines → ~17,000 lines
- **覆盖率**: 46% → 52%

---

## 高优先级缺口 (核心功能)

### 1. Engine 核心模块 ✅ 部分完成
| 文件 | 行数 | 功能描述 | 状态 |
|------|------|----------|------|
| `app/core/engine/tasks.py` | 234 | 引擎异步任务 | ✅ ~36% 已测试 |
| `app/core/engine/routers.py` | 39 | 节点路由逻辑 | ✅ ~85% 已测试 |
| `app/core/engine/history.py` | 79 | 对话历史管理 | ✅ ~34% 已测试 |
| `app/core/engine/cleanup.py` | 93 | 资源清理 | ✅ ~31% 已测试 |
| `app/core/engine/background_agent.py` | 161 | 后台代理 | ✅ ~32% 已测试 |
| `app/core/engine/graph_builder.py` | 71 | LangGraph构建 | ❌ 0% 待测试 |

### 2. Environment 环境管理 ✅ 部分完成
| 文件 | 当前 | 功能描述 |
|------|------|----------|
| `app/core/environment/handlers.py` | 0% | 环境事件处理器 |
| `app/core/environment/explorers/android.py` | 0% | Android设备探测 |
| `app/core/environment/focus.py` | 10% | 焦点管理 |

### 3. Desktop/Mobile 工具 ✅ 已完成
| 文件 | 当前 | 功能描述 |
|------|------|----------|
| `app/domain/tools/environment/desktop.py` | ~35% | 桌面控制工具 | ✅ 已测试 |
| `app/domain/tools/environment/mobile.py` | ~32% | 移动设备控制 | ✅ 已测试 |
| `app/domain/tools/environment/browser.py` | 9% | 浏览器控制 | ⚠️ 低优先级 |

### 4. Codebase 索引与检索 ✅ 已完成
| 文件 | 当前 | 功能描述 |
|------|------|----------|
| `app/domain/codebase/indexing/service.py` | ~60% | 索引服务 | ✅ 已测试 |
| `app/domain/codebase/retrieval/service.py` | ~70% | 检索服务 | ✅ 已测试 |
| `app/domain/project/sync_service.py` | ~40% | 项目同步服务 | ✅ 已测试 |

**已完成**: GUI自动化核心功能、索引服务、检索服务、项目同步服务已覆盖

---

## 中优先级缺口 (支撑功能)

### 4. Atlas 任务系统 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/atlas/tasks.py` | 76 | Atlas异步任务 |
| `app/core/brain/tasks.py` | 18 | Brain任务 |
| `app/core/brain/cleanup.py` | 20 | Brain清理 |

### 5. Learning 学习系统 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/learning/frame_extractor.py` | 74 | 视频帧提取 |
| `app/core/learning/skill_retriever.py` | 5 | 技能检索 |
| `app/core/learning/exceptions.py` | 6 | 学习异常 |

### 6. Vision 清理 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/vision/cleanup.py` | 45 | 截图清理任务 |

### 7. Context 线程存储 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/context/thread_store.py` | 49 | 线程上下文存储 |

### 8. Execution 沙盒 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/execution/sandbox/docker.py` | 62 | Docker沙盒执行 |

### 9. Codebase 索引提取器 (8% 覆盖率)
| 文件 | 当前 | 功能描述 |
|------|------|----------|
| `app/domain/codebase/indexing/extractors/treesitter_extractor.py` | 8% | TreeSitter代码提取 |

### 10. LSP 语言服务器 (14-22% 覆盖率)
| 文件 | 当前 | 功能描述 |
|------|------|----------|
| `app/infrastructure/solidlsp/ls.py` | 14% | LSP核心 |
| `app/domain/tools/coding/lsp.py` | 15% | LSP工具 |

---

## 低优先级缺口 (基础设施)

### 11. MCP 服务器 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/core/tools/mcp/server.py` | 138 | MCP服务器实现 |

### 12. 初始化数据 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/initial_data.py` | 76 | 数据库初始化 |

### 13. 重试工具 (0% 覆盖率)
| 文件 | 行数 | 功能描述 |
|------|------|----------|
| `app/utils/retry.py` | 24 | 重试装饰器 |

---

## 推荐测试补充优先级

### Phase 1: 核心引擎 (建议优先)
1. `app/core/engine/tasks.py` - 引擎任务系统
2. `app/core/engine/routers.py` - 路由逻辑
3. `app/core/engine/history.py` - 历史管理
4. `app/core/engine/background_agent.py` - 后台代理

### Phase 2: 环境/设备控制
5. `app/domain/tools/environment/desktop.py` - 桌面控制
6. `app/domain/tools/environment/mobile.py` - 移动控制
7. `app/core/environment/focus.py` - 焦点管理

### Phase 3: 索引/LSP
8. `app/domain/codebase/indexing/extractors/treesitter_extractor.py`
9. `app/domain/tools/coding/lsp.py`

### Phase 4: 支撑系统
10. `app/core/atlas/tasks.py`
11. `app/core/learning/frame_extractor.py`
12. `app/core/context/thread_store.py`
13. `app/core/vision/cleanup.py`

---

## 预估工作量

| 阶段 | 文件数 | 预估测试数 | 预估工时 |
|------|--------|-----------|----------|
| Phase 1 (Engine) | 4 | 30-40 | 2-3天 |
| Phase 2 (环境控制) | 3 | 25-35 | 2-3天 |
| Phase 3 (索引/LSP) | 2 | 15-20 | 1-2天 |
| Phase 4 (支撑) | 4 | 15-20 | 1-2天 |
| **总计** | **13** | **85-115** | **6-10天** |

---

## 当前已覆盖良好的模块 (供参考)

- ✅ `app/utils/time.py` - 100%
- ✅ `app/utils/text.py` - 100%
- ✅ `app/utils/security.py` - 100%
- ✅ `app/models/*` - 100%
- ✅ `app/core/brain/` - ~85%
- ✅ `app/core/identity/` - ~90%
- ✅ `app/domain/codebase/filter.py` - ~70%
