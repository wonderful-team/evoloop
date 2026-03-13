# EvoLoop 录制功能架构详解

## 概述

EvoLoop 的录制功能采用**双轨架构（Two-Track Architecture）**：

1. **全局事件录制** - 捕获键盘/鼠标操作（通过独立 binary）
2. **屏幕视频录制** - 捕获屏幕视频（通过 ffmpeg）

## 前端架构

### 1. 状态管理 (`recordingStore.ts`)

```typescript
interface RecordingState {
    isRecording: boolean          // 录制中状态
    isGlobalMode: boolean         // 是否全局模式
    activeThreadId: string | null // 关联的对话线程
    eventCount: number            // 事件计数
    sessionId: string | null      // 后端会话ID
    videoPath: string | null      // 视频文件路径
    postRecordingAction: 'synthesize' | null // 录制后操作
}
```

### 2. 录制管理器 (`GlobalRecorderManager.tsx`)

核心组件，协调多个录制源：

```
┌─────────────────────────────────────────────────────────────┐
│                    GlobalRecorderManager                     │
├─────────────────────────────────────────────────────────────┤
│  1. 系统托盘同步 (sync_tray_recording_state)                 │
│  2. 监听托盘事件 (tray-record-toggle)                       │
│  3. 监听看门狗自动停止 (recording-auto-stopped)              │
│  4. 协调三种录制源                                           │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌────────────────┐    ┌────────────────┐
│ useAction     │    │ useGlobal      │    │ Screen Video   │
│ Recorder      │    │ Recorder       │    │ (Tauri invoke) │
│ (DOM事件)      │    │ (全局键盘/鼠标)  │    │ (ffmpeg)       │
└───────────────┘    └────────────────┘    └────────────────┘
```

### 3. 全局录制 Hook (`useGlobalRecorder.ts`)

负责与 Tauri 后端通信：

- **启动**: `invoke("start_global_recording")`
- **停止**: `invoke("stop_global_recording")`
- **事件监听**: `listen<GlobalEvent>("global-event", ...)`
- **自动刷新**: 每2秒批量发送事件到后端

事件流向：
```
recorder binary → stdout → global-event → eventsBuffer → LearningService.recordGlobalEvents()
```

### 4. DOM 录制 Hook (`useActionRecorder.ts`)

捕获前端 DOM 事件，与后端共享同一个 `sessionId`。

## Tauri 后端架构

### 1. 核心文件

| 文件 | 职责 |
|------|------|
| `lib.rs` | 主入口，定义 AppServiceState 和 Tauri 命令 |
| `global_observer.rs` | 管理 recorder binary 进程 |
| `screen_recorder.rs` | 管理 ffmpeg 屏幕录制进程 |
| `bin/recorder.rs` | 独立的键盘/鼠标监听 binary |
| `tray.rs` | 系统托盘管理 |

### 2. AppServiceState

```rust
pub struct AppServiceState {
    // 进程管理
    pub children: Arc<Mutex<Vec<CommandChild>>>,  // sidecar 子进程

    // 系统托盘
    pub tray: Arc<Mutex<Option<TrayIcon>>>,
    pub record_item: Arc<Mutex<Option<MenuItem>>>,
    pub show_item: Arc<Mutex<Option<MenuItem>>>,
    pub quit_item: Arc<Mutex<Option<MenuItem>>>,

    // 全局观察者 (键盘/鼠标)
    pub global_observer: Arc<GlobalObserver>,

    // 屏幕录制 (ffmpeg)
    pub recording_process: Arc<Mutex<Option<std::process::Child>>>,
    pub recording_path: Arc<Mutex<Option<String>>>,
    pub is_blinking: Arc<AtomicBool>,              // 托盘闪烁状态
    pub recording_start_time: Arc<Mutex<Option<Instant>>>, // 计时器
}
```

### 3. 全局事件录制流程

```
前端调用 start_global_recording()
         │
         ▼
┌────────────────────┐
│ global_observer.rs │
│     .start()       │
└────────────────────┘
         │
         ▼
    查找 recorder binary
    (target/debug/recorder 或同目录)
         │
         ▼
┌────────────────────┐     ┌─────────────────────┐
│  spawn recorder    │────▶│   bin/recorder.rs   │
│     process        │     │ (独立监听进程)       │
└────────────────────┘     └─────────────────────┘
                                    │
                                    │ 监听 rdev 事件
                                    ▼
                            输出 JSON 到 stdout
                                    │
                                    ▼
┌────────────────────┐     ┌─────────────────────┐
│  global_observer   │◀────│   stdout reader     │
│  (parse GlobalEvent)│     │   (thread)          │
└────────────────────┘     └─────────────────────┘
         │
         ▼
    emit("global-event", event)
         │
         ▼
    前端 useGlobalRecorder 接收
```

### 4. 屏幕录制流程

```
前端调用 start_screen_recording()
         │
         ▼
┌────────────────────┐
│ screen_recorder.rs │
│   .spawn ffmpeg    │
└────────────────────┘
         │
         ▼
    /usr/local/bin/ffmpeg
    -f avfoundation -i "0"  (主屏幕)
    -c:v libx264
    -preset ultrafast
    ~/.evoloop/recordings/{timestamp}.mp4
         │
         ▼
    返回视频路径给前端
```

### 5. 看门狗机制

屏幕录制有自动保护机制：

```rust
// 10分钟超时 或 500MB 文件大小限制
const MAX_SECS: u64  = 10 * 60;
const MAX_BYTES: u64 = 500 * 1024 * 1024;

// 每30秒检查一次
// 触发时发送 SIGINT 优雅停止 ffmpeg
// 并 emit("recording-auto-stopped", reason)
```

### 6. 系统托盘交互

托盘菜单项：
- **显示主界面** - 唤起应用窗口
- **开始/停止录制** - 切换录制状态
- **退出** - 完全退出应用

托盘特性：
- 录制中图标闪烁（白圈变红）
- 录制中显示计时器（停止录制 (MM:SS)）
- 支持全局快捷键 ⌘R

## 数据流总结

```
┌────────────────────────────────────────────────────────────────┐
│                         录制启动时                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   前端: GlobalRecorderManager.manageRecording()                 │
│       ├── useActionRecorder.startRecording() ──▶ 后端创建 Session│
│       ├── useGlobalRecorder.startRecording() ──▶ Tauri 启动 recorder│
│       └── invoke("start_screen_recording") ────▶ Tauri 启动 ffmpeg│
│                                                                │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                         录制进行中                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   DOM 事件 ──▶ useActionRecorder ──▶ 批量发送到后端              │
│                                                                │
│   全局事件 ──▶ recorder binary ──▶ stdout ──▶ global-event     │
│                ──▶ useGlobalRecorder ──▶ 批量发送到后端          │
│                                                                │
│   屏幕视频 ──▶ ffmpeg ──▶ ~/.evoloop/recordings/xxx.mp4         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                         录制停止时                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   前端: stopRecording()                                         │
│       ├── useGlobalRecorder.stopRecording() ──▶ 最终刷新事件    │
│       ├── useActionRecorder.stopRecording() ──▶ 最终刷新事件    │
│       └── invoke("stop_screen_recording") ────▶ SIGINT ffmpeg   │
│                                                                │
│   然后: LearningService.extractKeyframes()                      │
│         (从视频中提取关键帧，与事件对齐)                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## 常见问题排查

### recorder binary 找不到

错误：`Could not find recorder binary`

解决：
```bash
cd frontend/src-tauri
cargo build --bin recorder
```

### 屏幕录制权限被拒绝

检查：
```bash
# macOS 屏幕录制权限
/usr/sbin/screencapture -x -R0,0,1,1 /tmp/test.png
# 如果失败，需要在 系统设置 > 隐私与安全 > 屏幕录制 中授权
```

### 全局事件不生效

检查：
```bash
# macOS 辅助功能权限
# 需要在 系统设置 > 隐私与安全 > 辅助功能 中授权
```

## 配置项

### Cargo.toml

```toml
[[bin]]
name = "recorder"
path = "src/bin/recorder.rs"
```

### tauri.conf.json

不需要配置 recorder（不是通过 externalBin 打包）

## 开发调试

启动 recorder 独立测试：
```bash
cd frontend/src-tauri
cargo run --bin recorder
# 然后点击鼠标或按键盘，应该输出 JSON 事件
```
