import { Avatar, AvatarFallback } from "@evoloop/shared/components/ui/avatar"
import { Badge } from "@evoloop/shared/components/ui/badge"
import { Button } from "@evoloop/shared/components/ui/button"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Separator } from "@evoloop/shared/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import { useNavigate } from "@tanstack/react-router"
import {
  Activity,
  Calendar,
  Layers,
  ListTree,
  MessageSquare,
  Play,
  User,
  Zap,
} from "lucide-react"
import type React from "react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { TasksService } from "@/client/sdk.gen"
import { SubtaskSection } from "./SubtaskSection"

interface TaskDetailProps {
  taskId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onUpdate: () => void
}

export const TaskDetail: React.FC<TaskDetailProps> = ({
  taskId,
  open,
  onOpenChange,
}) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [task, setTask] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [executing, setExecuting] = useState(false)

  const loadTaskDetail = useCallback(async (id: number) => {
    console.log("Loading task detail for id:", id)
    setLoading(true)
    try {
      const res = (await TasksService.getTaskDetail({
        taskId: id,
      })) as any
      console.log("Task detail response:", res)
      if (res.code === 0) {
        setTask(res.data)
      } else if (res && (res.task_id || res.id)) {
        // Handle case where response is the task object directly
        setTask(res)
      } else if (res?.data && (res.data.task_id || res.data.id)) {
        // Handle case where code is missing or different but data structure exists
        setTask(res.data)
      } else {
        console.error("Task detail error or unexpected format:", res)
        // Fallback: try setting res if it's an object
        if (res && typeof res === "object") {
          setTask(res)
        }
      }
    } catch (error) {
      console.error("Failed to load task detail", error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (taskId && open) {
      loadTaskDetail(taskId)
    } else {
      setTask(null)
    }
  }, [taskId, open, loadTaskDetail])

  const handleExecuteTask = async () => {
    if (!taskId) return

    setExecuting(true)
    try {
      // Backend identifies user via Cookie Session.
      const res = (await TasksService.executeTask({
        taskId: taskId,
      })) as any

      if (res.status === "queued" && res.thread_id) {
        // Navigate to chat
        navigate({ to: "/chat", search: { thread_id: res.thread_id } })
        onOpenChange(false)
      } else {
        toast.error(res.message || t("common.error.unknown"))
      }
    } catch (error) {
      console.error("Execute task failed:", error)
      toast.error(t("projects.tasks.executeFailed"))
    } finally {
      setExecuting(false)
    }
  }

  if (!taskId) return null

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:w-[800px] sm:max-w-[800px] flex flex-col p-0">
        <SheetHeader className="p-6 pb-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex gap-2">
              <Badge variant={task?.status === 2 ? "default" : "secondary"}>
                {task?.status === 2
                  ? t("projects.tasks.statusLabel.inProgress")
                  : task?.status === 3
                    ? t("projects.tasks.statusLabel.completed")
                    : t("projects.tasks.statusLabel.pending")}
              </Badge>
              <Badge variant="outline">
                {task?.priority === 4
                  ? t("projects.tasks.priorityLabel.urgent")
                  : task?.priority === 3
                    ? t("projects.tasks.priorityLabel.high")
                    : task?.priority === 1
                      ? t("projects.tasks.priorityLabel.low")
                      : t("projects.tasks.priorityLabel.normal")}
              </Badge>
            </div>
          </div>
          <SheetTitle className="text-xl">
            {task?.task_title || t("common.loading")}
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="p-6 space-y-8">
            {loading ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground">
                {t("common.loading")}
              </div>
            ) : task ? (
              <Tabs defaultValue="details" className="w-full">
                <TabsList className="mb-4">
                  <TabsTrigger
                    value="details"
                    className="flex items-center gap-1"
                  >
                    <Layers className="h-4 w-4" />
                    {t("projects.details.tabs.details")}
                  </TabsTrigger>
                  <TabsTrigger
                    value="subtasks"
                    className="flex items-center gap-1"
                  >
                    <ListTree className="h-4 w-4" />
                    {t("projects.details.tabs.subtasks")}
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="details" className="space-y-8 mt-0">
                  {/* General Info */}
                  <div className="space-y-6">
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium text-muted-foreground">
                        {t("projects.details.description")}
                      </h3>
                      <div className="text-sm leading-relaxed whitespace-pre-wrap bg-muted/30 p-4 rounded-lg">
                        {task.task_desc || t("projects.details.noDescription")}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-1">
                        <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                          <User className="h-4 w-4" />{" "}
                          {t("projects.tasks.assignee")}
                        </h3>
                        <div className="flex items-center gap-2">
                          <Avatar className="h-6 w-6">
                            <AvatarFallback>
                              {task.assignee_member_name?.substring(0, 2) ||
                                t("projects.tasks.unassigned").substring(0, 2)}
                            </AvatarFallback>
                          </Avatar>
                          <p className="text-sm font-medium">
                            {task.assignee_member_name ||
                              t("projects.tasks.unassigned")}
                          </p>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                          <Calendar className="h-4 w-4" />{" "}
                          {t("projects.details.created")}
                        </h3>
                        <p className="text-sm">{task.create_time_format}</p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <h3 className="text-sm font-medium text-muted-foreground">
                          {t("projects.tasks.columns.progress")}
                        </h3>
                        <span className="text-sm font-bold">
                          {task.progress || 0}
                          {t("common.percent")}
                        </span>
                      </div>
                      <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all duration-300 ease-in-out"
                          style={{ width: `${task.progress || 0}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  <Separator />

                  {/* AI Analysis */}
                  <div className="space-y-6">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <Activity className="h-5 w-5 text-indigo-500" />
                      {t("projects.details.tabs.ai")}
                    </h3>

                    <div className="grid md:grid-cols-2 gap-6">
                      {/* Match Score */}
                      <div className="bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/30 dark:to-purple-950/30 p-4 rounded-lg border border-indigo-100 dark:border-indigo-900/50">
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="text-sm font-medium flex items-center gap-2 text-indigo-700 dark:text-indigo-300">
                            <Activity className="h-4 w-4" />{" "}
                            {t("projects.tasks.matchScore")}
                          </h3>
                          <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                            {task.match_score || 0}
                            <span className="text-sm text-indigo-400">
                              {t("projects.tasks.scoreOutOf")}
                            </span>
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                          {task.relevance_analysis ||
                            t("projects.tasks.noAnalysis")}
                        </p>
                      </div>

                      <div className="space-y-4">
                        {/* Key Modules */}
                        <div className="space-y-2">
                          <h3 className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                            <Layers className="h-4 w-4" />{" "}
                            {t("projects.tasks.keyModules")}
                          </h3>
                          <div className="flex flex-wrap gap-2">
                            {task.key_modules_list &&
                            task.key_modules_list.length > 0 ? (
                              task.key_modules_list.map(
                                (mod: string, i: number) => (
                                  <Badge
                                    key={i}
                                    variant="outline"
                                    className="bg-background"
                                  >
                                    {mod}
                                  </Badge>
                                ),
                              )
                            ) : (
                              <span className="text-sm text-muted-foreground">
                                {t("projects.tasks.noModules")}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Technical Challenges */}
                        <div className="space-y-2">
                          <h3 className="text-sm font-medium flex items-center gap-2 text-muted-foreground">
                            <Zap className="h-4 w-4" />{" "}
                            {t("projects.tasks.techDifficulty")}
                          </h3>
                          <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                            {task.technical_challenges_list &&
                            task.technical_challenges_list.length > 0 ? (
                              task.technical_challenges_list.map(
                                (challenge: string, i: number) => (
                                  <li key={i}>{challenge}</li>
                                ),
                              )
                            ) : (
                              <li>{t("projects.tasks.noChallenges")}</li>
                            )}
                          </ul>
                        </div>
                      </div>
                    </div>
                  </div>

                  <Separator />

                  {/* Discussion (Placeholder) */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <MessageSquare className="h-5 w-5 text-muted-foreground" />
                      {t("projects.details.tabs.discussion")}
                    </h3>
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground bg-muted/20 rounded-lg">
                      <p>{t("projects.tasks.commentsComingSoon")}</p>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="subtasks" className="mt-0">
                  <SubtaskSection
                    projectId={task.project_id || task.projectId}
                    taskId={task.task_id || task.id}
                  />
                </TabsContent>
              </Tabs>
            ) : null}
          </div>
        </ScrollArea>

        {/* Footer / Actions */}
        <div className="p-6 border-t bg-muted/10 flex gap-4">
          <Button className="flex-1" variant="outline" disabled={loading}>
            {t("common.edit")}
          </Button>
          <Button
            className="flex-1 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white shadow-md transition-all hover:scale-[1.02]"
            disabled={loading || executing}
            onClick={handleExecuteTask}
          >
            {executing ? (
              t("projects.tasks.processing")
            ) : (
              <>
                <Play className="w-4 h-4 mr-2 fill-current" />
                {t("projects.tasks.execute")}
              </>
            )}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
