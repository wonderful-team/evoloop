# 统一分层存储系统 (Unified Hierarchical Storage System)

## 概述

系统实现了统一的分层存储方案，管理所有视觉相关数据（截图和屏幕录制），根据数据用途和生命周期进行分类存储。

## 存储分类

### 一、截图存储 (Screenshots)

#### 1. Temp (临时)
- **路径**: `~/.evoloop/artifacts/screenshots/temp/`
- **用途**: 即时 OCR、临时处理、中间结果
- **保留期**: 1 天
- **组织方式**: 按日期 `YYYYMMDD/`

#### 2. Atlas (知识图谱)
- **路径**: `~/.evoloop/artifacts/screenshots/atlas/`
- **用途**: App Atlas 学习、知识图谱构建
- **保留期**: 90 天
- **组织方式**: 按应用 `bundle_id/YYYYMMDD/`

#### 3. Debug (调试)
- **路径**: `~/.evoloop/artifacts/screenshots/debug/`
- **用途**: 故障排查、错误分析
- **保留期**: 7 天
- **组织方式**: 按日期 `YYYYMMDD/`

#### 4. Dataset (数据集)
- **路径**: `~/.evoloop/artifacts/screenshots/dataset/`
- **用途**: IL (Imitation Learning) 训练数据、人工录制截图
- **保留期**: 365 天
- **组织方式**: 按日期 `YYYYMMDD/` 或按 session `session_id/`

### 二、屏幕录制存储 (Screen Recordings)

#### 1. Videos (视频)
- **路径**: `~/.evoloop/artifacts/recordings/YYYYMMDD/`
- **用途**: 屏幕录制视频文件 (.mp4)
- **保留期**: 30 天
- **文件命名**: `recording_{session_id}_{timestamp}.mp4`
- **限制**:
  - 单次最大时长: 10 分钟
  - 单次最大文件: 500 MB
  - 总容量限制: 10 GB

#### 2. Frames (帧)
- **路径**: `~/.evoloop/artifacts/recordings/frames/{session_id}/`
- **用途**: 从视频中提取的关键帧
- **保留期**: 30 天（与视频同步）
- **文件命名**: `frame_{timestamp_ms}.png`

## 完整目录结构

```
~/.evoloop/
├── artifacts/
│   ├── screenshots/
│   │   ├── temp/              # 临时截图
│   │   │   └── 20260228/
│   │   ├── atlas/             # Atlas 学习
│   │   │   └── com_example_app/
│   │   │       └── 20260228/
│   │   ├── debug/             # 调试截图
│   │   │   └── 20260228/
│   │   └── dataset/           # IL 训练数据
│   │       └── 20260228/
│   │           └── macos_20260228_143052_123_event_0.png
│   │
│   ├── recordings/            # 屏幕录制
│   │   ├── 20260228/
│   │   │   └── recording_xxx_1709123456789.mp4
│   │   └── frames/            # 提取的帧
│   │       └── session_xxx/
│   │           ├── frame_0.png
│   │           ├── frame_1500.png
│   │           └── frame_3200.png
│   │
│   └── browser/               # 浏览器 artifacts
│
└── library/                   # 知识库
```

## 配置项

### 截图配置
```python
# 保留期（天）
SCREENSHOT_TEMP_RETENTION_DAYS = 1
SCREENSHOT_DEBUG_RETENTION_DAYS = 7
SCREENSHOT_ATLAS_RETENTION_DAYS = 90
SCREENSHOT_DATASET_RETENTION_DAYS = 365

# 路径
SCREENSHOTS_TEMP_DIR = "~/.evoloop/artifacts/screenshots/temp"
SCREENSHOTS_ATLAS_DIR = "~/.evoloop/artifacts/screenshots/atlas"
SCREENSHOTS_DEBUG_DIR = "~/.evoloop/artifacts/screenshots/debug"
SCREENSHOTS_DATASET_DIR = "~/.evoloop/artifacts/screenshots/dataset"
```

### 屏幕录制配置
```python
# 路径
SCREEN_RECORDINGS_DIR = "~/.evoloop/artifacts/recordings"
SCREEN_RECORDING_FRAMES_DIR = "~/.evoloop/artifacts/recordings/frames"

# 保留期和限制
SCREEN_RECORDING_RETENTION_DAYS = 30
SCREEN_RECORDING_MAX_SIZE_GB = 10
SCREEN_RECORDING_MAX_DURATION_MIN = 10
SCREEN_RECORDING_MAX_SIZE_MB = 500
```

## 使用方法

### 1. 截图存储

```python
from app.core.vision.storage import screenshot_storage, get_screenshot_path

# 获取存储路径
path = screenshot_storage.get_path(
    purpose="atlas",
    platform="android",
    bundle_id="com.example.app",
    suffix="login_screen"
)

# 保存截图
filepath = screenshot_storage.save_screenshot(
    image_data=png_bytes,
    purpose="debug",
    platform="macos"
)
```

### 2. 屏幕录制存储

```python
from app.core.vision.storage import screen_recording_storage, get_recording_path

# 获取录制路径
video_path = screen_recording_storage.get_recording_path(
    session_id="session_xxx",
    timestamp=1709123456789
)

# 获取帧路径
frame_path = screen_recording_storage.get_frame_path(
    session_id="session_xxx",
    timestamp_ms=1500
)

# 获取帧目录
frames_dir = screen_recording_storage.get_frames_dir(session_id="session_xxx")
```

### 3. 帧提取

```python
from app.core.learning.frame_extractor import FrameExtractor

# 创建提取器（使用分层存储）
extractor = FrameExtractor(video_path, session_id="session_xxx")
frames = extractor.extract_frames([0, 1500, 3200])

# 结果将保存在 ~/.evoloop/artifacts/recordings/frames/session_xxx/
```

### 4. 清理过期数据

```python
from app.core.vision.cleanup import (
    cleanup_screenshots,
    cleanup_screen_recordings,
    cleanup_all
)

# 清理过期截图
stats = cleanup_screenshots(dry_run=False)

# 清理过期录制
stats = cleanup_screen_recordings(dry_run=False)

# 清理所有
stats = cleanup_all(dry_run=False)
```

## CLI 工具

```bash
# 查看所有配置
cd backend
python scripts/manage_screenshots.py config

# 查看所有统计
python scripts/manage_screenshots.py stats

# 查看截图统计
python scripts/manage_screenshots.py stats --screenshots

# 查看录制统计
python scripts/manage_screenshots.py stats --recordings

# 预览清理
python scripts/manage_screenshots.py cleanup --dry-run

# 执行清理
python scripts/manage_screenshots.py cleanup

# 仅清理截图
python scripts/manage_screenshots.py cleanup --screenshots

# 仅清理录制
python scripts/manage_screenshots.py cleanup --recordings

# 测试存储功能
python scripts/manage_screenshots.py test
```

## Celery 定时任务

清理任务已配置在 `app/celery_app.py` 中，会自动运行：

```python
from celery.schedules import crontab

celery_app.conf.update(
    beat_schedule={
        # 每 24 小时清理一次过期截图
        "cleanup-screenshots-daily": {
            "task": "app.core.vision.cleanup_screenshots",
            "schedule": 86400.0,  # 24 hours
            "args": (False,),     # dry_run=False
        },
        # 每 24 小时清理一次过期录制
        "cleanup-screen-recordings-daily": {
            "task": "app.core.vision.cleanup_screen_recordings",
            "schedule": 86400.0,  # 24 hours
            "args": (False,),     # dry_run=False
        },
    },
)
```

### 启动 Celery Beat

要启用定时清理，需要启动 Celery Beat 调度器：

```bash
cd backend

# 启动 Celery Worker
celery -A app.celery_app worker --loglevel=info

# 启动 Celery Beat（定时任务调度器）
celery -A app.celery_app beat --loglevel=info

# 或者同时启动 Worker 和 Beat（仅适用于开发环境）
celery -A app.celery_app worker --beat --loglevel=info
```

## 与旧系统的对比

| 场景 | 旧路径 | 新路径 |
|------|--------|--------|
| macOS 截图 | `~/.evoloop/artifacts/screenshots/` | `~/.evoloop/artifacts/screenshots/debug/` |
| Android 截图 | `/tmp/` | `~/.evoloop/artifacts/screenshots/temp/` |
| 浏览器截图 | `/tmp/evoloop/` | `~/.evoloop/artifacts/screenshots/temp/` |
| Atlas 截图 | 分散 | `~/.evoloop/artifacts/screenshots/atlas/` |
| 屏幕录制 | `~/.evoloop/recordings/` | `~/.evoloop/artifacts/recordings/` |
| 帧提取 | `{video}_frames/` | `~/.evoloop/artifacts/recordings/frames/{session}/` |
| 前端录制截图 | `settings.SCREENSHOTS_DIR` | `~/.evoloop/artifacts/screenshots/dataset/` |

## 关键改进

1. **统一入口**: 所有视觉数据通过 `storage.py` 管理
2. **自动清理**: 基于保留期自动清理过期数据
3. **容量限制**: 屏幕录制有总容量限制检查
4. **分层组织**: 按用途、日期、session 分层
5. **向后兼容**: 旧代码仍可通过 legacy 路径访问
