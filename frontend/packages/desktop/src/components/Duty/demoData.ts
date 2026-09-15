/* Demo dataset for the Agent duty workbench (mirrors Chat/debug/mockData pattern).
 * Flip DEMO to false to return to live API data. */

export const DEMO = true

const NOW = Date.now()
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString()
const MIN = 60_000
const HOUR = 3_600_000
const DAY = 86_400_000

export const demoDashboard = {
  counts: {
    proposed: 2,
    pending: 3,
    in_progress: 1,
    waiting_acceptance: 2,
    completed: 2,
    failed: 1,
    cancelled: 0,
  },
  duty_state: "idle" as const,
  tokens: {
    today: { input: 86420, output: 23180, llm_calls: 47 },
    week: { input: 512300, output: 148900, llm_calls: 312 },
  },
  today_window: { since: null, until: null },
  daily: [
    { date: iso(6 * DAY), input_tokens: 41200, output_tokens: 12800, completed: 4 },
    { date: iso(5 * DAY), input_tokens: 58600, output_tokens: 17300, completed: 6 },
    { date: iso(4 * DAY), input_tokens: 39400, output_tokens: 9100, completed: 3 },
    { date: iso(3 * DAY), input_tokens: 71800, output_tokens: 22500, completed: 8 },
    { date: iso(2 * DAY), input_tokens: 66200, output_tokens: 19800, completed: 7 },
    { date: iso(1 * DAY), input_tokens: 88400, output_tokens: 26400, completed: 9 },
    { date: iso(0), input_tokens: 86420, output_tokens: 23180, completed: 5 },
  ],
  recent_events: [
    { at: iso(0.5 * MIN), kind: "progress", title: "库存巡检", status: "in_progress", task_id: "t-demo-4", result: "正在下架缺货商品（3/4 步）" },
    { at: iso(6 * MIN), kind: "proposal", title: "补货土鸡蛋", status: "proposed", task_id: "t-demo-1", result: "证据：stock=3 低于安全线 10" },
    { at: iso(18 * MIN), kind: "progress", title: "订单巡检", status: "completed", task_id: "t-demo-8", result: "23 单全部正常，无待发货超时" },
    { at: iso(32 * MIN), kind: "acceptance", title: "售后巡检", status: "waiting_acceptance", task_id: "t-demo-9", result: "自检通过，待人工验收" },
    { at: iso(65 * MIN), kind: "progress", title: "营销巡检", status: "failed", task_id: "t-demo-10", result: "营销 API 超时，已重试 2 次放弃" },
    { at: iso(3 * HOUR), kind: "acceptance", title: "上新 5 款商品", status: "completed", task_id: "t-demo-11", result: "人工验收通过 by 运营者" },
  ],
  current_run: null as null | {
    thread_id: string
    goal: string
    started_at: string
    input_tokens: number
    output_tokens: number
  },
}

const isoDay = (offsetDays: number) =>
  new Date(NOW + offsetDays * DAY).toISOString().slice(0, 10)

export const demoTasks = [
  {
    id: "t-demo-1",
    title: "补货土鸡蛋（Agent 提案）",
    description: "库存巡检发现 stock=3 低于安全库存 10，建议生成补货任务并同步供应商",
    type: "once", status: "proposed", category: "inventory",
    priority: "high", risk_level: "T3", source: "agent",
    provenance: { kind: "message", ref: "thread-demo", task_id: "t-demo-4" }, self_check: null, acceptance: null,
    due_at: null, last_thread_id: null,
  },
  {
    id: "t-demo-2",
    title: "首页 Banner 更换提案",
    description: "点击率连续 3 日下滑 12%，提案替换为秋季主推素材",
    type: "once", status: "proposed", category: "marketing",
    priority: "medium", risk_level: "T2", source: "agent",
    provenance: { kind: "message", ref: "thread-demo", task_id: "t-hist-10" }, self_check: null, acceptance: null,
    due_at: null, last_thread_id: null,
  },
  {
    id: "t-demo-3",
    title: "订单巡检",
    description: "每 30 分钟检查待发货/超时未付款订单",
    type: "recurring", status: "pending", category: "orders",
    priority: "high", risk_level: "T4", source: "system",
    trigger_spec: "interval:1800",
    provenance: null, self_check: null, acceptance: null,
    due_at: isoDay(0), last_thread_id: "thread-demo-old",
  },
  {
    id: "t-demo-4",
    title: "库存巡检",
    description: "全量商品库存健康检查，缺货自动下架并产出报告",
    type: "recurring", status: "pending", category: "inventory",
    priority: "high", risk_level: "T3", source: "system",
    trigger_spec: "interval:3600",
    provenance: null, self_check: null, acceptance: null,
    due_at: isoDay(0), last_thread_id: "thread-demo",
  },
  {
    id: "t-demo-5",
    title: "会员巡检",
    description: "新增会员权益发放核对",
    type: "recurring", status: "pending", category: "member",
    priority: "medium", risk_level: "T4", source: "system",
    trigger_spec: "interval:7200",
    provenance: null, self_check: null, acceptance: null,
    due_at: isoDay(1), last_thread_id: null,
  },
  {
    id: "t-demo-6",
    elapsed_sec: 480,
    title: "处理差评回复",
    description: "昨日新增 2 条一星差评，需拟回复话术",
    type: "once", status: "waiting_acceptance", category: "service",
    priority: "high", risk_level: "T2", source: "system",
    provenance: null,
    self_check: { verdict: "pass", notes: "话术符合客服规范，敏感词检测通过" },
    acceptance: null,
    due_at: isoDay(1), last_thread_id: "thread-demo-old2",
  },
  {
    id: "t-demo-7",
    elapsed_sec: 900,
    title: "竞品价格快照",
    description: "抓取 3 家竞店同款价格并生成对比表",
    type: "once", status: "waiting_acceptance", category: "marketing",
    priority: "medium", risk_level: "T3", source: "system",
    provenance: null,
    self_check: { verdict: "pass", notes: "数据完整率 100%" },
    acceptance: null,
    due_at: isoDay(2), last_thread_id: "thread-demo-old3",
  },
  {
    id: "t-demo-8",
    elapsed_sec: 190,
    title: "订单巡检（上一轮）",
    description: "已完成：23 单全部正常",
    type: "recurring", status: "completed", category: "orders",
    priority: "high", risk_level: "T4", source: "system",
    provenance: null, self_check: { verdict: "pass" },
    acceptance: { by: "system:auto" },
    due_at: isoDay(-1), last_thread_id: null,
  },
  {
    id: "t-demo-9",
    elapsed_sec: 240,
    title: "资金对账（昨日）",
    description: "已完成：差异 ¥0，流水 412 笔全对",
    type: "recurring", status: "completed", category: "finance",
    priority: "high", risk_level: "T1", source: "system",
    provenance: null, self_check: { verdict: "pass" },
    acceptance: { by: "system:auto" },
    due_at: null, last_thread_id: null,
  },
  {
    id: "t-demo-10",
    elapsed_sec: 660,
    title: "营销巡检",
    description: "失败：营销 API 超时，重试 2 次后放弃",
    type: "recurring", status: "failed", category: "marketing",
    priority: "medium", risk_level: "T3", source: "system",
    provenance: null, self_check: { verdict: "fail", notes: "upstream timeout" },
    acceptance: null,
    due_at: null, last_thread_id: null,
  },
]

// ── 历史记录：本周各日已完成的巡检/任务（供周历与完成数） ──
const hist = (n: number, title: string, day: number, cat: string, status = "completed") => ({
  id: `t-hist-${n}`,
  title,
  description: "历史记录：本轮已按计划完成",
  type: "recurring", status, category: cat,
  priority: "medium", risk_level: "T4", source: "system",
  provenance: null, self_check: { verdict: status === "completed" ? "pass" : "fail" },
  acceptance: status === "completed" ? { by: "system:auto" } : null,
  due_at: isoDay(day), last_thread_id: null,
  elapsed_sec: 120 + n * 30,
})

// ── 生成类任务（生图 / 生视频） ──
export const demoCreativeTasks = [
  {
    id: "t-creative-1",
    elapsed_sec: 360,
    title: "生成秋季上新主图（4 候选）",
    description: "秋季上新主图：暖橙色调、丰收氛围、突出新品南瓜燕麦粥。\n[生成参数] 类型=图片 比例=1:1 风格=写实商业 张数=4",
    type: "once", status: "waiting_acceptance", category: "creative",
    priority: "high", risk_level: "T2", source: "system",
    provenance: null,
    self_check: { verdict: "pass", notes: "4 张候选均已通过内容安全检测；第 1/3 张构图与色调最贴合需求" },
    acceptance: null,
    due_at: isoDay(1), last_thread_id: "thread-gen-img",
  },
  {
    id: "t-creative-2",
    elapsed_sec: 1140,
    title: "制作南瓜燕麦粥宣传短视频",
    description: "10 秒竖版产品宣传视频：热腾腾的产品特写开场→配料闪现→品牌收尾。\n[生成参数] 类型=视频 比例=9:16 时长=10s 风格=美食实拍感",
    type: "once", status: "completed", category: "creative",
    priority: "medium", risk_level: "T2", source: "system",
    provenance: null,
    self_check: { verdict: "pass", notes: "时长 10.2s，无花屏/黑帧，尾帧品牌 Logo 完整" },
    acceptance: { by: "运营者" },
    due_at: isoDay(-1), last_thread_id: "thread-gen-vid",
  },
]

export const demoHistoryTasks = [
  hist(1, "订单巡检（周一）", -6, "orders"),
  hist(2, "库存巡检（周一）", -6, "inventory"),
  hist(3, "售后巡检（周二）", -5, "service"),
  hist(4, "营销巡检（周二）", -5, "marketing", "failed"),
  hist(5, "资金对账（周三）", -4, "finance"),
  hist(6, "会员巡检（周三）", -4, "member"),
  hist(7, "订单巡检（周四）", -3, "orders"),
  hist(8, "库存巡检（周四）", -3, "inventory"),
  hist(9, "订单巡检（周五）", -2, "orders"),
  hist(10, "售后巡检（周五）", -2, "service"),
  hist(11, "营销巡检（周六）", -1, "marketing"),
  hist(12, "会员巡检（周六）", -1, "member"),
]

export const demoMessages: unknown[] = [
  { id: "m01", role: "ai", content: "开始执行库存巡检：全量商品库存健康检查，缺货自动下架并产出报告。" },
  { id: "m02", role: "ai", content: "先拉取全部在售商品列表，再逐个核对库存与安全线。" },
  { id: "m03", role: "assistant", name: "list_goods", tool_calls: [{ name: "list_goods" }], content: '{"category":"all","on_sale":true}' },
  { id: "m04", role: "tool", name: "list_goods", content: '共 86 款在售商品，返回分页 1/2（50 条）' },
  { id: "m05", role: "tool", name: "list_goods", content: '分页 2/2（36 条），合计 86 款' },
  { id: "m06", role: "ai", content: "86 款商品已就绪，接下来批量查询实时库存。" },
  { id: "m07", role: "assistant", name: "check_stock", tool_calls: [{ name: "check_stock" }], content: '{"sku_batch":86}' },
  { id: "m08", role: "tool", name: "check_stock", content: '5 款商品低于安全库存：土鸡蛋(3/10)、鲜牛奶(0/20)、有机蔬菜(8/15)、手工酸奶(2/12)、蜂蜜(1/8)' },
  { id: "m09", role: "ai", content: "发现 5 款缺货风险商品，其中鲜牛奶已完全断货，需要立即下架处理，其余 4 款生成补货提案。" },
  { id: "m10", role: "assistant", name: "update_stock", tool_calls: [{ name: "update_stock" }], content: '{"sku":"fresh-milk-01","action":"off_shelf"}' },
  { id: "m11", role: "tool", name: "update_stock", content: '商品「鲜牛奶 250ml×12」已下架成功' },
  { id: "m12", role: "ai", content: "已下架缺货商品：鲜牛奶。继续处理剩余 4 款低库存商品的补货建议。" },
  { id: "m13", role: "assistant", name: "call_supplier_api", tool_calls: [{ name: "call_supplier_api" }], content: '{"action":"quote","skus":4}' },
  { id: "m14", role: "tool", name: "call_supplier_api", content: '{"error":"upstream timeout"}' },
  { id: "m15", role: "ai", content: "供应商接口超时，进行第 1 次重试。" },
  { id: "m16", role: "assistant", name: "call_supplier_api", tool_calls: [{ name: "call_supplier_api" }], content: '{"action":"quote","skus":4,"retry":1}' },
  { id: "m17", role: "tool", name: "call_supplier_api", content: '报价返回成功：土鸡蛋 ¥1.2/枚、有机蔬菜 ¥9.8/份、手工酸奶 ¥6.5/盒、蜂蜜 ¥39/瓶' },
  { id: "m18", role: "ai", content: "已获取 4 款商品最新报价，生成补货提案并写入巡检报告。" },
  { id: "m19", role: "assistant", name: "create_proposal", tool_calls: [{ name: "create_proposal" }], content: '{"title":"补货土鸡蛋","evidence":"stock=3 < safe=10","quote":"¥1.2/枚"}' },
  { id: "m20", role: "tool", name: "create_proposal", content: '提案已创建（proposed，待运营者确认）' },
  { id: "m21", role: "assistant", name: "write_report", tool_calls: [{ name: "write_report" }], content: '{"path":"reports/stock-patrol-0913.md"}' },
  { id: "m22", role: "tool", name: "write_report", content: '报告已写入 reports/stock-patrol-0913.md（86 款扫描、5 款预警、1 款下架、4 款补货建议）' },
  { id: "m23", role: "ai", content: "本轮巡检已完成：下架 1 款断货商品，创建 4 项补货提案，报告已生成。自检：所有变更均为 T3 级以内，无需人工介入。任务进入待验收。" },
]

export const demoPlan: Record<string, unknown> = {
  plan: {
    title: "库存巡检 · 全量商品健康检查",
    steps: [
      { id: "s1", title: "拉取全量在售商品清单", status: "pending", result: null },
      { id: "s2", title: "批量核对实时库存与安全线", status: "pending", result: null },
      { id: "s3", title: "缺货商品自动下架并生成补货提案", status: "pending", result: null },
      { id: "s4", title: "写入巡检报告并提交自检", status: "pending", result: null },
    ],
  },
}


// ── planMap：按 threadId 各任务自己的执行计划 ──
export const demoPlanMap: Record<string, Record<string, unknown>> = {
  "thread-demo": demoPlan,
  "thread-demo-old2": {
    plan: {
      title: "差评回复 · 话术拟定",
      steps: [
        { id: "p1", title: "读取 2 条一星差评内容", status: "completed", result: "物流损坏 / 口味不合" },
        { id: "p2", title: "按客服规范拟回复话术", status: "completed", result: "2 条话术已生成" },
        { id: "p3", title: "敏感词与合规自检", status: "completed", result: "通过" },
      ],
    },
  },
  "thread-demo-old3": {
    plan: {
      title: "竞品价格快照",
      steps: [
        { id: "q1", title: "确定 3 家竞店与同款清单", status: "completed", result: "12 款同款" },
        { id: "q2", title: "抓取竞店实时售价", status: "completed", result: "12/12 成功" },
        { id: "q3", title: "生成价格对比表", status: "completed", result: "低 5% ~ 高 18%" },
        { id: "q4", title: "提交自检", status: "completed", result: "数据完整率 100%" },
      ],
    },
  },
  "thread-member-run": {
    plan: {
      title: "会员巡检 · 权益发放核对",
      steps: [
        { id: "b1", title: "拉取今日新增会员", status: "pending", result: null },
        { id: "b2", title: "核对权益发放完整性", status: "pending", result: null },
        { id: "b3", title: "缺漏补发并汇总", status: "pending", result: null },
      ],
    },
  },
  "thread-gen-img": {
    plan: {
      title: "秋季主图 · 生成与精选",
      steps: [
        { id: "g-s1", title: "解析创意要求与输出规格", status: "completed", result: "1:1 × 4" },
        { id: "g-s2", title: "生成 4 张候选图并过安全检测", status: "completed", result: "4/4 通过" },
        { id: "g-s3", title: "精选标注并提交人工验收", status: "completed", result: "推荐候选 1/3" },
      ],
    },
  },
  "thread-gen-vid": {
    plan: {
      title: "宣传视频 · 脚本到成片",
      steps: [
        { id: "v-s1", title: "拆解分镜脚本（3 镜 10s）", status: "completed", result: null },
        { id: "v-s2", title: "逐镜生成并合成", status: "completed", result: "渲染完成" },
        { id: "v-s3", title: "质检（黑帧/花屏/Logo）", status: "completed", result: "通过" },
      ],
    },
  },
  "thread-demo-old": {
    plan: {
      title: "订单巡检 · 待发货核对",
      steps: [
        { id: "r1", title: "拉取待发货订单", status: "completed", result: "23 单" },
        { id: "r2", title: "核对发货时效", status: "completed", result: "无超时" },
        { id: "r3", title: "汇总本轮结论", status: "completed", result: "全部正常" },
      ],
    },
  },
}

export const demoPlanFor = (threadId: string | null) =>
  (threadId && demoPlanMap[threadId]) || demoPlanMap["thread-demo"]


export interface DemoAttachment {
  type: "image" | "video"
  label: string
  w: number
  h: number
  duration?: number
  hue: number
}

export const demoGenMessages: Record<string, Record<string, unknown>[]> = {
  "thread-gen-img": [
    { id: "g01", role: "ai", content: "开始生成秋季上新主图：解析需求——暖橙色调、丰收氛围、主体为新品南瓜燕麦粥，输出 1:1 商业主图 4 张候选。" },
    { id: "g02", role: "assistant", name: "text2image", tool_calls: [{ name: "text2image" }], content: '{"prompt":"暖橙色调丰收氛围，南瓜燕麦粥特写，商业美食摄影，暖光","ratio":"1:1","n":4}' },
    { id: "g03", role: "tool", name: "text2image", content: "生成中 1/4…", attachments: [{ type: "image", label: "候选 1", w: 1, h: 1, hue: 28 }] },
    { id: "g04", role: "tool", name: "text2image", content: "生成中 4/4…", attachments: [{ type: "image", label: "候选 4", w: 1, h: 1, hue: 42 }] },
    { id: "g05", role: "tool", name: "text2image", content: "4 张候选全部生成完毕，内容安全检测通过", attachments: [
      { type: "image", label: "候选 1 · 暖光特写", w: 1, h: 1, hue: 28 },
      { type: "image", label: "候选 2 · 俯拍构图", w: 1, h: 1, hue: 16 },
      { type: "image", label: "候选 3 · 场景化摆盘", w: 1, h: 1, hue: 36 },
      { type: "image", label: "候选 4 · 暗调质感", w: 1, h: 1, hue: 8 },
    ] },
    { id: "g06", role: "ai", content: "已生成 4 张候选主图：候选 1 构图最稳、色调贴合；候选 3 场景感强适合详情页头图。已上传至素材库并提交人工验收，请选择上架主图。", attachments: [
      { type: "image", label: "候选 1 · 暖光特写", w: 1, h: 1, hue: 28 },
      { type: "image", label: "候选 2 · 俯拍构图", w: 1, h: 1, hue: 16 },
      { type: "image", label: "候选 3 · 场景化摆盘", w: 1, h: 1, hue: 36 },
      { type: "image", label: "候选 4 · 暗调质感", w: 1, h: 1, hue: 8 },
    ] },
  ],
  "thread-gen-vid": [
    { id: "v01", role: "ai", content: "开始制作产品宣传短视频：拆解脚本为 3 个分镜——产品特写开场（0-3s）、配料营养闪现（3-7s）、品牌收尾（7-10s），竖版 9:16。" },
    { id: "v02", role: "assistant", name: "write_storyboard", tool_calls: [{ name: "write_storyboard" }], content: '{"shots":3,"duration":10}' },
    { id: "v03", role: "tool", name: "write_storyboard", content: "分镜脚本已生成：3 镜、10s、每镜配转场与字幕文案" },
    { id: "v04", role: "assistant", name: "text2video", tool_calls: [{ name: "text2video" }], content: '{"style":"美食实拍感","ratio":"9:16","duration":10}' },
    { id: "v05", role: "tool", name: "text2video", content: "视频合成中：镜头 2/3…", attachments: [{ type: "video", label: "中间预览", w: 9, h: 16, duration: 4, hue: 200 }] },
    { id: "v06", role: "tool", name: "text2video", content: "成片渲染完成，附加字幕与背景音乐", attachments: [
      { type: "video", label: "成片 · 含字幕与 BGM", w: 9, h: 16, duration: 10, hue: 200 },
    ] },
    { id: "v07", role: "ai", content: "10 秒竖版宣传视频已完成：热气特写开场、四色配料闪现、品牌 Logo 收尾。质检无黑帧/花屏，已交付人工验收，验收通过后将推送至抖音与视频号。" },
  ],
}

export const demoMessagesOld2 = [
  { id: "o01", role: "ai", content: "开始处理差评回复任务：昨日新增 2 条一星差评，需要拟回复话术。" },
  { id: "o02", role: "assistant", name: "list_reviews", tool_calls: [{ name: "list_reviews" }], content: '{"rating":1,"since":"yesterday"}' },
  { id: "o03", role: "tool", name: "list_reviews", content: '2 条差评：①物流致蛋液破损 ②口感不合预期' },
  { id: "o04", role: "ai", content: "两条差评原因不同：前者需致歉+补偿指引，后者需感谢反馈+说明配方。分别拟话术。" },
  { id: "o05", role: "assistant", name: "draft_reply", tool_calls: [{ name: "draft_reply" }], content: '{"style":"empathetic","policy":"cs-v2"}' },
  { id: "o06", role: "tool", name: "draft_reply", content: '2 条回复话术已生成' },
  { id: "o07", role: "ai", content: "话术已按客服规范 v2 生成，并完成敏感词自检：通过。提交人工验收，确认后自动回复。" },
]
export const demoMessagesFor = (threadId: string | null) =>
  threadId === "thread-demo-old2" ? demoMessagesOld2 : demoMessages
