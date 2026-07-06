import { Badge } from "@evoloop/shared/components/ui/badge"
import { Card } from "@evoloop/shared/components/ui/card"
import { FileCode, FileImage, FileText, Folder, Package } from "lucide-react"
import { useTranslation } from "react-i18next"

interface Artifact {
  id: number
  name: string
  type: string
  status: string
  path?: string
}

interface ArtifactsListProps {
  artifacts: Artifact[]
}

export function ArtifactsList({ artifacts }: ArtifactsListProps) {
  const { t } = useTranslation()

  if (!artifacts || artifacts.length === 0) return null

  const getIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case "image":
        return <FileImage className="h-4 w-4 text-blue-500" />
      case "code":
        return <FileCode className="h-4 w-4 text-amber-500" />
      case "directory":
        return <Folder className="h-4 w-4 text-yellow-500" />
      default:
        return <FileText className="h-4 w-4 text-slate-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "created":
        return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800"
      case "modified":
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800"
      case "deleted":
        return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800"
      default:
        return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400"
    }
  }

  return (
    <div className="flex flex-col gap-2 mb-4 w-full">
      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 ml-1">
        <Package className="h-3 w-3" />
        {t("chat.artifacts.title")}
      </div>

      <div className="grid grid-cols-1 gap-2">
        {artifacts.map((artifact) => (
          <Card
            key={artifact.id}
            className="flex items-center p-3 gap-3 hover:bg-muted/50 transition-colors border-dashed"
          >
            <div className="shrink-0 p-2 bg-background rounded-md border shadow-sm">
              {getIcon(artifact.type)}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span
                  className="text-sm font-medium truncate"
                  title={artifact.name}
                >
                  {artifact.name}
                </span>
                <Badge
                  variant="outline"
                  className={`text-[10px] px-1.5 py-0 h-5 font-normal border ${getStatusColor(artifact.status)}`}
                >
                  {artifact.status}
                </Badge>
              </div>
              <div
                className="text-xs text-muted-foreground truncate font-mono opacity-80"
                title={artifact.path}
              >
                {artifact.path || artifact.name}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
