import { cn } from "@evoloop/shared/lib/utils"
import {
  Code2,
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  MessageSquare,
  Music,
  Zap,
} from "lucide-react"
import type React from "react"
import { useTranslation } from "react-i18next"
import { EChartsArtifact } from "./Artifacts/EChartsArtifact"
import { HtmlArtifact } from "./Artifacts/HtmlArtifact"
import { MapArtifact } from "./Artifacts/MapArtifact"
import { ReactArtifact } from "./Artifacts/ReactArtifact"
import { TestReportCard } from "./Artifacts/TestReportCard"

interface Reference {
  id: string
  type:
    | "file"
    | "image"
    | "audio"
    | "message"
    | "artifact"
    | "changeset"
    | "skill"
  target_id: string
  target_name: string
  meta_data?: any
}

interface MessageReferencesProps {
  references: Reference[]
  onReferenceClick?: (ref: Reference) => void
  isUser?: boolean
}

export const MessageReferences: React.FC<MessageReferencesProps> = ({
  references,
  onReferenceClick,
  isUser = false,
}) => {
  const { t } = useTranslation()

  if (!references || references.length === 0) return null

  const artifacts = references.filter((r) => r.type === "artifact")
  const resources = references.filter((r) =>
    ["file", "image", "audio", "message", "skill", "changeset"].includes(
      r.type,
    ),
  )

  return (
    <div className="flex flex-col gap-4 mt-3 w-full animate-in fade-in slide-in-from-bottom-2 duration-500">
      {/* 1. Artifacts Rendering (Full Width) */}
      {artifacts.length > 0 && (
        <div className="flex flex-col gap-4">
          {artifacts.map((art) => {
            const artType = art.meta_data?.artifact_type
            let data = art.meta_data?.data || {}

            if (
              (!data || Object.keys(data).length === 0) &&
              art.meta_data?.content
            ) {
              const content = art.meta_data.content
              if (typeof content === "string") {
                const trimmed = content.trim()
                if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                  try {
                    data = JSON.parse(trimmed)
                  } catch {
                    data = { html: content }
                  }
                } else {
                  data = { html: content }
                }
              } else {
                data = { html: String(content) }
              }
            }

            if (data && typeof data === "object") {
              data = { title: art.target_name, ...data }
            }

            switch (artType) {
              case "echarts":
                return <EChartsArtifact key={art.id} data={data} />
              case "map":
                return <MapArtifact key={art.id} data={data} />
              case "html":
                return <HtmlArtifact key={art.id} data={data} />
              case "react":
                return <ReactArtifact key={art.id} data={data} />
              case "test_report":
                return <TestReportCard key={art.id} data={data as any} />
              default:
                return (
                  <div
                    key={art.id}
                    className="p-4 border border-dashed rounded-xl bg-muted/10 text-xs text-muted-foreground flex items-center gap-2"
                  >
                    <Code2 className="w-4 h-4" />
                    Unknown Artifact Type: {artType}
                  </div>
                )
            }
          })}
        </div>
      )}

      {/* 2. Resources Rendering (Chips/Cards) */}
      {resources.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {resources.map((res) => (
            <ResourceChip
              key={res.id}
              reference={res}
              onClick={() => onReferenceClick?.(res)}
              isUser={isUser}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const ResourceChip = ({
  reference,
  onClick,
  isUser = false,
}: {
  reference: Reference
  onClick: () => void
  isUser?: boolean
}) => {
  const { t } = useTranslation()

  const getIcon = () => {
    switch (reference.type) {
      case "file":
        return <FileText className="w-3.5 h-3.5" />
      case "image":
        return <ImageIcon className="w-3.5 h-3.5" />
      case "audio":
        return <Music className="w-3.5 h-3.5" />
      case "message":
        return <MessageSquare className="w-3.5 h-3.5" />
      case "skill":
        return <Zap className="w-3.5 h-3.5 text-amber-500" />
      case "changeset":
        return <Code2 className="w-3.5 h-3.5 text-purple-500" />
      default:
        return <ExternalLink className="w-3.5 h-3.5" />
    }
  }

  const getColors = () => {
    if (isUser) {
      return "bg-white/15 text-white border-white/25 hover:bg-white/25 dark:bg-black/20 dark:border-white/15"
    }
    switch (reference.type) {
      case "skill":
        return "bg-amber-500/10 text-amber-600 border-amber-200/50 dark:border-amber-800/50"
      case "message":
        return "bg-blue-500/10 text-blue-600 border-blue-200/50 dark:border-blue-800/50"
      case "changeset":
        return "bg-purple-500/10 text-purple-600 border-purple-200/50 dark:border-purple-800/50"
      default:
        return "bg-muted/30 text-muted-foreground border-border/40 hover:bg-muted/50 hover:border-border/80"
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] font-medium transition-all active:scale-95",
        getColors(),
      )}
    >
      {getIcon()}
      <span className="max-w-[180px] truncate">{reference.target_name}</span>
      {reference.type === "file" && (
        <Download className="w-3 h-3 opacity-40 ml-1" />
      )}
    </button>
  )
}
