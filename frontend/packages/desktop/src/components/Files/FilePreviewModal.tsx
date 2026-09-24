import {useEffect, useState} from "react"
import {useTranslation} from "react-i18next"
import {AppSheet} from "@/components/Common/AppSheet"
import {FilePreview, type FilePreviewProps} from "./FilePreview"

export interface FilePreviewModalProps extends Omit<FilePreviewProps, "file"> {
  file: { path: string; name: string } | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FilePreviewModal({
  projectId,
  file,
  open,
  onOpenChange,
}: FilePreviewModalProps) {
  const { t } = useTranslation()
  const [shouldRender, setShouldRender] = useState(false)

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => setShouldRender(true), 50)
      return () => clearTimeout(timer)
    }
    setShouldRender(false)
  }, [open])

  return (
    <AppSheet
      open={open}
      onOpenChange={onOpenChange}
      title={file?.name || t("files.previewTitle")}
      subtitle={typeof file?.path === "string" ? file.path : undefined}
      hideHeader
    >
      <div className="flex-1 overflow-hidden min-h-0 relative">
        {shouldRender ? (
          <FilePreview projectId={projectId} file={file} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary mr-3" />
            {t("common.loading")}
          </div>
        )}
      </div>
    </AppSheet>
  )
}
