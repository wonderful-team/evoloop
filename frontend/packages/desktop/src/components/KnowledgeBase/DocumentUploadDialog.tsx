import { useState, useRef, useCallback } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Upload, File, X, Loader2, FileArchive, Files } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@evoloop/shared/components/ui/dialog"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { KnowledgeService, type ZipValidationResult } from "@/services/knowledgeService"

interface DocumentUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  projects: string[]
}

const DOC_TYPES = [
  { value: "doc", label: "文档" },
  { value: "code", label: "代码" },
  { value: "guide", label: "指南" },
  { value: "api", label: "API文档" },
  { value: "design", label: "设计文档" },
  { value: "architecture", label: "架构文档" },
  { value: "requirement", label: "需求文档" },
]

export function DocumentUploadDialog({
  open,
  onOpenChange,
  projects,
}: DocumentUploadDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [activeTab, setActiveTab] = useState("single")
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [project, setProject] = useState("default")
  const [docType, setDocType] = useState("doc")
  const [isDragging, setIsDragging] = useState(false)
  const [zipValidation, setZipValidation] = useState<ZipValidationResult | null>(null)

  // Single/Bulk upload mutation
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (selectedFiles.length === 0) throw new Error("No files selected")
      
      if (selectedFiles.length === 1 && !selectedFiles[0].name.endsWith('.zip')) {
        // Single file
        return KnowledgeService.uploadDocument(selectedFiles[0], project, docType)
      } else if (selectedFiles.length === 1 && selectedFiles[0].name.endsWith('.zip')) {
        // ZIP import
        return KnowledgeService.importZip(selectedFiles[0], project, true)
      } else {
        // Bulk upload
        return KnowledgeService.bulkUpload(selectedFiles, project, docType)
      }
    },
    onSuccess: (result) => {
      if (result.success) {
        toast.success(t("knowledge.uploadSuccess", "上传成功"))
        queryClient.invalidateQueries({ queryKey: ["knowledge-documents"] })
        queryClient.invalidateQueries({ queryKey: ["knowledge-projects"] })
        resetForm()
        onOpenChange(false)
      } else {
        toast.error(result.error || t("knowledge.uploadError", "上传失败"))
      }
    },
    onError: () => {
      toast.error(t("knowledge.uploadError", "上传失败"))
    },
  })

  const resetForm = () => {
    setSelectedFiles([])
    setProject("default")
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
      if (files.length === 1 && files[0].name.endsWith('.zip')) {
        validateZip(files[0])
      }
    }
  }

  const validateZip = async (file: File) => {
    try {
      const validation = await KnowledgeService.validateZip(file)
      setZipValidation(validation)
    } catch (e) {
      setZipValidation({ valid: false, error: "Validation failed" } as ZipValidationResult)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files) {
      const files = Array.from(e.dataTransfer.files)
      setSelectedFiles(files)
      
      if (files.length === 1 && files[0].name.endsWith('.zip')) {
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
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
    setZipValidation(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const hasZipFile = selectedFiles.some(f => f.name.endsWith('.zip'))
  const isBulkUpload = selectedFiles.length > 1

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.uploadTitle", "上传文档")}</DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="single">
              <File className="mr-2 h-4 w-4" />
              {t("knowledge.singleFile", "单文件")}
            </TabsTrigger>
            <TabsTrigger value="bulk">
              <Files className="mr-2 h-4 w-4" />
              {t("knowledge.bulkUpload", "批量/ZIP")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="single" className="space-y-4 py-4">
            {/* Single file upload */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"
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
                  <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); clearFiles() }}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <>
                  <Upload className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm font-medium">{t("knowledge.dropFile", "点击或拖放文件")}</p>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="bulk" className="space-y-4 py-4">
            {/* Bulk/ZIP upload */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"
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
                    <div key={i} className="flex items-center justify-between bg-muted p-2 rounded">
                      <div className="flex items-center gap-2">
                        {file.name.endsWith('.zip') ? <FileArchive className="h-4 w-4 text-orange-500" /> : <File className="h-4 w-4 text-primary" />}
                        <span className="text-sm font-medium">{file.name}</span>
                        <span className="text-xs text-muted-foreground">({formatFileSize(file.size)})</span>
                      </div>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); removeFile(i) }}>
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <Files className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm font-medium">{t("knowledge.dropMultiple", "选择多个文件或ZIP")}</p>
                  <p className="text-xs text-muted-foreground mt-1">支持批量上传或ZIP导入</p>
                </>
              )}
            </div>

            {/* ZIP validation result */}
            {zipValidation && (
              <div className={`p-3 rounded text-sm ${zipValidation.valid ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                {zipValidation.valid ? (
                  <div className="space-y-1">
                    <p className="font-medium text-green-700">✓ ZIP 有效</p>
                    <p className="text-green-600">包含 {zipValidation.processable_files} 个可处理文件</p>
                    <p className="text-green-600">总大小: {formatFileSize(zipValidation.total_size_bytes)}</p>
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
            <Label>{t("knowledge.project", "项目")}</Label>
            <Select value={project} onValueChange={setProject}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">default</SelectItem>
                {projects.filter(p => p !== "default").map((p) => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!hasZipFile && (
            <div className="space-y-2">
              <Label>{t("knowledge.docType", "文档类型")}</Label>
              <Select value={docType} onValueChange={setDocType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* File count badge */}
        {selectedFiles.length > 1 && (
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{selectedFiles.length} 个文件</Badge>
            {hasZipFile && <Badge variant="outline">ZIP 导入</Badge>}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel", "取消")}
          </Button>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={selectedFiles.length === 0 || uploadMutation.isPending}
          >
            {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isBulkUpload ? t("knowledge.uploadBulk", "批量上传") : t("knowledge.upload", "上传")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
