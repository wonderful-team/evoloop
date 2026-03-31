# EvoLoop 版本管理指南

## 概述

EvoLoop 采用统一的版本管理机制，确保桌面端、前端和 Agent 端的版本一致性。

## 版本号格式

遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/) 规范：

```
主版本号.次版本号.修订号
```

- **主版本号**: 不兼容的 API 修改
- **次版本号**: 向下兼容的功能新增
- **修订号**: 向下兼容的问题修正

示例: `1.2.3`

## 版本阶段

| 阶段 | 说明 | 颜色标识 |
|------|------|----------|
| alpha | 内测版本，可能包含严重问题 | 🟠 橙色 |
| beta | 公测版本，功能基本稳定 | 🔵 蓝色 |
| rc | 发布候选版本，准备正式发布 | 🟣 紫色 |
| stable | 正式稳定版本 | 🟢 绿色 |

## 快速开始

### 1. 初始化版本

运行版本更新脚本：

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop
./scripts/update-version.sh 0.1.0
```

### 2. 更新版本

```bash
# 更新到 1.2.3，构建号为 45
./scripts/update-version.sh 1.2.3 45
```

脚本会自动更新以下文件：
- `.env` - 环境变量
- `frontend/package.json` - NPM 包版本
- `frontend/src-tauri/Cargo.toml` - Rust 版本
- `frontend/src-tauri/tauri.conf.json` - Tauri 配置
- `frontend/src/version.json` - 前端版本信息
- `frontend/src-tauri/src/version.rs` - Rust 版本常量

### 3. 在代码中使用版本信息

#### 前端 (React)

```tsx
import { VersionDisplay } from '@/components/VersionDisplay';
import { useVersion } from '@/hooks/useVersion';

// 简单显示版本号
<VersionDisplay variant="minimal" />
// 输出: v0.1.0

// 详细版本信息
<VersionDisplay variant="detailed" />
// 显示版本号、构建号、Git Commit、构建时间

// 徽章样式
<VersionDisplay variant="badge" />
// 显示: [v0.1.0] [alpha]

// 使用 Hook
function MyComponent() {
  const { version, versionString, checkForUpdates } = useVersion();
  
  return (
    <div>
      <p>当前版本: {versionString}</p>
      <button onClick={checkForUpdates}>检查更新</button>
    </div>
  );
}
```

#### Rust (Tauri)

```rust
use crate::version::{VERSION, FULL_VERSION, VersionInfo};

// 获取版本字符串
println!("版本: {}", VERSION); // "0.1.0"
println!("完整版本: {}", FULL_VERSION); // "0.1.0+1 (abc1234)"

// 获取版本信息结构体
let info = VersionInfo::new();
println!("{:?}", info);
```

#### 通过 Tauri Command

```typescript
import { invoke } from '@tauri-apps/api/core';

// 获取版本信息
const versionInfo = await invoke('get_version_info');
// {
//   version: "0.1.0",
//   build_number: "1",
//   build_time: "20240115120000",
//   git_commit: "abc1234",
//   stage: "alpha",
//   full_version: "0.1.0+1 (abc1234)"
// }

// 获取版本号
const version = await invoke('get_version'); // "0.1.0"

// 检查是否需要更新
const needsUpdate = await invoke('needs_update', {
  current: '1.0.0',
  latest: '1.1.0'
}); // true
```

## 环境变量配置

在 `.env` 文件中配置版本信息：

```env
# 应用版本号
APP_VERSION=0.1.0

# 构建号
BUILD_NUMBER=1

# 版本阶段: alpha|beta|rc|stable
RELEASE_STAGE=alpha

# 构建时间 (CI自动填充)
BUILD_TIME=20240115120000

# Git Commit (CI自动填充)
GIT_COMMIT=abc1234567890
```

## CI/CD 集成

### GitHub Actions 示例

```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - name: Setup Rust
        uses: dtolnay/rust-action@stable
      
      - name: Update Version
        run: |
          VERSION=${GITHUB_REF#refs/tags/v}
          BUILD_NUMBER=${GITHUB_RUN_NUMBER}
          ./scripts/update-version.sh $VERSION $BUILD_NUMBER
        env:
          BUILD_TIME: ${{ github.run_id }}
          GIT_COMMIT: ${{ github.sha }}
      
      - name: Build Frontend
        run: |
          cd frontend
          npm install
          npm run build
      
      - name: Build Tauri
        run: |
          cd frontend
          npm run tauri build
```

## 关于页面

已提供完整的关于页面组件：

```tsx
import { AboutPage } from '@/pages/settings/AboutPage';

// 在路由中使用
<Route path="/settings/about" component={AboutPage} />
```

关于页面包含：
- ✅ 版本信息展示
- ✅ 一键复制版本号
- ✅ 检查更新按钮
- ✅ 外部链接 (官网、文档、GitHub)
- ✅ 法律信息 (用户协议、隐私政策)
- ✅ 版本详情对话框

## 最佳实践

### 1. 版本号管理

- 功能开发时保持 `alpha` 阶段
- 内部测试完成后进入 `beta` 阶段
- 发布前一周进入 `rc` 阶段
- 正式发布时使用 `stable` 阶段

### 2. 构建号规则

- 每次 CI 构建时递增
- 用于区分同一版本的不同构建
- 便于追踪问题来源

### 3. Git Commit

- 自动从 Git 获取
- 用于精确定位代码版本
- 便于调试和问题追踪

### 4. 更新策略

- **可选更新**: 用户可以选择跳过
- **推荐更新**: 显示提示但不强制
- **强制更新**: 用户必须更新才能继续使用

## 文件结构

```
evoloop/
├── .env                          # 环境变量 (包含版本信息)
├── .env.example                  # 环境变量模板
├── scripts/
│   └── update-version.sh         # 版本更新脚本
├── frontend/
│   ├── package.json              # NPM 版本
│   ├── src/
│   │   ├── version.json          # 前端版本信息
│   │   ├── components/
│   │   │   └── VersionDisplay.tsx    # 版本显示组件
│   │   ├── hooks/
│   │   │   └── useVersion.ts         # 版本管理 Hook
│   │   └── pages/
│   │       └── settings/
│   │           └── AboutPage.tsx     # 关于页面
│   └── src-tauri/
│       ├── Cargo.toml            # Rust 版本
│       ├── tauri.conf.json       # Tauri 配置
│       └── src/
│           ├── lib.rs            # 主库 (注册版本命令)
│           └── version.rs        # 版本模块
```

## 故障排除

### 版本号不更新

1. 检查 `.env` 文件是否正确配置
2. 运行 `./scripts/update-version.sh` 更新所有文件
3. 重新编译前端和 Rust 代码

### 版本显示不一致

1. 确认 `frontend/src/version.json` 已更新
2. 确认 `frontend/src-tauri/src/version.rs` 已更新
3. 重新构建 Tauri 应用

### CI 构建版本不对

1. 检查 CI 脚本是否正确调用 `update-version.sh`
2. 检查环境变量是否正确传递
3. 检查 Git 标签格式是否正确 (`v1.2.3`)

## 相关文档

- [语义化版本规范](https://semver.org/lang/zh-CN/)
- [Tauri 文档](https://tauri.app/v1/guides/)
- [EvoLoop 版本更新机制设计](./VERSION_UPDATE_DESIGN.md)
