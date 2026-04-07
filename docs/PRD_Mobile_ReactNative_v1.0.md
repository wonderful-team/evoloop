# 📱 EvoLoop Mobile React Native 重构 PRD

**版本**: v1.0  
**日期**: 2026-04-06  
**状态**: 待评审  

---

## 1. 项目概述

### 1.1 项目背景

EvoLoop 移动端目前基于 Tauri Web 技术构建，存在以下核心问题：
- **手势体验差**：Web 技术在移动端的手势响应延迟高
- **原生能力受限**：语音、蓝牙等硬件访问能力不足
- **性能瓶颈**：复杂列表滚动卡顿，内存占用高

### 1.2 项目目标

将 EvoLoop 移动端从 Tauri Web 架构**彻底重构**为 React Native 原生架构，实现：
- 原生级手势体验和动画性能（60fps）
- 实时语音对话（ASR + LLM 全双工）
- 完整的设备管理和控制能力
- 与 Desktop Agent 的无缝协同

### 1.3 重构范围

| 模块 | 范围 | 说明 |
|------|------|------|
| 语音对话 | 全新设计 | 实时 ASR + LLM 流式对话 |
| 设备管理 | 保留功能 | 扫码绑定、状态监控、指令下发 |
| 项目管理 | 保留功能 | 列表、切换、当前项目显示 |
| 用户系统 | 保留功能 | 登录/注册/找回密码 |
| 会员订阅 | 保留功能 | 套餐展示、支付跳转 |
| 历史会话 | 增强 | 语音对话历史留存 |

### 1.4 目标用户画像

**主要用户**：软件开发工程师

**使用场景**：
- 通勤路上通过语音快速创建/跟进任务
- 会议中语音记录需求，会后自动同步到 Desktop
- 远程查看 Desktop Agent 执行状态

**技术特征**：熟悉开发工具，对响应速度敏感

---

## 2. 产品功能详细设计

### 2.1 功能架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        EvoLoop Mobile                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     核心功能层                           │   │
│  │                                                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ 🎙️ 实时语音   │  │ 💻 设备管理   │  │ 📁 项目管理   │  │   │
│  │  │   对话        │  │              │  │              │  │   │
│  │  │ • 按住说话    │  │ • 扫码绑定    │  │ • 列表查看    │  │   │
│  │  │ • 实时转录    │  │ • 在线状态    │  │ • 快速切换    │  │   │
│  │  │ • 流式回复    │  │ • 指令下发    │  │ • 项目详情    │  │   │
│  │  │ • 指令确认    │  │ • 历史记录    │  │              │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     支撑功能层                           │   │
│  │                                                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ 🔐 用户认证   │  │ 💳 会员订阅   │  │ 📜 历史会话   │  │   │
│  │  │              │  │              │  │              │  │   │
│  │  │ • 手机号登录  │  │ • 套餐展示    │  │ • 对话列表    │  │   │
│  │  │ • 密码登录    │  │ • 权益说明    │  │ • 搜索筛选    │  │   │
│  │  │ • 短信验证码  │  │ • 支付购买    │  │ • 详情查看    │  │   │
│  │  │ • 找回密码    │  │ • 续费管理    │  │              │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.2 双模式对话系统

重构后的移动端支持**两种对话模式**，用户可在使用过程中自由切换：

| 模式 | 默认状态 | 输入方式 | 技术路径 | 适用场景 |
|------|----------|----------|----------|----------|
| **ASR 语音模式** | ✅ 默认 | 按住说话 | Mobile → Gateway → NLS → LLM → Desktop | 快速指令、自然对话、移动场景 |
| **常规文本模式** | 可切换 | 键盘输入 | Mobile → Gateway → LLM → Desktop | 精确指令、长文本、安静环境 |

**模式切换设计**:
- 对话界面底部提供切换按钮（麦克风图标 ↔ 键盘图标）
- 切换后当前对话上下文保持，仅改变输入方式
- 用户偏好保存到本地存储，下次启动恢复
- 文本模式不走 NLS 语音服务，直接发送文本到 LLM

**技术差异**:

| 环节 | ASR 语音模式 | 常规文本模式 |
|------|--------------|--------------|
| 用户输入 | 录音 → PCM 音频流 | TextInput 输入 |
| Gateway 处理 | 转发到阿里云 NLS | 直接转发到 LLM |
| 延迟特性 | ASR 延迟 + LLM 延迟 | 仅 LLM 延迟 |
| 打断支持 | ✅ 支持语音打断 | ✅ 支持发送新消息打断 |

---

### 2.3 核心功能：实时语音对话 (ASR 模式)

#### 2.3.1 功能流程图

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  启动   │───►│  录音   │───►│ ASR识别 │───►│ LLM处理 │───►│ 指令确认 │
│         │    │         │    │         │    │         │    │         │
│点击语音 │    │按住说话 │    │实时转录 │    │澄清/确认│    │用户确认 │
│  入口   │    │VAD检测  │    │流式显示 │    │生成指令 │    │下发执行 │
└─────────┘    └────┬────┘    └─────────┘    └────┬────┘    └────┬────┘
     │               │                            │              │
     │               └────────────────────────────┘              │
     │                      支持打断                            │
     │         ┌─────────────────────────────────┐               │
     └────────►│ 用户按住按钮 → 打断AI → 重新录音  │◄──────────────┘
               └─────────────────────────────────┘
```

#### 2.3.2 状态机详细设计

```typescript
enum VoiceSessionState {
  // 空闲状态
  IDLE = 'idle',
  
  // 连接中
  CONNECTING = 'connecting',
  
  // 监听中（用户说话）
  LISTENING = 'listening',
  
  // 等待 ASR 最终结果
  RECOGNIZING = 'recognizing',
  
  // AI 处理中
  PROCESSING = 'processing',
  
  // AI 回复中（流式输出）
  RESPONDING = 'responding',
  
  // 确认型回复（如"收到"）
  ACKNOWLEDGING = 'acknowledging',
  
  // 澄清需求
  CLARIFYING = 'clarifying',
  
  // 指令已生成
  COMMAND_READY = 'command_ready',
  
  // 指令执行中
  EXECUTING = 'executing',
  
  // 出错
  ERROR = 'error'
}

interface VoiceSession {
  id: string;
  state: VoiceSessionState;
  startTime: number;
  
  // 用户输入
  userTranscript: string;
  userMessages: ChatMessage[];
  
  // AI 响应
  aiResponse: string;
  aiResponseBuffer: string;  // 流式缓冲
  
  // 当前指令
  currentCommand?: TaskCommand;
  
  // 关联设备
  targetDeviceId?: string;
  targetProjectId?: number;
}
```

#### 2.3.3 多轮对话场景设计

**场景一：单次明确指令**

| 步骤 | 用户 | 系统 | 状态 |
|------|------|------|------|
| 1 | 按住："分析 login.js 的第 15 行" | - | listening |
| 2 | 松开 | ASR："分析 login.js 的第 15 行" | recognizing |
| 3 | - | AI："收到，正在分析..." | acknowledging |
| 4 | - | 显示指令卡片 | command_ready |
| 5 | 点击"确认" | 发送到 Desktop | executing |

**场景二：需要澄清**

| 步骤 | 用户 | 系统 | 状态 |
|------|------|------|------|
| 1 | 按住："分析一下登录功能" | - | listening |
| 2 | 松开 | ASR："分析一下登录功能" | processing |
| 3 | - | AI："请问您想分析哪个文件？1. src/auth/login.js 2. components/Login.tsx" | clarifying |
| 4 | 按住："第一个" | - | listening |
| 5 | 松开 | ASR："第一个" | processing |
| 6 | - | 显示指令卡片（已确定目标） | command_ready |

**场景三：打断**

| 步骤 | 用户 | 系统 | 状态 |
|------|------|------|------|
| 1 | - | AI 正在说话："我将对项目进行全面分析..." | responding |
| 2 | 按住按钮 | 立即停止 AI 播放，清空当前 | listening |
| 3 | 说话："停，先分析登录功能" | 新录音 | listening |
| 4 | 松开 | 新识别结果，重新处理 | processing |

#### 2.2.4 UI 设计规范

**主界面布局**：

```
┌─────────────────────────────────────────┐
│  🔷 EvoLoop              [设备状态] ⚡  │  ← Header
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────┐   │
│  │                                 │   │
│  │      对话内容区域                │   │
│  │                                 │   │
│  │  🤖 收到，请稍等...             │   │  ← AI 消息（左对齐）
│  │                                 │   │
│  │           分析哪个文件？        │   │
│  │           1. login.js           │   │
│  │           2. Login.tsx          │   │
│  │                                 │   │
│  │  第一个                         │   │  ← 用户消息（右对齐）
│  │                                 │   │
│  │      [音波动画 - 录音中]        │   │
│  │                                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  📋 即将执行                     │   │  ← 指令卡片
│  │  分析 src/auth/login.js          │   │
│  │  描述: 检查登录逻辑实现          │   │
│  │                                 │   │
│  │  [确认执行] [修改] [取消]        │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │                                 │   │
│  │         [ 按住说话 🔘 ]         │   │  ← 主按钮
│  │         长按打断 松开发送        │   │
│  │                                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [📎] [📷] [📁]               [💬]    │  ← 快捷操作
└─────────────────────────────────────────┘
```

**按钮状态**：

| 状态 | 视觉 | 交互 |
|------|------|------|
| 空闲 | 圆形按钮，渐变背景 | 按住开始录音 |
| 录音中 | 放大动画 + 红色脉冲 + 音波 | 松开发送，长按持续 |
| AI 说话中 | 绿色呼吸灯 | 按住打断 |

---

### 2.4 设备管理功能

#### 2.3.1 功能清单

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 设备列表 | 显示所有绑定的 Desktop 设备 | P0 |
| 在线状态 | 实时显示设备在线/离线/忙碌 | P0 |
| 扫码绑定 | 扫描二维码绑定新设备 | P0 |
| 设备详情 | 查看设备信息、当前项目、能力 | P1 |
| 解绑设备 | 解除设备绑定 | P1 |
| 快捷指令 | 发送常用指令（如切换项目） | P2 |

#### 2.3.2 设备绑定流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  设备列表   │───►│  点击添加   │───►│  扫码页面   │
│             │    │             │    │             │
│  [+] 按钮   │    │             │    │ 相机权限申请 │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                              │
                                              ▼ QR: evoloop://bind?key=xxx&name=xxx
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Desktop    │◄───│  Gateway    │◄───│  识别成功   │
│  显示二维码  │    │  处理绑定   │    │  确认绑定   │
└─────────────┘    └─────────────┘    └─────────────┘
```

#### 2.3.3 设备卡片设计

```
┌─────────────────────────────────────────┐
│  💻 MacBook-Pro (在线)          [更多]  │
│  ─────────────────────────────────────  │
│  📍 当前项目: my-project                │
│  ⏱️ 最后活跃: 2分钟前                   │
│  ⚡ 能力: 语音对话 文件传输              │
│                                         │
│  [💬 对话] [📂 切换项目] [⚙️ 设置]      │
└─────────────────────────────────────────┘
```

---

### 2.5 项目管理功能

#### 2.5.1 功能清单

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 项目列表 | 显示所有可访问项目 | P0 |
| 项目切换 | 切换当前激活项目 | P0 |
| 当前项目显示 | 全局显示当前项目名 | P0 |
| 项目详情 | 查看项目基本信息 | P1 |
| 最近项目 | 快速访问最近使用 | P2 |

#### 2.5.2 项目切换流程

```
1. 用户点击底部"项目" Tab
2. 显示项目列表（带当前标记 ✓）
3. 用户选择新项目
4. 发送 switch_project 指令到 Desktop
5. Desktop 确认切换
6. 本地状态更新，全局显示新项目名
```

---

### 2.6 用户认证功能

#### 2.6.1 登录方式

| 方式 | 优先级 | 说明 |
|------|--------|------|
| 手机号 + 验证码 | P0 | 主要方式 |
| 手机号 + 密码 | P0 | 备选方式 |
| 邮箱 + 密码 | P1 | 复用现有接口 |

#### 2.6.2 登录流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  启动 App   │───►│  检查 Token │───►│  有效       │
│             │    │             │    │             │
└─────────────┘    └──────┬──────┘    │  进入首页    │
                          │             └─────────────┘
                          │ Token 无效/过期
                          ▼
                   ┌─────────────┐
                   │  登录页面   │
                   │             │
                   │  [手机号]   │
                   │  [验证码]   │
                   │  [获取验证码] │
                   │             │
                   │  [登录]     │
                   └─────────────┘
```

---

### 2.7 会员订阅功能

**与 Desktop 端复用同一套会员等级和支付体系**，但权益配置针对移动端场景进行精简。

#### 2.7.1 会员体系架构

**接口复用路径**: Mobile → Gateway (evoloop/backend) → member-center/backend

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         会员体系架构                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐   │
│  │   Mobile    │────►│  Gateway    │────►│   member-center         │   │
│  │   (RN)      │     │  evoloop/   │     │   /backend (PHP)        │   │
│  │             │◄────│  backend    │◄────│                         │   │
│  └─────────────┘     │  /api/v1/*  │     │  addon/subscription/    │   │
│                      └─────────────┘     │  • MemberBenefitService │   │
│                                          │  • Order management     │   │
│                                          │  • Quota tracking       │   │
│                                          └─────────────────────────┘   │
│                                                                         │
│  **Subscription API 定义在**:                                            │
│  @evoloop/backend/app/core/evocloud/backends/http_client.py            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**统一 Base URL**:

```typescript
// 所有接口共用同一个 Base URL (来自 @evoloop/.env)
const BASE_URL = 'https://evoloop.develop-assistant.cn';
```

**URL 前缀规则** (参考 http_client.py L113-123):

| 功能模块 | 路径前缀 | 示例 | 说明 |
|----------|----------|------|------|
| **聊天对话** (WebSocket) | `/gateway/ws` | `wss://.../gateway/ws` | ASR + LLM 实时对话 |
| **设备管理** | `/gateway/api/v1` | `/gateway/api/v1/devices` | 设备列表、绑定、指令 |
| **项目管理** | `/gateway/api/v1` | `/gateway/api/v1/projects` | 项目列表、切换 |
| **订阅管理** | `/member` | `/member/subscription/api/plans` | 套餐、订单、权益 |
| **用户认证** | `/member` | `/member/api/login/mobile` | 登录、注册 |

**完整 URL 示例**:

```typescript
// ===== Gateway 路由 (聊天、设备、项目) =====
// WebSocket 聊天对话
wss://${BASE_URL}/gateway/ws

// 设备管理
GET  ${BASE_URL}/gateway/api/v1/devices
POST ${BASE_URL}/gateway/api/v1/devices/bind
POST ${BASE_URL}/gateway/api/v1/commands/send

// 项目管理
GET  ${BASE_URL}/gateway/api/v1/projects
POST ${BASE_URL}/gateway/api/v1/projects/switch

// ===== Member 路由 (订阅、认证) =====
// 订阅管理
GET  ${BASE_URL}/member/subscription/api/subscription/status
POST ${BASE_URL}/member/subscription/api/subscription/createOrder

// 用户认证
POST ${BASE_URL}/member/api/login/mobile
GET  ${BASE_URL}/member/api/member/info
```

**关键说明**:
- 所有接口共用 Base URL: `https://evoloop.develop-assistant.cn`
- Mobile 调用 **Gateway (evoloop/backend)** 提供的各类 API
- Gateway 的 `EvoCloudHTTPClient` 根据路径前缀路由到不同后端服务
- Subscription API 定义在 http_client.py L428-522

#### 2.7.2 会员等级与权益

**Mobile 端权益配置** (基于 @member-center/backend/addon/subscription/):

Mobile 端权益针对移动端场景进行精简，仅保留相关功能：

| 权益编码 | 权益名称 | 类型 | 免费版 | 创作者版 | 极客版 | 专家版 | 企业版 | 说明 |
|----------|----------|------|--------|----------|--------|--------|--------|------|
| `ai_quota` | AI 调用额度 | 数值 | 50/月 | 300/月 | 1000/月 | 3000/月 | 无限 | 0=无限 |
| `ai_advanced` | 高级模型 | 布尔 | ❌ | ❌ | ✅ | ✅ | ✅ | GPT-4 等 |
| `voice` | 语音交互 | 布尔 | ❌ | ❌ | ✅ | ✅ | ✅ | **Mobile 核心** |
| `project_limit` | 项目数量 | 数值 | 1 | 3 | 10 | 50 | 0 | 0=无限 |
| `gantt` | 甘特图 | 布尔 | ❌ | ❌ | ❌ | ❌ | ✅ | 项目管理 |
| `timesheet` | 工时表 | 布尔 | ❌ | ❌ | ❌ | ❌ | ✅ | 项目管理 |

**Mobile 端不使用的 Desktop 权益**:

| 权益编码 | 权益名称 | 不使用原因 |
|----------|----------|-----------|
| `browser_control` | 浏览器控制 | Desktop 专属 |
| `desktop_control` | 桌面控制 | Desktop 专属 |
| `mobile_control` | 手机控制 | Desktop 专属 |
| `skill_learning` | 技能学习 | Desktop 专属 |
| `wiki_generation` | Wiki 生成 | Desktop 专属 |
| `knowledge_base` | 知识库 | Desktop 专属 |
| `mcp` | MCP 服务 | Desktop 专属 |
| `code_execution` | 代码执行 | Desktop 专属 |
| `storage` | 存储空间 | Desktop 专属 |

**权益配置存储位置**:
- 权益定义存储在 `member_level.charge_rule` JSON 字段中的 `evoloop_benefits` 对象
- Mobile 权益与 Desktop 权益共用同一配置，但 Mobile 只读取其需要的字段

#### 2.7.3 移动端订阅页面设计

**页面结构** (`/subscription`):

```
┌─────────────────────────────────────────────────────────────┐
│ ← 订阅管理                                    [关闭]         │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 💎 当前套餐: 极客版                     [状态: 活跃]      │ │
│ │ 有效期至: 2026-05-15 (剩余 30 天)                        │ │
│ │                                        [续费] [升级]      │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ⚡ AI 配额使用                           [刷新]          │ │
│ │ ████████████░░░░░░░░  1200 / 1000 (已超额)               │ │
│ │ 额度将在 2026-05-01 自动重置                              │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ───────────────── 可选方案 ─────────────────                │
│                                                             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │   创作者版     │ │ ⭐ 极客版     │ │   专家版     │         │
│ │   (当前)      │ │   (当前)      │ │              │         │
│ │              │ │              │ │              │         │
│ │   ¥29/月     │ │   ¥99/月     │ │   ¥299/月    │         │
│ │              │ │              │ │              │         │
│ │ • AI 300次   │ │ • AI 1000次  │ │ • AI 3000次  │         │
│ │ • Wiki生成   │ │ • 浏览器控制  │ │ • 桌面控制   │         │
│ │              │ │ • 技能学习    │ │ • 手机控制   │         │
│ │              │ │              │ │              │         │
│ │   [当前使用]  │ │   [当前使用]  │ │   [立即升级]  │         │
│ └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                             │
│ ─────────────── 权益对比说明 ───────────────                │
│ [查看完整功能对比表]                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.7.4 支付确认页面 (PayConfirm)

参考 `member-center/mobile_uniapp/components/ns-payment/ns-payment.vue`：

```
┌─────────────────────────────────────────────────────────────┐
│ ←  确认支付                                     [关闭]       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    支付金额                                  │
│                   ¥ 99.00                                   │
│              EvoLoop 极客版 - 年费                           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  选择支付方式                                                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 💚  微信支付                                  [选中]  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 🔵  支付宝支付                               [未选中]  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│     点击支付即表示您同意《服务协议》和《隐私政策》              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    立即支付                            │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**支付流程交互**:
1. 用户选择套餐 → 跳转支付确认页
2. 显示支付金额和订单信息
3. 选择支付方式（默认微信支付）
4. 点击"立即支付" → 创建订单 → 获取支付参数 → 调起微信 SDK
5. 支付完成后 → 跳转支付结果页

#### 2.7.5 支付结果页面 (PayResult)

参考 `member-center/mobile_uniapp/pages_tool/pay/result.vue`：

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    [支付成功图标]                            │
│                      支付成功                                │
│                     ¥ 99.00                                 │
│                                                             │
│           您已成功订阅 EvoLoop 极客版                        │
│           有效期至: 2027-04-06                              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    查看权益                            │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    返回首页                            │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**支付失败状态**:
```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    [支付失败图标]                            │
│                      支付失败                                │
│                                                             │
│              失败原因: 用户取消支付                          │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   重新支付                             │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.7.4 API 接口 (通过 Gateway)

**接口定义源文件**: `@evoloop/backend/app/core/evocloud/backends/http_client.py`

**统一 Base URL**: `https://evoloop.develop-assistant.cn`

```typescript
// 完整 URL 示例
const BASE_URL = 'https://evoloop.develop-assistant.cn';

// Subscription API 前缀: /member/subscription/api
// 完整路径: ${BASE_URL}/member/subscription/api/...

// ===== 订阅状态查询 =====
// 获取订阅状态
// 请求: GET ${BASE_URL}/member/subscription/api/subscription/status
Headers: { Authorization: "Bearer {token}" }
Resp: { 
  code: number; 
  data: { 
    has_subscription: boolean; 
    level_id: number;
    status: string;
  } 
}

// 获取订阅详情
// 请求: GET ${BASE_URL}/member/subscription/api/subscription/getDetail
Headers: { Authorization: "Bearer {token}" }
Resp: { 
  code: number; 
  data: {
    member_id: number;
    level_id: number;
    level_name: string;
    status: string;
    expire_time: number;
    is_member: number;
    remaining_days: number;
  }
}

// ===== 套餐列表 =====
// 获取可用订阅计划（包含权益详情）
// 请求: GET ${BASE_URL}/member/subscription/api/subscription/plans
Headers: { Authorization: "Bearer {token}" }
Resp: {
  code: number;
  data: Array<{
    level_id: number;
    level_name: string;
    price: string;
    market_price: string;
    subscription_quota: number;
    description?: string;
    benefits: {
      ai_quota: number;
      ai_advanced: boolean;
      voice: boolean;
      project_limit: number;
      gantt: boolean;
      timesheet: boolean;
      sort: number;
    };
  }>;
}

// 计算升级价格预览
// 请求: POST ${BASE_URL}/member/subscription/api/plan/calculateUpgradePrice
Headers: { Authorization: "Bearer {token}" }
Body: { target_level_id: number }
Resp: {
  code: number;
  data: {
    is_upgrade: boolean;
    pay_amount: string;
    refund_amount: string;
    net_amount: string;
  }
}

// ===== 权益检查 =====
// 获取会员完整权益信息
// 请求: GET ${BASE_URL}/member/subscription/api/subscription/benefits
Headers: { Authorization: "Bearer {token}" }
Resp: {
  code: number;
  data: {
    member_id: number;
    level_id: number;
    level_name: string;
    is_expired: boolean;
    expire_time: number;
    remaining_days: number;
    benefits: {
      ai_quota: number;
      ai_advanced: boolean;
      voice: boolean;
      project_limit: number;
      gantt: boolean;
      timesheet: boolean;
    };
  }
}

// 检查单项权益
// 请求: POST ${BASE_URL}/member/subscription/api/subscription/checkBenefit
Headers: { Authorization: "Bearer {token}" }
Body: { code: string }  // 'voice', 'ai_advanced' 等
Resp: {
  code: number;
  data: {
    has_benefit: boolean;
    value: any;
    benefit_code: string;
    expire_time: number;
  }
}

// 检查特定功能权限
// 请求: POST ${BASE_URL}/member/subscription/api/subscription/checkPermission
Headers: { Authorization: "Bearer {token}" }
Body: { feature: string }
Resp: {
  code: number;
  data: {
    has_permission: boolean;
    required_level: string;
  }
}

// ===== AI 配额 =====
// 获取 AI 配额 (统一配额池)
// 请求: GET ${BASE_URL}/member/subscription/api/aiQuota
Headers: { Authorization: "Bearer {token}" }
Resp: {
  code: number;
  data: {
    quota: number;        // 总额度 (-1=无限)
    quota_used: number;   // 已使用
    remaining: number;    // 剩余
    is_unlimited: boolean;
  }
}

// 获取配额使用历史
// 请求: GET ${BASE_URL}/member/subscription/api/aiQuota/getUsageHistory?page=1&page_size=20
Headers: { Authorization: "Bearer {token}" }
Resp: {
  code: number;
  data: {
    list: Array<{
      count: number;
      source: string;
      deducted_at: number;
    }>;
    count: number;
  }
}

// ===== 订单与支付 =====
// 创建订阅订单
// 请求: POST ${BASE_URL}/member/subscription/api/subscription/createOrder
Headers: { Authorization: "Bearer {token}" }
Body: { 
  level_id: number;
  auto_renew: 0|1;
  app_type: 'app';  // APP 支付，区别于 Desktop 的 'pc'
}
Resp: {
  code: number;
  data: {
    order_id: string;
    out_trade_no: string;
    order: object;
    pay_data: {
      appid: string;
      partnerid: string;
      prepayid: string;
      noncestr: string;
      timestamp: string;
      package: 'Sign=WXPay';
      sign: string;
    };
  }
}

// 检查订单状态
// 请求: GET ${BASE_URL}/member/subscription/api/order/checkStatus?order_id={id}
Headers: { Authorization: "Bearer {token}" }
Resp: {
  code: number;
  data: {
    order_id: number;
    pay_status: number;  // 0:未支付 1:已支付
    pay_time: number;
    order_status: number;
  }
}

// 取消订阅
// 请求: POST ${BASE_URL}/member/subscription/api/subscription/cancel
Headers: { Authorization: "Bearer {token}" }
Body: { cancel_type: 'expire'|'now', reason?: string }
Resp: { code: number; message: string }
```

#### 2.7.5 支付流程设计 (微信 APP 支付)

**移动端使用微信 APP 支付 SDK**，直接调起微信客户端完成支付。

```
┌─────────────┐    ┌─────────────────────────────────────────────────────────────┐
│ 选择套餐    │───►│              member-center/backend                           │
│             │    │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│ 点击升级    │    │  │ 创建订单     │───►│  微信支付    │───►│  返回 APP   │     │
│             │    │  │             │    │  统一下单    │    │  支付参数   │     │
└─────────────┘    │  └─────────────┘    └─────────────┘    └──────┬──────┘     │
                                                            │               │
                                                            ▼               │
                                                   ┌─────────────┐        │
                                                   │ 调起微信     │        │
                                                   │ 客户端支付   │        │
                                                   └──────┬──────┘        │
                                                          │               │
                                                          ▼               │
                                                   ┌─────────────┐        │
                                                   │ 微信支付     │        │
                                                   │ 结果回调     │────────┘
                                                   │ (App/URL)   │
                                                   └─────────────┘
```

**支付流程详细步骤**:

| 步骤 | 调用方 | 接口/操作 | 说明 |
|------|--------|-----------|------|
| 1 | Mobile | `POST /subscription/Subscription/createOrder` | 创建订单，`app_type: 'app'` |
| 2 | member-center | 调用微信支付统一下单 | 生成 APP 支付参数 |
| 3 | Mobile | `WeChat.pay(pay_data)` | react-native-wechat-lib 调起微信 |
| 4 | 微信客户端 | 用户完成支付 | 输入密码/指纹 |
| 5 | 微信服务器 | 回调 member-center | 异步通知支付结果 |
| 6 | Mobile | `AppState` / `Linking` | 监听 App 从微信返回 |
| 7 | Mobile | `GET /subscription/Order/getPayStatus` | 主动查询确认支付状态 |
| 8 | Mobile | 刷新会员权益缓存 | 权益立即生效 |

**React Native 支付调用**:

```typescript
import * as WeChat from 'react-native-wechat-lib';
import { Linking, AppState } from 'react-native';

// 初始化微信 SDK (App 启动时)
WeChat.registerApp('wx1234567890', 'https://evoloop.cn/universal-link/');

// 支付函数
async function payWithWechat(levelId: number) {
  try {
    // 1. 创建订单 (指定 app_type: 'app')
    const orderRes = await SubscriptionService.createOrder({
      level_id: levelId,
      pay_type: 'wechatpay',
      app_type: 'app',  // 关键：使用 APP 支付
    });
    
    if (orderRes.code !== 0) {
      throw new Error(orderRes.message);
    }
    
    const { order_id, pay_data } = orderRes.data;
    
    // 2. 调起微信支付
    const payResult = await WeChat.pay({
      partnerId: pay_data.partnerid,
      prepayId: pay_data.prepayid,
      nonceStr: pay_data.noncestr,
      timeStamp: pay_data.timestamp,
      package: pay_data.package,
      sign: pay_data.sign,
    });
    
    // 3. 处理支付结果
    if (payResult.errCode === 0) {
      // 支付成功，查询确认
      const statusRes = await SubscriptionService.getPayStatus(order_id);
      if (statusRes.data.pay_status === 1) {
        // 刷新权益缓存
        await queryClient.invalidateQueries({ queryKey: ['member', 'benefits'] });
        return { success: true, order_id };
      }
    } else if (payResult.errCode === -2) {
      // 用户取消
      return { success: false, cancelled: true };
    } else {
      throw new Error(`支付失败: ${payResult.errStr}`);
    }
  } catch (error) {
    console.error('Payment error:', error);
    return { success: false, error };
  }
}

// iOS 支付回调处理 (AppDelegate.mm)
// 已在 react-native-wechat-lib 中封装，无需额外配置
```

**支付参数数据结构**:

```typescript
interface CreateOrderResponse {
  code: number;
  data: {
    order_id: string;
    out_trade_no: string;
    order: {
      order_no: string;
      order_money: string;
      level_name: string;
    };
    // APP 支付参数 (与 Desktop 的 qrcode 不同)
    pay_data: {
      appid: string;       // 应用ID
      partnerid: string;   // 商户号
      prepayid: string;    // 预支付交易会话ID
      noncestr: string;    // 随机字符串
      timestamp: string;   // 时间戳
      package: 'Sign=WXPay';
      sign: string;        // 签名
    };
  };
}
```

**与 Desktop 支付的区别**:

| 平台 | 支付方式 | 后端接口 | 调起方式 | 回调处理 |
|------|----------|----------|----------|----------|
| Desktop | 微信扫码支付 | `app_type: 'pc'` | 展示二维码图片 | 轮询检查 |
| Mobile (RN) | 微信 APP 支付 | `app_type: 'app'` | `WeChat.pay()` | App 回调 + 主动查询 |

#### 2.7.6 会员权益与访问权限机制

**Mobile 端权益定义** (精简版，仅包含移动端需要的权益):

```typescript
// Mobile 端权益编码定义
export type MobileBenefitCode = 
  | 'ai_quota'           // AI 调用额度 (数值)
  | 'ai_advanced'        // 高级模型 (布尔)
  | 'voice'              // 语音交互 (布尔) - 核心功能
  | 'project_limit'      // 项目数量 (数值)
  | 'gantt'              // 甘特图 (布尔)
  | 'timesheet';         // 工时表 (布尔)

// 权益到所需套餐的映射
export const BENEFIT_PLAN_MAP: Record<MobileBenefitCode, string> = {
  ai_quota: '探索者版',      // 基础额度所有等级都有
  ai_advanced: '极客版',
  voice: '极客版',           // 语音交互核心权益
  project_limit: '探索者版', // 项目限制各等级不同
  gantt: '企业版',
  timesheet: '企业版',
};

// 权益中文名称映射
export const BENEFIT_NAME_MAP: Record<MobileBenefitCode, string> = {
  ai_quota: 'AI 调用额度',
  ai_advanced: '高级模型',
  voice: '语音交互',
  project_limit: '项目数量',
  gantt: '甘特图',
  timesheet: '工时表',
};

// Desktop 端权益 (Mobile 不检查，仅作为参考)
export type DesktopOnlyBenefitCode =
  | 'browser_control'    // 浏览器控制
  | 'desktop_control'    // 桌面控制
  | 'mobile_control'     // 手机控制
  | 'skill_learning'     // 技能学习
  | 'wiki_generation'    // Wiki生成
  | 'knowledge_base'     // 知识库
  | 'mcp'                // MCP服务
  | 'code_execution'     // 代码执行
  | 'storage';           // 存储空间
```

**权益检查 Hook 实现** (Mobile 精简版):

```typescript
// hooks/useMemberBenefits.ts
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { MemberService } from '../client';  // Gateway API Client

const BENEFITS_CACHE_TTL = 30 * 1000; // 30秒缓存

export interface MobileBenefitsData {
  member_id: number;
  level_id: number;
  level_name: string;
  is_expired: boolean;
  expire_time: number;
  remaining_days: number;
  benefits: {
    ai_quota: number;
    ai_advanced: boolean;
    voice: boolean;
    project_limit: number;
    gantt: boolean;
    timesheet: boolean;
    // Desktop 权益也会返回，但 Mobile 不读取
    browser_control?: boolean;
    desktop_control?: boolean;
    mobile_control?: boolean;
    // ...
  };
}

// 获取会员权益 (带缓存)
export function useMemberBenefits(forceRefresh = false) {
  return useQuery({
    queryKey: ['member', 'benefits'],
    queryFn: async (): Promise<MobileBenefitsData> => {
      const res = await MemberService.getMemberBenefits({ force_refresh: forceRefresh });
      return res.data;
    },
    staleTime: BENEFITS_CACHE_TTL,
    gcTime: 5 * 60 * 1000,
  });
}

// 检查单项权益 (Mobile 专属)
export function useBenefitAccess(benefitCode: MobileBenefitCode) {
  const { data: benefitsData, isLoading, error } = useMemberBenefits();
  
  const value = benefitsData?.benefits?.[benefitCode];
  let hasAccess = false;
  
  // 统一转换为bool
  if (typeof value === 'boolean') {
    hasAccess = value;
  } else if (typeof value === 'number') {
    hasAccess = value > 0;
  } else if (typeof value === 'string') {
    hasAccess = ['true', 'on', '1', 'yes'].includes(value.toLowerCase());
  }
  
  // 检查是否过期
  if (benefitsData?.is_expired) {
    hasAccess = false;
  }
  
  return {
    hasAccess,
    isLoading,
    error,
    isExpired: benefitsData?.is_expired ?? false,
    levelName: benefitsData?.level_name ?? '探索者',
    featureName: BENEFIT_NAME_MAP[benefitCode],
    requiredPlan: BENEFIT_PLAN_MAP[benefitCode],
  };
}

// 检查语音交互权限 (核心功能)
export function useVoiceAccess() {
  return useBenefitAccess('voice');
}

// 检查项目限制
export function useProjectLimit() {
  const { data: benefitsData } = useMemberBenefits();
  const limit = benefitsData?.benefits?.project_limit ?? 1;
  return {
    limit,
    isUnlimited: limit === 0,
    canCreate: (currentCount: number) => limit === 0 || currentCount < limit,
  };
}

// 刷新权益缓存
export function useRefreshBenefits() {
  const queryClient = useQueryClient();
  
  return {
    refresh: () => queryClient.invalidateQueries({ queryKey: ['member', 'benefits'] }),
    refreshAsync: () => queryClient.refetchQueries({ queryKey: ['member', 'benefits'] }),
  };
}

// ============================================
// API Client 封装 (基于 Gateway)
// ============================================

// client/index.ts
import { httpClient } from './core';

// 统一 Base URL: https://evoloop.develop-assistant.cn
// 不同接口使用不同前缀

const API_PREFIX = {
  // Gateway 路由 (聊天对话、设备管理、项目管理)
  GATEWAY: '/gateway/api/v1',
  
  // member-center addon (订阅、认证)
  MEMBER: '/member/subscription/api',
  
  // project-manage addon (项目列表)
  PROJECT: '/projectmanage/api/projectOpen',
};

export class MemberService {
  // 获取会员权益
  static async getMemberBenefits(params?: { force_refresh?: boolean }) {
    return httpClient.get(`${API_PREFIX.MEMBER}/subscription/benefits`, { params });
  }
  
  // 获取订阅状态
  static async getSubscriptionStatus() {
    return httpClient.get(`${API_PREFIX.MEMBER}/subscription/status`);
  }
  
  // 获取订阅详情
  static async getSubscriptionDetail() {
    return httpClient.get(`${API_PREFIX.MEMBER}/subscription/getDetail`);
  }
  
  // 获取套餐列表
  static async getSubscriptionPlans() {
    return httpClient.get(`${API_PREFIX.MEMBER}/subscription/plans`);
  }
  
  // 获取 AI 配额
  static async getAiQuota() {
    return httpClient.get(`${API_PREFIX.MEMBER}/aiQuota`);
  }
  
  // 创建订阅订单
  static async createSubscriptionOrder(data: {
    level_id: number;
    auto_renew?: number;
    app_type: 'app';
  }) {
    return httpClient.post(`${API_PREFIX.MEMBER}/subscription/createOrder`, data);
  }
  
  // 检查订单状态
  static async checkOrderStatus(order_id: string) {
    return httpClient.get(`${API_PREFIX.MEMBER}/order/checkStatus`, { params: { order_id } });
  }
}

export class ProjectService {
  // 获取项目列表 (通过 Gateway)
  static async getProjects(page = 1, page_size = 100) {
    return httpClient.get(`${API_PREFIX.GATEWAY}/projects`, { params: { page, page_size } });
  }
  
  // 创建项目 (通过 Gateway)
  static async createProject(data: { name: string; description: string; path: string }) {
    return httpClient.post(`${API_PREFIX.GATEWAY}/projects`, data);
  }
  
  // 切换当前项目 (通过 Gateway)
  static async switchProject(projectId: number) {
    return httpClient.post(`${API_PREFIX.GATEWAY}/projects/switch`, { project_id: projectId });
  }
}

export class DeviceService {
  // 获取设备列表 (通过 Gateway)
  static async getDevices() {
    return httpClient.get(`${API_PREFIX.GATEWAY}/devices`);
  }
  
  // 绑定设备 (通过 Gateway)
  static async bindDevice(deviceKey: string) {
    return httpClient.post(`${API_PREFIX.GATEWAY}/devices/bind`, { device_key: deviceKey });
  }
  
  // 发送指令到 Desktop (通过 Gateway)
  static async sendCommand(data: { device_id: number; content: any }) {
    return httpClient.post(`${API_PREFIX.GATEWAY}/commands/send`, data);
  }
}

// 刷新权益缓存
export function useRefreshBenefits() {
  const queryClient = useQueryClient();
  
  return {
    refresh: () => queryClient.invalidateQueries({ queryKey: ['member', 'benefits'] }),
    refreshAsync: () => queryClient.refetchQueries({ queryKey: ['member', 'benefits'] }),
  };
}
```

**权益守卫组件**:

```typescript
// components/BenefitGuard.tsx
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Button } from 'react-native-paper';
import { useBenefitAccess, BenefitCode } from '../hooks/useMemberBenefits';

interface BenefitGuardProps {
  benefitCode: BenefitCode;
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onUpgrade?: () => void;
}

export function BenefitGuard({ 
  benefitCode, 
  children, 
  fallback,
  onUpgrade 
}: BenefitGuardProps) {
  const { hasAccess, isLoading, featureName, requiredPlan, levelName } = 
    useBenefitAccess(benefitCode);
  
  if (isLoading) {
    return <LoadingSkeleton />;
  }
  
  if (hasAccess) {
    return <>{children}</>;
  }
  
  // 自定义降级 UI
  if (fallback) {
    return <>{fallback}</>;
  }
  
  // 默认升级提示 UI
  return (
    <View style={styles.container}>
      <View style={styles.iconContainer}>
        <Text style={styles.icon}>🔒</Text>
      </View>
      <Text style={styles.title}>功能受限</Text>
      <Text style={styles.description}>
        {featureName}功能需要{requiredPlan}及以上套餐
      </Text>
      <Text style={styles.currentLevel}>当前: {levelName}</Text>
      <Button 
        mode="contained" 
        onPress={onUpgrade}
        style={styles.upgradeButton}
      >
        升级套餐
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 24,
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    margin: 16,
  },
  iconContainer: {
    marginBottom: 16,
  },
  icon: {
    fontSize: 48,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  description: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    marginBottom: 4,
  },
  currentLevel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 16,
  },
  upgradeButton: {
    width: '100%',
  },
});

// 使用示例
function VoiceChatScreen() {
  return (
    <BenefitGuard 
      benefitCode="voice"
      onUpgrade={() => navigation.navigate('Subscription')}
    >
      <VoiceChatInterface />
    </BenefitGuard>
  );
}
```

**AI 配额检查**:

```typescript
// hooks/useAIQuota.ts
import { useQuery } from '@tanstack/react-query';
import { MemberService } from '../client';

export interface AIQuota {
  total: number;
  used: number;
  remaining: number;
  is_unlimited: boolean;
  reset_time?: number;
}

export function useAIQuota() {
  return useQuery({
    queryKey: ['member', 'quota'],
    queryFn: async (): Promise<AIQuota> => {
      const res = await MemberService.getAiQuota();
      return res.data;
    },
    staleTime: 60 * 1000, // 1分钟缓存
    refetchInterval: 60 * 1000, // 自动刷新
  });
}

// 检查是否还有额度
export function useHasQuota() {
  const { data: quota } = useAIQuota();
  
  if (!quota) return { hasQuota: false, isLoading: true };
  
  if (quota.is_unlimited) {
    return { hasQuota: true, isUnlimited: true, isLoading: false };
  }
  
  return {
    hasQuota: quota.remaining > 0,
    remaining: quota.remaining,
    total: quota.total,
    usagePercent: (quota.used / quota.total) * 100,
    isLoading: false,
  };
}
```

#### 2.7.7 权益限制提示设计

当用户使用受限功能时，展示升级提示：

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ 功能受限                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   语音交互功能需要 极客版 及以上套餐                          │
│                                                             │
│   当前: 创作者版                                            │
│   升级后可用: 浏览器控制、技能学习、语音交互                   │
│                                                             │
│   [查看方案对比]              [立即升级 ¥99/月]              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 2.7.8 与 Desktop 共享的实现

**接口调用方式**:

Mobile 和 Desktop 都通过 **Gateway (evoloop/backend)** 访问 subscription 服务：

```
┌─────────────────────────────────────────────────────────────────┐
│                     接口调用架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Mobile (RN)              Desktop (Tauri)                      │
│        │                        │                               │
│        └──────────┬─────────────┘                               │
│                   │                                             │
│                   ▼                                             │
│   ┌───────────────────────────────┐                            │
│   │   Gateway (evoloop/backend)   │                            │
│   │   /api/v1/subscription/*      │                            │
│   │                               │                            │
│   │   EvoCloudHTTPClient          │                            │
│   │   @ http_client.py:428-522    │                            │
│   └───────────────┬───────────────┘                            │
│                   │                                             │
│                   ▼                                             │
│   ┌───────────────────────────────┐                            │
│   │   member-center/backend       │                            │
│   │   addon/subscription/         │                            │
│   └───────────────────────────────┘                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**核心实现文件**:

| 文件 | 作用 |
|------|------|
| `@evoloop/backend/app/core/evocloud/backends/http_client.py:428-522` | Subscription API 封装 |
| `@member-center/backend/addon/subscription/service/MemberBenefitService.php` | 权益服务实现 |
| `@member-center/backend/addon/subscription/shop/view/plan/edit.html` | 权益配置页面 |

**权益配置共享**:

```
member_level.charge_rule JSON 字段:
└── evoloop_benefits: {
    ├── ai_quota: number              ← 共用
    ├── ai_advanced: boolean         ← 共用
    ├── voice: boolean               ← Mobile 核心
    ├── project_limit: number        ← Mobile 需要
    ├── gantt: boolean               ← Mobile 需要
    ├── timesheet: boolean           ← Mobile 需要
    ├── browser_control: boolean     ← Desktop 专属
    ├── desktop_control: boolean     ← Desktop 专属
    └── ...
}
```

**支付差异**:

| 平台 | `app_type` | 支付方式 |
|------|------------|----------|
| Desktop | `pc` | 微信扫码支付 |
| Mobile | `app` | 微信 APP 支付 (react-native-wechat-lib) |

**无需修改后端**，Mobile 复用 Gateway 已有的 subscription API。

---

### 2.8 历史会话功能

#### 2.8.1 功能清单

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 会话列表 | 按时间倒序显示所有对话 | P1 |
| 搜索 | 按关键词搜索历史 | P2 |
| 详情查看 | 查看完整对话内容 | P1 |
| 重新执行 | 基于历史指令再次发送 | P2 |

---

## 3. 技术架构设计

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端 (React Native)                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Presentation Layer (UI)                                │   │
│  │  - Screens (Expo Router)                                │   │
│  │  - Components (React Native Paper + Custom)             │   │
│  │  - Animations (Reanimated 3)                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Business Logic Layer                                   │   │
│  │  - VoiceSessionManager (语音会话管理)                    │   │
│  │  - DeviceManager (设备管理)                             │   │
│  │  - ProjectManager (项目管理)                            │   │
│  │  - AuthManager (认证管理)                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Data Layer                                             │   │
│  │  - GatewayClient (WebSocket 通信)                       │   │
│  │  - API Client (HTTP REST)                               │   │
│  │  - State Store (Zustand)                                │   │
│  │  - Local Storage (AsyncStorage/MMKV)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Native Layer                                           │   │
│  │  - Audio Recorder (expo-av)                             │   │
│  │  - Audio Player (PCM Player)                            │   │
│  │  - Camera (expo-camera)                                 │   │
│  │  - File System (expo-file-system)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket (wss://) / HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         服务端                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Go Gateway   │  │ PHP Backend  │  │ Desktop      │          │
│  │ - 协议转换   │  │ - 用户/设备  │  │ - Python     │          │
│  │ - ASR 代理   │  │ - 历史留存   │  │ - Agent      │          │
│  │ - LLM 代理   │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈

| 层级 | 技术选型 | 版本 | 理由 |
|------|----------|------|------|
| 框架 | React Native + Expo | 0.76 / SDK 52 | 生态完善，热更新 |
| 导航 | Expo Router | v4 | 文件路由，简洁 |
| UI | React Native Paper | v5 | Material Design |
| 状态 | Zustand | v5 | 轻量，TypeScript |
| 网络 | axios + WebSocket | - | 标准方案 |
| 音频 | expo-av | v14 | Expo 官方 |
| 存储 | MMKV + AsyncStorage | - | 高性能+兼容 |
| 错误监控 | Sentry | ^6.0.0 | 线上错误追踪 |

### 3.3 项目目录结构

```
evoloop-mobile/
├── app/                          # Expo Router 文件路由
│   ├── (auth)/                   # 认证路由组
│   │   ├── _layout.tsx           # 认证布局
│   │   ├── index.tsx             # 登录入口
│   │   ├── login.tsx             # 手机号/账号登录
│   │   ├── register.tsx          # 注册
│   │   └── forgot-password.tsx   # 找回密码
│   ├── (main)/                   # 主应用路由组
│   │   ├── _layout.tsx           # 底部 Tab 布局
│   │   ├── index.tsx             # 首页 (语音对话)
│   │   ├── devices.tsx           # 设备列表
│   │   ├── projects.tsx          # 项目列表
│   │   └── profile.tsx           # 个人中心
│   ├── (subscription)/           # 订阅路由组
│   │   ├── _layout.tsx
│   │   ├── plans.tsx             # 套餐列表
│   │   ├── pay-confirm.tsx       # 支付确认
│   │   └── pay-result.tsx        # 支付结果
│   ├── _layout.tsx               # 根布局
│   └── +not-found.tsx            # 404 页面
├── components/                   # 共享组件
│   ├── ui/                       # 基础 UI 组件
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Card.tsx
│   │   └── Skeleton.tsx
│   ├── auth/                     # 认证相关组件
│   │   ├── MobileInput.tsx
│   │   ├── Captcha.tsx
│   │   └── WechatAuth.tsx
│   ├── chat/                     # 聊天相关组件
│   │   ├── MessageList.tsx
│   │   ├── MessageItem.tsx
│   │   ├── ChatInput.tsx
│   │   ├── VoiceRecorder.tsx
│   │   └── CommandCard.tsx
│   ├── device/                   # 设备相关组件
│   │   ├── DeviceCard.tsx
│   │   ├── DeviceStatus.tsx
│   │   └── QRScanner.tsx
│   └── subscription/             # 订阅相关组件
│       ├── PlanCard.tsx
│       ├── BenefitList.tsx
│       └── PaymentSheet.tsx
├── hooks/                        # 自定义 Hooks
│   ├── useAuth.ts
│   ├── useGateway.ts
│   ├── useVoiceSession.ts
│   ├── useDevices.ts
│   ├── useProjects.ts
│   └── useSubscription.ts
├── services/                     # 服务层
│   ├── api/                      # API 客户端
│   │   ├── client.ts             # axios 实例
│   │   ├── auth.ts               # 认证 API
│   │   ├── devices.ts            # 设备 API
│   │   ├── projects.ts           # 项目 API
│   │   ├── subscription.ts       # 订阅 API
│   │   └── payment.ts            # 支付 API
│   ├── auth/                     # 认证服务
│   │   ├── AuthManager.ts
│   │   └── WechatAuth.ts
│   ├── gateway/                  # Gateway 服务
│   │   ├── GatewayClient.ts
│   │   └── types.ts
│   ├── voice/                    # 语音服务
│   │   ├── VoiceSessionManager.ts
│   │   ├── AudioRecorder.ts
│   │   └── VADDetector.ts
│   └── storage/                  # 存储服务
│       ├── mmkv.ts
│       └── asyncStorage.ts
├── stores/                       # 状态管理 (Zustand)
│   ├── authStore.ts
│   ├── voiceStore.ts
│   ├── deviceStore.ts
│   ├── projectStore.ts
│   └── subscriptionStore.ts
├── constants/                    # 常量
│   ├── config.ts                 # 应用配置
│   ├── api.ts                    # API 端点
│   ├── theme.ts                  # 主题配置
│   └── benefits.ts               # 权益配置
├── types/                        # TypeScript 类型
│   ├── auth.ts
│   ├── device.ts
│   ├── project.ts
│   ├── chat.ts
│   ├── subscription.ts
│   └── api.ts
├── utils/                        # 工具函数
│   ├── format.ts                 # 格式化
│   ├── validate.ts               # 验证
│   ├── error.ts                  # 错误处理
│   └── logger.ts                 # 日志
├── locales/                      # 国际化
│   ├── zh.json
│   ├── en.json
│   └── index.ts
├── assets/                       # 静态资源
│   ├── images/
│   ├── fonts/
│   └── icons/
└── __tests__/                    # 测试
    ├── unit/
    └── integration/
```

### 3.4 文件结构详细说明

#### 3.4.1 路由文件组织 (Expo Router)

Expo Router 使用文件系统路由，约定式路由配置：

| 文件路径 | 路由 | 说明 |
|----------|------|------|
| `app/(auth)/login.tsx` | `/login` | 登录页面 |
| `app/(main)/index.tsx` | `/` | 首页（语音对话）|
| `app/(main)/devices.tsx` | `/devices` | 设备列表 |
| `app/+not-found.tsx` | 404 | 未匹配路由 |

**路由组 (Route Groups)**:
- `(auth)` - 认证路由组，无底部 Tab
- `(main)` - 主应用路由组，有底部 Tab
- `(subscription)` - 订阅路由组，独立导航栈

**布局文件**:
```typescript
// app/(main)/_layout.tsx
import { Tabs } from 'expo-router';
import { MaterialIcons } from '@expo/vector-icons';

export default function MainLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#0066FF',
        tabBarInactiveTintColor: '#666666',
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '首页',
          tabBarIcon: ({ color }) => (
            <MaterialIcons name="home" size={24} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="devices"
        options={{
          title: '设备',
          tabBarIcon: ({ color }) => (
            <MaterialIcons name="desktop-mac" size={24} color={color} />
          ),
        }}
      />
      {/* ... */}
    </Tabs>
  );
}
```

#### 3.4.2 组件分层设计

| 层级 | 目录 | 职责 | 示例 |
|------|------|------|------|
| 基础 UI | `components/ui/` | 原子级通用组件 | Button, Input, Card |
| 业务组件 | `components/{domain}/` | 领域内可复用组件 | DeviceCard, MessageItem |
| 页面组件 | `app/**/xxx.tsx` | 页面级组件 | login.tsx, devices.tsx |

**组件命名规范**:
- 使用 PascalCase: `DeviceCard.tsx`
- 组件与样式文件同名: `DeviceCard.tsx` + `DeviceCard.styles.ts`
- 测试文件: `DeviceCard.test.tsx`

#### 3.4.3 服务层设计

```
services/
├── api/                    # 纯 HTTP 请求
│   ├── client.ts          # axios 实例配置
│   ├── auth.ts            # POST /api/login
│   └── devices.ts         # GET /api/devices
│
├── auth/                  # 业务逻辑封装
│   ├── AuthManager.ts     # 登录流程管理
│   └── WechatAuth.ts      # 微信授权
│
├── gateway/               # WebSocket 通信
│   ├── GatewayClient.ts   # WebSocket 客户端
│   └── types.ts           # 消息类型定义
│
└── voice/                 # 语音相关
    ├── VoiceSessionManager.ts
    ├── AudioRecorder.ts
    └── VADDetector.ts
```

**分层原则**:
- `api/` - 只处理 HTTP 请求/响应，无业务逻辑
- `*/Manager.ts` - 封装业务流程（如登录流程包含多个 API 调用）
- `*/types.ts` - 该模块专用的类型定义

#### 3.4.4 状态管理 (Zustand)

```typescript
// stores/authStore.ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { MMKV } from 'react-native-mmkv';

const storage = new MMKV();

const mmkvStorage = {
  getItem: (name: string) => storage.getString(name) || null,
  setItem: (name: string, value: string) => storage.set(name, value),
  removeItem: (name: string) => storage.delete(name),
};

interface AuthState {
  token: string | null;
  userInfo: UserInfo | null;
  isLoggedIn: boolean;
  setToken: (token: string) => void;
  setUserInfo: (info: UserInfo) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userInfo: null,
      isLoggedIn: false,
      setToken: (token) => set({ token, isLoggedIn: true }),
      setUserInfo: (userInfo) => set({ userInfo }),
      logout: () => set({ token: null, userInfo: null, isLoggedIn: false }),
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => mmkvStorage),
    }
  )
);
```

**Store 划分原则**:
| Store | 职责 | 持久化 |
|-------|------|--------|
| authStore | 登录状态、Token | ✅ MMKV |
| voiceStore | 当前会话状态、消息列表 | ❌ 内存 |
| deviceStore | 设备列表、当前设备 | ❌ 内存 |
| projectStore | 项目列表、当前项目 | ❌ 内存 |
| subscriptionStore | 会员信息、权益 | ✅ AsyncStorage |

#### 3.4.5 类型定义组织

```
types/
├── index.ts              # 统一导出
├── auth.ts               # 认证相关
├── device.ts             # 设备相关
├── project.ts            # 项目相关
├── chat.ts               # 聊天/语音
├── subscription.ts       # 订阅相关
└── api.ts                # API 通用响应
```

**类型定义示例**:
```typescript
// types/auth.ts
export interface LoginResponse {
  token: string;
  user: UserInfo;
}

export interface UserInfo {
  id: number;
  nickname: string;
  mobile: string;
  avatar?: string;
  memberLevel: 'free' | 'basic' | 'pro';
}

// types/index.ts
export * from './auth';
export * from './device';
// ...
```

#### 3.4.6 工具函数组织

```
utils/
├── index.ts              # 统一导出
├── format.ts             # 格式化 (日期、数字等)
├── validate.ts           # 验证 (手机号、邮箱等)
├── error.ts              # 错误处理
└── logger.ts             # 日志工具
```

**工具函数示例**:
```typescript
// utils/validate.ts
export const validate = {
  mobile: (value: string): boolean => {
    return /^1[3-9]\d{9}$/.test(value);
  },
  
  password: (value: string): boolean => {
    return value.length >= 6;
  },
  
  captcha: (value: string): boolean => {
    return /^\d{4,6}$/.test(value);
  },
};

// utils/index.ts
export * from './validate';
export * from './format';
```

#### 3.4.7 测试文件组织

```
__tests__/
├── unit/                 # 单元测试
│   ├── utils/
│   │   └── validate.test.ts
│   ├── services/
│   │   └── AuthManager.test.ts
│   └── components/
│       └── DeviceCard.test.tsx
│
├── integration/          # 集成测试
│   └── auth-flow.test.ts
│
└── e2e/                  # E2E 测试
    └── login.spec.ts
```

**测试命名规范**:
- 单元测试: `*.test.ts` 或 `*.test.tsx`
- 集成测试: `*.integration.test.ts`
- E2E 测试: `*.spec.ts`

#### 3.4.8 文件命名规范总结

| 类型 | 命名规范 | 示例 |
|------|----------|------|
| 组件 | PascalCase.tsx | `DeviceCard.tsx` |
| 页面 | kebab-case.tsx | `forgot-password.tsx` |
| 工具函数 | camelCase.ts | `formatDate.ts` |
| 类型定义 | PascalCase.ts | `AuthTypes.ts` |
| 常量 | UPPER_SNAKE_CASE | `API_ENDPOINTS.ts` |
| 测试 | *.test.ts | `validate.test.ts` |
| Hooks | useCamelCase.ts | `useAuth.ts` |
| Store | camelCaseStore.ts | `authStore.ts` |

### 3.5 核心模块设计

#### 3.5.1 GatewayClient

```typescript
class GatewayClient {
  // 连接管理
  connect(): Promise<void>
  disconnect(): void
  reconnect(): Promise<void>
  
  // ASR
  startASR(): void
  stopASR(): void
  sendAudioChunk(chunk: ArrayBuffer): void
  
  // Chat
  sendChatMessage(text: string): void
  interruptChat(): void
  
  // Command
  confirmCommand(confirmed: boolean): void
  
  // 事件
  on(event: 'asrResult' | 'chatStream' | 'commandReady', handler: Function)
}
```

#### 3.5.2 AuthManager

参考 `member-center/mobile_uniapp` 登录逻辑实现：

```typescript
class AuthManager {
  // ========== 配置获取 ==========
  // 获取注册/登录配置
  async getRegisterConfig(): Promise<RegisterConfig>
  
  // 获取验证码配置
  async getCaptchaConfig(): Promise<CaptchaConfig>
  
  // 获取图形验证码
  async getCaptcha(captchaId?: string): Promise<CaptchaResponse>
  
  // ========== 手机号登录 ==========
  // 发送手机验证码
  async sendMobileCode(
    mobile: string, 
    captchaId?: string, 
    captchaCode?: string
  ): Promise<{ key: string }>
  
  // 手机号+验证码登录
  async loginWithMobile(
    mobile: string, 
    key: string, 
    code: string
  ): Promise<LoginResponse>
  
  // ========== 账号密码登录 ==========
  async loginWithAccount(
    username: string, 
    password: string,
    captchaId?: string,
    captchaCode?: string
  ): Promise<LoginResponse>
  
  // ========== 微信登录 ==========
  // 初始化微信 SDK
  async initWechat(appId: string): Promise<void>
  
  // 发起微信授权
  async wechatAuth(): Promise<WechatAuthData>
  
  // 微信授权登录
  async loginWithWechat(authData: WechatAuthData): Promise<LoginResponse>
  
  // 微信+手机号绑定登录
  async loginWithWechatMobile(
    authData: WechatAuthData,
    mobile: string,
    key: string,
    code: string
  ): Promise<LoginResponse>
  
  // ========== 用户信息 ==========
  async getMemberInfo(): Promise<MemberInfo>
  
  // ========== Token 管理 ==========
  getToken(): string | null
  setToken(token: string): void
  clearToken(): void
  isLoggedIn(): boolean
  
  // ========== 登出 ==========
  async logout(): Promise<void>
}

// 登录状态管理
interface AuthState {
  isLoggedIn: boolean;
  token: string | null;
  userInfo: MemberInfo | null;
  config: RegisterConfig | null;
}
```

#### 3.5.3 VoiceSessionManager

```typescript
class VoiceSessionManager {
  // 生命周期
  startSession(): Promise<void>
  stopSession(): Promise<void>
  
  // 控制
  startRecording(): void
  stopRecording(): void
  interrupt(): void
  
  // 状态
  getState(): VoiceSessionState
  getMessages(): ChatMessage[]
  
  // 指令
  confirmCurrentCommand(): void
  editCommand(updates: Partial<TaskCommand>): void
}
```

---

## 4. UI/UX 设计规范

### 4.1 设计原则

- **简洁**：核心功能一键触达
- **反馈**：每个操作都有即时视觉反馈
- **容错**：网络/识别错误可重试

### 4.2 登录页面设计

#### 4.2.1 登录入口页面 (LoginIndex)

参考 `member-center/mobile_uniapp/pages_tool/login/index.vue`：

```
┌─────────────────────────┐
│                         │
│       [Logo]            │  ← EvoLoop 品牌 Logo
│                         │
│   "AI 助手，随时待命"    │  ← wap_desc 配置文案
│                         │
│  ┌─────────────────┐    │
│  │   微信一键登录   │    │  ← 绿色按钮 (third_party=1 时显示)
│  └─────────────────┘    │
│                         │
│  ┌─────────────────┐    │
│  │   手机号登录     │    │  ← 主按钮
│  └─────────────────┘    │
│                         │
│    ── 其他方式登录 ──    │  ← 分割线 (login 包含多种方式时显示)
│                         │
│       👤 账号密码       │  ← 图标按钮
│                         │
│  ☑ 我已阅读并同意        │  ← 协议勾选 (agreement_show=true 时显示)
│  《隐私协议》和《用户协议》│
│                         │
└─────────────────────────┘
```

#### 4.2.2 手机号登录页面 (MobileLogin)

参考 `member-center/mobile_uniapp/pages_tool/login/login.vue`：

```
┌─────────────────────────┐
│  ←  登录                 │  ← 返回按钮
│                         │
│       手机号登录         │  ← 页面标题
│                         │
│  ┌─────────────────┐    │
│  │ +86 │ 手机号     │    │  ← 区号 + 手机号输入
│  └─────────────────┘    │
│                         │
│  ┌─────────────────┐    │
│  │ [验证码图片]     │    │  ← 图形验证码 (captcha=1 时显示)
│  └─────────────────┘    │
│                         │
│  ┌─────────────────┐    │
│  │ 动态码    [获取] │    │  ← 短信验证码 + 倒计时按钮
│  └─────────────────┘    │
│                         │
│  使用账号密码登录  →     │  ← 切换登录方式
│                         │
│  ┌─────────────────┐    │
│  │      登录       │    │  ← 主按钮
│  └─────────────────┘    │
│                         │
│  ☑ 我已阅读并同意...    │  ← 协议勾选
│                         │
└─────────────────────────┘
```

**交互说明**:
- 手机号输入：限制11位数字，实时校验格式
- 获取验证码按钮：
  - 初始状态：蓝色文字 "获取动态码"
  - 点击后：灰色文字 "120s后可重新获取"，倒计时 120 秒
  - 倒计时结束：恢复初始状态
- 登录按钮：手机号和验证码都填写后才可点击

#### 4.2.3 账号密码登录页面 (AccountLogin)

```
┌─────────────────────────┐
│  ←  登录                 │
│                         │
│      账号密码登录        │
│                         │
│  ┌─────────────────┐    │
│  │   请输入账号     │    │
│  └─────────────────┘    │
│                         │
│  ┌─────────────────┐    │
│  │   请输入密码  👁 │    │  ← 密码可见性切换
│  └─────────────────┘    │
│         忘记密码?        │  ← 右侧文字链接
│                         │
│  ┌─────────────────┐    │
│  │      登录       │    │
│  └─────────────────┘    │
│                         │
│  使用手机号登录  →       │
│                         │
└─────────────────────────┘
```

#### 4.2.4 微信登录流程

```
┌─────────────────────────┐
│                         │
│  1. 点击"微信一键登录"   │
│                         │
│  2. 唤起微信授权页       │
│     ┌──────────────┐    │
│     │  微信授权     │    │
│     │  EvoLoop申请  │    │
│     │  获取你的昵称 │    │
│     │  ...         │    │
│     └──────────────┘    │
│                         │
│  3. 授权成功，回调App    │
│                         │
│  4. 判断用户状态         │
│     ├── 已注册 → 登录成功 │
│     └── 新用户 → 绑定手机号│
│                         │
│  ┌─────────────────────┐│
│  │  检测到您还未绑定    ││  ← 强制绑定手机号弹窗
│  │  手机号              ││     (bind_mobile=1 时显示)
│  │                     ││
│  │  手机号: [输入框]    ││
│  │  动态码: [输入框][获取]││
│  │                     ││
│  │      [保存]         ││
│  └─────────────────────┘│
│                         │
└─────────────────────────┘
```

### 4.3 颜色规范

```
主色: #0066FF (品牌蓝)
辅助色: #00C853 (成功/在线)
警告色: #FFAB00 (注意)
错误色: #FF3D00 (错误)
微信绿: #07C160 (微信登录按钮)

背景: #FFFFFF (亮) / #121212 (暗)
文字: #1A1A1A (主) / #666666 (次)
```

### 4.4 字体规范

```
标题: 20-24px, SemiBold
正文: 16px, Regular
辅助: 14px, Regular
标签: 12px, Medium
```

### 4.5 间距规范

```
基础单位: 8px
常用间距: 8, 16, 24, 32
屏幕边距: 16px (移动端)
卡片内边距: 16px
```

### 4.6 错误状态与加载状态

#### 4.6.1 全局错误处理

| 错误类型 | 展示方式 | 用户操作 |
|----------|----------|----------|
| 网络错误 | Toast + 重试按钮 | 点击重试 |
| 服务器错误 | 全屏错误页 | 返回/重试 |
| 权限错误 | Dialog 提示 | 去设置/取消 |
| 业务错误 | Toast | 自动消失 |

#### 4.6.2 加载状态规范

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    [骨架屏/Skeleton]                         │
│  ┌──────────────┐  ┌─────────────────────────────────────┐  │
│  │              │  │  ████████████████████               │  │
│  │   灰色占位   │  │  ██████████                         │  │
│  │              │  │  ████████████████████████           │  │
│  └──────────────┘  └─────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘

骨架屏适用场景:
- 页面首次加载
- 下拉刷新
- 列表数据加载

加载指示器适用场景:
- 按钮加载状态
- 局部数据刷新
- 提交操作
```

#### 4.6.3 空状态设计

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                      [插图图标]                              │
│                                                             │
│                    暂无设备                                  │
│          连接您的第一台设备开始使用                          │
│                                                             │
│                  [连接设备]                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘

空状态必备元素:
- 情感化插图
- 主标题 (简洁明了)
- 副标题 (引导操作)
- 操作按钮 (可选)
```

---

## 5. 数据模型

### 5.1 核心实体

```typescript
// 用户
interface User {
  id: number;
  nickname: string;
  mobile: string;
  email?: string;
  avatar?: string;
  memberLevel: 'free' | 'basic' | 'pro';
  memberExpireTime?: number;
  quota: {
    used: number;
    total: number;
  };
}

// 设备
interface Device {
  id: string;
  name: string;
  type: 'desktop' | 'mobile';
  status: 'online' | 'offline' | 'busy';
  osInfo: string;
  currentProject?: {
    id: number;
    name: string;
  };
  lastSeen: number;
  capabilities: string[];
}

// 项目
interface Project {
  id: number;
  name: string;
  description?: string;
  rootPath: string;
  isActive: boolean;
}

// 语音会话
interface VoiceSession {
  id: string;
  state: VoiceSessionState;
  messages: ChatMessage[];
  currentCommand?: TaskCommand;
  startTime: number;
  endTime?: number;
}

// 聊天消息
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  type: 'text' | 'command';
  timestamp: number;
  metadata?: any;
}

// 任务指令
interface TaskCommand {
  id: string;
  type: 'analyze' | 'edit' | 'run' | 'debug';
  target?: string;
  description: string;
  parameters?: Record<string, any>;
  status: 'pending' | 'confirmed' | 'executing' | 'completed';
}
```

---

## 6. API 接口规范

### 6.1 REST API

**Base URL**: `https://evoloop.develop-assistant.cn`

#### 6.1.1 认证登录接口

参考 `member-center/mobile_uniapp` 实现，对接 member-center 后端：

| 端点 | 方法 | 描述 | 前缀 | 请求 | 响应 |
|------|------|------|------|------|------|
| `/api/register/config` | GET | 获取注册/登录配置 | `/member` | - | `RegisterConfig` |
| `/api/config/getCaptchaConfig` | GET | 获取验证码开关配置 | `/member` | - | `CaptchaConfig` |
| `/api/captcha/captcha` | GET | 获取图形验证码 | `/member` | `captcha_id` | `{id, img}` |
| `/api/login/mobileCode` | POST | 发送手机验证码 | `/member` | `{mobile, captcha_id, captcha_code}` | `{key}` |
| `/api/login/mobile` | POST | 手机号+动态码登录 | `/member` | `{mobile, key, code}` | `{token, user}` |
| `/api/login/login` | POST | 账号密码登录 | `/member` | `{username, password}` | `{token, user}` |
| `/api/login/auth` | POST | 微信授权登录 | `/member` | `{wx_openid, wx_unionid}` | `{token, user}` |
| `/api/tripartite/mobileauth` | POST | 微信+手机号绑定登录 | `/member` | `{iv, encryptedData, ...}` | `{token, user}` |
| `/api/member/info` | GET | 获取用户信息 | `/member` | Header: `Authorization` | `MemberInfo` |
| `/subscription/api/order/create` | POST | 创建订阅订单 | `/member` | `{level_id, period}` | `OrderInfo` |
| `/api/pay/pay` | POST | 发起支付 | `/member` | `{out_trade_no, pay_type}` | `PayParams` |
| `/api/pay/status` | GET | 查询支付状态 | `/member` | `out_trade_no` | `PayStatus` |

**URL 前缀说明**:
- `/member` - 用户认证、订阅管理 (直接访问 member-center)
- `/gateway` - 聊天对话、设备管理、项目管理 (通过 Gateway 代理)

#### 6.1.2 登录配置数据结构

```typescript
// 注册/登录配置 (GET /api/register/config)
interface RegisterConfig {
  register: string;        // 注册方式: mobile/username/both
  login: string[];         // 允许的登录方式: ['mobile', 'username']
  third_party: number;     // 是否开启第三方登录: 0/1
  bind_mobile: number;     // 第三方登录是否强制绑定手机号: 0/1
  agreement_show: boolean; // 是否显示用户协议
  wap_desc: string;        // 登录页描述文案
}

// 验证码配置 (GET /api/config/getCaptchaConfig)
interface CaptchaConfig {
  shop_reception_login: number;  // 0: 关闭, 1: 开启
}

// 图形验证码响应 (GET /api/captcha/captcha)
interface CaptchaResponse {
  id: string;   // 验证码ID
  img: string;  // Base64 图片数据
}

// 手机验证码发送 (POST /api/login/mobileCode)
interface MobileCodeRequest {
  mobile: string;
  captcha_id?: string;    // 图形验证码ID
  captcha_code?: string;  // 图形验证码值
}
interface MobileCodeResponse {
  key: string;  // 验证码key，登录时需要回传
}

// 手机号登录 (POST /api/login/mobile)
interface MobileLoginRequest {
  mobile: string;
  key: string;    // 发送验证码返回的key
  code: string;   // 短信验证码
}

// 账号密码登录 (POST /api/login/login)
interface AccountLoginRequest {
  username: string;
  password: string;
  captcha_id?: string;
  captcha_code?: string;
}

// 微信授权登录 (POST /api/login/auth)
interface WechatLoginRequest {
  wx_openid?: string;
  wx_unionid?: string;
  weapp_openid?: string;  // 小程序openid
}

// 登录成功响应
interface LoginResponse {
  code: number;
  message: string;
  data: {
    token: string;               // JWT Token
    can_receive_registergift: number;  // 是否可领取注册礼
    is_register?: boolean;       // 是否新注册用户
  }
}

// 用户信息 (GET /api/member/info)
interface MemberInfo {
  member_id: number;
  nickname: string;
  headimg: string;           // 头像URL
  mobile: string;
  member_level: number;
  member_level_name: string;
}
```

#### 6.1.3 微信 APP 登录流程

React Native 使用 `react-native-wechat-lib` 实现微信 APP 登录：

```typescript
// 微信登录流程
class WechatAuthManager {
  // 1. 注册微信 SDK (App 启动时调用)
  async registerApp(appId: string): Promise<void>;
  
  // 2. 发起微信授权请求
  async sendAuthRequest(scopes?: string[], state?: string): Promise<AuthResponse>;
  
  // 3. 获取 AccessToken 和 OpenId
  async getAccessToken(code: string): Promise<{
    access_token: string;
    openid: string;
    unionid?: string;
  }>;
  
  // 4. 获取用户信息
  async getUserInfo(accessToken: string, openId: string): Promise<WechatUserInfo>;
  
  // 5. 调用后端登录
  async loginWithWechat(authData: WechatAuthData): Promise<LoginResponse>;
}

// 微信授权数据结构
interface WechatAuthData {
  wx_openid?: string;
  wx_unionid?: string;
  nickname?: string;
  headimg?: string;
}
```

**微信登录步骤**:
1. 调用 `registerApp` 初始化微信 SDK
2. 调用 `sendAuthRequest` 唤起微信授权页
3. 用户授权后，App 通过 Linking 接收回调，获取 `code`
4. 调用微信接口交换 `code` 获取 `access_token` 和 `openid`
5. 调用后端 `/api/login/auth` 完成登录
6. 如果是新用户且配置要求绑定手机号，弹出绑定手机号界面

#### 6.1.4 设备与项目接口

| 端点 | 方法 | 描述 | 前缀 | 请求 | 响应 |
|------|------|------|------|------|------|
| `/api/devices` | GET | 设备列表 | `/gateway` | - | `Device[]` |
| `/api/devices/bind` | POST | 绑定设备 | `/gateway` | `{deviceKey}` | `Device` |
| `/api/projects` | GET | 项目列表 | `/gateway` | - | `Project[]` |
| `/api/projects/switch` | POST | 切换项目 | `/gateway` | `{project_id}` | `Project` |

**URL 前缀说明**:
- `/gateway` - 聊天对话、设备管理、项目管理 (通过 Gateway 代理)
- `/member` - 用户认证、订阅管理 (通过 member-center)
- `/projectmanage` - 项目管理 (直接访问 project-manage addon)

#### 6.1.5 支付接口

参考 `member-center/mobile_uniapp/components/ns-payment/ns-payment.vue` 实现 APP 支付：

```typescript
// 创建订阅订单 (POST /subscription/api/order/create)
interface CreateOrderRequest {
  level_id: number;    // 会员等级ID
  period: 'month' | 'year';  // 订阅周期
}

interface CreateOrderResponse {
  code: number;
  data: {
    out_trade_no: string;  // 商户订单号
    pay_money: string;     // 支付金额
    pay_body: string;      // 订单描述
  }
}

// 发起支付 (POST /api/pay/pay)
interface PayRequest {
  out_trade_no: string;   // 商户订单号
  pay_type: string;       // 支付方式: wechatpay
}

// 微信支付参数 (APP支付)
interface WechatPayParams {
  partnerId: string;      // 商户号
  prepayId: string;       // 预支付交易会话标识
  nonceStr: string;       // 随机字符串
  timeStamp: string;      // 时间戳
  package: string;        // 固定值: Sign=WXPay
  sign: string;           // 签名
}

// 支付状态查询
interface PayStatus {
  pay_status: 0 | 1 | 2;  // 0:未支付, 1:支付中, 2:已支付
  pay_money: string;
}

// 支付结果
interface PayResult {
  success: boolean;
  outTradeNo: string;
  message?: string;
}
```

**APP 支付流程**:

1. **创建订单**
   ```typescript
   const orderRes = await api.post('/subscription/api/order/create', {
     level_id: selectedPlan.id,
     period: 'year'
   });
   const { out_trade_no } = orderRes.data;
   ```

2. **获取支付参数**
   ```typescript
   const payRes = await api.post('/api/pay/pay', {
     out_trade_no,
     pay_type: 'wechatpay'
   });
   const payData = payRes.data.data;  // WechatPayParams
   ```

3. **调用微信 SDK 支付** (react-native-wechat-lib)
   ```typescript
   import * as WeChat from 'react-native-wechat-lib';
   
   const result = await WeChat.pay({
     partnerId: payData.partnerId,
     prepayId: payData.prepayId,
     nonceStr: payData.nonceStr,
     timeStamp: payData.timeStamp,
     package: payData.package,
     sign: payData.sign,
   });
   
   if (result.errCode === 0) {
     // 支付成功，跳转结果页
     navigation.navigate('PayResult', { outTradeNo, success: true });
   } else if (result.errCode === -2) {
     // 用户取消
     showToast('您已取消支付');
   } else {
     // 支付失败
     showModal({ content: '支付失败: ' + result.errStr });
   }
   ```

4. **轮询支付状态** (备选方案)
   ```typescript
   const checkPayStatus = (outTradeNo: string) => {
     const timer = setInterval(async () => {
       const res = await api.get('/api/pay/status', { 
         params: { out_trade_no: outTradeNo } 
       });
       if (res.data.pay_status === 2) {
         clearInterval(timer);
         navigation.navigate('PayResult', { success: true });
       }
     }, 1000);
   };
   ```

**注意事项**:
- APP 支付使用 `react-native-wechat-lib` 而非 `react-native-wechat`，后者不支持 APP 支付
- iOS 需要在 Xcode 中配置 Universal Link 或 URL Scheme
- Android 需要配置包名和签名

### 6.2 WebSocket 协议

**WebSocket URL**: `wss://evoloop.develop-assistant.cn/gateway/ws`

移动端聊天对话（包括 ASR 语音对话和文本对话）通过 Gateway WebSocket 连接。

#### 6.2.1 消息类型

```typescript
enum GatewayMessageType {
  // 连接管理
  AUTH = 'auth',
  AUTH_RESULT = 'auth_result',
  PING = 'ping',
  PONG = 'pong',
  
  // ASR 相关
  ASR_START = 'asr_start',
  ASR_STOP = 'asr_stop',
  ASR_CHUNK = 'asr_chunk',
  ASR_RESULT = 'asr_result',
  ASR_ERROR = 'asr_error',
  
  // LLM 对话
  CHAT_START = 'chat_start',
  CHAT_MESSAGE = 'chat_message',
  CHAT_STREAM = 'chat_stream',
  CHAT_DONE = 'chat_done',
  CHAT_INTERRUPT = 'chat_interrupt',
  
  // 指令生成
  COMMAND_BUILD = 'command_build',
  COMMAND_READY = 'command_ready',
  COMMAND_CONFIRM = 'command_confirm',
  COMMAND_SEND = 'command_send',
  
  // Desktop 指令通道
  DEVICE_COMMAND = 'device_command',
  DEVICE_RESPONSE = 'device_response',
  
  // 历史留存
  HISTORY_SYNC = 'history_sync',
  
  // 状态广播
  STATUS_UPDATE = 'status_update',
}
```

#### 6.2.2 关键消息格式

```typescript
// ASR 结果
interface ASRResultMessage {
  type: 'asr_result';
  payload: {
    text: string;
    isFinal: boolean;
    confidence: number;
    beginTime?: number;
    endTime?: number;
  };
}

// AI 流式回复
interface ChatStreamMessage {
  type: 'chat_stream';
  payload: {
    sessionId: string;
    chunk: string;
    isDone: boolean;
    intent?: 'acknowledge' | 'clarify' | 'command_ready';
  };
}

// 指令就绪
interface CommandReadyMessage {
  type: 'command_ready';
  payload: {
    sessionId: string;
    command: {
      type: 'analyze' | 'edit' | 'run' | 'debug' | 'general';
      target?: string;
      description: string;
      parameters?: Record<string, any>;
    };
    preview: string;
  };
}

// 设备指令（复用 evolooplink）
interface DeviceCommandMessage {
  type: 'device_command';
  payload: {
    deviceId: string;
    command: {
      type: string;
      params: any;
    };
    source: 'voice_chat';
    sessionId: string;
  };
}
```

---

## 7. 实施计划

### 7.1 里程碑

| 阶段 | 时间 | 交付物 | 验收标准 |
|------|------|--------|----------|
| M1 | Week 1-2 | 基础设施 | 项目可运行，导航正常 |
| M2 | Week 3-4 | 核心通信 | 连接 Gateway，收发消息 |
| M3 | Week 5-6 | 语音对话 | 完成一次端到端对话 |
| M4 | Week 7 | 设备/项目 | 绑定设备，切换项目 |
| M5 | Week 8 | 认证/订阅 | 登录、支付流程通 |
| M6 | Week 9 | 优化测试 | 性能达标，无明显 Bug |

### 7.2 详细任务

**Week 1-2: 基础设施**
- [ ] Expo Bare 项目初始化
- [ ] 目录结构搭建
- [ ] 导航配置 (Expo Router)
- [ ] UI 组件库集成 (React Native Paper)
- [ ] 主题配置 (浅色/深色模式)
- [ ] 错误边界 (Error Boundary) 实现
- [ ] 全局加载状态管理
- [ ] 网络状态监听

**Week 3-4: 核心通信**
- [ ] GatewayClient 实现
- [ ] WebSocket 连接管理
- [ ] 消息协议实现
- [ ] 重连机制

**Week 5-6: 语音对话**
- [ ] Audio Recorder (expo-av)
- [ ] VAD 检测
- [ ] ASR 集成
- [ ] LLM 流式响应
- [ ] 打断机制
- [ ] 指令确认 UI

**Week 7: 设备与项目**
- [ ] 设备列表 UI
- [ ] 扫码绑定
- [ ] 项目列表
- [ ] 项目切换

**Week 8: 认证与订阅**
- [ ] AuthManager 模块实现
- [ ] 登录配置获取接口
- [ ] 图形验证码组件
- [ ] 手机号登录页面
- [ ] 账号密码登录页面
- [ ] 微信 SDK 集成 (react-native-wechat-lib)
- [ ] 微信登录流程
- [ ] 绑定手机号弹窗
- [ ] Token 持久化存储
- [ ] SubscriptionManager 模块实现
- [ ] 订阅套餐列表页面
- [ ] 支付确认页面
- [ ] react-native-wechat-lib 支付集成
- [ ] 微信支付流程
- [ ] 支付结果页面
- [ ] 会员权益展示页面

**Week 9: 优化与测试**
- [ ] 性能优化 (启动速度、内存占用)
- [ ] 错误处理完善
- [ ] 单元测试补全
- [ ] E2E 测试 (关键流程)
- [ ] iOS/Android 真机测试
- [ ] Bug 修复
- [ ] 文档完善

---

## 8. 测试计划

### 8.1 测试策略

| 测试类型 | 覆盖范围 | 工具 | 责任人 |
|----------|----------|------|--------|
| 单元测试 | 工具函数、Hooks | Jest + RNTL | 开发 |
| 集成测试 | API 调用、状态管理 | Jest | 开发 |
| E2E 测试 | 核心用户流程 | Detox / Maestro | QA |
| 性能测试 | 启动、内存、帧率 | Flipper / Xcode | 开发 |
| 真机测试 | iOS/Android 真机 | 手动 | QA |

### 8.2 功能测试

| 模块 | 测试项 | 预期结果 |
|------|--------|----------|
| 语音 | 按住说话 | 实时转录，准确显示 |
| 语音 | 打断 | AI 立即停止，重新录音 |
| 语音 | 指令确认 | 确认后发送到 Desktop |
| 设备 | 扫码绑定 | 成功绑定，显示在列表 |
| 设备 | 在线状态 | 实时更新，准确反映 |
| 项目 | 切换项目 | Desktop 收到指令并切换 |
| 认证 | 手机号登录 | 验证码接收，登录成功 |
| 认证 | 微信登录 | 授权成功，绑定手机号 |
| 支付 | 订阅购买 | 支付成功，权益到账 |

### 8.3 测试用例示例

```typescript
// 单元测试示例: AuthManager
import { AuthManager } from '@/services/auth/AuthManager';

describe('AuthManager', () => {
  beforeEach(() => {
    AuthManager.clearToken();
  });

  it('should send mobile code successfully', async () => {
    const result = await AuthManager.sendMobileCode('13800138000');
    expect(result.key).toBeDefined();
  });

  it('should login with mobile', async () => {
    const result = await AuthManager.loginWithMobile(
      '13800138000',
      'key123',
      '123456'
    );
    expect(result.token).toBeDefined();
    expect(AuthManager.isLoggedIn()).toBe(true);
  });
});

// 组件测试示例: LoginScreen
describe('LoginScreen', () => {
  it('should show error when mobile is invalid', () => {
    const { getByPlaceholderText, getByText } = render(<LoginScreen />);
    
    fireEvent.changeText(
      getByPlaceholderText('请输入手机号'),
      '123' // 无效手机号
    );
    fireEvent.press(getByText('获取验证码'));
    
    expect(getByText('请输入正确的手机号')).toBeDefined();
  });
});
```

### 8.4 性能测试

| 指标 | 目标 | 测试方法 | 测试环境 |
|------|------|----------|----------|
| 启动时间 | < 2s | 冷启动计时 | iPhone 12, Android 12 |
| 语音延迟 | < 500ms | 说完到首字显示 | 4G 网络 |
| 内存占用 | < 200MB | Xcode Profiler / Android Studio | 30 分钟使用 |
| 帧率 | 60fps | 滚动测试 | 长列表滚动 |
| 包体积 | < 50MB | APK/IPA 分析 | Release 包 |

### 8.5 兼容性测试

| 设备类型 | 系统版本 | 优先级 |
|----------|----------|--------|
| iPhone 15 Pro | iOS 17+ | P0 |
| iPhone 12 | iOS 16+ | P0 |
| iPhone SE | iOS 16+ | P1 |
| Samsung S24 | Android 14+ | P0 |
| Xiaomi 14 | Android 13+ | P0 |
| 低端 Android | Android 10+ | P1 |

---

## 9. 风险评估

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Gateway 协议变更 | 中 | 高 | 提前与后端对齐，预留适配层 |
| ASR 准确率不足 | 中 | 中 | 支持用户编辑转录结果 |
| iOS 审核问题 | 低 | 高 | 遵守录音权限规范，提供说明 |
| 进度延期 | 中 | 中 | 分阶段交付，优先 MVP |
| 微信 SDK 兼容性 | 中 | 高 | 使用 react-native-wechat-lib，关注更新 |
| 音频权限被拒 | 中 | 中 | 友好引导用户开启权限 |
| 支付流程异常 | 低 | 高 | 完善错误处理和退款机制 |

---

## 10. 附录

### 10.1 原移动端功能迁移清单

根据对原 Tauri Web 移动端（`evoloop/frontend/packages/mobile`）的代码分析，以下功能需要在 React Native 重构中迁移或重新设计：

#### 10.1.1 完全保留并复用的功能

| 功能模块 | 原文件位置 | 复用方式 | 优先级 |
|----------|------------|----------|--------|
| **i18n 国际化** | `locales/*.json` | 翻译文件直接复用 | P0 |
| **HTTP API Client** | `client/index.ts` | 接口逻辑保留，适配 RN HTTP 客户端 | P0 |
| **设备服务** | `DevicesService` | API 调用逻辑复用 | P0 |
| **指令服务** | `CommandService` | 复用现有 evolooplink 指令格式 | P0 |
| **项目服务** | `ProjectsService` | API 调用逻辑复用 | P0 |
| **认证服务** | `AuthService` | 登录/注册/验证码逻辑复用 | P0 |
| **日志搜索** | `LogsService.searchLogs` | 搜索历史会话功能复用 | P1 |

#### 10.1.1a 参考实现: uniapp 登录模块

React Native 登录模块参考 `member-center/mobile_uniapp` 实现：

| 文件 | 说明 | RN 对应实现 |
|------|------|-------------|
| `pages_tool/login/index.vue` | 登录入口页 | `app/(auth)/index.tsx` |
| `pages_tool/login/login.vue` | 手机号/账号登录 | `app/(auth)/login.tsx` |
| `components/ns-login/ns-login.vue` | 微信授权登录组件 | `components/WechatAuth.tsx` |
| `common/js/auth.js` | 微信授权逻辑 | `services/WechatAuth.ts` |

**关键登录流程对应**:
1. **登录配置获取** → `AuthManager.getRegisterConfig()`
2. **图形验证码** → `AuthManager.getCaptcha()`
3. **手机验证码** → `AuthManager.sendMobileCode()` (120s 倒计时)
4. **手机号登录** → `AuthManager.loginWithMobile()`
5. **账号密码登录** → `AuthManager.loginWithAccount()`
6. **微信授权登录** → `react-native-wechat-lib` + `AuthManager.loginWithWechat()`
7. **绑定手机号** → `AuthManager.loginWithWechatMobile()`

#### 10.1.1b 参考实现: uniapp 支付模块

React Native 支付模块参考 `member-center/mobile_uniapp` 实现：

| 文件 | 说明 | RN 对应实现 |
|------|------|-------------|
| `components/ns-payment/ns-payment.vue` | 支付组件 | `components/PaymentSheet.tsx` |
| `pages_tool/pay/result.vue` | 支付结果页 | `app/(subscription)/pay-result.tsx` |
| `pages_tool/pay/index.vue` | 支付信息页 | `app/(subscription)/pay-confirm.tsx` |

**关键支付流程对应**:
1. **创建订阅订单** → `SubscriptionService.createOrder(levelId, period)`
2. **获取支付参数** → `PaymentService.getPayParams(outTradeNo, 'wechatpay')`
3. **调起微信 APP 支付** → `react-native-wechat-lib` `WeChat.pay(payData)`
4. **支付回调处理** → `PayResult.success ? 跳转成功页 : 显示错误`
5. **轮询支付状态** → `PaymentService.checkPayStatus(outTradeNo)` (备选)

**支付库选择**:
- 使用 `react-native-wechat-lib` 而非 `react-native-wechat`
- `react-native-wechat-lib` 支持 APP 支付，维护更活跃
- iOS/Android 配置与微信登录共用同一个 AppID

#### 10.1.2 需要重新设计的功能

| 功能模块 | 原实现 | 新设计 | 原因 |
|----------|--------|--------|------|
| **WebSocket 连接** | Cloud + Local 双连接 | 单一 Gateway 连接 | 架构简化，统一协议 |
| **消息归一化** | `normalizeLogMessage` | Gateway 层统一处理 | 后端承担复杂度 |
| **Cloud 模式对话** | 基于 HTTP 轮询 | 全新 ASR 流式对话 | 升级为实时语音 |
| **Local 模式对话** | 直连 Desktop WS | Gateway 代理转发 | 网络穿透问题 |
| **UI 组件** | React + Tailwind | React Native Paper | 原生渲染 |
| **路由导航** | TanStack Router | Expo Router | RN 生态 |
| **状态管理** | Zustand (Web) | Zustand (RN) | 相同库，适配存储层 |
| **手势交互** | Framer Motion (Web) | React Native Gesture Handler | 原生手势 |
| **音频录制** | Web Audio API | expo-av | RN 原生能力 |
| **音频播放** | Web Audio | 原生 PCM 播放器 | 实时流式播放 |

#### 10.1.3 需要新增的功能

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **语音对话 (ASR)** | 按住说话、实时转录 | P0 |
| **流式 LLM 响应** | AI 回复逐字显示 | P0 |
| **指令确认卡片** | 用户确认后再下发 Desktop | P0 |
| **双模式切换** | ASR 模式 ↔ 文本模式切换 | P1 |
| **多轮澄清对话** | AI 主动询问缺失信息 | P1 |
| **语音打断** | 按住打断 AI 播放 | P1 |
| **原生推送通知** | Desktop 指令完成推送 | P2 |
| **扫码绑定优化** | 原生相机体验优化 | P1 |

#### 10.1.4 移除的功能

| 功能 | 原位置 | 移除原因 |
|------|--------|----------|
| **Cloud/Local 双 Tab 切换** | `TabsLayout.tsx` | 架构简化，统一走 Gateway |
| **本地 P2P 连接** | `useEvoLoopWebSocket.ts` | Gateway 代理转发替代直连 |
| **HTTP 轮询日志** | Cloud 模式 | WebSocket 实时推送替代 |
| **Web 手势引导** | `SpotlightTour.tsx` | RN 版本重新设计引导 |

### 10.2 术语表

| 术语 | 说明 |
|------|------|
| ASR | 自动语音识别 |
| VAD | 语音活动检测 |
| Gateway | EvoLoop 统一网关 |
| Desktop | Desktop Agent (Python) |
| LLM | 大语言模型 |
| NLS | 阿里云语音服务 (Natural Language Service) |
| PCM | 脉冲编码调制音频格式 |

### 10.3 项目配置文件

#### 10.3.1 package.json

```json
{
  "name": "evoloop-mobile",
  "version": "1.0.0",
  "main": "expo/AppEntry.js",
  "scripts": {
    "start": "expo start",
    "android": "expo run:android",
    "ios": "expo run:ios",
    "web": "expo start --web",
    "lint": "eslint . --ext .js,.jsx,.ts,.tsx",
    "type-check": "tsc --noEmit",
    "test": "jest",
    "build:android": "eas build --platform android",
    "build:ios": "eas build --platform ios"
  },
  "dependencies": {
    "expo": "~52.0.0",
    "expo-status-bar": "~2.0.0",
    "expo-splash-screen": "~0.29.0",
    "expo-font": "~13.0.0",
    "expo-router": "~4.0.0",
    "expo-camera": "~16.0.0",
    "expo-av": "~14.0.0",
    "expo-file-system": "~18.0.0",
    "expo-linking": "~7.0.0",
    "expo-haptics": "~14.0.0",
    "expo-localization": "~16.0.0",
    "react": "18.3.1",
    "react-native": "0.76.3",
    "react-native-paper": "^5.12.0",
    "react-native-gesture-handler": "~2.20.0",
    "react-native-reanimated": "~3.16.0",
    "react-native-safe-area-context": "4.12.0",
    "react-native-screens": "~4.1.0",
    "react-native-mmkv": "^3.1.0",
    "react-native-wechat-lib": "^1.1.26",
    "@shopify/flash-list": "^1.7.0",
    "zustand": "^5.0.0",
    "axios": "^1.7.0",
    "@react-native-async-storage/async-storage": "1.23.1",
    "date-fns": "^4.0.0",
    "i18next": "^23.0.0",
    "react-i18next": "^15.0.0",
    "eventemitter3": "^5.0.0"
  },
  "devDependencies": {
    "@types/react": "~18.3.0",
    "typescript": "~5.3.0",
    "eslint": "^8.57.0",
    "eslint-config-universe": "^14.0.0",
    "jest": "^29.7.0",
    "jest-expo": "~52.0.0",
    "@testing-library/react-native": "^12.8.0",
    "eas-cli": "^14.0.0"
  },
  "private": true
}
```

**关键依赖说明**:

| 依赖 | 版本 | 用途 |
|------|------|------|
| expo | ~52.0.0 | Expo SDK |
| expo-router | ~4.0.0 | 文件系统路由 |
| expo-av | ~14.0.0 | 音频录制/播放 |
| expo-camera | ~16.0.0 | 扫码功能 |
| react-native-paper | ^5.12.0 | Material Design UI |
| react-native-reanimated | ~3.16.0 | 动画库 |
| react-native-mmkv | ^3.1.0 | 高性能存储 |
| react-native-wechat-lib | ^1.1.26 | 微信登录/支付 |
| @shopify/flash-list | ^1.7.0 | 高性能虚拟列表 |
| @expo/vector-icons | ^14.0.0 | 图标库 (Expo内置) |
| zustand | ^5.0.0 | 状态管理 |
| axios | ^1.7.0 | HTTP 客户端 |

**旧版依赖分析** (`@evoloop/mobile`):

旧版基于 Tauri WebView (React Web)，依赖与 RN 版本差异较大：

| 旧版依赖 | 旧版用途 | RN 替代方案 | 说明 |
|----------|----------|-------------|------|
| `@evoloop/shared` | UI组件/主题/i18n | `react-native-paper` + 自定义 | 需重新实现 |
| `@tanstack/react-query` | 数据获取 | `axios` + `zustand` | 简化方案 |
| `@tanstack/react-router` | 路由 | `expo-router` | RN 专用路由 |
| `virtua` | 虚拟列表 | `@shopify/flash-list` | 高性能列表 |
| `lucide-react` | 图标 | `@expo/vector-icons` | Expo 内置图标库 |
| `zustand` | 状态管理 | `zustand` | ✅ 保持相同 |
| `i18next` | 国际化 | `i18next` + `react-i18next` | ✅ 保持相同 |

**可复用资源**:
- `locales/zh.json`, `locales/en.json` - 翻译文案可直接复用
- `stores/useMobileStore.ts` - 状态管理逻辑参考
- API 接口定义 - 与后端对接的接口保持一致

**不适用于 RN 的依赖**:
- 所有 `@radix-ui/*` 组件 (Web Only)
- `lucide-react` → 使用 `@expo/vector-icons` (Expo 内置图标库)
- `tailwindcss` (使用 React Native Paper 样式方案)
- `framer-motion` (使用 `react-native-reanimated`)

#### 10.3.2 app.json

```json
{
  "expo": {
    "name": "EvoLoop",
    "slug": "evoloop-mobile",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/images/icon.png",
    "scheme": "evoloop",
    "userInterfaceStyle": "automatic",
    "newArchEnabled": true,
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "cn.develop-assistant.evoloop",
      "buildNumber": "1.0.0",
      "infoPlist": {
        "LSApplicationQueriesSchemes": [
          "weixin",
          "weixinULAPI"
        ],
        "CFBundleURLTypes": [
          {
            "CFBundleURLName": "wechat",
            "CFBundleURLSchemes": ["wx[YOUR_APP_ID]"]
          },
          {
            "CFBundleURLName": "evoloop",
            "CFBundleURLSchemes": ["evoloop"]
          }
        ],
        "NSMicrophoneUsageDescription": "EvoLoop 需要使用麦克风进行语音对话",
        "NSCameraUsageDescription": "EvoLoop 需要使用相机扫描二维码绑定设备"
      }
    },
    "android": {
      "package": "cn.develop_assistant.evoloop",
      "versionCode": 1,
      "adaptiveIcon": {
        "foregroundImage": "./assets/images/adaptive-icon.png",
        "backgroundColor": "#0066FF"
      },
      "permissions": [
        "android.permission.RECORD_AUDIO",
        "android.permission.CAMERA"
      ]
    },
    "web": {
      "bundler": "metro",
      "output": "static",
      "favicon": "./assets/images/favicon.png"
    },
    "plugins": [
      "expo-router",
      [
        "expo-splash-screen",
        {
          "image": "./assets/images/splash-icon.png",
          "imageWidth": 200,
          "resizeMode": "contain",
          "backgroundColor": "#0066FF"
        }
      ],
      [
        "expo-av",
        {
          "microphonePermission": "EvoLoop 需要使用麦克风进行语音对话"
        }
      ],
      [
        "expo-camera",
        {
          "cameraPermission": "EvoLoop 需要使用相机扫描二维码绑定设备"
        }
      ]
    ],
    "experiments": {
      "typedRoutes": true
    },
    "extra": {
      "router": {
        "origin": false
      },
      "eas": {
        "projectId": "[YOUR_EAS_PROJECT_ID]"
      }
    }
  }
}
```

#### 10.3.3 tsconfig.json

```json
{
  "extends": "expo/tsconfig.base",
  "compilerOptions": {
    "strict": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"],
      "@/components/*": ["./components/*"],
      "@/services/*": ["./services/*"],
      "@/stores/*": ["./stores/*"],
      "@/types/*": ["./types/*"],
      "@/utils/*": ["./utils/*"],
      "@/constants/*": ["./constants/*"],
      "@/hooks/*": ["./hooks/*"],
      "@/locales/*": ["./locales/*"]
    }
  },
  "include": [
    "**/*.ts",
    "**/*.tsx",
    ".expo/types/**/*.ts",
    "expo-env.d.ts"
  ]
}
```

#### 10.3.4 .env 文件模板

```bash
# API 基础 URL
EXPO_PUBLIC_BASE_URL=https://evoloop.develop-assistant.cn

# 微信配置
EXPO_PUBLIC_WECHAT_APP_ID=wx[YOUR_APP_ID]

# 环境
EXPO_PUBLIC_ENV=development
# EXPO_PUBLIC_ENV=production

# Sentry (错误监控)
EXPO_PUBLIC_SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
```

#### 10.3.5 i18n 配置

```typescript
// locales/index.ts
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import * as Localization from 'expo-localization';

import zh from './zh.json';
import en from './en.json';

const resources = {
  'zh-CN': { translation: zh },
  'zh-TW': { translation: zh }, // 复用简体中文
  'en-US': { translation: en },
  'en': { translation: en },
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: Localization.locale,
    fallbackLng: 'zh-CN',
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
```

**使用方式**:

```typescript
import { useTranslation } from 'react-i18next';

function LoginScreen() {
  const { t, i18n } = useTranslation();
  
  return (
    <View>
      <Text>{t('auth.login.title')}</Text>
      <Text>{t('auth.login.mobilePlaceholder')}</Text>
    </View>
  );
}
```

#### 10.3.6 axios 配置

```typescript
// services/api/client.ts
import axios from 'axios';
import { MMKV } from 'react-native-mmkv';
import { router } from 'expo-router';

const storage = new MMKV();

const apiClient = axios.create({
  baseURL: process.env.EXPO_PUBLIC_BASE_URL,
  timeout: 30000, // 30 秒超时
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    const token = storage.getString('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // URL 前缀处理
    if (config.url?.startsWith('/gateway')) {
      config.baseURL = `${process.env.EXPO_PUBLIC_BASE_URL}/gateway`;
    } else if (config.url?.startsWith('/member')) {
      config.baseURL = `${process.env.EXPO_PUBLIC_BASE_URL}/member`;
    }
    
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      // Token 过期，清除登录状态并跳转登录
      storage.delete('token');
      router.replace('/(auth)/login');
    }
    
    // 统一错误处理
    const message = error.response?.data?.message || '请求失败';
    return Promise.reject(new Error(message));
  }
);

export default apiClient;
```

#### 10.3.8 eas.json (EAS Build 配置)

```json
{
  "cli": {
    "version": ">= 14.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "env": {
        "EXPO_PUBLIC_ENV": "development"
      }
    },
    "development-simulator": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": {
        "simulator": true
      },
      "env": {
        "EXPO_PUBLIC_ENV": "development"
      }
    },
    "preview": {
      "distribution": "internal",
      "android": {
        "buildType": "apk"
      },
      "env": {
        "EXPO_PUBLIC_ENV": "staging"
      }
    },
    "production": {
      "autoIncrement": true,
      "env": {
        "EXPO_PUBLIC_ENV": "production"
      }
    }
  },
  "submit": {
    "production": {
      "ios": {
        "ascAppId": "[YOUR_APPLE_APP_ID]",
        "ascApiKeyPath": "[PATH_TO_API_KEY]",
        "ascApiKeyIssuerId": "[ISSUER_ID]",
        "ascApiKeyId": "[KEY_ID]"
      },
      "android": {
        "serviceAccountKeyPath": "[PATH_TO_SERVICE_ACCOUNT_JSON]",
        "track": "production"
      }
    }
  }
}
```

**构建命令**:

```bash
# 开发构建 (带 DevClient)
eas build --profile development --platform ios
eas build --profile development --platform android

# 预览构建 (内测分发)
eas build --profile preview --platform ios
eas build --profile preview --platform android

# 生产构建 (App Store / Play Store)
eas build --profile production --platform ios
eas build --profile production --platform android

# 提交到商店
eas submit --platform ios
eas submit --platform android
```

### 10.5 微信 SDK 配置

#### 10.5.1 iOS 配置

在 `ios/EvoLoopMobile/Info.plist` 中添加：

```xml
<key>LSApplicationQueriesSchemes</key>
<array>
  <string>weixin</string>
  <string>weixinULAPI</string>
</array>

<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLName</key>
    <string>wechat</string>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>wx[YOUR_APP_ID]</string>
    </array>
  </dict>
</array>
```

#### 10.5.2 Android 配置

在 `android/app/src/main/AndroidManifest.xml` 中添加：

```xml
<queries>
  <package android:name="com.tencent.mm" />
</queries>

<activity
  android:name=".wxapi.WXEntryActivity"
  android:exported="true"
  android:launchMode="singleTask"
  android:taskAffinity="[YOUR_PACKAGE_NAME]"
  android:theme="@android:style/Theme.Translucent.NoTitleBar" />
```

创建 `android/app/src/main/java/com/evoloop/wxapi/WXEntryActivity.java`:

```java
package com.evoloop.wxapi;

import android.app.Activity;
import android.os.Bundle;
import com.theweflex.react.WeChatModule;

public class WXEntryActivity extends Activity {
  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    WeChatModule.handleIntent(getIntent());
    finish();
  }
}
```

### 10.6 安全与隐私

#### 10.6.1 数据安全

| 数据类型 | 存储位置 | 加密方式 | 说明 |
|----------|----------|----------|------|
| Token | MMKV | AES-256 | 用户认证令牌 |
| 用户密码 | 不存储 | - | 仅内存中传输 |
| 聊天记录 | 服务端 | HTTPS/TLS | 不本地持久化 |
| 录音缓存 | 临时目录 | 无 | 会话结束自动清理 |

#### 10.6.2 网络安全

- **HTTPS**: 所有 API 请求强制 HTTPS
- **证书固定**: 可选配置，防止中间人攻击
- **WebSocket WSS**: 加密 WebSocket 连接
- **Token 刷新**: JWT Token 自动刷新机制

#### 10.6.3 隐私合规

- **权限最小化**: 仅申请必要的麦克风、相机权限
- **隐私政策**: 用户注册时必须同意隐私协议
- **数据导出**: 支持用户导出个人数据
- **账号注销**: 提供账号注销功能

### 10.7 错误监控与日志

#### 10.7.1 错误监控 (Sentry)

```typescript
// 集成 Sentry 进行线上错误追踪
import * as Sentry from '@sentry/react-native';

Sentry.init({
  dsn: 'https://xxx@xxx.ingest.sentry.io/xxx',
  environment: __DEV__ ? 'development' : 'production',
  beforeSend: (event) => {
    // 过滤敏感信息
    if (event.exception) {
      // 脱敏处理
    }
    return event;
  },
});
```

**监控范围**:
- JavaScript 运行时错误
- Native 崩溃 (iOS/Android)
- API 请求失败
- WebSocket 异常断开

#### 10.7.2 日志级别

| 级别 | 使用场景 | 是否上报 |
|------|----------|----------|
| DEBUG | 开发调试 | 否 |
| INFO | 关键流程记录 | 否 |
| WARN | 非致命异常 | 是 |
| ERROR | 致命错误 | 是 |

#### 10.7.3 用户反馈

```
┌─────────────────────────────────────────────────────────────┐
│ ←  问题反馈                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  问题类型                                                   │
│  ○ 功能异常  ○ 闪退  ○ 卡顿  ○ 其他                         │
│                                                             │
│  问题描述                                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                                                       │  │
│  │  请详细描述您遇到的问题...                             │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ☑ 上传日志 (帮助我们更快定位问题)                          │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                      提交反馈                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 10.8 推送通知

#### 10.8.1 推送场景

| 场景 | 触发条件 | 通知内容 |
|------|----------|----------|
| 指令完成 | Desktop 执行完成 | "代码分析完成，点击查看结果" |
| 设备离线 | Desktop 断开连接 | "设备已离线，请检查连接" |
| 订阅到期 | 会员即将过期 | "您的会员将在3天后到期" |
| 系统公告 | 运营推送 | 公告内容 |

#### 10.8.2 技术方案

使用 `expo-notifications`:

```typescript
import * as Notifications from 'expo-notifications';

// 请求权限
async function requestPermissions() {
  const { status } = await Notifications.requestPermissionsAsync();
  return status === 'granted';
}

// 本地通知
async function scheduleLocalNotification(title: string, body: string) {
  await Notifications.scheduleNotificationAsync({
    content: { title, body },
    trigger: null, // 立即显示
  });
}

// 远程推送 Token
async function getPushToken() {
  const token = await Notifications.getExpoPushTokenAsync();
  return token.data;
}
```

#### 10.8.3 推送配置

**iOS**: 需要配置 APNs 证书
**Android**: 使用 Firebase Cloud Messaging (FCM)

### 10.9 性能优化策略

#### 10.9.1 启动优化

| 优化项 | 策略 | 目标 |
|--------|------|------|
| 首屏 | 骨架屏占位 | < 1s 可交互 |
| JS Bundle | Hermes 引擎 + 代码分割 | 减少 30% 体积 |
| 图片 | 懒加载 + 压缩 | 按需加载 |

#### 10.9.2 运行优化

```typescript
// 1. 列表虚拟化
import { FlashList } from '@shopify/flash-list';
<FlashList
  data={messages}
  estimatedItemSize={80}
  renderItem={renderItem}
/>

// 2. 组件懒加载
const HeavyComponent = React.lazy(() => import('./HeavyComponent'));

// 3. 图片优化
import { Image } from 'expo-image';
<Image
  source={{ uri }}
  contentFit="cover"
  transition={200}
  cachePolicy="memory-disk"
/>
```

#### 10.9.3 内存管理

- 及时清理 WebSocket 连接
- 录音文件及时释放
- 图片缓存策略 (LRU)
- 页面离开取消未完成的请求

### 10.10 无障碍支持 (Accessibility)

#### 10.10.1 支持范围

- **屏幕阅读器**: 支持 TalkBack (Android) / VoiceOver (iOS)
- **字体缩放**: 适配系统字体大小设置
- **颜色对比**: 符合 WCAG 2.1 AA 标准
- **焦点管理**: 清晰的焦点指示器

#### 10.10.2 实现示例

```typescript
// 添加 accessibility 属性
<Button
  onPress={handlePress}
  accessibilityLabel="发送消息"
  accessibilityHint="双击发送当前输入的内容"
  accessibilityRole="button"
  accessibilityState={{ disabled: isSending }}
>
  发送
</Button>
```

### 10.11 参考文档

- [Expo 文档](https://docs.expo.dev)
- [React Native 文档](https://reactnative.dev)
- [React Native Paper 文档](https://callstack.github.io/react-native-paper/)
- [阿里云 NLS 文档](https://help.aliyun.com/document_detail/84426.html)
- [react-native-wechat-lib](https://github.com/hewigovens/react-native-wechat-lib)
- [Shopify FlashList](https://shopify.github.io/flash-list/)
- [Sentry React Native](https://docs.sentry.io/platforms/react-native/)

---

**文档状态**: 待评审  
**下次评审日期**: 待定  
**文档版本**: v1.0
