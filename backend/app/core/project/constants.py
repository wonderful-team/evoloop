"""Project subsystem constants."""

# ====================== Cache keys / TTL ======================
#: Cache key prefix for project-scoped data.
KEY_PREFIX = "project"
#: Default cache TTL for project-scoped data (seconds).
DEFAULT_TTL = 3600  # 1 hour

# ====================== Task execution statuses ======================
#: Task / subtask is waiting to be executed.
TASK_STATUS_PENDING = "pending"
#: Task / subtask is currently being executed.
TASK_STATUS_IN_PROGRESS = "in_progress"
#: Task / subtask finished successfully.
TASK_STATUS_COMPLETED = "completed"
#: Task / subtask failed.
TASK_STATUS_FAILED = "failed"

#: All statuses placeholder for list filters.
TASK_STATUS_FILTER_ALL = "all"

#: Canonical set of task statuses (used for validation / iteration).
TASK_STATUSES = {
    TASK_STATUS_PENDING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
}

# ====================== Task sync statuses ======================
#: Sync pending / not yet pushed to external system.
SYNC_STATUS_PENDING = "pending"
#: Sync completed / pushed to external system.
SYNC_STATUS_COMPLETED = "completed"
#: Sync failed.
SYNC_STATUS_FAILED = "failed"

#: Canonical set of sync statuses.
SYNC_STATUSES = {
    SYNC_STATUS_PENDING,
    SYNC_STATUS_COMPLETED,
    SYNC_STATUS_FAILED,
}

# ====================== Task priority ======================
#: Low priority.
TASK_PRIORITY_LOW = "low"
#: Medium priority.
TASK_PRIORITY_MEDIUM = "medium"
#: High priority.
TASK_PRIORITY_HIGH = "high"

#: Canonical set of task priorities.
TASK_PRIORITIES = {
    TASK_PRIORITY_LOW,
    TASK_PRIORITY_MEDIUM,
    TASK_PRIORITY_HIGH,
}
