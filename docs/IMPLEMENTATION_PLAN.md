# EvoLoop Mobile React Native 重构实施计划

**版本**: v1.0  
**日期**: 2026-04-06  
**状态**: 待评审  

---

## 1. 项目概述

### 1.1 项目目标
将 EvoLoop 移动端从 Tauri Web 架构重构为 React Native 原生架构，实现原生级手势体验、实时语音对话和完整的设备管理能力。

### 1.2 项目范围
- **核心功能**: 语音对话（ASR）、设备管理、项目管理
- **用户系统**: 登录/注册、会员订阅、支付
- **平台**: iOS + Android

### 1.3 项目周期
**预计工期**: 9 周（2 个月 + 1 周缓冲）  
**团队规模**: 2-3 名 React Native 开发工程师  
**启动日期**: 待定

---

## 2. 团队配置

### 2.1 角色分工

| 角色 | 人数 | 职责 | 技能要求 |
|------|------|------|----------|
| **技术负责人** | 1 | 架构设计、代码审查、技术决策 | 5+ 年 RN 经验，熟悉 Expo |
| **RN 开发工程师** | 2 | 功能开发、单元测试 | 2+ 年 RN 经验 |
| **后端对接人** | 0.5 | Gateway API 对接支持 | 熟悉 Go Gateway 协议 |
| **UI/UX 设计师** | 0.3 | 设计稿确认、交互优化 | 熟悉移动端设计规范 |
| **测试工程师** | 0.5 | 测试用例、真机测试 | 熟悉 iOS/Android 测试 |

### 2.2 开发环境

```bash
# 必需工具
- Node.js 18+
- npm 9+ 或 yarn 1.22+
- Expo CLI / EAS CLI
- Xcode 15+ (iOS)
- Android Studio Hedgehog+ (Android)
- Git

# 推荐工具
- VS Code + 推荐插件
- Flipper (调试)
- React Native Debugger
- Postman / Insomnia (API 测试)
```

---

## 3. 阶段划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         实施计划甘特图                                   │
├─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬──┤
│  Week 1 │  Week 2 │  Week 3 │  Week 4 │  Week 5 │  Week 6 │  Week 7 │..│
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│ [  M1   ]│         │         │         │         │         │         │  │
│ 基础设施 │         │         │         │         │         │         │  │
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│         │         │ [  M2   ]│         │         │         │         │  │
│         │         │ 核心通信 │         │         │         │         │  │
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│         │         │         │         │ [  M3   ]│         │         │  │
│         │         │         │         │ 语音对话 │         │         │  │
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│         │         │         │         │         │         │ [  M4   ]│  │
│         │         │         │         │         │         │ 设备/项目│  │
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│         │         │         │         │         │         │         │[M│
│         │         │         │         │         │         │         │5]│
│         │         │         │         │         │         │         │认证│
├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼──┤
│         │         │         │         │         │         │         │[M│
│         │         │         │         │         │         │         │6]│
│         │         │         │         │         │         │         │优化│
└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴──┘
```

---

## 4. 详细实施计划

### Phase 1: 基础设施 (Week 1-2)

**目标**: 搭建可运行的项目骨架，建立开发规范

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 1-2** | | | | |
| 1.1 | Expo Bare 项目初始化 | `evoloop-mobile/` 项目 | RN Dev 1 | `npx create-expo-app --template bare` |
| 1.2 | Git 仓库设置 + CI/CD 配置 | `.github/workflows/` | Tech Lead | EAS Build 自动化 |
| 1.3 | 目录结构创建 | 完整目录树 | RN Dev 1 | 按 PRD 3.3 章节 |
| **Day 3-4** | | | | |
| 1.4 | 安装核心依赖 | `package.json` 完整 | RN Dev 1 | Expo SDK 52 全套 |
| 1.5 | 配置路径别名 | `tsconfig.json` paths | RN Dev 1 | `@/*` 映射 |
| 1.6 | React Native Paper 配置 | 主题配置文件 | RN Dev 2 | 浅色/深色主题 |
| **Day 5-7** | | | | |
| 1.7 | Expo Router 配置 | 基础路由结构 | RN Dev 2 | `(auth)` `(main)` 路由组 |
| 1.8 | 基础布局组件 | `TabLayout.tsx` | RN Dev 2 | 底部导航栏 |
| 1.9 | 错误边界实现 | `ErrorBoundary.tsx` | RN Dev 1 | 全局错误捕获 |
| **Day 8-10** | | | | |
| 2.1 | 网络状态监听 | `useNetworkStatus.ts` | RN Dev 1 | 断网提示 |
| 2.2 | 全局加载状态 | `LoadingProvider.tsx` | RN Dev 2 | 骨架屏组件 |
| 2.3 | 基础 UI 组件 | `Button.tsx` `Input.tsx` | RN Dev 2 | React Native Paper 封装 |
| 2.4 | 国际化配置 | `i18n/index.ts` | RN Dev 1 | 复用 locales 文件 |

**里程碑 M1 验收标准**:
- [ ] 项目在 iOS Simulator 可运行
- [ ] 项目在 Android Emulator 可运行
- [ ] 路由导航正常 (登录 ↔ 首页)
- [ ] 主题切换正常 (浅色/深色)
- [ ] 代码规范 ESLint/Prettier 配置完成

---

### Phase 2: 核心通信 (Week 3-4)

**目标**: 建立与 Gateway 的 WebSocket 通信能力

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 11-13** | | | | |
| 2.5 | axios 客户端配置 | `services/api/client.ts` | RN Dev 1 | 拦截器、错误处理 |
| 2.6 | API 端点定义 | `constants/api.ts` | RN Dev 1 | Gateway + Member API |
| 2.7 | 类型定义完善 | `types/*.ts` | RN Dev 1 | API 请求/响应类型 |
| **Day 14-17** | | | | |
| 2.8 | GatewayClient 实现 | `services/gateway/GatewayClient.ts` | Tech Lead | WebSocket 连接管理 |
| 2.9 | 消息协议实现 | `services/gateway/types.ts` | RN Dev 2 | 消息类型定义 |
| 2.10 | 心跳/重连机制 | `GatewayClient.reconnect()` | RN Dev 2 | 断线自动重连 |
| **Day 18-20** | | | | |
| 2.11 | Zustand Store 实现 | `stores/voiceStore.ts` | RN Dev 1 | 状态管理 |
| 2.12 | Hook 封装 | `useGateway.ts` | RN Dev 1 | 组件层使用 |
| 2.13 | 连接状态 UI | `ConnectionStatus.tsx` | RN Dev 2 | 在线/离线指示器 |

**里程碑 M2 验收标准**:
- [ ] WebSocket 连接 Gateway 成功
- [ ] 心跳保活机制正常
- [ ] 断网自动重连正常
- [ ] 消息收发测试通过

---

### Phase 3: 语音对话 (Week 5-6)

**目标**: 实现 ASR 语音对话核心功能

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 21-24** | | | | |
| 3.1 | AudioRecorder 实现 | `services/voice/AudioRecorder.ts` | RN Dev 1 | expo-av 录音 |
| 3.2 | 录音权限处理 | `useAudioPermission.ts` | RN Dev 2 | iOS/Android 权限 |
| 3.3 | 音频数据处理 | PCM/AMR 格式转换 | Tech Lead | Gateway 协议对齐 |
| **Day 25-28** | | | | |
| 3.4 | VAD 检测 | `services/voice/VADDetector.ts` | RN Dev 1 | 简单能量检测 |
| 3.5 | VoiceSessionManager | `services/voice/VoiceSessionManager.ts` | Tech Lead | 会话生命周期管理 |
| 3.6 | 语音按钮组件 | `VoiceRecorder.tsx` | RN Dev 2 | 按住说话 UI |
| **Day 29-32** | | | | |
| 3.7 | 消息列表组件 | `MessageList.tsx` | RN Dev 2 | FlashList 虚拟化 |
| 3.8 | 消息项组件 | `MessageItem.tsx` | RN Dev 2 | 用户/AI 消息样式 |
| 3.9 | 指令确认卡片 | `CommandCard.tsx` | RN Dev 1 | 确认/编辑 UI |
| **Day 33-35** | | | | |
| 3.10 | 打断机制实现 | `interruptChat()` | RN Dev 1 | 按住打断 |
| 3.11 | 流式响应显示 | `useChatStream.ts` | RN Dev 2 | 逐字显示效果 |
| 3.12 | 文本模式切换 | `ChatModeToggle.tsx` | RN Dev 2 | ASR/文本模式切换 |

**里程碑 M3 验收标准**:
- [ ] 按住说话 → ASR 转录正常
- [ ] AI 流式响应正常
- [ ] 指令确认流程正常
- [ ] 打断机制可用
- [ ] 端到端语音对话通

---

### Phase 4: 设备与项目 (Week 7)

**目标**: 实现设备管理和项目管理功能

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 36-38** | | | | |
| 4.1 | 扫码绑定功能 | `QRScanner.tsx` | RN Dev 1 | expo-camera |
| 4.2 | 设备列表 API | `services/api/devices.ts` | RN Dev 2 | CRUD 接口 |
| 4.3 | 设备卡片组件 | `DeviceCard.tsx` | RN Dev 2 | 在线/离线状态 |
| **Day 39-40** | | | | |
| 4.4 | 设备状态管理 | `stores/deviceStore.ts` | RN Dev 1 | 当前设备 |
| 4.5 | 设备详情页面 | `app/(main)/devices.tsx` | RN Dev 2 | 设备信息展示 |
| **Day 41-43** | | | | |
| 4.6 | 项目列表 API | `services/api/projects.ts` | RN Dev 1 | CRUD 接口 |
| 4.7 | 项目切换功能 | `ProjectSwitcher.tsx` | RN Dev 2 | 弹窗选择 |
| 4.8 | 项目列表页面 | `app/(main)/projects.tsx` | RN Dev 2 | 项目展示 |

**里程碑 M4 验收标准**:
- [ ] 扫码绑定设备成功
- [ ] 设备列表实时更新
- [ ] 项目切换成功
- [ ] 当前项目显示正确

---

### Phase 5: 认证与订阅 (Week 8)

**目标**: 实现登录、支付、会员订阅

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 44-47** | | | | |
| 5.1 | AuthManager 实现 | `services/auth/AuthManager.ts` | Tech Lead | 参考 uniapp |
| 5.2 | 图形验证码组件 | `Captcha.tsx` | RN Dev 2 | 图片验证码 |
| 5.3 | 手机号登录页面 | `app/(auth)/login.tsx` | RN Dev 2 | 短信验证码 |
| 5.4 | Token 持久化 | `stores/authStore.ts` | RN Dev 1 | MMKV 存储 |
| **Day 48-50** | | | | |
| 5.5 | 微信 SDK 集成 | `services/auth/WechatAuth.ts` | Tech Lead | react-native-wechat-lib |
| 5.6 | 微信登录流程 | `WechatAuth.tsx` 组件 | RN Dev 1 | 授权 + 登录 |
| 5.7 | 绑定手机号弹窗 | `BindMobileModal.tsx` | RN Dev 2 | 新用户绑定 |
| **Day 51-53** | | | | |
| 5.8 | 会员套餐 API | `services/api/subscription.ts` | RN Dev 1 | 套餐列表 |
| 5.9 | 套餐列表页面 | `app/(subscription)/plans.tsx` | RN Dev 2 | 套餐展示 |
| 5.10 | 支付确认页面 | `PaymentSheet.tsx` | RN Dev 2 | 支付信息确认 |
| **Day 54-56** | | | | |
| 5.11 | 微信支付集成 | `services/api/payment.ts` | Tech Lead | react-native-wechat-lib |
| 5.12 | 支付结果处理 | `PayResult.tsx` | RN Dev 1 | 成功/失败页 |
| 5.13 | 会员权益展示 | `BenefitList.tsx` | RN Dev 2 | 权益列表 |

**里程碑 M5 验收标准**:
- [ ] 手机号登录成功
- [ ] 微信登录成功
- [ ] 创建订单成功
- [ ] 微信支付成功
- [ ] 会员权益显示正确

---

### Phase 6: 优化与上线 (Week 9)

**目标**: 性能优化、测试完善、准备上线

| 天数 | 任务 | 交付物 | 负责人 | 备注 |
|------|------|--------|--------|------|
| **Day 57-59** | | | | |
| 6.1 | 性能优化 | 优化报告 | Tech Lead | 启动速度、内存 |
| 6.2 | 单元测试补全 | `__tests__/unit/` | RN Dev 1 | 核心函数测试 |
| 6.3 | 集成测试 | `__tests__/integration/` | RN Dev 2 | API 测试 |
| **Day 60-62** | | | | |
| 6.4 | iOS 真机测试 | 测试报告 | QA | iPhone 12/15 |
| 6.5 | Android 真机测试 | 测试报告 | QA | 小米/三星 |
| 6.6 | Bug 修复 | Bug 修复清单 | All | 优先级 P0/P1 |
| **Day 63-65** | | | | |
| 6.7 | Sentry 配置 | 错误监控上线 | Tech Lead | 线上错误追踪 |
| 6.8 | 应用商店准备 | 截图、描述 | Designer | App Store/Play Store |
| 6.9 | 上线文档 | 运维手册 | Tech Lead | 部署、回滚 |

**里程碑 M6 验收标准**:
- [ ] 性能指标达标 (启动<2s, 内存<200MB)
- [ ] 单元测试覆盖率 > 60%
- [ ] 真机测试无 P0/P1 Bug
- [ ] 应用商店审核材料齐全

---

## 5. 关键依赖项

### 5.1 外部依赖

| 依赖项 | 责任人 | 截止时间 | 状态 |
|--------|--------|----------|------|
| Gateway WebSocket 协议确认 | Backend Team | Week 2 | ⏳ |
| ASR 音频帧格式确认 | Backend Team | Week 3 | ⏳ |
| 微信支付商户号申请 | 运营 | Week 7 | ⏳ |
| 微信开放平台 AppID | 运营 | Week 1 | ⏳ |
| iOS 开发者账号 | 运营 | Week 1 | ⏳ |
| Android 开发者账号 | 运营 | Week 1 | ⏳ |

### 5.2 技术依赖

| 依赖项 | 说明 | 风险等级 |
|--------|------|----------|
| Expo SDK 52 | 确保稳定性 | 低 |
| react-native-wechat-lib | 微信登录/支付核心 | 中 |
| Gateway API | 后端接口可用性 | 高 |
| 阿里云 NLS | ASR 服务质量 | 中 |

---

## 6. 风险管理

### 6.1 风险登记册

| 风险 ID | 风险描述 | 概率 | 影响 | 应对策略 | 责任人 |
|---------|----------|------|------|----------|--------|
| R01 | Gateway 协议变更 | 中 | 高 | Week 2 前冻结协议，预留适配层 | Tech Lead |
| R02 | 微信 SDK 兼容性问题 | 中 | 高 | 提前集成测试，准备降级方案 | RN Dev 1 |
| R03 | ASR 准确率不达标 | 中 | 中 | 支持用户编辑转录结果 | RN Dev 2 |
| R04 | iOS 审核被拒 | 低 | 高 | 提前准备权限说明，遵循指南 | Tech Lead |
| R05 | 开发人员离职/请假 | 低 | 中 | 代码文档齐全，交叉备份 | Tech Lead |
| R06 | 第三方库弃用 | 低 | 中 | 选择社区活跃库，定期评估 | Tech Lead |

### 6.2 应急预案

**微信 SDK 集成失败**:
- 降级方案: 仅支持手机号登录
- 时间缓冲: Week 8 前完成，留 1 周调整

**ASR 延迟过高**:
- 优化: 本地 VAD + 云端 ASR
- 备选: 文本模式优先

**iOS 审核被拒**:
- 常见原因: 权限说明不足、功能不完整
- 预留时间: Week 9 后 1 周缓冲

---

## 7. 沟通计划

### 7.1 会议安排

| 会议 | 频率 | 参与人 | 内容 |
|------|------|--------|------|
| 每日站会 | 每天 10:00 | 全体开发 | 昨日进展、今日计划、阻塞问题 |
| 周会 | 每周五下午 | 全体 + 产品 | 里程碑检查、风险同步、下周计划 |
| 技术评审 | 按需 | 技术负责人 + 开发 | 架构决策、代码审查 |
| 里程碑评审 | 每阶段结束 | 全体 + 管理层 | 交付物验收、阶段总结 |

### 7.2 沟通渠道

- **即时通讯**: 飞书/钉钉群 (日常沟通)
- **文档协作**: 飞书文档/Notion (PRD、设计稿)
- **项目管理**: Linear/Jira (任务跟踪)
- **代码审查**: GitHub PR (代码 Review)

---

## 8. 质量保证

### 8.1 代码规范

- **ESLint**: 统一代码风格
- **Prettier**: 自动格式化
- **TypeScript**: 严格模式
- **Commit 规范**: Conventional Commits

### 8.2 代码审查

- **PR 必须 Review**: 至少 1 人审批
- **禁止直接 Push**: 所有代码走 PR 流程
- **CI 必须通过**: 类型检查 + 单元测试

### 8.3 测试要求

| 测试类型 | 覆盖率要求 | 负责人 |
|----------|------------|--------|
| 单元测试 | > 60% | 开发 |
| 集成测试 | 核心 API | 开发 |
| E2E 测试 | 关键流程 | QA |
| 真机测试 | iOS + Android | QA |

---

## 9. 交付物清单

### 9.1 源代码

- [ ] `evoloop-mobile/` 完整源代码
- [ ] 完整的测试代码
- [ ] 配置文件 (不含敏感信息)

### 9.2 文档

- [ ] 开发文档 (README.md)
- [ ] API 对接文档
- [ ] 部署运维手册
- [ ] 用户手册 (可选)

### 9.3 上线材料

- [ ] App Store 截图、描述
- [ ] Google Play 截图、描述
- [ ] 应用图标、启动图
- [ ] 隐私政策文档

---

## 10. 项目跟踪

### 10.1 任务看板

使用 Linear/Jira 管理任务，看板列：

```
Backlog → Todo → In Progress → Code Review → Testing → Done
```

### 10.2 里程碑检查点

| 里程碑 | 检查日期 | 验收人 | 状态 |
|--------|----------|--------|------|
| M1 基础设施 | Week 2 周五 | Tech Lead | ⬜ |
| M2 核心通信 | Week 4 周五 | Tech Lead | ⬜ |
| M3 语音对话 | Week 6 周五 | Tech Lead | ⬜ |
| M4 设备/项目 | Week 7 周五 | Tech Lead | ⬜ |
| M5 认证/订阅 | Week 8 周五 | Tech Lead | ⬜ |
| M6 上线准备 | Week 9 周五 | 管理层 | ⬜ |

### 10.3 进度追踪

每周更新甘特图，标记：
- ✅ 已完成
- 🔄 进行中
- ⏸️ 阻塞
- ⏳ 待开始

---

## 附录

### A. 推荐 VS Code 插件

```
- ES7+ React/Redux/React-Native snippets
- React Native Tools
- Expo Tools
- Prettier - Code: formatter
- ESLint
- GitLens
- Error Lens
- Todo Tree
```

### B. 学习资源

- [Expo 官方文档](https://docs.expo.dev)
- [React Native 中文文档](https://reactnative.cn)
- [React Native Paper 文档](https://callstack.github.io/react-native-paper/)
- [EAS Build 文档](https://docs.expo.dev/build/introduction/)

### C. 常见问题

**Q: 开发过程中 Gateway 不可用怎么办？**
A: 使用 Mock 数据，参考 `__mocks__/gateway.ts`

**Q: iOS/Android 真机如何调试？**
A: 使用 Flipper + React Native Debugger

**Q: 微信 SDK 测试需要哪些条件？**
A: 需要正式 AppID，开发阶段可使用测试号

---

**文档状态**: 待评审  
**最后更新**: 2026-04-06  
**版本**: v1.0
