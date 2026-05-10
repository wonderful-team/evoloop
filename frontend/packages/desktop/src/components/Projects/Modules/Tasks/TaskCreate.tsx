import React, { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { TasksService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"

interface TaskCreateProps {
  projectId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export const TaskCreate: React.FC<TaskCreateProps> = ({
  projectId,
  open,
  onOpenChange,
  onSuccess,
}) => {
  const { t } = useTranslation()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [priority, setPriority] = useState("2") // Default to normal
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      toast.error(t("projects.create.errorNameRequired"))
      return
    }

    setIsSubmitting(true)
    try {
      await TasksService.createTask({
        requestBody: {
          project_id: projectId,
          task_title: title,
          task_desc: description,
          priority: parseInt(priority, 10),
          status: 1, // Pending
        } as any,
      })
      toast.success(t("projects.create.success"))
      setTitle("")
      setDescription("")
      setPriority("2")
      onSuccess()
      onOpenChange(false)
    } catch (error) {
      console.error(error)
      toast.error(t("common.error.unknown"))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t("projects.tasks.create")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="title">{t("projects.tasks.columns.title")}</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("projects.tasks.columns.title")}
                autoFocus
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="priority">{t("projects.tasks.columns.priority")}</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger id="priority">
                  <SelectValue placeholder={t("projects.tasks.columns.priority")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">{t("projects.tasks.priorityLabel.low")}</SelectItem>
                  <SelectItem value="2">{t("projects.tasks.priorityLabel.normal")}</SelectItem>
                  <SelectItem value="3">{t("projects.tasks.priorityLabel.high")}</SelectItem>
                  <SelectItem value="4">{t("projects.tasks.priorityLabel.urgent")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">{t("projects.details.description")}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("projects.details.description")}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t("common.processing") : t("common.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
