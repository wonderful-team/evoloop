# 分层截图存储系统 (Hierarchical Screenshot Storage)

## 概述

系统实现了统一的截图分层存储方案，根据截图的用途将其分类存储到不同的目录中，并应用不同的保留策略。

## 存储分类

### 1. Temp (临时)
- **路径**: `~/.evoloop/artifacts/screenshots/temp/`
- **用途**: 即时 OCR、临时处理、中间结果
- **保留期**: 1 天
- **组织方式**: 按日期 `YYYYMM/DD/`

### 2. Atlas (知识图谱)
- **路径**: `~/.evoloop/artifacts/screenshots/atlas/`
- **用途**: App Atlas 学习、知识图谱构建
- **保留期**: 90 天
- **组织方式**: 按应用 `bundle_id/YYYYMM/DD/`

### 3. Debug (调试)
- **路径**: `~/.evoloop/artifacts/screenshots/debug/`
- **用途**: 故障排查、错误分析
- **保留期**: 7 天
- **组织方式**: 按日期 `YYYYMM/DD/`

### 4. Dataset (数据集)
- **路径**: `~/.evoloop/artifacts/screenshots/dataset/`
- **用途**: IL (Imitation Learning) 训练数据
- **保留期**: 365 天
- **组织方式**: 按日期 `YYYYMM/DD/`

## 文件命名规范

```
{platform}_{timestamp}_{bundle_id}_{suffix}.png

示例:
- android_20260228_143052_123.png
- macos_20260228_143052_456.png
- browser_20260228_143052_789.png
```

## 配置选项

在 `backend/app/core/config.py` 中：

```python
# 保留期设置（天）
SCREENSHOT_TEMP_RETENTION_DAYS = 1
SCREENSHOT_DEBUG_RETENTION_DAYS = 7
SCREENSHOT_ATLAS_RETENTION_DAYS = 90
SCREENSHOT_DATASET_RETENTION_DAYS = 365
```

## 使用方法

### 1. 使用存储管理器

```python
from app.core.vision.storage import screenshot_storage, ScreenshotPurpose

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

# 复制到另一分类
new_path = screenshot_storage.copy_to_purpose(
    source_path="/tmp/temp.png",
    purpose="atlas",
    bundle_id="com.example.app"
)
```

### 2. 驱动层使用

#### Android (ADB)
```python
from app.infrastructure.drivers.adb import adb_driver

# 临时截图（默认）
path = adb_driver.screenshot(device_id="xxx")

# Atlas 学习截图
path = adb_driver.screenshot(
    device_id="xxx",
    purpose="atlas",
    bundle_id="com.example.app"
)
```

#### macOS
```python
from app.infrastructure.drivers.macos import macos_driver

# Debug 截图（默认）
path = macos_driver.screenshot()

# 指定用途
path = macos_driver.screenshot(
    purpose="dataset",
    bundle_id="com.apple.Safari"
)
```

### 3. 清理过期截图

```python
from app.core.vision.cleanup import cleanup_screenshots

# 预览清理
stats = cleanup_screenshots(dry_run=True)

# 实际清理
stats = cleanup_screenshots(dry_run=False)
```

## CLI 工具

```bash
# 查看配置
cd backend
python scripts/manage_screenshots.py config

# 查看统计
python scripts/manage_screenshots.py stats

# 预览清理
python scripts/manage_screenshots.py cleanup --dry-run

# 执行清理
python scripts/manage_screenshots.py cleanup

# 测试存储
python scripts/manage_screenshots.py test
```

## 与旧系统的区别

| 方面 | 旧系统 | 新系统 |
|------|--------|--------|
| macOS 截图 | `~/.evoloop/artifacts/screenshots/` | `~/.evoloop/artifacts/screenshots/debug/` |
| Android 截图 | `/tmp/` | `~/.evoloop/artifacts/screenshots/temp/` |
| 浏览器截图 | `/tmp/evoloop/` | `~/.evoloop/artifacts/screenshots/temp/` |
| 组织方式 | 平铺 | 按用途 + 日期分层 |
| 自动清理 | 无 | 有（按保留期） |
| Atlas 截图 | 分散 | 统一组织在 `atlas/` |

## 最佳实践

1. **临时操作** → 使用 `temp`，用完即走
2. **Atlas 学习** → 使用 `atlas`，确保传递 `bundle_id`
3. **调试问题** → 使用 `debug`，便于事后分析
4. **收集训练数据** → 使用 `dataset`，长期保留

## Celery 定时清理

可以在 Celery 配置中添加定时任务：

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "cleanup-screenshots": {
        "task": "app.core.vision.cleanup_screenshots",
        "schedule": crontab(hour=2, minute=0),  # 每天凌晨 2 点
        "args": (False,),  # dry_run=False
    },
}
```
