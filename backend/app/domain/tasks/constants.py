"""自主值守任务队列常量（域级归口，禁止散落业务文件）。"""

from __future__ import annotations

# ── 状态机 ────────────────────────────────────────────────

QUEUE_STATUSES = (
    "proposed",
    "pending",
    "in_progress",
    "self_checked",
    "waiting_acceptance",
    "completed",
    "failed",
    "cancelled",
)

# 合法状态转移（所有写操作必须受此约束）
QUEUE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "proposed": ("pending", "cancelled"),
    "pending": ("in_progress", "cancelled"),
    "in_progress": ("self_checked", "failed", "pending", "cancelled"),
    "self_checked": ("waiting_acceptance", "in_progress"),
    "waiting_acceptance": ("completed", "pending"),
    # failed 非绝对终态：允许人工重跑回队（失败链自愈的唯一路径）
    "failed": ("pending", "cancelled"),
}

# 结果字段截断长度（task_data.last_result）
RESULT_MAX = 500

# 优先级 → 排序权重（dispatch/list 排序：priority → due → category）
PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

# reconcile 回队上限：超过即转 failed（防毒任务无限循环）
REQUEUE_LIMIT = 3

# 派发熔断上限：系统认领次数达到阈值仍未推进终态 → 强制 failed。
# 覆盖不经 reconcile 的重试环（如派发失败回滚→下一拍重认领）；
# 经 reconcile 的环由 REQUEUE_LIMIT 先行收敛（正常序列下 4 次认领即达终态）。
DISPATCH_CLAIM_CIRCUIT_LIMIT = 5

# ── 外部事件摄取 ──────────────────────────────────────────

# spec 必填字段（缺失即 EventSpecError）
INGESTION_REQUIRED_FIELDS = ("title",)

# ── 连续运行时（runtime/） ────────────────────────────────

# 事件丢失兜底：supervisor 最长 60s 必醒来重扫一次队列
DRAIN_IDLE_TIMEOUT_SECONDS = 60.0
# 稳态兜底扫描间隔（秒）——即使没有任何事件也周期性 reconcile
RECONCILE_INTERVAL_SECONDS = 300.0
# 进程重启后：上一进程遗留的 running activity 一律视为死亡（in-process run 不可能跨进程存活）
RESTART_GRACE_SECONDS = 0.0
# 稳态：running 超过该时长且无 pending HumanRequest → 判死（watchdog 截止 + 余量）
STALE_RUNNING_MINUTES = 35.0
# 单 run 硬截止（看门狗）：网络抖动/工具挂起导致 run 永不终态时强制取消
WAKEUP_RUN_DEADLINE_SECONDS = 1800.0
# 配额熔断：quota_exhausted 后暂停值守派发的时长（分钟）。
# 周配额重置通常在整点/午夜，15 分钟粒度的重试足够贴合且不会烧 429。
QUOTA_COOLDOWN_MINUTES = 15.0

# run 终态集合（reconcile 据此判定"run 已死"）
RUN_TERMINAL_STATUSES = frozenset({
    "done",
    "cancelled",
    "failed",
    "quota_exhausted",
    "error",
})
# 这些状态下任务现场仍在推进/等待，不得回队
RUN_SKIP_STATUSES = frozenset({"running", "stopping", "human_interrupt"})

WORKFLOW_RETRY_LIMIT = 2

# 这些错误重试也不会好：内容审查拦截 / 配置缺模型等确定性失败
# failed 任务自动重跑预算（仅瞬时错误，审查/配置类永不）；耗时 10 分钟退避
FAILED_AUTO_RETRY_BUDGET = 1
FAILED_AUTO_RETRY_DELAY_SECONDS = 600.0

NON_RETRYABLE_ERROR_MARKERS = (
    "DataInspectionFailed",
    "must provide a model parameter",
    "invalid_request_error",
)

WORKFLOW_RETRY_DELAY_SECONDS = 60.0
