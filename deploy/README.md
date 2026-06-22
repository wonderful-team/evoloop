# EvoLoop 部署与打包指南

本目录包含 EvoLoop 项目的构建、部署、打包和发布脚本。

---

## 目录结构

```
deploy/
├── build.sh              # 统一构建入口
├── build/                # 各平台构建脚本
│   ├── common.sh         # 公共函数
│   ├── config.sh         # 构建配置
│   ├── sidecar.sh        # 后端 Sidecar 构建
│   ├── macos-arm64.sh    # macOS Apple Silicon
│   ├── macos-x86_64.sh   # macOS Intel
│   ├── windows-x86_64.sh # Windows
│   ├── mobile.sh         # Android / iOS / HarmonyOS
│   ├── harmony.sh        # HarmonyOS HAP
│   └── web.sh            # Web 前端
├── upload.sh             # 产物上传到服务器
├── update-version.sh     # 全局版本号管理
├── deploy.sh             # 服务端部署脚本
├── dev.sh                # 开发环境启动脚本
├── download_models.sh    # 模型下载
├── generate-client.sh    # OpenAPI 客户端生成
├── mobile-download-sherpa-asr-model.sh
├── mobile-generate-icons.sh
└── nginx/                # Nginx 配置模板
```

---

## 全局版本号

EvoLoop 使用单一版本来源：`evoloop/VERSION`。

```bash
cat /Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/VERSION
# 0.7.0
```

修改版本后，执行同步脚本，自动更新所有平台配置：

```bash
cd /Users/huangjinhuan/Projects/develop-assistant.cn/evoloop
echo "0.7.0" > VERSION
./deploy/update-version.sh 2
```

会同步到：

- `frontend/package.json`
- `frontend/src-tauri/Cargo.toml`
- `frontend/src-tauri/tauri.conf.json`
- `mobile/package.json`
- `mobile/android/app/build.gradle`
- `mobile/ios/EvoLoopMobile.xcodeproj/project.pbxproj`
- `mobile/harmony/AppScope/app.json5`
- `.env.prod.desktop`
- `.env.example`

---

## 环境文件

EvoLoop 使用根目录 `.env` 作为运行时配置。不同场景使用不同的模板文件：

| 模板文件 | 面向平台 | 运行场景 |
|---|---|---|
| `.env.local` | 本地开发 | 本地调试 Desktop / Web / Mobile |
| `.env.prod.desktop` | macOS / Windows 桌面端 | Tauri 桌面客户端生产包 |
| `.env.prod.web.single` | Web 前端 | Linux 单用户 Web 部署 |
| `.env.prod.web.multi` | Web 前端 | Linux 多用户 Web 部署 |

构建时通过 `--env-file` 指定模板，脚本会自动复制为根目录 `.env`。

### 使用示例

```bash
# 桌面端打包
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop

# Android 打包
./deploy/build.sh android --env-file=.env.prod.desktop

# Web 多用户部署
./deploy/build.sh web --env-file=.env.prod.web.multi

# 手动指定（等效于先 cp .env.prod.desktop .env）
cp .env.prod.desktop .env
./deploy/build.sh macos-arm64 --env production
```

---

## 构建

### 交互式构建

```bash
./deploy/build.sh
```

按菜单选择目标、环境、模型、上传等选项。

### 命令行构建

```bash
# macOS Apple Silicon
./deploy/build.sh macos-arm64 --env production

# macOS Intel
./deploy/build.sh macos-x86_64 --env production

# Windows
./deploy/build.sh windows --env production

# Android APK
./deploy/build.sh android --env production

# Android AAB
./deploy/build.sh android --env production --aab

# iOS
./deploy/build.sh ios --env production

# Android + iOS + HarmonyOS
./deploy/build.sh mobile --env production

# HarmonyOS
./deploy/build.sh harmony --env production

# Web 前端
./deploy/build.sh web --env production

# 全部
./deploy/build.sh all --env production
```

### 常用构建选项

| 选项 | 说明 |
|---|---|
| `--env production\|development` | 构建环境 |
| `--env-file FILE` | 指定环境模板文件（会自动复制为 `.env`） |
| `--dev` | 开发模式 |
| `--with-models` | 把模型打包进桌面端 |
| `--download-models [LIST]` | 下载语音模型 |
| `--generate-icons` | 重新生成 App 图标 |
| `--clean` | 清理构建产物 |
| `--help, -h` | 显示帮助 |

---

## 上传

构建完成后产物在 `deploy/dist/` 或各自平台的输出目录。

`upload.sh` **只上传，不构建**。

### 产物上传

```bash
# 上传所有产物
./deploy/upload.sh --all

# 按类型上传
./deploy/upload.sh --desktop
./deploy/upload.sh --android
./deploy/upload.sh --hap
./deploy/upload.sh --ios
./deploy/upload.sh --web

# 组合上传
./deploy/upload.sh --desktop --android --hap

# 测试上传（不执行）
./deploy/upload.sh --all --dry-run
```

### 后端代码上传

```bash
# 上传 backend/app/ 到服务器，覆盖 /www/wwwroot/evoloop/app/
./deploy/upload.sh --backend

# 和后端产物一起上传
./deploy/upload.sh --backend --web
```

### 上传配置

默认配置：

```bash
产物服务器: root@149.88.92.19:40890
产物目录:   /www/wwwroot/member-center/website/bundle/
后端目录:   /www/wwwroot/evoloop/
SSH Key:    ~/.ssh/evoloop_deploy
```

自定义：

```bash
./deploy/upload.sh --all \
  --server root@149.88.92.19 \
  --port 40890 \
  --path /www/wwwroot/member-center/website/bundle/ \
  --backend-path /www/wwwroot/evoloop/
```

---

## 服务端完整部署

如需完整部署后端服务，使用 `deploy/deploy.sh`。它会执行：

- 前端构建并同步到服务器
- 同步整个 `evoloop/` 项目到 `/www/wwwroot/evoloop/`
- 启动 Docker 中间件（postgres / redis / neo4j / meilisearch）
- 安装 Python 依赖（uv sync）
- 执行数据库迁移
- 验证服务连通性

```bash
./deploy/deploy.sh --host=149.88.92.19 --port=40890 --key=~/.ssh/evoloop_deploy --env-file=.env.prod.web.multi
```

如果只想**快速覆盖后端代码**，不重启服务、不安装依赖、不迁移数据库，请用：

```bash
./deploy/upload.sh --backend
```

---

## 完整发版流程

```bash
cd /Users/huangjinhuan/Projects/develop-assistant.cn/evoloop

# 1. 更新版本号
echo "0.7.0" > VERSION
./deploy/update-version.sh 2

# 2. 快速覆盖后端代码（不重启服务）
./deploy/upload.sh --backend

# 3. 构建并上传 macOS Apple Silicon
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop
./deploy/upload.sh --desktop

# 4. 构建并上传 Android
./deploy/build.sh android --env-file=.env.prod.desktop
./deploy/upload.sh --android

# 5. 构建并上传 HarmonyOS HAP
./deploy/build.sh harmony --env-file=.env.prod.desktop
./deploy/upload.sh --hap
```

如果需要完整部署后端服务（含数据库迁移、依赖安装、Docker 中间件启动），在第 2 步替换为：

```bash
./deploy/deploy.sh --host=149.88.92.19 --port=40890 --key=~/.ssh/evoloop_deploy --env-file=.env.prod.web.multi
```

---

## 产物命名规则

从 `VERSION` 文件自动读取：

| 平台 | 产物文件名 |
|---|---|
| macOS Apple Silicon | `EvoLoop_0.7.0_aarch64.dmg` |
| macOS Intel | `EvoLoop_0.7.0_x86_64.dmg` |
| Android APK | `Evoloop_mobile_0.7.0.apk` |
| Android AAB | `Evoloop_mobile_0.7.0.aab` |
| HarmonyOS HAP | `EvoLoop_0.7.0.hap` |
| iOS | `EvoLoopMobile_0.7.0.ipa` |
