/**
 * EvoLoop 版本信息 Hook
 *
 * 功能:
 * - 获取当前应用版本信息
 * - 检查新版本 (连接到 MC 版本检查 API)
 * - 版本比较工具函数
 */

import i18n from "@evoloop/shared/i18n"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import versionInfo from "@/version.json"

/** 版本信息接口 */
export interface VersionInfo {
  version: string
  buildNumber: number
  buildTime: string
  gitCommit: string
  stage: "alpha" | "beta" | "rc" | "stable"
  fullVersion: string
}

/** 更新检查结果 */
export interface UpdateCheckResult {
  hasUpdate: boolean
  latestVersion?: string
  downloadUrl?: string
  releaseNotes?: string
  isForceUpdate?: boolean
}

// 本地版本信息
const localVersion: VersionInfo = versionInfo as VersionInfo

/**
 * 解析版本号为数字数组 [major, minor, patch]
 */
export function parseVersion(version: string): number[] {
  return version.split(".").map(Number)
}

/**
 * 比较两个版本号
 * @returns -1: v1 < v2, 0: v1 = v2, 1: v1 > v2
 */
export function compareVersions(v1: string, v2: string): number {
  const parts1 = parseVersion(v1)
  const parts2 = parseVersion(v2)

  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0
    const p2 = parts2[i] || 0

    if (p1 < p2) return -1
    if (p1 > p2) return 1
  }

  return 0
}

/**
 * 检查是否需要更新
 */
export function isUpdateNeeded(
  currentVersion: string,
  latestVersion: string,
): boolean {
  return compareVersions(currentVersion, latestVersion) < 0
}

/**
 * 获取版本显示字符串
 */
export function getVersionDisplayString(
  info: VersionInfo = localVersion,
): string {
  const stageTag = info.stage !== "stable" ? `-${info.stage}` : ""
  return i18n.t("versionDisplay.versionString", {
    version: info.version,
    stageTag,
    buildNumber: info.buildNumber,
  })
}

/**
 * 版本信息 Hook
 */
export function useVersion() {
  const { t } = useTranslation()
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResult | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /**
   * 检查新版本
   */
  const checkForUpdates = useCallback(async (): Promise<UpdateCheckResult> => {
    setIsChecking(true)
    setError(null)

    try {
      // 这里应该调用 MC 的版本检查 API
      const MEMBER_BASE_URL =
        import.meta.env.VITE_EVOCLOUD_MEMBER_BASE_URL ||
        "https://evoloop.cn/member"
      const response = await fetch(
        `${MEMBER_BASE_URL}/api/evoloop/version/check`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            app_type: "desktop",
            platform: getPlatform(),
            arch: getArchitecture(),
            version: localVersion.version,
            build_number: localVersion.buildNumber,
            device_id: await getDeviceId(),
            os_version: getOSVersion(),
          }),
        },
      )

      if (!response.ok) {
        throw new Error(
          t("about.toast.checkFailedWithStatus", {
            message: t("about.toast.checkFailed"),
            status: response.status,
          }),
        )
      }

      const result = await response.json()

      const updateResult: UpdateCheckResult = {
        hasUpdate: result.data?.has_update || false,
        latestVersion: result.data?.version,
        downloadUrl: result.data?.download_url,
        releaseNotes: result.data?.release_notes,
        isForceUpdate: result.data?.update_type === 2,
      }

      setUpdateInfo(updateResult)
      return updateResult
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : t("about.toast.checkFailed")
      setError(errorMsg)

      // 返回无更新的结果
      const noUpdate: UpdateCheckResult = { hasUpdate: false }
      setUpdateInfo(noUpdate)
      return noUpdate
    } finally {
      setIsChecking(false)
    }
  }, [])

  /**
   * 获取当前平台
   */
  const getPlatform = (): string => {
    const userAgent = navigator.userAgent.toLowerCase()

    if (userAgent.includes("win")) return "windows"
    if (userAgent.includes("mac")) return "macos"
    if (userAgent.includes("linux")) return "linux"

    return "unknown"
  }

  /**
   * 获取 CPU 架构
   * 使用 navigator.userAgentData 或从 User-Agent 推断
   */
  const getArchitecture = (): string => {
    // 优先使用新的 API (Chrome 90+)
    // @ts-expect-error
    if (navigator.userAgentData?.architecture) {
      // @ts-expect-error
      const arch = navigator.userAgentData.architecture
      // 映射到标准值
      const archMap: Record<string, string> = {
        x86: "x86_64",
        x86_64: "x86_64",
        arm: "arm64",
        arm64: "arm64",
        aarch64: "aarch64",
      }
      return archMap[arch] || "x86_64"
    }

    // 从 User-Agent 推断
    const userAgent = navigator.userAgent.toLowerCase()

    // Windows ARM
    if (userAgent.includes("arm64") || userAgent.includes("aarch64")) {
      return "arm64"
    }

    // macOS Apple Silicon
    if (
      userAgent.includes("mac") &&
      (userAgent.includes("arm64") || userAgent.includes("apple silicon"))
    ) {
      return "arm64"
    }

    // 默认 x86_64
    return "x86_64"
  }

  /**
   * 获取操作系统版本
   */
  const getOSVersion = (): string => {
    const userAgent = navigator.userAgent

    // Windows 版本解析
    const windowsMatch = userAgent.match(/Windows NT (\d+\.\d+)/)
    if (windowsMatch) {
      const versionMap: Record<string, string> = {
        "10.0": "10",
        "6.3": "8.1",
        "6.2": "8",
        "6.1": "7",
      }
      return versionMap[windowsMatch[1]] || windowsMatch[1]
    }

    // macOS 版本解析
    const macMatch = userAgent.match(/Mac OS X (\d+[._]\d+[._]?\d*)/)
    if (macMatch) {
      return macMatch[1].replace(/_/g, ".")
    }

    return ""
  }

  /**
   * 获取设备 ID (从本地存储或生成)
   */
  const getDeviceId = async (): Promise<string> => {
    // 从 localStorage 获取或生成新的设备 ID
    let deviceId = localStorage.getItem("evoloop_device_id")

    if (!deviceId) {
      deviceId = generateDeviceId()
      localStorage.setItem("evoloop_device_id", deviceId)
    }

    return deviceId
  }

  /**
   * 生成设备 ID
   */
  const generateDeviceId = (): string => {
    const timestamp = Date.now().toString(36)
    const random = Math.random().toString(36).substring(2, 10)
    return `evo_${timestamp}_${random}`
  }

  // 组件挂载时自动检查更新 (可选)
  useEffect(() => {
    // 可以在这里自动检查更新，或者根据配置决定
    // checkForUpdates();
  }, [checkForUpdates])

  return {
    // 本地版本信息
    version: localVersion,
    versionString: getVersionDisplayString(localVersion),

    // 更新检查
    checkForUpdates,
    updateInfo,
    isChecking,
    error,

    // 工具函数
    compareVersions,
    isUpdateNeeded,
  }
}

export default useVersion
