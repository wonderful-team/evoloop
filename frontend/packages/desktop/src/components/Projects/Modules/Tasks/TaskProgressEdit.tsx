import { useMutation } from "@tanstack/react-query"
import { Check, Loader2, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { SubtasksService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"

interface TaskProgressEditProps {
  projectId: number
  taskId: number
  currentProgress: number
  onSuccess?: () => void
}

export function TaskProgressEdit({
  projectId,
  taskId,
  currentProgress,
  onSuccess,
}: TaskProgressEditProps) {
  const { t } = useTranslation()
  const [isEditing, setIsEditing] = useState(false)
  const [progress, setProgress] = useState(currentProgress)

  const mutation = useMutation({
    mutationFn: async (newProgress: number) => {
      // 根据进度自动推断状态
      let status = "pending"
      if (newProgress === 100) {
        status = "completed"
      } else if (newProgress > 0) {
        status = "in_progress"
      }

      const res: any = await SubtasksService.updateTaskProgress({
        projectId,
        taskId,
        requestBody: {
          progress: newProgress,
          status,
        },
      })
      return res
    },
    onSuccess: () => {
      toast.success(t("projects.tasks.progressUpdated", "Progress updated"))
      setIsEditing(false)
      onSuccess?.()
    },
    onError: () => {
      toast.error(t("projects.tasks.progressUpdateFailed", "Failed to update progress"))
    },
  })

  const handleSave = () => {
    mutation.mutate(progress)
  }

  const handleCancel = () => {
    setProgress(currentProgress)
    setIsEditing(false)
  }

  // 显示模式
  if (!isEditing) {
    return (
      <button
        onClick={() => setIsEditing(true)}
        className="flex items-center gap-2 group"
        title={t("projects.tasks.clickToEdit", "Click to edit")}
      >
        <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${currentProgress}%` }}
          />
        </div>
        <span className="text-sm font-medium w-10 text-right group-hover:text-primary transition-colors">
          {Math.round(currentProgress)}%
        </span>
      </button>
    )
  }

  // 编辑模式
  return (
    <div className="flex items-center gap-2 animate-in fade-in slide-in-from-top-1">
      <Input
        type="number"
        min={0}
        max={100}
        step={5}
        value={progress}
        onChange={(e) => setProgress(Number(e.target.value))}
        className="w-20 h-8"
      />
      <span className="text-sm font-medium w-10">{progress}%</span>
      
      <div className="flex gap-1">
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={handleSave}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5 text-green-600" />
          )}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={handleCancel}
          disabled={mutation.isPending}
        >
          <X className="h-3.5 w-3.5 text-red-600" />
        </Button>
      </div>
    </div>
  )
}
