# E2E 页面测试发现的问题报告

> 来源:frontend/tests/ 逐页 E2E 测试(26 用例,已全绿)。
> 说明:全绿只保证"页面可渲染、不崩、无全局 ErrorBoundary",不保证业务逻辑正确。
> 以下每项均已在本机真实复现,标注了代码位置与复现方式。

## 严重等级

| 级别 | 含义 |
|------|------|
| P1 | 阻塞用户主流程 / 数据安全 |
| P2 | 明显缺陷,用户会遇到且体验差 |
| P3 | 健壮性 / 可访问性 / 注释误导 |

---

## P2-1 [已修复] 首次登录 SetupWizard 强制弹出,且平台模式误判"LLM 缺失"

- **现象(修复前)**:`useSetupRequired.ts:49-53` 无条件要求 `LLM_BASE_URL` 非空。而 platform 模式(`LLM_CONFIG_TYPE=platform`,走 EvoLoop Gateway)根本不需要用户自配 base_url/API Key——真实环境 `LLM_BASE_URL=""`、`LLM_API_KEY=""` 却已在正常使用渗透测试。因此 platform 用户的 `missingLLM` 恒为 true,向导每次进非 settings 页都被强制点亮(N 弹),而弹窗又无可关闭入口。
- **修复(2026-xx)**:`useSetupRequired.ts` 判定改为按 `LLM_CONFIG_TYPE` 分支——platform 仅要求 `LLM_MODEL` 非空;custom 才要求 base_url/api_key。同时 `SetupWizard.tsx` 动态裁剪步骤:platform 且已有默认模型时跳过 LLM 配置步(welcome→projects→completion),此时**不再调用 `applyLlmConfig`**,避免用空数据覆盖既有配置;custom 或 platform 未选模型时仍保留 LLM 步。
- **验证**:真实环境(platform + model 已配 + 无 `evoloop_setup_completed`)向导不再弹出;切到 custom 后向导恢复出 4 步且 LLM 步可进入;E2E 29 用例 × 3 轮全绿。
- **注意**:首次进入 LLM 步时 Next 短暂禁用(`canProceed=false`)是预期——custom 插槽需填 provider/base_url/model 并 Test Connection 后放开;platform preset 由 `llmTested=true` 自动放开。

## P2-2 项目列表无 `<a>` 链接(键盘/爬虫不可达)

- **现象**:`ProjectList.tsx` 项目卡片是 `Card` + `onClick={() => navigate(...)}`(JS 导航),DOM 中没有 `<a href>` 或 `<button>`,Tab 聚焦丢失、无法中键新开、无 `data-tour`。
- **影响**:可访问性;也让页面测试拿不到项目跳转目标,只能绕过 UI 直接调 `/api/v1/projects/` 解析 projectId。
- **证据**:`frontend/packages/desktop/src/components/Projects/ProjectList.tsx:101,140-142`
- **建议**:卡片内容用 `<a href={`/projects/${id}`}>`(配合 hash 路由)或 `asChild` 包裹,保留 onClick 逻辑。

## P3-1 [已随 P2-1 修复] `isLoggedIn()` 与 login 注释互相矛盾

- **现象**:`login.tsx:131` 注释声称 "Frontend no longer stores tokens in localStorage";但认证判断与登录成功落库全依赖 localStorage:
  - `useAuth.ts:14` `isLoggedIn = localStorage.getItem("access_token") !== null`
  - `useAuth.ts:106,141` 登录成功 `localStorage.setItem("access_token", ...)`
- **影响**:注释误导维护者(例如凭直觉改登录流程会直接破坏认证),且一旦未来真改为仅 cookie,`_layout` 的 `beforeLoad` 守卫会失效。
- **建议**:要么存储改为 cookie 并同步三个 API Key 路由守卫,要么删掉过时注释、明确"本地 token"是既定方案。

## P3-2 `html.lang` 与渲染语言可能不一致

- **现象**:同一登录态、`localStorage.i18nextLng=en-US` 时,部分页面标题中文/英文不定(如 `/learning` 曾渲染 "Learning Center" 也渲染过「学习中心」),而 `document.documentElement.lang` 恒为 `en`。
- **原因**:`shared/src/i18n.ts` 用 `localStorage → navigator` 检测并缓存;首次加载时读取结果受时序影响(测试中是否注入 initScript 会改变语言),且 `lang` 属性未随 i18n 变更同步。
- **影响**:真实用户可能偶发看到中英混排;对依赖 `lang` 的无障碍/字体选择不可靠。
- **建议**:i18n 初始化后显式同步 `document.documentElement.lang`;语言切换走统一 setter 并写缓存。

## P3-3 `formatDuration` 对非整秒输出不收敛

- **现象**:`voiceStorage.ts:162` 的 `formatDuration`,`seconds < 60` 时直接 `String(seconds)`,不取整:
  - `formatDuration(7.9)` → `"0:7.9"`
  - 超过 60 时 `secs = seconds % 60` 同样可能为小数 → `"1:1.5"`
- **影响**:录音时长显示出现"秒数带小数点",UI 观感缺陷。
- **证据**:`frontend/packages/desktop/src/utils/voiceStorage.ts:162-170`,单测 `voiceStorage.test.ts` 已固化 `formatDuration(7.9)="0:7.9"`。
- **建议**:秒数 `Math.floor` 后再补零(与 `0:07` 语义一致)。

## P3-4 `getFileName` 对无文件名路径返回原串

- **现象**:`getFileName("/a/b/")` → `"/a/b/"`(尾斜杠目录把整串当文件名返回)。
- **影响**:文件列表遇到目录路径时可能展示错误名称。
- **证据**:`packages/desktop/src/utils/fileUtils.test.ts:38` 已固化该行为。
- **建议**:去掉尾斜杠后再取最后一段;为空则返回空字符串或组件处兜底。

---

## 既有后端问题(非本轮 E2E 引入,早前工作流已发现)

| 项 | 状态 | 说明 |
|----|------|------|
| `tests/unit/infrastructure/vision/test_generation.py::TestIsGatewayConfigured` | 2 失败 | 引用了 `app/infrastructure/vision/generation.py` 中不存在的 `is_gateway_configured`;integration 786 全过,unit 其余 1428 过。 |
| `tests/unit/core/mcp/test_config.py::TestMcpServerConfig::test_from_db_model_sse` | 1 失败 | 断言 `transport==SSE`,实际路由为 `streamable_http`;与 MCP transport 行为变更相关,与 LLM 改动无关,grep 确认未改动该测试。 |
| Alembic revision `a1b2c3d4e5f6` | 重复 | 被 `a1b2c3d4e5f6_add_app_maps_and_macros.py` 与 `a1b2c3d4e5f6_add_react_metrics_to_agent_activities.py` 两个文件共用,当前 3 个 head,`alembic upgrade head` 不可用。 |
| `app/core/engine/extraction/schema.py:37` | UP007 lint | `Optional[...]` 应为 `X | None`,既有未修。 |

---

## 默认 LLM 移除(EvoCloud 网关默认分配方案落地)

**背景**:EvoCloud 远端线上网关对登录 token 请求在未传 `LLM_MODEL` 时自行分配默认模型;本地 Python 后端和前端无需维护"默认 LLM"概念。

**落地改动**(全部实测通过):
- `backend/app/api/routes/system.py::apply_llm_config` — platform 模式(无 base_url)拒不落 `LLM_MODEL`/`CUSTOM_LLM_MODEL` 并清空残留(防旧 custom 配置泄漏);custom 模式照旧写入。
- `backend/app/infrastructure/llm/factory.py:248-261` — DB `LLM_BASE_URL` 回退仅在 `LLM_CONFIG_TYPE=custom` 时生效,platform 空 model 请求不再被陈旧 base_url 劫持。
- `frontend .../Settings/ModelSettings.tsx::saveModel` — `evocloud`(平台)源只展示、不调用 `applyLlmConfig` 写本地默认;custom/lm-studio/ollama 源保留保存。
- `frontend .../Wizard/useSetupRequired.ts` + `SetupWizard.tsx` — platform 模式永不判 LLM 缺失(`missingLLM=false`)、永不显示 LLM 步;custom 才校验 model+base_url。

**实测验证矩阵**(真实后端,重启加载新代码后):
| 场景 | 期望 | 结果 |
|------|------|------|
| platform apply (base_url=null) | LLM_MODEL/CUSTOM_LLM_MODEL 被清空 | ✓ (旧值 deepseek-v4-flash → 空) |
| custom apply (base_url 有值) | LLM_MODEL/CUSTOM_LLM_MODEL 写入 | ✓ |
| platform + 无 LLM_MODEL | 向导不弹、chat 可用 | ✓ |
| custom 不完整(model 空) | 向导弹出(需配置) | ✓ |
| custom 完整(model+base_url) | 向导不弹 | ✓ |

测试:后端 `tests/unit/infrastructure/llm/test_llm_factory_fallback.py`(4 新增)+ `test_system.py` 扩展 platform 清空用例;全套 unit 1433 passed(3 个既有失败与本改动无关)、integration 787 passed;前端 32 unit + 29 E2E passed。

**自动化覆盖补全**(本轮新增,针对默认 LLM 移除逻辑):
- 前端新增纯函数 `llmConfig.ts::needsLlmStepForConfig`(8 用例,平台/自定义/空串全分支),`useSetupRequired.test.tsx`(7 用例,覆盖 loading/平台/自定义/工作区/已完成后 4 次登录 localStorage 语义),`ModelSettings.test.tsx`(3 用例,evocloud 不写、自定义/本地写入、CUSTOM_LLM_MODEL 恢复)。
- 前端 `vitest.setup.ts` 增补 Radix UI 所需 polyfill(`hasPointerCapture`/`setPointerCapture`/`releasePointerCapture`/`scrollIntoView`),jsdom 下 Select 可交互。
- 后端 `test_system.py::TestLLMConfig` 新增 3 用例(自定义 `LLM_MODEL=req.model` 且合法忽略残留 `default_model_id`、vision/api_key/headers 持久化、平台即使带残留 `default_model_id` 仍清空)。
- 后端 `test_llm_factory_fallback.py` 新增 2 用例(缺省配置型默认平台不劫持、显式 base_url/api_key 直连)。
- 重构:`useSetupRequired` 与 `SetupWizard` 复用同一 `needsLlmStepForConfig`,消除重复判定逻辑。
- 结果:前端 50 unit(原 32+18)全绿、后端相关 40 全绿、biome/ruff 干净。

**残余清理**(default_model_id 死代码移除):
- `default_model_id` 是「选择默认模型」旧概念的剩余字段:LLM/Embedding apply 都只把它写进 `LLM_MODEL`/`EMBEDDING_MODEL`(legacy fallback key),而实际生效值永远是 `req.model`(`CUSTOM_LLM_MODEL`/`CUSTOM_EMBEDDING_MODEL` 优先);`system.py` 里还有一段 `if not default_id.startswith("embedding-"): pass` 纯 no-op 死代码。
- 已删除:`api/schemas/system.py` 两处字段、`apply_llm_config`/`apply_embedding_config` 取值逻辑与死代码、前端 `WizardContext`/`LLMConfigStep`/`SetupWizard` 的 `defaultModelId`、生成客户端 `types.gen.ts`/`schemas.gen.ts`。
- 兼容性:`LLMConfigRequest` 为 `DynamicBaseModel`(extra=allow),旧请求体残留 `default_model_id` 不 422 且被忽略;`EmbeddingConfigRequest` 为 `ScopedRequest`(extra=forbid),但无任何前端发该字段,安全。
- 测试:原「默认模型 id 优先」用例改写为「忽略残留 default_model_id 回归」,platform 清空用例加上「忽略残留」语义;相关 30 用例全绿。

---

## 测试基础设施本身的风险(SEC)

- **账号凭据**:`E2E_USERNAME` / `E2E_PASSWORD` 存于 `frontend/.env`(真实账号 `preterchan`)。已确认 `frontend/.gitignore` 覆盖 `.env`,git 不追踪;但仍是明文真实凭据,建议改用仅测试用途的账号,并保持该文件始终在 ignore 列表。