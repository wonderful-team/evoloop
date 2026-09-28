<p align="center">
  <img src="https://www.evoloop.cn/assets/images/WoodenRobot.png" alt="EvoLoop" width="120" />
</p>
<p align="center"><b>EvoLoop Agent - 自值守智能体，任务可编排，擅长上夜班</b></p>

<p align="center">
  <img src="https://img.shields.io/github/stars/wonderful-team/evoloop" alt="GitHub stars" />
  <img src="https://img.shields.io/github/v/release/wonderful-team/evoloop" alt="GitHub release" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  <a href="https://github.com/wonderful-team/evoloop/wiki"><img src="https://img.shields.io/badge/Docs-Wiki-blue" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://github.com/wonderful-team/evoloop/releases">Releases</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn">Website</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn/agent">Try Online</a> &nbsp;·&nbsp;
  <a href="https://github.com/wonderful-team/evoloop/issues">Issues</a>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README_CN.md">中文</a> | <a href="README_JA.md">日本語</a> | <a href="README_KO.md">한국어</a>
</p>

---

EvoLoop 是一个**自值守智能体**，任务可编排，在智能体内部设立三权沟通机制：**决策者、执行者、评审监察者**，让任务的每一项落实到位。

你在使用 Agent 时是否遇到过：规划一个长程任务，方案看起来很好，且有 SKILL 约束，实际执行**不完整、留尾巴，甚至跑偏**——你只能反复检查、多轮沟通去纠正？

EvoLoop 致力于解决此类问题，为此新设计了**值守式任务系统**：任务到点自动执行、每步进度实时留底；完成后由**评审监察者**站在你的立场核实——执行者说「做完了」不算数，不完整就打回重做；资金和不可逆操作由**决策者**（你）拍板。你只管规划任务、验收结果。

系统覆盖 Web、桌面、移动三端，支持唤醒词的自然语音对话。

🌐 官网 [evoloop.cn](https://evoloop.cn) · 💻 [GitHub](https://github.com/wonderful-team/evoloop)

---

## 🎬 产品演示

<table>
  <tr>
    <td valign="top">
      <img src="images/evoloop-ui.png" alt="EvoLoop Desktop" height="500" />
      <p align="center"><em>Desktop</em></p>
    </td>
    <td valign="top">
      <img src="images/evoloop-mobile.jpg" alt="EvoLoop Mobile" height="500" />
      <p align="center"><em>Mobile</em></p>
    </td>
  </tr>
<tr>
<td colspan="2" align="center">
<img src="images/evoloop-duty.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty</em></p>

<img src="images/evoloop-duty-2.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty HITL</em></p>
</td>
</tr>
</table>

**EvoLoop 完整功能演示**

https://www.evoloop.cn/assets/video/demo.mp4

**值守任务系统演示 1**

https://www.evoloop.cn/assets/video/duty1.webm

**值守任务系统演示 2**

https://www.evoloop.cn/assets/video/duty2.webm

---

## 🏗 系统架构

<p><img src="images/arch.png" alt="EvoLoop Desktop" /></p>

| 层 | 组成 |
|------|------|
| 客户端 | Web（React + Vite）、桌面端（Tauri + Rust 语音管线）、移动端（React Native，支持远程拍板/验收） |
| 服务 | FastAPI：REST + SSE + 语音 WebSocket 通道 |
| 引擎 | 基于 [OpenHands](https://github.com/All-Hands-AI/OpenHands) SDK 的 Agent 引擎：计划 → 工具执行 → 结构化自检 → 存疑挂起问人 |
| 路由 | 指令分流：常见指令直接执行，拿不准的才交给 Agent 思考 |
| 值守 | 任务队列 + Supervisor 调度：到期执行、崩溃收敛、熔断护栏 |
| 扩展 | MCP 工具服务、能力包（SOP）、运行时工具创建、宏引擎（确定性回放 + 自愈） |
| 数据 | 桌面内置（SQLite + LanceDB，数据不出本机）/ SaaS 服务端（PostgreSQL + Redis） |

---

## ⏱ 值守任务系统 (Autonomous Duty)

### 解决什么问题

大模型把需求**实施不完整或部分漂移**——长程任务做到一半，上下文被噪音淹没甚至腐烂，模型疲惫提前退出、谎称完成、不正面回复、交付物偏离目标。你只能靠**反复检查、多轮持续沟通**去纠正，人被拖进了执行细节里。

值守任务系统就是为消掉这个纠正成本而设计的：任务建立时先明确场景、目标与验收标准；执行状态全落库、断点续跑；完成后结果**以用户名义回灌到当初提需求的对话**，由当初听懂你需求的 Agent 站在你的立场核实——执行者嘴里「做完了」不算数，打回不过两轮即升级人工仲裁。

### 目标

让 Agent 可靠地长期运转一个业务：需求一次讲清，纠正交给制度。人只需在拍板、验收、仲裁三个时刻出现。

### 任务执行流程

<p><img src="images/duty-workflow.png" alt="EvoLoop Desktop" height="500" /></p>

### 适合的场景

- **电商 / 零售运营托管**：选品调研 → 定价 → 上架 → 日常巡检（缺货、差评、异常订单）——首个试点场景是「接管一座商城」
- **内容与增长流水线**：策划 → 写稿 → 素材制作 → 多平台发布 → 投放复盘，每步留痕、每步验收
- **数据与巡检机器人**：经营日报、库存 / 资金 / 指标定时巡检，异常即告警、即提案
- **第三方事件持续响应**：订单、工单、审核消息自动入列处理，全程可审计
- **企业后台 SOP**：审批辅助、对账、盘点等可重复、可验收的流程
- **研发项目管家**：代码库巡检、依赖安全检查、备份验证、需求池整理
- **客服接待**：企微 / 微信客服轮巡自动应答，资金类问题转人工
- **人不盯盘**：值守循环夜以继日地跑，人只在拍板、验收、仲裁三个时刻出现

换一个接管对象（商城 → CRM → 供应链 → 内容站），只需更换能力包与任务数据，调度与执行层零改动。

### 工作台

无限画布主视图：异构产物卡 + 依赖连线，视觉焦点自动跟随 Agent 当前节点；拍板 / 验收 / 评审卡内嵌在节点上。人随时可答三问——**Agent 正在干什么、此前干了什么、还要干什么**。

---

## 🌟 核心特性

| 能力 | 说明 |
|---|---|
| **长时程执行** | 单任务 300+ 连续步数，小时级稳定运行，自动错误恢复 |
| **跨设备 A2A 协作** | 设备间 Agent 发现、委派、回传，异步完成 |
| **值守执行** | 任务到点自动排队干活，每一步进度实时留底，做完了附上可核对的证据；执行者说「做完了」不算数——结果会以你的名义送回你提需求的对话，由监察评审者替你核实「是不是真做对了」。钱和不可逆的操作，永远等人拍板才动手 |
| **模仿学习** | 你演示一遍，它学会一套——你点鼠标走流程它记轨迹，丢一段录屏它逐帧看懂，提炼成可复用的技能或「宏」；之后同样的活机械复跑、不烧算力，遇到环境变化自动交回 AI 想办法；AI 自己写的流程，必须实测通过才允许上岗 |
| **随叫随到** | 语音、网页、企微/微信客服、手机——消息从哪来都一视同仁。常见指令直接秒办、不惊动大模型；说不清或太复杂的，才交给 AI 认真想 |
| **语音对话** | 喊一声「你好Evo」就能开口，说话可以打断它播报，也能帮你听写代发，语音不出你的设备 |
| **替你动手** | 在你已有的设备上干活——浏览器里的网页、电脑桌面上的应用、Android / iOS / 鸿蒙手机，它都能亲自操作；人不在电脑前，手机上也能拍板、验收 |
| **会找人帮忙（A2A）** | 这台机器上的 Agent 可以把活儿转给你另一台设备上的 Agent 去干——任务派出去时主线自动等待，结果回传立刻接续，整个委派过程在界面上实时可见 |
| **有保险丝** | 拿不准就停下来问人，绝不编一个答案糊弄；危险操作有权限门卡着，密码密钥不会出现在输出里，发现原地打转会果断掐停 |
| **接得进生态** | 外部工具按 MCP 协议随时接入或摘除；业务知识打包成能力包按需装配——今天接管商城，明天换接管别的系统，不用改核心代码 |

---

## 🚀 安装部署

EvoLoop 有三种部署形态，按需选择：

| 模式 | 场景 | 栈 | 配置文件 |
|---|---|---|---|
| **桌面内置** | 个人电脑、本地使用 | SQLite + LanceDB + Huey | `.env.prod.desktop` |
| **Web 单用户** | 个人服务器 | SQLite + LanceDB + Huey | `.env.prod.web.single` |
| **Web 多用户** | 团队 / 企业生产 | PostgreSQL + Redis + Meilisearch + Neo4j + Celery | `.env.prod.web.multi` |

### 桌面内置模式（个人电脑，零外部依赖）

后端内置 SQLite + LanceDB + Huey，随桌面应用单机即起，数据不出本机：

```bash
# 克隆仓库
git clone https://github.com/wonderful-team/evoloop.git
cd evoloop

# 后端：装依赖 + 一键启动
cd backend
./bin/evo install
cp .env.prod.desktop .env      # 填入 LLM API Key
./bin/evo start                # API + Worker 一起拉起（evo stop 停止）

# 桌面端（Tauri，含语音唤醒；后端作为 sidecar 随应用启动）
cd frontend
npm install
npm run tauri dev
```

### Web 单用户模式（个人服务器）

```bash
cd backend
cp .env.prod.web.single .env
./bin/evo start
```

### Web 多用户模式（团队 / 企业生产）

```bash
cd backend
cp .env.prod.web.multi .env
# 配置 PostgreSQL / Redis / Meilisearch / Neo4j，或 ./bin/evo install full
./bin/evo start
```

`evo` 命令速览：`evo start / stop / status / logs` 管服务，`evo test` 跑测试，`evo check` 查代码——完整列表 `./bin/evo help`。

---

## 📦 构建与发布

```bash
# 桌面端打包
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop
./deploy/build.sh macos-x86_64 --env-file=.env.prod.desktop

# 移动端打包（Android APK / AAB、iOS、HarmonyOS HAP）
./deploy/build.sh android --env-file=.env.prod.desktop   # APK，改 --aab 上架 Google Play
./deploy/build.sh ios --env-file=.env.prod.desktop
./deploy/build.sh harmony --env-file=.env.prod.desktop
./deploy/build.sh mobile --env-file=.env.prod.desktop    # 三平台一次构建

# Web 静态资源构建
./deploy/build.sh web --env-file=.env.prod.web.multi

# 模型下载
./deploy/download_models.sh --models nomic-embed,paraformer-zh
```

---

## 🤝 合作与共建

我正在承接 Agent 相关的定制与落地合作。

如果你在企业生产、运营、市场、投研、数据处理、内容处理或其他业务流程里，有希望用 Agent 自动化的环节，欢迎加我微信交流。

不需要你已经想清楚方案。只要你有真实流程、真实问题或真实需求，我可以一起判断 Agent 能不能解决、怎么做。

加好友请备注：**业务 + 你想让 Agent 帮你做什么**

**我们也欢迎有兴趣的朋友加入本项目，共同交流建设**——提需求、报 Bug、写代码、分享玩法，都是这个生态的建设者。

Builder 也欢迎备注：**Builder + 你在做什么**

- **官网**: [evoloop.cn](https://evoloop.cn)
- **GitHub**: [wonderful-team/evoloop](https://github.com/wonderful-team/evoloop)
- **Issues**: [GitHub Issues](https://github.com/wonderful-team/evoloop/issues)
- **邮件**: [wonderful@develop-assistant.cn](mailto:wonderful@develop-assistant.cn)
- **微信**: 扫码可以联系到我

<p align="center">
  <img src="images/wechat.png" alt="EvoLoop 微信群" width="200" />
</p>

---

<p align="center">
  <b>Built with ❤️ by EvoLoop Team</b>
</p>
