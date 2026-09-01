"""Infrastructure-level shared constants."""

# Android 系统包 / 桌面 launcher 前缀。
# 判断"当前前台是否业务 App"时，命中这些前缀的包应视为系统界面（桌面/状态栏/输入法），
# 不应被当作当前业务 App。覆盖主流 Android（com.android.*）与国产厂商
# （华为 com.huawei.* / 小米 com.miui.* / OPPO com.coloros.*, com.oplus.* / vivo com.vivo.*）。
SYSTEM_PACKAGE_PREFIXES: tuple[str, ...] = (
    "com.android.systemui",
    "com.android.launcher",
    "com.huawei.android.launcher",
    "com.huawei.systemui",
    "com.miui.home",
    "com.miui.systemui",
    "com.coloros.launcher",
    "com.oplus.launcher",
    "com.vivo.launcher",
    "com.google.android.inputmethod",
    "android",
)

# 明确不属于任何系统前缀、但仍应视为系统界面的完整包名（is_system_package 兜底）。
SYSTEM_PACKAGE_EXACT: frozenset[str] = frozenset(
    {
        "unknown",
        "error",
    }
)


def is_system_package(pkg: str | None) -> bool:
    """Return True if ``pkg`` is a system/launcher package (not a business app)."""
    if not pkg:
        return True
    if pkg in SYSTEM_PACKAGE_EXACT:
        return True
    return pkg.startswith(SYSTEM_PACKAGE_PREFIXES)


# ====================== Database Infrastructure Constants ======================

# Extra columns for agent_activities table (schema fallback for existing DBs)
# Added via ALTER TABLE in resource_manager.py during initialization
AGENT_ACTIVITY_EXTRA_COLUMNS = [
    ("run_id", "VARCHAR(100)"),
    ("llm_calls", "INTEGER"),
    ("input_tokens", "INTEGER"),
    ("output_tokens", "INTEGER"),
    ("tool_errors", "INTEGER"),
]
