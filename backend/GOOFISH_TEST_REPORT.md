# Smart Replay Synthesis - 闲鱼实战测试报告

## 测试概述
- **测试时间**: 2026-03-05
- **测试目标**: 闲鱼网站 (https://www.goofish.com/)
- **测试内容**: 模拟录制 → 标注关键区域 → AI技能合成 → 执行模式对比

## 1. 网站结构分析

通过 Playwright 访问闲鱼首页，识别到以下关键结构：

### 页面元素
| 元素 | 说明 |
|-----|------|
| 搜索框 | 顶部搜索栏，placeholder="搜闲置" |
| 商品分类 | 手机、数码、电脑、服饰、箱包、运动等20+分类 |
| 商品列表 | 双列瀑布流布局，每个商品卡片包含： |
| - 商品图片 | 封面图 |
| - 商品标题 | 名称+描述 |
| - 价格 | ¥符号+数字 |
| - 上架时间 | "一周内发布" / "72小时内发布" |
| - 想要人数 | "X人想要" |
| - 卖家信息 | 昵称 + 信用等级 |

### 商品数据结构
```
商品卡片 {
  title: "商品名称+详情描述",
  price: "¥350",
  publish_time: "一周内发布",
  want_count: "2人想要",
  seller: {
    nickname: "云***司",
    credit: "卖家信用极好"
  }
}
```

## 2. 标注创建

基于页面结构，创建了4个关键标注：

| ID | 时间戳 | 区域 | 说明 |
|---|-------|------|------|
| 3 | 2000ms | (150,600,400x80) | 商品标题区域（名称、详情描述） |
| 4 | 3000ms | (150,680,100x30) | 商品价格区域 |
| 5 | 3500ms | (280,680,80x25) | 想要人数区域 |
| 6 | 4000ms | (150,630,120x25) | 上架时间标签 |

## 3. 技能合成结果对比

### 任务1: 确定性数据采集 (Deterministic)

**任务目标**:
> 采集闲鱼最新上架的商品数据，包括：商品名称、价格、详情描述、上架时间、多少人想要。

**生成技能**: `goofish_product_scraper`

**执行模式**: deterministic

**核心特征**:
- 详细的6阶段执行流程（初始化 → 搜索筛选 → 列表提取 → 详情页采集 → 分页处理 → 数据持久化）
- 具体的DOM选择器锚点（`.search-input`, `.item-card`等）
- 反爬策略（随机延迟、滚动触发、频率控制）
- 数据标准化处理（时间戳转换、价格数值化）

**心法亮点**:
```markdown
## Mental Model
分层渐进式采集策略：先通过搜索+筛选锁定目标商品池，
在列表页快速收割高频字段，再选择性深入详情页获取完整描述。

## Error Recovery Table
| 异常场景 | 恢复策略 |
|---------|---------|
| 反爬验证码 | 暂停采集，人工介入，或降低频率 |
| 详情页返回丢失 | 记录滚动位置，返回后恢复 |
| 无限滚动停滞 | 强制点击"加载更多"或判定末页 |
```

---

### 任务2: 模糊智能筛选 (Agentic-style Goal)

**任务目标**:
> 帮我在闲鱼上找最近的超值好货，要判断价格是否合理，还要看看卖家靠不靠谱

**生成技能**: `xianyu_treasure_hunter`

**执行模式**: deterministic (注意：虽然是模糊目标，但仍然是确定性模式)

**核心特征**:
- 策略导向的心法（"信息不对称套利"、"快筛慢决"）
- 价格评估三维锚定法（官方原价/二手均价/历史低价）
- 卖家信誉"负面优先"评估原则
- 强调人工决策点（收藏条件、放弃信号）

**心法亮点**:
```markdown
## Mental Model
闲鱼捡漏的本质是信息不对称套利——在卖家急于出手、
信息展示不充分的场景中发现被低估的商品。

## Strategic Guidance
### Phase 3: 详情页深度评估
**价格合理性三维验证**：
1. 截图商品标题关键词 → 搜索同款 → 对比5-10个同类价格
2. 详情页查找"价格参考"模块
3. 结合成色、配件调整心理价位

**卖家信誉快速扫描**：
- 芝麻信用：极好/优秀为绿灯
- 来过时间："刚刚来过"活跃度高
- 历史动态：观察上架频率和类型
```

## 4. 执行模式分析

### 当前行为
- 两个任务都生成了 `execution_mode: "deterministic"`
- 即使第二个目标很模糊（"找超值好货"），也没有触发 agentic 模式

### 触发条件分析
当前代码判断逻辑：
```python
has_llm_decisions = any(
    "decision" in str(m.get("description", "")).lower()
    for m in macro_script
)
execution_mode = "agentic" if has_llm_decisions else "deterministic"
```

**问题**: 判断过于简单，仅检查 "decision" 关键词。

### 建议改进
应该基于以下因素综合判断：
1. 任务目标的模糊程度（需要 LLM 解释的程度）
2. 是否需要实时决策（价格判断、风险评估等）
3. 是否有明确的输入输出规范

## 5. 生成的宏脚本对比

### goofish_product_scraper (4步)
```json
[
  {"step_number": 1, "type": "action", "description": "Start: Initialization & Navigation"},
  {"step_number": 2, "type": "extract", "extract_type": "batch", "keys": ["data_3", "data_4", "data_5", "data_6"]},
  {"step_number": 3, "type": "action", "description": "Start: List Page Data Extraction"},
  {"step_number": 4, "type": "dump", "payload": {}}
]
```

### xianyu_treasure_hunter (3步)
```json
[
  {"step_number": 1, "type": "action", "description": "Start: App Launch & Navigation"},
  {"step_number": 2, "type": "extract", "extract_type": "get_text", "key": "data_7", "target_region": {...}},
  {"step_number": 3, "type": "dump", "payload": {}}
]
```

**观察**: 宏脚本相对简单，复杂逻辑主要在"心法"(instructions)中体现。

## 6. 测试结论

### 成功点 ✅
1. 成功分析闲鱼网站结构
2. 创建了针对性的标注（4个关键区域）
3. 生成了详细的技能心法（包含具体策略和错误恢复）
4. 支持中文任务目标，生成中文技能文档
5. FrameExtractor (FFmpeg) 集成正常

### 改进点 ⚠️
1. **执行模式判断**需要更智能：
   - 当前仅检查 "decision" 关键词
   - 应该分析任务目标的模糊程度和决策需求

2. **宏脚本生成**可以更丰富：
   - 目前是高层级步骤，缺少具体操作指令
   - 可以结合标注生成更精确的 CSS 选择器

3. **Vision 分析**尚未启用：
   - 需要配置 GPT-4V/Claude 进行真实的视频帧分析
   - 当前使用文本 fallback

## 7. 下一步建议

1. **配置 Vision LLM**: 设置 `VISION_LLM_PROVIDER` 环境变量
2. **真实视频测试**: 使用实际录制的屏幕视频进行端到端测试
3. **执行模式优化**: 改进 `execution_mode` 的判断逻辑
4. **宏脚本细化**: 基于标注区域生成更精确的 DOM 操作指令

