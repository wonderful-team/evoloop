/**
 * MarkdownEditor - A markdown editor with live preview using Monaco Editor
 */

import {Button} from "@evoloop/shared/components/ui/button"
import {cn} from "@evoloop/shared/lib/utils"
import {Edit3, Eye, SplitSquareHorizontal} from "lucide-react"
import {useState} from "react"
import {useTranslation} from "react-i18next"
import {MarkdownRenderer} from "./MarkdownRenderer"
import MonacoEditor from "./MonacoEditor"

// Markdown Preview Component
function MarkdownPreview({ content }: { content: string }) {
  const { t } = useTranslation()

  return (
    <div className="p-4 overflow-auto h-full">
      <MarkdownRenderer content={content || t("learning.editor.noContent")} />
    </div>
  )
}

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

type ViewMode = "edit" | "preview" | "split"

export function MarkdownEditor({
  value,
  onChange,
  placeholder,
  className,
}: MarkdownEditorProps) {
  const { t } = useTranslation()
  const [viewMode, setViewMode] = useState<ViewMode>("preview")

  return (
    <div
      className={cn(
        "flex flex-col h-full border rounded-xl bg-background overflow-hidden",
        className,
      )}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 border-b border-border bg-muted/30 shrink-0">
        <div className="flex items-center gap-1">
          {/* Placeholder for potential future toolbar items */}
        </div>

        <div className="flex items-center gap-1 bg-background rounded-lg p-0.5 border">
          <Button
            variant={viewMode === "edit" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5"
            onClick={() => setViewMode("edit")}
          >
            <Edit3 className="h-3.5 w-3.5" />
            {t("common.edit")}
          </Button>
          <Button
            variant={viewMode === "split" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5"
            onClick={() => setViewMode("split")}
          >
            <SplitSquareHorizontal className="h-3.5 w-3.5" />
            {t("common.split")}
          </Button>
          <Button
            variant={viewMode === "preview" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5"
            onClick={() => setViewMode("preview")}
          >
            <Eye className="h-3.5 w-3.5" />
            {t("common.preview")}
          </Button>
        </div>
      </div>

      {/* Editor Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Editor */}
        {(viewMode === "edit" || viewMode === "split") && (
          <div
            className={cn(
              "flex flex-col",
              viewMode === "split" ? "w-1/2 border-r" : "w-full",
            )}
          >
            <MonacoEditor
              language="markdown"
              value={value}
              onChange={onChange}
              placeholder={placeholder}
            />
          </div>
        )}

        {/* Preview */}
        {(viewMode === "preview" || viewMode === "split") && (
          <div
            className={cn(
              "flex flex-col bg-background",
              viewMode === "split" ? "w-1/2" : "w-full",
            )}
          >
            <MarkdownPreview content={value} />
          </div>
        )}
      </div>
    </div>
  )
}
