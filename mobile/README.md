# EvoLoop Mobile

EvoLoop 移动端 React Native 应用

## 技术栈

- **框架**: React Native + Expo SDK 52
- **导航**: Expo Router v4 (文件系统路由)
- **UI**: React Native Paper v5 (Material Design)
- **状态管理**: Zustand + MMKV 持久化
- **网络**: Axios + WebSocket
- **音频**: expo-av
- **扫码**: expo-camera
- **图标**: @expo/vector-icons

## 项目结构

```
evoloop-mobile/
├── app/                          # Expo Router 文件路由
│   ├── (auth)/                   # 认证路由组
│   ├── (main)/                   # 主应用路由组 (底部 Tab)
│   ├── (subscription)/           # 订阅路由组
│   ├── onboarding/               # 新手引导
│   ├── help/                     # 帮助与反馈
│   ├── settings/                 # 设置页面组
│   └── _layout.tsx               # 根布局
├── components/                   # 组件
│   ├── common/                   # 通用组件 (Header 等)
│   ├── device/                   # 设备相关组件
│   ├── feedback/                 # 反馈组件 (Toast, Snackbar)
│   ├── ui/                       # 基础 UI 组件
│   └── voice/                    # 语音对话组件
├── constants/                    # 常量配置
├── hooks/                        # 自定义 Hooks
├── locales/                      # 国际化
├── services/                     # 服务层
│   ├── api/                      # API 客户端
│   ├── auth/                     # 认证服务
│   ├── devices/                  # 设备管理服务
│   ├── gateway/                  # Gateway WebSocket
│   ├── projects/                 # 项目管理服务
│   ├── voice/                    # 语音服务
│   └── storage/                  # 存储服务
├── stores/                       # 状态管理 (Zustand)
├── theme/                        # 主题配置
├── types/                        # TypeScript 类型
└── utils/                        # 工具函数
```

## 快速开始

### 1. 安装依赖

```bash
cd evoloop/mobile
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入正确的配置
```

### 3. 启动开发服务器

```bash
# iOS
npm run ios

# Android
npm run android
```

## 开发规范

### 文件命名

- 组件: `PascalCase.tsx` (如 `Button.tsx`)
- 页面: `kebab-case.tsx` (如 `forgot-password.tsx`)
- Hooks: `useCamelCase.ts` (如 `useAuth.ts`)
- 工具函数: `camelCase.ts` (如 `formatDate.ts`)

### 代码规范

- 使用 TypeScript 严格模式
- ESLint + Prettier 自动格式化
- 组件使用函数式 + Hooks
- 状态管理使用 Zustand

## 路由说明

| 页面 | 路径 | 说明 |
|------|------|------|
| 登录入口 | `/(auth)/index` | 未登录用户首页 |
| 手机号登录 | `/(auth)/login` | 登录表单 |
| 注册 | `/(auth)/register` | 注册表单 |
| 找回密码 | `/(auth)/forgot-password` | 密码重置 |
| 首页 | `/(main)/index` | 主界面 |
| 语音助手 | `/(main)/voice` | 语音对话页面 |
| 设备列表 | `/(main)/devices` | 设备管理 |
| 项目列表 | `/(main)/projects` | 项目管理 |
| 个人中心 | `/(main)/profile` | 用户信息 |
| 订阅套餐 | `/(subscription)/plans` | 会员订阅 |
| 支付确认 | `/(subscription)/pay-confirm` | 微信支付 |
| 支付结果 | `/(subscription)/pay-result` | 支付状态 |
| 新手引导 | `/onboarding` | 应用介绍引导 |
| 设置主页 | `/settings` | 设置入口 |
| 语音设置 | `/settings/voice` | 语音偏好配置 |
| 账号设置 | `/settings/account` | 账号与安全 |
| 关于 | `/settings/about` | 版本和版权信息 |
| 帮助反馈 | `/help` | FAQ 和反馈 |

## API 配置

- **Gateway API**: `https://evoloop.develop-assistant.cn/gateway`
- **Member API**: `https://evoloop.develop-assistant.cn/member`
- **WebSocket**: `wss://evoloop.develop-assistant.cn/gateway/ws`

## 构建发布

```bash
# iOS 预览构建
eas build --profile preview --platform ios

# Android 预览构建
eas build --profile preview --platform android

# 生产构建
eas build --profile production --platform ios
eas build --profile production --platform android
```

## 功能模块

### Phase 1: 基础设施
- ✅ Expo SDK 52 项目搭建
- ✅ TypeScript + ESLint 配置
- ✅ 主题系统 (light/dark)
- ✅ 国际化 (i18n)
- ✅ 路由导航
- ✅ 基础 UI 组件

### Phase 2: 核心通信
- ✅ HTTP API 客户端 (Axios)
- ✅ WebSocket Gateway 连接
- ✅ 设备管理 (CRUD、绑定)
- ✅ 项目管理 (切换、同步)
- ✅ 认证系统 (登录/注册)

### Phase 3: 语音对话
- ✅ 音频录制 (expo-av)
- ✅ VAD 语音活动检测
- ✅ ASR 语音识别集成
- ✅ 流式 LLM 对话
- ✅ 指令确认机制
- ✅ 消息列表 UI
- ✅ 语音控制按钮

### Phase 4: 设置与优化
- ✅ 设置中心 (语音/账号/关于)
- ✅ 新手引导页面
- ✅ 帮助与反馈
- ✅ Toast/Snackbar 反馈
- ✅ 骨架屏加载
- ✅ 空状态组件
- ✅ 全屏加载器

## 注意事项

1. **微信 SDK**: 需要配置正确的 AppID 才能使用微信登录/支付
2. **音频权限**: iOS 需要在真机测试录音功能
3. **推送通知**: 需要配置 APNs 和 FCM

## 参考文档

- [EvoLoop Mobile PRD](./docs/PRD_Mobile_ReactNative_v1.0.md)
- [实施计划](./docs/IMPLEMENTATION_PLAN.md)
