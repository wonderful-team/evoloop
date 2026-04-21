# EvoLoop 更新服务

Tauri 前端调用 MC API 进行更新检查的完整解决方案。

## 更新检查时机

### 1. 应用启动时检查 (默认启用)
- **延迟**: 启动后 3 秒
- **目的**: 避免影响应用启动速度
- **条件**: 24 小时内未检查过才执行

### 2. 定时检查 (默认启用)
- **频率**: 每 24 小时一次
- **机制**: 每小时检查一次上次检查时间

### 3. 手动检查
- **位置**: 关于页面
- **触发**: 用户点击 "检查更新" 按钮
- **特点**: 立即执行，无视时间间隔

### 4. 网络恢复检查 (默认启用)
- **触发**: 从离线状态恢复在线
- **延迟**: 网络恢复后 1 秒 (确保网络稳定)

## 使用方法

### 方式一: 使用 UpdateProvider (推荐)

在应用根组件中包裹:

```tsx
import { UpdateProvider } from '@/components/UpdateProvider';

function App() {
  return (
    <UpdateProvider>
      <YourApp />
    </UpdateProvider>
  );
}
```

### 方式二: 手动初始化

```tsx
import { updateService } from '@/services/updateService';

// 应用启动时
updateService.init();

// 应用关闭时
updateService.destroy();
```

### 方式三: 在 Hook 中使用

```tsx
import { useVersion } from '@/hooks/useVersion';

function MyComponent() {
  const { checkForUpdates, updateInfo, isChecking } = useVersion();

  const handleCheck = async () => {
    const result = await checkForUpdates();
    if (result.hasUpdate) {
      console.log('发现新版本:', result.latestVersion);
    }
  };

  return <button onClick={handleCheck}>检查更新</button>;
}
```

## 配置选项

```typescript
import { UpdateProvider } from '@/components/UpdateProvider';

<UpdateProvider
  config={{
    baseUrl: 'https://member.evoloop.cn',      // MC API 地址
    checkInterval: 24 * 60 * 60 * 1000,        // 检查间隔 (24小时)
    startupDelay: 3000,                        // 启动延迟 (3秒)
  }}
>
```

## 更新类型

### 强制更新 (Force Update)
- 显示全屏遮罩，无法关闭
- 必须更新后才能继续使用
- 触发条件: `update_type === 2` 或低于最低兼容版本

### 推荐更新 (Recommended)
- 显示通知卡片，可关闭
- 显示 "立即更新" 和 "稍后提醒" 按钮

### 可选更新 (Optional)
- 静默提示
- 用户可跳过

## API 端点

### 检查更新
```
POST https://member.evoloop.cn/api/evoloop/version/check

Request:
{
  "app_type": "desktop",
  "platform": "windows|macos|linux",
  "version": "1.0.0",
  "build_number": "123",
  "device_id": "evo_xxx",
  "channel": "stable|beta"
}

Response:
{
  "code": 0,
  "data": {
    "has_update": true,
    "version": "1.1.0",
    "download_url": "https://...",
    "release_notes": "...",
    "update_type": 1,  // 0=可选, 1=推荐, 2=强制
    "is_force": false
  }
}
```

### 上报更新状态
```
POST https://member.evoloop.cn/api/evoloop/version/report

Request:
{
  "device_id": "evo_xxx",
  "app_type": "desktop",
  "platform": "windows",
  "from_version": "1.0.0",
  "to_version": "1.1.0",
  "action": "download_start|install_success|install_failed"
}
```

## 数据存储

### LocalStorage Keys
- `evoloop_device_id` - 设备唯一标识
- `evoloop_update_check` - 上次检查记录
  ```json
  {
    "lastCheckTime": 1234567890,
    "lastVersion": "1.0.0",
    "skippedVersion": "1.1.0"
  }
  ```

## 组件说明

### UpdateNotification
显示更新提示的 UI 组件:
- 强制更新: 全屏遮罩
- 普通更新: 右下角通知卡片

### UpdateProvider
上下文提供者，自动管理:
- 初始化更新服务
- 监听更新结果
- 显示更新通知

## 最佳实践

1. **不要在启动时立即检查** - 使用延迟避免影响启动速度
2. **尊重用户选择** - 记录用户跳过的版本
3. **静默失败** - 更新检查失败不打扰用户
4. **网络感知** - 离线时不检查，恢复时补偿
5. **状态上报** - 更新过程中上报状态便于统计

## 文件结构

```
src/
├── components/
│   ├── UpdateNotification.tsx   # 更新提示 UI
│   ├── UpdateProvider.tsx       # 更新上下文
│   └── VersionDisplay.tsx       # 版本显示
├── hooks/
│   └── useVersion.ts            # 版本 Hook
├── services/
│   └── updateService.ts         # 更新服务
└── pages/settings/
    └── AboutPage.tsx            # 关于页面 (手动检查)
```
