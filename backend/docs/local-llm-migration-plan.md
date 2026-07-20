# 前端设置界面架构评估与简化方案

## 现状复杂度评估

### 6 个 Tab，40+ 配置项

| Tab | 子分区 | 配置项数 | 用户理解成本 |
|-----|--------|---------|------------|
| General | 语言、设备名、工作区 | ~5 | ✅ 低 |
| **Models** | **AI Assistant / Advanced(Heavy+Lightning+Embedding)** | **~25** | **⚠️ 中（已简化）** |
| Voice | TTS / Advanced(STT+WakeWord+Shortcut) | ~15 | ✅ 低（已简化） |
| Profile | 昵称、邮箱、密码 | ~5 | ✅ 低 |
| Appearance | 主题、思考显示 | ~3 | ✅ 低 |
| Danger | 删号 | ~1 | ✅ 低 |

## 实施进度

### Phase 1：自动发现（后端）✅ 已完成

- `ModelDiscoveryService` — 扫描 LM Studio / Ollama / GGUF / 自定义配置
- `GET /system/models/discover` API
- 8 个测试覆盖
- 自动检测连通性

### Phase 2：简化设置页（前端）✅ 已完成

- Models Tab：AI Assistant（默认视图）+ Advanced Settings（折叠）
- Voice Tab：TTS（默认视图）+ Advanced Voice Settings（折叠）
- STT / Wake Word / Shortcut 移入折叠面板

### Phase 3：移除冗余字段 ⬜ 进行中

- 移除 `provider` / `provider_type` 字段，从 URL 自动推断
- 移除 `OllamaEmbedder`，统一走 OpenAI 兼容

### 后端已做

- `embedder factory.py` 改为 3 级优先级链（gguf → local → remote）
- `lightning.py` 移除嵌入管理，纯 LLM
- `local.py` 从 `sentence-transformers` 迁移到 `llama-cpp-python`
- 移除 `torch` / `transformers` 依赖
- 新增 `GET /system/models/discover` API
- 新增 `GET /system/lightning/status` / `POST /system/lightning/apply` / `POST /system/lightning/test`
- 新增 `GET /system/embedding/tier-status` / `POST /system/embedding/tier-apply` / `POST /system/embedding/tier-test`

### 前端已做

- `LightningSettings.tsx` — 仅 LLM 配置（mode, llm_model, ctx, base_url）
- `EmbeddingSettings.tsx` — Mode 选择器（none/gguf/local/remote）
- `ModelSettings.tsx` — AI Assistant 默认视图 + Advanced Settings 折叠
- `VoiceControlSettings.tsx` — TTS 默认视图 + Advanced 折叠
- 统一样式（h-10 Input, text-sm font-medium Label, rounded-xl 测试结果）

## 已知问题待办

- [x] Phase 1: 自动发现 API
- [x] Phase 2: 前端简化
- [ ] Phase 3: 移除 `provider`/`provider_type` 字段
- [ ] 设置页合并 `getSystemConfig()` 请求（Lightning/Embedding/Heavy 3 次独立加载）
- [ ] 嵌入模式状态指示（当前走 GGUF/Local/Remote 哪个）
- [ ] GGUF 路径输入无下载引导
- [ ] 对话 `ModelSelector` 集成发现 API（现在只用旧模型列表）
