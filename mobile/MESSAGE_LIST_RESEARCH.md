# 桌面端消息列表调研报告

**调研目标**: 了解桌面端消息列表支持的功能，为 Mobile 端实现提供参考
**调研日期**: 2026-04-07

---

## 1. 消息数据结构 (Message Interface)

```typescript
interface Message {
  id: number | string
  role: "human" | "ai" | "tool" | "system"
  content: string
  thinking?: string              // AI 思考过程
  timestamp?: string             // ISO 时间戳
  run_id?: string               // 深度链接
  parent_id?: number            // 父消息 ID（线程）
  node_source?: string          // Agent 节点来源 (chat/finish/worker/supervisor)
  
  // 引用/来源
  references?: Array<{
    id: string
    type: string                 // memory, file, knowledge, image, audio
    target_id: string           // URL 或路径
    target_name: string
    metadata?: {
      duration?: number
      waveform?: number[]
      transcript?: string
    }
  }>
  
  // 附件（语音等）
  attachments?: Array<{
    id: string
    type: string
    url: string
    name: string
    metadata?: {
      duration?: number
      waveform?: number[]
      transcript?: string
      localPath?: string
    }
  }>
  
  // 工具执行步骤
  steps?: AgentProcessStep[]
  steps_snapshot?: Array<...>   // 历史快照
  
  status?: "pending" | "streaming" | "completed" | "failed"
}
```

---

## 2. 支持的消息类型

### 2.1 文本消息
- **Markdown 渲染**: 使用 `react-markdown` + `remark-gfm`
- **代码高亮**: 使用 `react-syntax-highlighter` (vscDarkPlus 主题)
- **Mermaid 图表**: 支持流程图等

### 2.2 图片消息
支持两种格式：
1. **Markdown 图片**: `![alt](url)`
2. **特殊标记**: `[Image: url]`

功能：
- 点击放大查看
- 图片预览器 (Dialog)
- 最大显示尺寸限制 (300x300)

### 2.3 文件消息
格式：`[File: url]`

功能：
- 显示文件名和图标
- 点击打开/下载
- 文件类型识别

### 2.4 音频/语音消息
格式：`[Audio: name](url)`

功能：
- 语音波形可视化
- 播放/暂停控制
- 时长显示
- 转文字内容显示

组件：`VoiceMessage`
- 波形动画
- 播放进度
- 剩余时间/总时长切换显示

### 2.5 Artifact 消息（特殊类型）
- **测试报告**: `type: "artifact", artifact_type: "test_report"`
- **需求分析**: `type: "artifact", artifact_type: "requirement_analysis"`

### 2.6 工具执行消息
- 折叠/展开式显示
- 实时步骤更新
- 成功/失败状态

---

## 3. Markdown 支持详情

### 3.1 基础元素
- 段落 `<p>`
- 列表 `<ul>` / `<ol>` / `<li>`
- 链接 `<a>` (新标签页打开)
- 引用 `<blockquote>`
- 表格 `<table>` / `<th>` / `<td>`
- 行内代码 `<code>`
- 代码块 `<pre>` + 语法高亮

### 3.2 代码块特性
- 语言识别 (`language-xxx`)
- 语法高亮 (Prism)
- 复制按钮
- 行数显示 (超过15行显示)
- 最大高度限制 (200px)

### 3.3 特殊处理
- 工具动作列表项识别 (📄📝💻 等 emoji 开头)
- 自动链接处理

---

## 4. 消息渲染流程

```
MessageContent
├── 1. 预处理
│   ├── 提取 <report> 标签内容
│   └── 过滤内部标签 (<audit>, <thought>, <outcome>)
│
├── 2. 内容分割
│   └── 按 [Image:/File:/Audio:] 分割成 parts
│
├── 3. 遍历渲染 parts
│   ├── Image → 图片组件 + 预览器
│   ├── File → 文件卡片
│   ├── Audio → 音频播放器
│   └── Text → ReactMarkdown
│
└── 4. Markdown 组件映射
    ├── code → SyntaxHighlighter (代码高亮)
    ├── p → 段落
    ├── ul/ol → 列表
    ├── a → 链接
    ├── blockquote → 引用
    ├── table → 表格
    └── img → 图片
```

---

## 5. Mobile 端适配建议

### 5.1 必需实现的功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Markdown 渲染 | P0 | 基础文本格式 |
| 代码高亮 | P0 | 开发者场景核心 |
| 图片显示 | P0 | 已支持上传，需要显示 |
| 链接点击 | P0 | 基础交互 |

### 5.2 建议实现的功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 图片预览 | P1 | 点击放大查看 |
| 文件下载 | P1 | 文件类型消息 |
| 语音播放 | P1 | 语音消息回显 |
| 引用显示 | P1 | 来源 footnotes |

### 5.3 可选功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Mermaid 图表 | P2 | 移动端可能太小 |
| 代码复制 | P2 | 长代码需要 |
| 表格横向滚动 | P2 | 大表格适配 |

### 5.4 技术选型

| 功能 | 桌面端 | Mobile 建议 |
|------|--------|-------------|
| Markdown | react-markdown | react-native-markdown-display |
| 代码高亮 | react-syntax-highlighter | react-native-syntax-highlighter |
| 图片预览 | 自定义 Dialog | react-native-image-zoom-viewer |
| 音频播放 | HTML Audio | expo-av |

---

## 6. 关键实现文件

### 桌面端
- `MessageList.tsx` - 消息列表容器
- `ChatMessageItem.tsx` - 消息项组件
- `MessageContent.tsx` - 消息内容渲染
- `VoiceMessage.tsx` - 语音消息组件

### Mobile 端需创建/修改
- `components/chat/MessageList.tsx` - 消息列表
- `components/chat/MessageItem.tsx` - 消息项
- `components/chat/MessageContent.tsx` - 内容渲染
- `components/chat/VoiceMessage.tsx` - 语音消息

---

## 7. 消息类型标记格式

桌面端使用特殊标记嵌入富媒体：

```markdown
// 图片
[Image: https://example.com/image.jpg]

// 文件
[File: https://example.com/document.pdf]

// 音频
[Audio: 语音消息](https://example.com/audio.mp3)

// 或者直接 URL
https://example.com/image.jpg
```

Mobile 端需要解析这些标记并渲染对应组件。
