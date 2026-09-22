# HITL 授权终态化 v2：全量路径审批 + 拒绝台账 + 跨进程认领 + 作用域模型

> 状态：**已落地**（2026-09-22，提交 efcb4603d / c46335139 / f27a4e342 / 78a10afc6）。
> 结论先行：
> 1. 弹审批风暴的结构性根因是「授权粒度 = 精确路径字符串 × 复合命令多路径 × 探索型 Agent」三者相乘，不是权限模型设计错误——修复钉在每个故障的结构根因上，安全语义未变松；
> 2. 终态四件套：**一次调用全量路径授权**、**拒绝台账（列匹配 + TTL）**、**跨进程 DB 放行认领**、**exact/prefix 作用域模型 + 四档批准**；
> 3. 任何路径判断只允许查 `human_requests.resource_path` 列，**禁止再对 description 文本做 contains/endswidth 子串匹配**。

## 1. v1 复盘：审批风暴的三层根因

### 根因一（主因）：grant 只授权单路径，复合命令逐路径连环弹审批

修复前 gate 在首个越界路径上 break（旧 `hooks/authorization.py`），审批只 grant `decision.resource_path` 一个路径；批准后 `resolve_approved_tool_result` 用原始参数重执行工具，重执行再次穿过门控，对同命令的下一个未授权路径**再次**发起审批。实测证据：一条引用 4 个越界路径的复合命令在 4 秒内连环弹 3 次审批（HumanRequest 96adc267 → bd737fbd → 3b8a6c82），加上 Agent 后续命令变体，单线程累计 7 次审批。

### 根因二：破坏性命令被标成 read（审批语义倒挂）

旧 `_extract_path_from_input` 只按工具名判读写；命令文本路径提取（`extract_command_paths`）只把重定向算 write，`rm /outside/x` 的路径参数被标 `read`——审批卡显示"读取"，用户按只读预期批准，实际执行的是删除。

### 根因三：resume 无幂等，多端并发 = 副作用×2

`/chat/resume` 单发路径（`app/api/routes/agent/chat.py`）在 `handle_resume`（finalize）与 `resolve_approved_tool_result`（重执行）之间没有认领语义：手机/桌面/CLI 自动批准同时 resume 时，第二个客户端的 finalize 是 no-op，但**两个都会重执行工具**（副作用×2）。日志中同 5ms 两次 "Located pending" 即多端并发痕迹。

### 附带缺陷：进程内放行注册表

重执行放行依赖进程内 dict（取后即焚）——重启即失效、API/Worker 双进程不成立；grant 落盘失败或 `grant_mode=once` 时重执行会再撞门控形成批准-重执行-再审批死循环。

## 2. 终态设计（机制与落点）

### 2.1 门控全量路径收集（单一事实源）

`app/core/engine/hooks/authorization.py:137-240`：候选循环不再 break 于首个越界路径，改为收集 `pending_paths`（全部不安全、未授权、未判死候选）；`authorization.all_paths` 是**唯一权威列表**（含首路径），`resolve` 批准/拒绝只认这一份。

- 拒绝决策优先级最高：循环中命中 `previously_rejected` 即 break 为硬拒绝；
- 有越界路径时路径决策替换 evaluator 决策（保持旧语义：Safety-Boundary 优先于 project.json 策略）。

### 2.2 写动词分类

`app/core/security/path.py:229-334`：

- `_WRITE_VERB_COMMANDS`（rm/mv/cp/rmdir/chmod/chown/dd/tee/truncate/shred/unlink/ln/install/mkdir/touch）+ `sed -i`/`sed -i.bak`：分段级判定，写动词分段的路径参数按 `write` 门控；
- `xargs` 归入 prelude 但透传动词（`find … | xargs rm` 的有效动词是 rm；经 stdin 传参的目标路径文本不可见，属 best-effort 已知边界）；
- `KEY=value` 操作数（`dd if=/a of=/b`）取等号后的绝对路径值；动词之前的 `VAR=val` 仍视为环境赋值豁免；
- 同一路径先读后写 → **升级为 write，绝不降级**（`path.py:312`）。

### 2.3 resume 认领幂等（防副作用×2）

- `HITLOrchestrator.handle_resume`（`app/core/hitl/orchestrator.py:372`）返回 `(normalized, claimed)`：`claimed=False` = pending 已被其他端并发消费，调用方**跳过重执行与 agent 恢复**；
- 三处调用方全部接入：`chat.py` 单发路径、`orchestrator.resume_and_persist`（会话/runner 共用）；
- `handle_cancel` 无副作用，双击幂等，不改。

### 2.4 拒绝判死台账（列匹配 + TTL）

`app/models/conversation.py`：`human_requests` 增加 `resource_path`（String 1024，归一化绝对路径）/ `resource_action` / `expires_at` 三列 + `ix_human_requests_thread_resource` 索引（迁移 `b3e6f8a2c4d0`）。

- 创建端即落锚点：`request_authorization` / `raise_approval` 经 `create_request(resource_path=…, resource_action=…)` 写入（`orchestrator.py:290,810`）；
- `mark_thread_resource_rejected`（`orchestrator.py:643`）：关闭同线程同资源 pending（**列相等匹配**）+ 台账续期，无台账行则插入（复合命令多路径各有台账）；TTL = `REJECTION_TTL_HOURS=24`（`hitl/constants.py`）；
- `has_thread_resource_rejection`（`orchestrator.py:706`）：列相等 + TTL 未过期才判死——**误拒 24h 后自动解封**，不再永久 poison 线程；
- 拒绝覆盖该调用的全部路径候选（`resolve` 的拒绝分支按 `all_paths` 逐路径 mark）。

### 2.5 重执行放行 = DB 双轨认领（跨进程）

`was_call_recently_approved`（`orchestrator.py:735`）：同一 `tool_call_id` 在 `RECENT_APPROVAL_WINDOW_SECONDS=600` 内有 messages（hitl_request, completed, updated_at≥cutoff）+ human_requests（completed + `result=APPROVED`）双轨定局 → 门控放行本次重执行（`hooks/authorization.py:279`）。数据源是 `finalize_request` 的原子双轨定局，DB 共享 → **跨进程、重启后均成立**；同一 call_id 之后的新调用拿全新 id，不命中窗口。

### 2.6 作用域模型 + 四档批准

- `GrantedPermission.scope_type`（`app/core/security/policy_loader.py`）：`exact`（默认，历史记录兼容）/ `prefix`（目录级递归）；
- `AuthorizationService.grant_permission(scope_type=…)` / `is_granted` 按 scope 匹配（prefix 用 realpath 目录前缀命中）；
- `grant_mode` 四档（`ResumeRequest.grant_mode: Literal["once","always","dir","default"]`）：
  - `once` → 不落盘（靠 2.5 的 DB 认领放行一次重执行）；
  - `always` → 无 TTL 永久授权；
  - `dir` → 授权**父目录**（`resolve` 中 `grant_mode == "dir"` → `grant(dirname(path), scope_type="prefix")`）；
  - `default`/None → exact + 7 天 TTL。
- 前端：`@evoloop/shared` 的 `HumanRequestCard` 在 `request.payload.resource_path` 在场（授权门控请求标记，由 `request_authorization` 的 `request_data.payload` 经 SSE `HumanRequestEvent` 透传）时显示「授权父目录」按钮；desktop/agentStore/workbench/i18n/SDK 生成类型同步 `dir`。

## 3. 关键不变式（改 HITL 前必读）

1. **路径判断只查列**：`resource_path` 列（归一化绝对路径）相等比较；`description.contains/endswith` 一律禁止（子串误杀：`/Users/foo` 的拒绝曾命中 `/Users/foo2`）；
2. **直插 `messages` 必须推进 `thread_sequences`**：真实写入统一走 `SequenceService`（`app/core/engine/message/sequence.py`，原子 upsert）。任何绕过分配器的插入（e2e 种子、修复脚本）不推进计数器 → 后续写入撞 `UNIQUE(thread_id, sequence_number)`；
3. **`AgentHumanInterruptException` 继承 `BaseException`**：保证 `except Exception` 吞不掉中断（重执行中断能正确冒泡到 run 终态）；新增捕获分支时必须显式放行该类型；
4. **`finalize_request` 双轨原子**（human_requests + messages 单事务），其 `claimed` 返回值是 resume 认领的权威信号，禁止在 `claimed=False` 时重执行工具；
5. **`all_paths` 是批准/拒绝的唯一权威列表**（含首路径）；`resource_path/action` 仅用于提示文案与拒绝消息文本。

## 4. 测试地图

| 层 | 文件 | 覆盖 |
|---|------|------|
| 单元（mock 契约） | `tests/unit/core/test_hitl_authorization.py` | 批准全量授权、dir 父目录、拒绝全路径（mock）、自由文本透传 |
| 单元（真实 DB） | `tests/unit/core/hitl/test_hitl_authorization_ledger.py` | 台账插入/续期/关 pending、列匹配无误杀、TTL 过期、线程域、was_call 全链/过期/拒绝态、兄弟请求合并关闭、模型列契约 |
| 单元（门控） | `tests/unit/core/engine/hooks/test_authorization_hooks.py` | 复合命令单次审批、rm→write、prefix 放行子路径、动作不匹配拦截、DB 认领放行/无记录、越界/判死/值守/docker |
| 单元（提取器） | `tests/unit/core/security/test_path.py` | 写动词分类、读写升级不降级、dd/tee/sed -i.bak、env 赋值豁免 |
| 单元（迁移） | `tests/unit/infrastructure/test_alembic_migration_smoke.py` | 空库回放 base→head、终态列/索引/版本断言（子进程 + 临时 APP_DATA_DIR） |
| E2E | `tests/e2e/test_29_hitl_resume_chain.py` | 批准：HTTP→双轨定局→工具真实重执行；拒绝：REJECTED+TTL 台账→不重执行（真实 HTTP + 直插种子，无 LLM） |

全量回归基线：`pytest tests/unit -q` = **1798 passed**（2 skipped 存量）；前端 `vitest` 118 passed（含审批卡四档按钮用例）+ `tsc --noEmit` 全绿。改动模块行覆盖率 93%。

## 5. 部署与运维

1. **升级前必须执行** `alembic upgrade head`（迁移 `b3e6f8a2c4d0`）；未迁移直接上新代码会在 human_requests 缺列报错；
2. e2e 套件需运行中的后端（`./bin/evo start`），CI 无服务时自动 skip（与 test_19 同约定）；
3. 移动端 bundle 为编译产物，本变更未触及移动端作答界面（HITL 作答在 Web）。

## 6. 已知保留项（有意不做，非缺陷）

1. **作用域不对称**：grant 落 project 级（7 天 TTL 跨线程共享），拒绝判死是 thread 级——批准一次全项目免审、拒绝只毒当前线程。是"批准求便利、拒绝防误伤"的权衡，是否统一（拒绝也 project 级）留产品决策；
2. **docker 模式 MCP 业务写 auto-approve**（`matcher=".*"`）无沙箱兜底——决策边界在任务级 risk gate（T1-T4），不在工具门控，属另一工作流；
3. **两套 resume 实现并存**（`chat.py` 单发路径 vs `resume_and_persist`）：单发路径刻意将用户原始输入按"点了什么存什么"落库（本地化文案），与共用路径的归一化存储不同；claim 幂等语义已双向对齐，合并需先统一落库语义，暂以不变式 §3-4 锁住行为；
4. **提取器 best-effort 边界**：经 stdin 传参的目标路径（xargs）、无法解析的 shell 构造不可见——安全兜底由 runner 层 cd 硬拦与 `is_dangerous_command` 承担（既有分工，见 `path.py` 模块注释）。
