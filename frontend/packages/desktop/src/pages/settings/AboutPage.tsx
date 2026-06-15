/**
 * EvoLoop 关于页面
 *
 * 显示应用版本信息、检查更新、许可证等
 */

import {
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  FileText,
  Github,
  Globe,
  Info,
  RefreshCw,
  Shield,
} from "lucide-react"
import type React from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { VersionDialog, VersionDisplay } from "@/components/VersionDisplay"
import { useVersion } from "@/hooks/useVersion"
import { updateService } from "@/services/updateService"

/**
 * 关于页面组件
 */
export const AboutPage: React.FC = () => {
  const { t } = useTranslation()
  const [showVersionDialog, setShowVersionDialog] = useState(false)
  const { version, versionString, checkForUpdates, updateInfo, isChecking } =
    useVersion()

  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // 显示提示
  const showToast = (
    message: string,
    _type: "success" | "info" | "error" = "info",
  ) => {
    setToastMessage(message)
    setTimeout(() => setToastMessage(null), 3000)
  }

  // 处理检查更新
  const handleCheckUpdate = async () => {
    try {
      const result = await checkForUpdates()
      if (result.hasUpdate) {
        showToast(
          t("about.toast.newVersion", { version: result.latestVersion }),
          "success",
        )
      } else {
        showToast(t("about.toast.upToDate"), "success")
      }
    } catch (_error) {
      showToast(t("about.toast.checkFailed"), "error")
    }
  }

  // 处理立即更新
  const handleUpdateNow = async () => {
    if (updateInfo?.latestVersion) {
      await updateService.reportUpdateStatus(
        "download_start",
        updateInfo.latestVersion,
      )

      if (updateInfo.downloadUrl) {
        window.open(updateInfo.downloadUrl, "_blank")
        showToast(t("about.toast.openingDownload"), "info")
      } else {
        showToast(t("about.toast.downloadUnavailable"), "error")
      }
    }
  }

  // 处理稍后提醒 (跳过此版本)
  const handleSkipVersion = () => {
    if (updateInfo?.latestVersion) {
      updateService.skipVersion(updateInfo.latestVersion)
      showToast(t("about.toast.skipped"), "info")
    }
  }

  // 外部链接
  const externalLinks = [
    {
      icon: Globe,
      label: t("about.links.official"),
      href: "https://evoloop.cn",
      description: t("about.links.officialDesc"),
    },
    {
      icon: FileText,
      label: t("about.links.help"),
      href: "https://docs.evoloop.cn",
      description: t("about.links.helpDesc"),
    },
    {
      icon: Github,
      label: t("about.links.github"),
      href: "https://github.com/evoloop",
      description: t("about.links.githubDesc"),
    },
  ]

  // 法律信息
  const legalLinks = [
    { label: t("about.legal.userAgreement"), href: "#" },
    { label: t("about.legal.privacy"), href: "#" },
    { label: t("about.legal.openSource"), href: "#" },
  ]

  return (
    <div style={{ maxWidth: "768px", margin: "0 auto", padding: "32px 16px" }}>
      {/* Toast 提示 */}
      {toastMessage && (
        <div
          style={{
            position: "fixed",
            top: "16px",
            right: "16px",
            zIndex: 9999,
            padding: "12px 20px",
            borderRadius: "8px",
            backgroundColor: toastMessage.includes("失败")
              ? "#fef2f2"
              : "#f0fdf4",
            color: toastMessage.includes("失败") ? "#dc2626" : "#16a34a",
            boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
            animation: "slideIn 0.3s ease-out",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <CheckCircle2 style={{ width: "16px", height: "16px" }} />
            {toastMessage}
          </div>
        </div>
      )}

      {/* 页面标题 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          marginBottom: "24px",
        }}
      >
        <Info style={{ width: "24px", height: "24px", color: "#2563eb" }} />
        <h1 style={{ fontSize: "24px", fontWeight: "bold" }}>
          {t("about.title")}
        </h1>
      </div>

      {/* 版本信息卡片 */}
      <div
        style={{
          borderRadius: "16px",
          border: "1px solid #e5e7eb",
          backgroundColor: "#fff",
          marginBottom: "24px",
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "24px", borderBottom: "1px solid #f3f4f6" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div>
              <h2
                style={{
                  fontSize: "18px",
                  fontWeight: "600",
                  marginBottom: "4px",
                }}
              >
                {t("about.versionInfo.title")}
              </h2>
              <p style={{ fontSize: "14px", color: "#6b7280" }}>
                {t("about.versionInfo.desc")}
              </p>
            </div>
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "12px",
                background: "linear-gradient(135deg, #dbeafe, #eff6ff)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                style={{
                  fontSize: "20px",
                  fontWeight: "bold",
                  color: "#2563eb",
                }}
              >
                E
              </span>
            </div>
          </div>
        </div>

        <div style={{ padding: "24px" }}>
          {/* 版本号显示 */}
          <div
            onClick={() => setShowVersionDialog(true)}
            style={{
              padding: "16px",
              borderRadius: "12px",
              backgroundColor: "#f9fafb",
              cursor: "pointer",
              marginBottom: "24px",
            }}
          >
            <VersionDisplay variant="detailed" showCopy={true} />
          </div>

          {/* 更新检查按钮 */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div>
              <p style={{ fontSize: "14px", fontWeight: "500" }}>
                {t("about.update.title")}
              </p>
              <p style={{ fontSize: "12px", color: "#6b7280" }}>
                {updateInfo?.hasUpdate
                  ? t("about.update.newVersion", {
                      version: updateInfo.latestVersion,
                    })
                  : versionString}
              </p>
            </div>
            <button
              onClick={handleCheckUpdate}
              disabled={isChecking}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "8px 16px",
                borderRadius: "8px",
                border: "1px solid #e5e7eb",
                backgroundColor: "#fff",
                fontSize: "14px",
                cursor: isChecking ? "not-allowed" : "pointer",
                opacity: isChecking ? 0.6 : 1,
              }}
            >
              <RefreshCw
                style={{
                  width: "16px",
                  height: "16px",
                  animation: isChecking ? "spin 1s linear infinite" : undefined,
                }}
              />
              {isChecking
                ? t("about.update.checking")
                : t("about.update.checkUpdate")}
            </button>
          </div>

          {/* 更新提示 */}
          {updateInfo?.hasUpdate && (
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                borderRadius: "12px",
                backgroundColor: "#eff6ff",
                border: "1px solid #dbeafe",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "12px",
                }}
              >
                <RefreshCw
                  style={{
                    width: "20px",
                    height: "20px",
                    color: "#2563eb",
                    marginTop: "2px",
                  }}
                />
                <div style={{ flex: 1 }}>
                  <p
                    style={{
                      fontSize: "14px",
                      fontWeight: "500",
                      color: "#2563eb",
                    }}
                  >
                    {t("about.update.newVersion", {
                      version: updateInfo.latestVersion,
                    })}
                  </p>
                  {updateInfo.isForceUpdate && (
                    <p
                      style={{
                        fontSize: "12px",
                        color: "#ea580c",
                        marginTop: "4px",
                      }}
                    >
                      {t("about.update.forceUpdateWarning")}
                    </p>
                  )}
                  {updateInfo.releaseNotes && (
                    <p
                      style={{
                        fontSize: "12px",
                        color: "#6b7280",
                        marginTop: "8px",
                      }}
                    >
                      {updateInfo.releaseNotes}
                    </p>
                  )}
                  <div
                    style={{ display: "flex", gap: "8px", marginTop: "12px" }}
                  >
                    <button
                      onClick={handleUpdateNow}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                        padding: "8px 16px",
                        borderRadius: "8px",
                        border: "none",
                        backgroundColor: "#2563eb",
                        color: "#fff",
                        fontSize: "14px",
                        cursor: "pointer",
                      }}
                    >
                      <Download style={{ width: "16px", height: "16px" }} />
                      {t("about.update.updateNow")}
                    </button>
                    {!updateInfo.isForceUpdate && (
                      <button
                        onClick={handleSkipVersion}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "8px 16px",
                          borderRadius: "8px",
                          border: "none",
                          backgroundColor: "transparent",
                          color: "#6b7280",
                          fontSize: "14px",
                          cursor: "pointer",
                        }}
                      >
                        <Clock style={{ width: "16px", height: "16px" }} />
                        {t("about.update.remindLater")}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 外部链接卡片 */}
      <div
        style={{
          borderRadius: "16px",
          border: "1px solid #e5e7eb",
          backgroundColor: "#fff",
          marginBottom: "24px",
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "24px", borderBottom: "1px solid #f3f4f6" }}>
          <h2 style={{ fontSize: "18px", fontWeight: "600" }}>
            {t("about.links.title")}
          </h2>
          <p style={{ fontSize: "14px", color: "#6b7280" }}>
            {t("about.links.desc")}
          </p>
        </div>

        {externalLinks.map((link, index) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "16px 24px",
              textDecoration: "none",
              color: "inherit",
              borderBottom:
                index < externalLinks.length - 1
                  ? "1px solid #f3f4f6"
                  : undefined,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  backgroundColor: "#eff6ff",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <link.icon
                  style={{ width: "16px", height: "16px", color: "#2563eb" }}
                />
              </div>
              <div>
                <p style={{ fontSize: "14px", fontWeight: "500" }}>
                  {link.label}
                </p>
                <p style={{ fontSize: "12px", color: "#6b7280" }}>
                  {link.description}
                </p>
              </div>
            </div>
            <ExternalLink
              style={{ width: "16px", height: "16px", color: "#9ca3af" }}
            />
          </a>
        ))}
      </div>

      {/* 法律信息 */}
      <div
        style={{
          borderRadius: "16px",
          border: "1px solid #e5e7eb",
          backgroundColor: "#fff",
          marginBottom: "24px",
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "24px", borderBottom: "1px solid #f3f4f6" }}>
          <h2
            style={{
              fontSize: "18px",
              fontWeight: "600",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Shield style={{ width: "20px", height: "20px" }} />
            {t("about.legal.title")}
          </h2>
        </div>

        {legalLinks.map((link, index) => (
          <a
            key={link.label}
            href={link.href}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "16px 24px",
              textDecoration: "none",
              color: "inherit",
              borderBottom:
                index < legalLinks.length - 1 ? "1px solid #f3f4f6" : undefined,
            }}
          >
            <span style={{ fontSize: "14px" }}>{link.label}</span>
            <ChevronRight
              style={{ width: "16px", height: "16px", color: "#9ca3af" }}
            />
          </a>
        ))}
      </div>

      {/* 版权信息 */}
      <div
        style={{
          textAlign: "center",
          padding: "24px",
          fontSize: "12px",
          color: "#9ca3af",
        }}
      >
        <p>© 2024 EvoLoop. All rights reserved.</p>
        <p style={{ marginTop: "4px" }}>版本 {version.fullVersion}</p>
      </div>

      {/* 版本详情对话框 */}
      <VersionDialog
        open={showVersionDialog}
        onClose={() => setShowVersionDialog(false)}
      />

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

export default AboutPage
