/**
 * EvoLoop 版本显示组件
 *
 * 功能:
 * - 显示当前应用版本号
 * - 支持多种显示样式 (简洁/详细/徽章)
 * - 点击可复制版本信息
 * - 显示构建信息和 Git Commit
 */

import { Check, Copy, GitBranch, Info } from "lucide-react"
import type React from "react"
import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import versionInfo from "@/version.json"

interface VersionDisplayProps {
  /** 显示样式 */
  variant?: "simple" | "detailed" | "badge" | "minimal"
  /** 是否显示复制按钮 */
  showCopy?: boolean
  /** 自定义类名 */
  className?: string
  /** 点击版本号时的回调 */
  onClick?: () => void
}

/**
 * 版本显示组件
 */
export const VersionDisplay: React.FC<VersionDisplayProps> = ({
  variant = "simple",
  showCopy = true,
  className = "",
  onClick,
}) => {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()

    const versionText = `${versionInfo.version} (${versionInfo.gitCommit})`

    try {
      await navigator.clipboard.writeText(versionText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error("Failed to copy version:", err)
    }
  }, [])

  // 格式化构建时间
  const formatBuildTime = (timeStr: string): string => {
    if (!timeStr || timeStr.length !== 14) return "Unknown"

    const year = timeStr.slice(0, 4)
    const month = timeStr.slice(4, 6)
    const day = timeStr.slice(6, 8)
    const hour = timeStr.slice(8, 10)
    const minute = timeStr.slice(10, 12)

    return `${year}-${month}-${day} ${hour}:${minute}`
  }

  // 获取阶段颜色
  const getStageColor = (stage: string): string => {
    const colors: Record<string, string> = {
      alpha: "bg-orange-500/20 text-orange-400 border-orange-500/30",
      beta: "bg-blue-500/20 text-blue-400 border-blue-500/30",
      rc: "bg-purple-500/20 text-purple-400 border-purple-500/30",
      stable: "bg-green-500/20 text-green-400 border-green-500/30",
    }
    return colors[stage] || colors.alpha
  }

  // 简洁样式: v1.2.3
  if (variant === "minimal") {
    return (
      <span
        className={`text-xs text-muted-foreground font-mono ${className}`}
        onClick={onClick}
      >
        v{versionInfo.version}
      </span>
    )
  }

  // 徽章样式
  if (variant === "badge") {
    return (
      <div className={`inline-flex items-center gap-2 ${className}`}>
        <span className="px-2 py-0.5 text-xs font-medium bg-primary/10 text-primary rounded-full">
          v{versionInfo.version}
        </span>
        {versionInfo.stage !== "stable" && (
          <span
            className={`px-1.5 py-0.5 text-[10px] uppercase rounded border ${getStageColor(versionInfo.stage)}`}
          >
            {versionInfo.stage}
          </span>
        )}
      </div>
    )
  }

  // 详细样式
  if (variant === "detailed") {
    return (
      <div
        className={`inline-flex flex-col gap-1 p-3 rounded-lg bg-card border ${className}`}
        onClick={onClick}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold">
              v{versionInfo.version}
            </span>
            {versionInfo.stage !== "stable" && (
              <span
                className={`px-1.5 py-0.5 text-[10px] uppercase rounded border ${getStageColor(versionInfo.stage)}`}
              >
                {versionInfo.stage}
              </span>
            )}
          </div>
          {showCopy && (
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-md hover:bg-accent transition-colors"
              title={t("versionDisplay.copyTitle")}
            >
              {copied ? (
                <Check className="w-4 h-4 text-green-500" />
              ) : (
                <Copy className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
          )}
        </div>

        <div className="flex flex-col gap-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <GitBranch className="w-3.5 h-3.5" />
            <span className="font-mono">
              {versionInfo.gitCommit.slice(0, 7)}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5" />
            <span>Build {versionInfo.buildNumber}</span>
            <span>•</span>
            <span>{formatBuildTime(versionInfo.buildTime)}</span>
          </div>
        </div>
      </div>
    )
  }

  // 默认简洁样式
  return (
    <div
      className={`inline-flex items-center gap-2 text-sm text-muted-foreground ${className}`}
      onClick={onClick}
    >
      <span className="font-mono">v{versionInfo.version}</span>
      {versionInfo.stage !== "stable" && (
        <span
          className={`px-1.5 py-0 text-[10px] uppercase rounded border ${getStageColor(versionInfo.stage)}`}
        >
          {versionInfo.stage}
        </span>
      )}
      {showCopy && (
        <button
          onClick={handleCopy}
          className="p-1 rounded hover:bg-accent transition-colors"
          title="复制版本信息"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-green-500" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>
      )}
    </div>
  )
}

/**
 * 版本信息对话框
 */
export const VersionDialog: React.FC<{
  open: boolean
  onClose: () => void
}> = ({ open, onClose }) => {
  const { t } = useTranslation()
  if (!open) return null

  const formatBuildTime = (timeStr: string): string => {
    if (!timeStr || timeStr.length !== 14) return "Unknown"
    const year = timeStr.slice(0, 4)
    const month = timeStr.slice(4, 6)
    const day = timeStr.slice(6, 8)
    const hour = timeStr.slice(8, 10)
    const minute = timeStr.slice(10, 12)
    return `${year}-${month}-${day} ${hour}:${minute}`
  }

  const versionDetails = [
    { label: t("versionDisplay.version"), value: versionInfo.version },
    { label: t("versionDisplay.buildNumber"), value: versionInfo.buildNumber },
    { label: t("versionDisplay.stage"), value: versionInfo.stage },
    { label: "Git Commit", value: versionInfo.gitCommit },
    {
      label: t("versionDisplay.buildTime"),
      value: formatBuildTime(versionInfo.buildTime),
    },
    { label: t("versionDisplay.fullVersion"), value: versionInfo.fullVersion },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md p-6 rounded-xl bg-card border shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">
            {t("versionDisplay.aboutTitle")}
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-accent transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
            <span className="text-3xl font-bold text-primary">E</span>
          </div>
        </div>

        <div className="space-y-3 mb-6">
          {versionDetails.map(({ label, value }) => (
            <div
              key={label}
              className="flex justify-between items-center py-2 border-b border-border/50 last:border-0"
            >
              <span className="text-sm text-muted-foreground">{label}</span>
              <span className="text-sm font-mono">{value}</span>
            </div>
          ))}
        </div>

        <div className="text-center text-xs text-muted-foreground">
          <p>© 2024 EvoLoop. All rights reserved.</p>
          <p className="mt-1">
            <a
              href="https://evoloop.cn"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors"
            >
              {t("versionDisplay.visitWebsite")}
            </a>
            {" • "}
            <a
              href="https://docs.evoloop.cn"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors"
            >
              {t("versionDisplay.helpDocs")}
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}

export default VersionDisplay
