import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { File, FileArchive, Files, Loader2, Upload, X } from "lucide-react"
import { useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  KnowledgeBaseAPI,
  type ZipValidationResult,
} from "@/services/knowledgeService"

interface DocumentUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  collections: string[]
}

const DOC_TYPES = [
  { value: "doc", label: "Document" },
  { value: "code", label: "Code" },
  { value: "guide", label: "Guide" },
  { value: "api", label: "API Documentation" },
  { value: "design", label: "Design Document" },
  { value: "architecture", label: "Architecture Document" },
  { value: "requirement", label: "Requirement Document" },
]

export function DocumentUploadDialog({
  open,
  onOpenChange,
  collections,
}: DocumentUploadDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [activeTab, setActiveTab] = useState("single")
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [collection, setCollection] = useState("default")
  const [docType, setDocType] = useState("doc")
  const [isDragging, setIsDragging] = useState(false)
  const [zipValidation, setZipValidation] =
    useState<ZipValidationResult | null>(null)

  // Single/Bulk upload mutation
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (selectedFiles.length === 0) throw new Error("No files selected")

      if (
        selectedFiles.length === 1 &&
        !selectedFiles[0].name.endsWith(".zip")
      ) {
        // Single file
        return KnowledgeBaseAPI.uploadDocument(
          selectedFiles[0],
          collection,
          docType,
        )
      }
      if (
        selectedFiles.length === 1 &&
        selectedFiles[0].name.endsWith(".zip")
      ) {
        // ZIP import
        return KnowledgeBaseAPI.importZip(selectedFiles[0], collection, true)
      }
      // Bulk upload
      return KnowledgeBaseAPI.bulkUpload(selectedFiles, collection, docType)
    },
    onSuccess: (result) => {
      if (result.success) {
        toast.success(t("knowledge.uploadSuccess"))
        queryClient.invalidateQueries({ queryKey: ["knowledge-documents"] })
        queryClient.invalidateQueries({ queryKey: ["knowledge-collections"] })
        resetForm()
        onOpenChange(false)
      } else {
        toast.error(result.message || t("knowledge.uploadError"))
      }
    },
    onError: () => {
      toast.error(t("knowledge.uploadError"))
    },
  })

  const resetForm = () => {
    setSelectedFiles([])
    setCollection("default")
    setDocType("doc")
    setZipValidation(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files)
      setSelectedFiles(files)

      // Validate ZIP if single file
      if (files.length === 1 && files[0].name.endsWith(".zip")) {
        validateZip(files[0])
      }
    }
  }

  const validateZip = async (file: File) => {
    try {
      const validation = await KnowledgeBaseAPI.validateZip(file)
      setZipValidation(validation)
    } catch (_e) {
      setZipValidation({
        valid: false,
        error: "Validation failed",
      } as ZipValidationResult)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files) {
      const files = Array.from(e.dataTransfer.files)
      setSelectedFiles(files)

      if (files.length === 1 && files[0].name.endsWith(".zip")) {
        validateZip(files[0])
      }
    }
  }, [])

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const clearFiles = () => {
    setSelectedFiles([])
    setZipValidation(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
    setZipValidation(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const hasZipFile = selectedFiles.some((f) => f.name.endsWith(".zip"))
  const isBulkUpload = selectedFiles.length > 1

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.uploadTitle")}</DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="single">
              <File className="mr-2 h-4 w-4" />
              {t("knowledge.singleFile")}
            </TabsTrigger>
            <TabsTrigger value="bulk">
              <Files className="mr-2 h-4 w-4" />
              {t("knowledge.bulkUpload")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="single" className="space-y-4 py-4">
            {/* Single file upload */}
            {/* biome-ignore lint/a11y/useSemanticElements: Drop zone uses div for drag-and-drop file handling */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/50"
              }`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
              />

              {selectedFiles.length > 0 ? (
                <div className="flex items-center justify-center gap-2">
                  <File className="h-5 w-5 text-primary" />
                  <span className="font-medium">{selectedFiles[0].name}</span>
                  <span className="text-sm text-muted-foreground">
                    ({formatFileSize(selectedFiles[0].size)})
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      clearFiles()
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <>
                  <Upload className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm font-medium">
                    {t("knowledge.dropFile")}
                  </p>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="bulk" className="space-y-4 py-4">
            {/* Bulk/ZIP upload */}
            {/* biome-ignore lint/a11y/useSemanticElements: Drop zone uses div for drag-and-drop file handling */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-muted-foreground/50"
              }`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".zip,.md,.txt,.pdf,.docx,.html,.py,.js,.ts,.png,.jpg"
                onChange={handleFileSelect}
                className="hidden"
              />

              {selectedFiles.length > 0 ? (
                <div className="text-left space-y-2 max-h-40 overflow-auto">
                  {selectedFiles.map((file, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between bg-muted p-2 rounded"
                    >
                      <div className="flex items-center gap-2">
                        {file.name.endsWith(".zip") ? (
                          <FileArchive className="h-4 w-4 text-orange-500" />
                        ) : (
                          <File className="h-4 w-4 text-primary" />
                        )}
                        <span className="text-sm font-medium">{file.name}</span>
                        <span className="text-xs text-muted-foreground">
                          ({formatFileSize(file.size)})
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeFile(i)
                        }}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <Files className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm font-medium">
                    {t("knowledge.dropMultiple")}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {t("knowledge.bulkUploadHint")}
                  </p>
                </>
              )}
            </div>

            {/* ZIP validation result */}
            {zipValidation && (
              <div
                className={`p-3 rounded text-sm ${zipValidation.valid ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"}`}
              >
                {zipValidation.valid ? (
                  <div className="space-y-1">
                    <p className="font-medium text-green-700">
                      ✓ {t("knowledge.zipValid")}
                    </p>
                    <p className="text-green-600">
                      {t("knowledge.zipFilesCount", {
                        count: zipValidation.processable_files,
                      })}
                    </p>
                    <p className="text-green-600">
                      {t("knowledge.zipTotalSize", {
                        size: formatFileSize(zipValidation.total_size_bytes),
                      })}
                    </p>
                  </div>
                ) : (
                  <p className="text-red-700">✗ {zipValidation.error}</p>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Common settings */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>{t("knowledge.collection")}</Label>
            <Select value={collection} onValueChange={setCollection}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">default</SelectItem>
                {collections
                  ?.filter((p) => p !== "default")
                  .map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>

          {!hasZipFile && (
            <div className="space-y-2">
              <Label>{t("knowledge.docType")}</Label>
              <Select value={docType} onValueChange={setDocType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {t(`knowledge.docTypes.${type.value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* File count badge */}
        {selectedFiles.length > 1 && (
          <div className="flex items-center gap-2">
            <Badge variant="secondary">
              {t("knowledge.filesCount", { count: selectedFiles.length })}
            </Badge>
            {hasZipFile && (
              <Badge variant="outline">{t("knowledge.zipImport")}</Badge>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={selectedFiles.length === 0 || uploadMutation.isPending}
          >
            {uploadMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isBulkUpload ? t("knowledge.uploadBulk") : t("knowledge.upload")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
