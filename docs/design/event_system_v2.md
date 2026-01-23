# 前端消息回显系统扩展架构设计 (Frontend Event System Architecture V2)

## 1. 设计背景与目标
当前 EvoLoop 的消息回显机制主要依赖硬编码的 SSE 监听（`ChatConnection`）和 状态更新（`chatStore`）。随着未来事件类型的扩展（如：引用来源、调试日志、计费信息、多模态输出等），现有的“打补丁”式开发会导致代码难以维护。

**核心目标：**
*   **可扩展性 (Extensibility)**: 新增一种回显事件类型时，只需增加配置/适配器，无需修改核心连接逻辑。
*   **解耦 (Decoupling)**: UI 组件（气泡）与数据传输层分离，通过“插件化”方式渲染内容。
*   **完整性 (Completeness)**: 确保所有后端状态（如 Artifacts）都能被自动映射到前端状态。

---

## 2. 架构概览

我们将采用 **"Pipeline + Plugin"** 模式重构现有的处理流程。

```mermaid
graph LR
    SSE[SSE Stream] --> Connection[Connection Hub]
    Connection --> Dispatcher[Event Dispatcher]
    
    subgraph Data Layer
        Dispatcher --Raw Payload--> Adapter[Event Adapters]
        Adapter --> Store[Chat Store (Slices)]
    end
    
    subgraph UI Layer
        Store --> Bubble[Composite AI Bubble]
        Bubble --Context--> R1[Task Renderer]
        Bubble --Context--> R2[Artifact Renderer]
        Bubble --Context--> R3[Content Renderer]
        Bubble --Context--> R4[Citation Renderer (Future)]
    end
```

---

## 3. 详细设计

### 3.1 数据层：类型化事件总线 (Typed Event Bus)

不再在 `ChatConnection` 中硬编码 `if (event.type === 'token')`，而是建立统一的事件注册表。

**类型定义 (`src/types/events.ts`):**

```typescript
// 定义后端可能发送的所有事件类型枚举
export enum EventType {
  TOKEN = 'token',
  ACTIVITY = 'activity', // 全量/增量状态同步
  HUMAN_REQUEST = 'human_request',
  ERROR = 'error',
  // Future:
  CITATION = 'citation',
  DEBUG_LOG = 'debug_log'
}

// 定义每种事件的数据载荷结构
export interface EventPayloads {
  [EventType.TOKEN]: { content: string };
  [EventType.ACTIVITY]: ActivitySnapshot; // 复用现有的全量结构
  [EventType.HUMAN_REQUEST]: HumanRequest;
  [EventType.CITATION]: { source: string, url: string }; // 示例扩展
}
```

### 3.2 逻辑层：适配器模式 (Adapter Pattern)

在 Store 中引入 **Slices (切片)** 概念，每个切片负责处理一部分业务数据。

**ChatStore重构建议:**

```typescript
interface ChatState {
  // Slices
  conversation: { messages: Message[]; ... },
  execution: { tasks: Task[]; status: string; ... },
  artifacts: { items: Artifact[]; ... },          // ✅ 新增
  interaction: { request: HumanRequest | null; ... }
}

// Event Handlers (Reducers)
const eventHandlers = {
  [EventType.TOKEN]: (state, payload) => {
    // 仅更新流式缓冲区
    state.streaming.buffer += payload.content;
  },
  [EventType.ACTIVITY]: (state, payload) => {
    // 分发到各个切片
    state.execution.tasks = payload.tasks;
    state.execution.status = payload.status;
    state.artifacts.items = payload.artifacts;    // ✅自动映射
    state.memories.active = payload.active_memories;
  }
}
```

### 3.3 UI层：动态渲染器 (Dynamic Renderers)

`CompositeAIBubble` 不再由一堆 `if/else` 组成，而是转变为一个 **容器 (Container)**，根据当前状态中包含的数据类型，动态挂载子组件。

**组件注册表:**

| 优先级 | 渲染器组件 | 渲染条件 (Condition) | 说明 |
| :--- | :--- | :--- | :--- |
| 10 | `<TaskSteps />` | `state.tasks.length > 0` | 渲染执行步骤与进度 |
| 20 | `<ArtifactsList />` | `state.artifacts.length > 0` | **(新增)** 渲染生成的文件/资源卡片 |
| 30 | `<MessageContent />` | `state.streamedContent !== ""` | 渲染正文/Markdown |
| 40 | `<HumanRequestCard />` | `state.interaction.request !== null` | 渲染交互卡片 |

---

## 4. 实施路线图 (Implementation Plan)

### 第一阶段：基础补全 (本次任务)
1.  **扩展 Store**: 在 `useChatStore` 中添加 `artifacts` 字段。
2.  **更新 Handler**: 在 `_setActivitySnapshot` 中添加 `artifacts` 的解构赋值。
3.  **实现 UI**: 新建 `src/components/Chat/Artifacts/ArtifactsList.tsx` 组件，用于展示文件图标和名称。
4.  **集成 UI**: 在 `CompositeAIBubble` 中插入 `<ArtifactsList />`。

### 第二阶段：重构连接层 (未来优化)
1.  改造 `ChatConnection.ts` 支持泛型事件监听。
2.  将 Store 拆分为多个 Slice 避免巨型对象。

## 5. 预览：Artifacts UI 设计

在 AI 气泡内部，位于“任务步骤 (Accordion)”下方，“正文内容”上方。

```
+--------------------------------------------------+
| 🤖 AI Agent                                     |
+--------------------------------------------------+
| > 3/5 Steps Completed (Running...)               | [TaskSteps]
+--------------------------------------------------+
| 📄 index.html   🎨 style.css   (✨ Created)      | [ArtifactsList] (New!)
+--------------------------------------------------+
|                                                  |
| I have created the landing page files as         | [MessageContent]
| requested. You can now access...                 |
|                                                  |
+--------------------------------------------------+
```

该设计确保了无论后端增加何种类型的回显数据（如生成的图片、调用的API记录），我们只需在中间插入一行新的渲染器即可。
