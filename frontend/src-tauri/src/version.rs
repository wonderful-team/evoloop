// =============================================================================
// EvoLoop 版本信息模块
// =============================================================================

use serde::Serialize;

/// 应用版本号，从 Cargo.toml 读取
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// 应用名称，从 Cargo.toml 读取
pub const APP_NAME: &str = env!("CARGO_PKG_NAME");

/// 构建号 (每次 CI/CD 构建递增)
pub const BUILD_NUMBER: &str = match option_env!("BUILD_NUMBER") {
    Some(v) => v,
    None => "1",
};

/// 构建时间 (格式: YYYYMMDDHHMMSS)
pub const BUILD_TIME: &str = match option_env!("BUILD_TIME") {
    Some(v) => v,
    None => "",
};

/// Git Commit Hash (短格式)
pub const GIT_COMMIT: &str = match option_env!("GIT_COMMIT") {
    Some(v) => v,
    None => "unknown",
};

/// 版本阶段: alpha|beta|rc|stable
pub const RELEASE_STAGE: &str = match option_env!("RELEASE_STAGE") {
    Some(v) => v,
    None => "production",
};

/// 完整版本字符串
pub const FULL_VERSION: &str = match option_env!("EVOLOOP_FULL_VERSION") {
    // 默认值：无法从单一 const 拼接，这里用占位符，运行时通过 VersionInfo::full_version 获取
    Some(v) => v,
    None => "",
};

/// 版本信息结构体
#[derive(Debug, Clone, Serialize)]
pub struct VersionInfo {
    pub version: String,
    pub build_number: String,
    pub build_time: String,
    pub git_commit: String,
    pub stage: String,
    pub full_version: String,
}

impl VersionInfo {
    /// 创建版本信息实例
    pub fn new() -> Self {
        Self::from_env()
    }

    /// 从环境变量创建 (用于 CI/CD 环境)
    pub fn from_env() -> Self {
        let version = std::env::var("APP_VERSION")
            .unwrap_or_else(|_| VERSION.to_string());
        let build_number = std::env::var("BUILD_NUMBER")
            .unwrap_or_else(|_| BUILD_NUMBER.to_string());
        let build_time = std::env::var("BUILD_TIME")
            .unwrap_or_else(|_| BUILD_TIME.to_string());
        let git_commit = std::env::var("GIT_COMMIT")
            .unwrap_or_else(|_| GIT_COMMIT.to_string());
        let stage = std::env::var("RELEASE_STAGE")
            .unwrap_or_else(|_| RELEASE_STAGE.to_string());
        let full_version = format!("{}+{} ({})", version, build_number, git_commit);

        Self {
            version,
            build_number,
            build_time,
            git_commit,
            stage,
            full_version,
        }
    }
}

impl Default for VersionInfo {
    fn default() -> Self {
        Self::new()
    }
}

/// 获取版本信息
#[tauri::command]
pub fn get_version_info() -> VersionInfo {
    VersionInfo::from_env()
}

/// 获取当前版本号
#[tauri::command]
pub fn get_version() -> String {
    VERSION.to_string()
}

/// 检查是否为特定阶段版本
#[tauri::command]
pub fn is_stage(stage: &str) -> bool {
    RELEASE_STAGE.eq_ignore_ascii_case(stage)
}

/// 比较版本号
/// 返回值: -1 (current < target), 0 (equal), 1 (current > target)
#[tauri::command]
pub fn compare_versions(current: &str, target: &str) -> i8 {
    match compare_version_strings(current, target) {
        std::cmp::Ordering::Less => -1,
        std::cmp::Ordering::Equal => 0,
        std::cmp::Ordering::Greater => 1,
    }
}

/// 检查是否需要更新
#[tauri::command]
pub fn needs_update(current: &str, latest: &str) -> bool {
    compare_version_strings(current, latest) == std::cmp::Ordering::Less
}

/// 内部函数: 比较版本字符串
fn compare_version_strings(v1: &str, v2: &str) -> std::cmp::Ordering {
    let parts1: Vec<u32> = v1.split('.')
        .filter_map(|s| s.parse().ok())
        .collect();
    let parts2: Vec<u32> = v2.split('.')
        .filter_map(|s| s.parse().ok())
        .collect();

    let max_len = std::cmp::max(parts1.len(), parts2.len());

    for i in 0..max_len {
        let p1 = parts1.get(i).copied().unwrap_or(0);
        let p2 = parts2.get(i).copied().unwrap_or(0);

        match p1.cmp(&p2) {
            std::cmp::Ordering::Equal => continue,
            other => return other,
        }
    }

    std::cmp::Ordering::Equal
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compare_versions() {
        assert_eq!(compare_version_strings("1.0.0", "1.0.0"), std::cmp::Ordering::Equal);
        assert_eq!(compare_version_strings("1.0.0", "1.0.1"), std::cmp::Ordering::Less);
        assert_eq!(compare_version_strings("1.1.0", "1.0.0"), std::cmp::Ordering::Greater);
        assert_eq!(compare_version_strings("2.0.0", "1.9.9"), std::cmp::Ordering::Greater);
    }

    #[test]
    fn test_needs_update() {
        assert!(needs_update("1.0.0", "1.0.1"));
        assert!(needs_update("1.0.0", "2.0.0"));
        assert!(!needs_update("1.0.1", "1.0.0"));
        assert!(!needs_update("1.0.0", "1.0.0"));
    }

    #[test]
    fn test_version_info() {
        let info = VersionInfo::new();
        assert!(!info.version.is_empty());
        assert!(!info.full_version.is_empty());
    }
}
