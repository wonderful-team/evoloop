import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent } from "@evoloop/shared/components/ui/card"
import { cn } from "@evoloop/shared/lib/utils"
import { FileText, Loader2, Upload, X } from "lucide-react"
import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"

interface UploadButtonProps {
  onUpload: (file: File) => void
  isUploading?: boolean
  accept?: string
}

const ALLOWED_TYPES = [".docx", ".doc", ".pdf", ".xlsx", ".xls", ".md", ".txt"]

export function UploadButton({
  onUpload,
  isUploading = false,
  accept = ALLOWED_TYPES.join(","),
}: UploadButtonProps) {
  const { t } = useTranslation()
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)

      const files = e.dataTransfer.files
      if (files.length > 0) {
        const file = files[0]
        if (validateFile(file)) {
          setSelectedFile(file)
        }
      }
    },
    [t],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        const file = files[0]
        if (validateFile(file)) {
          setSelectedFile(file)
        }
      }
    },
    [t],
  )

  const validateFile = (file: File): boolean => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`
    if (!ALLOWED_TYPES.includes(extension)) {
      alert(
        t("requirements.upload.invalidType", {
          types: ALLOWED_TYPES.join(", "),
        }),
      )
      return false
    }
    if (file.size > 50 * 1024 * 1024) {
      alert(t("requirements.upload.tooLarge"))
      return false
    }
    return true
  }

  const handleUpload = () => {
    if (selectedFile) {
      onUpload(selectedFile)
      setSelectedFile(null)
    }
  }

  const handleClear = () => {
    setSelectedFile(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return t("common.fileSizeB", { size: 0 })
    const k = 1024
    const units = ["B", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    const unit = units[i] || "GB"
    const value = parseFloat((bytes / k ** i).toFixed(2))
    if (unit === "B") return t("common.fileSizeB", { size: value })
    if (unit === "KB") return t("common.fileSizeKB", { size: value })
    if (unit === "MB") return t("common.fileSizeMB", { size: value })
    return `${value} ${unit}`
  }

  return (
    <div className="space-y-4">
      <Card
        className={cn(
          "border-2 border-dashed transition-colors",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50",
          selectedFile && "border-solid",
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <CardContent className="p-6">
          {!selectedFile ? (
            <div className="text-center">
              <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                <Upload className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-sm font-medium mb-1">
                {t("requirements.upload.title")}
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                {t("requirements.upload.dragDrop")}
              </p>
              <p className="text-xs text-muted-foreground/70 mb-4">
                {t("requirements.upload.supportedTypes")}
                {t("common.colon")}{" "}
                {t("requirements.upload.supportedTypesList")}
              </p>
              <label>
                <input
                  type="file"
                  className="hidden"
                  accept={accept}
                  onChange={handleFileSelect}
                  disabled={isUploading}
                />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isUploading}
                  asChild
                >
                  <span>
                    {isUploading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                        {t("common.uploading")}
                      </>
                    ) : (
                      <>
                        <FileText className="h-4 w-4 mr-1" />
                        {t("common.selectFile")}
                      </>
                    )}
                  </span>
                </Button>
              </label>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(selectedFile.size)}
                  </p>
                </div>
                <button
                  onClick={handleClear}
                  className="p-1 hover:bg-muted rounded"
                  disabled={isUploading}
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  onClick={handleClear}
                  disabled={isUploading}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  size="sm"
                  className="flex-1"
                  onClick={handleUpload}
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      {t("common.uploading")}
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-1" />
                      {t("common.upload")}
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
