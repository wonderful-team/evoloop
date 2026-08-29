"""客服值守渠道常量。

涵盖 config / scheduler / mcp_kf / wecom 各子模块的 duty 级常量，
供逻辑文件统一导入，避免常量散落在业务代码中。
"""

from __future__ import annotations

# ── config 相关 ──────────────────────────────────────────

# 全局值守配置在 SystemConfigService 中的 key
GLOBAL_DUTY_CONFIG_KEY = "CUSTOMER_SERVICE_DUTY"

# 值守轮巡缺省间隔（秒）。对齐全局扫描粒度（60s tick），
# 钳制 60~3600s（1~60 分钟）。
DUTY_INTERVAL = 60
DUTY_INTERVAL_MIN = 60
DUTY_INTERVAL_MAX = 3600

# 运营线（业务巡检）扫描频率（分钟）。固定系统常量，对齐 60s tick 粒度。
BUSINESS_POLL_INTERVAL = 1


# ── scheduler 相关 ───────────────────────────────────────

# 值守任务标记（params_template 里携带，dispatch 时用于分流）
DUTY_PARAM_MARKER = "duty_channel"

# 值守任务种类
KIND_WECOM = "wecom"  # 企微线（本地客户端 GUI 轮巡）
KIND_KF = "kf"  # 商城微信客服线（经 MCP 接入）
KIND_BUSINESS_POLL = "business_poll"  # 运营线：业务巡检

# 客服轮巡硬超时（电路断路器）：即使轮巡内部有未知卡点，
# 超过时限强制中断并释放全局锁，避免拖死整个值守调度器。
KF_POLL_HARD_TIMEOUT = 180.0

# 项目渠道名 → 值守任务种类（provision 按 active_channels 建任务）
CHANNEL_KIND_MAP = {
    "wecom": KIND_WECOM,
    "callback": KIND_KF,
}

# 值守任务种类 → DutyChannel 类名（run_duty_poll 按 kind 分流）
KIND_CHANNEL_MAP = {
    KIND_WECOM: "WeComDutyChannel",
    KIND_KF: "MpcKfChannel",
}


# ── mcp_kf 相关 ──────────────────────────────────────────

# 渠道在 project.json customer_service_duty.channels 里的 key
CHANNEL_KEY = "callback"

# 商城微信客服单条消息长度上限（复用 GUI 线实测值，取安全余量）
MAX_MESSAGE_LEN = 1500

# 单次 Agent delivery 上限（秒）：防止长任务/HITL 把 poll 无限阻塞。
DUTY_KF_DELIVERY_TIMEOUT = 60

# 单次 kf 工具调用超时：远程 MCP 会话偶发僵死时，避免把轮巡拖死。
KF_TOOL_TIMEOUT = 10.0

# 推送后首次轮巡拉空时的补轮巡延迟：覆盖远程"推送即断"后 keepalive 重连窗口。
KF_PUSH_RETRY_DELAY = 8.0


# ── wecom 相关 ───────────────────────────────────────────

# 企微单条消息长度上限（实测 5201 字符被拦截；取安全余量）
WECOM_MAX_MESSAGE_LEN = 1500

# 企微线单次 Agent delivery 上限（秒）：防止 HITL/长任务钉死 worker 线程。
DUTY_WECOM_DELIVERY_TIMEOUT = 60

# 系统横幅/导航文本，排除在联系人之外
BAD_CONTACTS = [
    "当前企业",
    "未认证",
    "认证",
    "星期一",
    "企业使用",
    "我的企业",
    "单聊",
    "群聊",
    "外部聊天",
    "内部聊天",
    "标记",
    "未读",
    "@我",
    "分组",
    "高级功能",
    "文档",
    "日程",
    "待办",
    "会议",
    "智能表格",
    "智能总结",
    "工作台",
    "通讯录",
    "微盘",
    "消息",
    "管理企业",
    "前往认证",
    "还不是你的联系人",
    "请发送",
    "申请验证",
]

# 企业微信 Mac 客户端 bundle id
WECOM_BUNDLE_ID = "com.tencent.WeWorkMac"

# 服务号/系统通知（不能回复）
SERVICE_ACCOUNTS = [
    "企业微信团队",
    "企业微信服务商助手",
    "登录操作通知",
    "管理企业",
    "当前企业未认证",
    "客户咨询",
    "文件传输助手",
]
