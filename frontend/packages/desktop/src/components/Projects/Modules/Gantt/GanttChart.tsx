import { Button } from "@evoloop/shared/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
} from "@evoloop/shared/components/ui/card"
import { useParams } from "@tanstack/react-router"
import {
  addDays,
  differenceInDays,
  format,
  isSameDay,
  startOfWeek,
} from "date-fns"
import { enUS, zhCN } from "date-fns/locale"
import { ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react"
import type React from "react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { TasksService } from "@/client"
import { type Task, TaskStatus } from "@/types/task"

export const GanttChart: React.FC = () => {
  const { t, i18n } = useTranslation()
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [viewStartDate, setViewStartDate] = useState(
    startOfWeek(new Date(), { weekStartsOn: 1 }),
  )
  const daysToShow = 14

  const getDateLocale = () => {
    return i18n.language === "zh" ? zhCN : enUS
  }

  const fetchTasks = useCallback(async () => {
    if (!projectId) return
    setIsLoading(true)
    try {
      // Re-using fetch logic
      const res: any = await TasksService.getProjectTasks({
        projectId: parseInt(projectId, 10),
        pageSize: 100,
        status: undefined, // Assuming statusFilter is not defined yet, using undefined for now
      })
      let list: Task[] = []
      if (res?.list) list = res.list
      else if (Array.isArray(res)) list = res

      // Mock dates for visualization if missing (since backend might not return them yet)
      const mockedList = list.map((task) => {
        const now = new Date()
        const start = task.start_date ? new Date(task.start_date) : now
        const end = task.end_date
          ? new Date(task.end_date)
          : addDays(
              start,
              task.match_score ? Math.ceil(task.match_score / 20) : 2,
            )
        return {
          ...task,
          start_date: start.toISOString(),
          end_date: end.toISOString(),
        }
      })

      setTasks(mockedList)
    } catch (error) {
      console.error(error)
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  // Generate calendar days
  const calendarDays = useMemo(() => {
    return Array.from({ length: daysToShow }).map((_, i) =>
      addDays(viewStartDate, i),
    )
  }, [viewStartDate])

  const handlePrev = () => setViewStartDate((d) => addDays(d, -7))
  const handleNext = () => setViewStartDate((d) => addDays(d, 7))

  const getTaskStyle = (task: Task) => {
    const start = new Date(task.start_date!)
    const end = new Date(task.end_date!)
    const viewStart = viewStartDate

    let offset = differenceInDays(start, viewStart)
    let duration = differenceInDays(end, start) + 1

    // Clip logic
    if (offset < 0) {
      duration += offset
      offset = 0
    }

    // If completely out of view
    if (offset >= daysToShow || duration <= 0) return null

    return {
      left: `${(offset / daysToShow) * 100}%`,
      width: `${(Math.min(duration, daysToShow - offset) / daysToShow) * 100}%`,
    }
  }

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold tracking-tight">
            {t("projects.gantt.title")}
          </h2>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handlePrev}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="flex items-center text-sm font-medium px-2">
              {format(viewStartDate, "MMM d", { locale: getDateLocale() })} -{" "}
              {format(addDays(viewStartDate, daysToShow - 1), "MMM d", {
                locale: getDateLocale(),
              })}
            </span>
            <Button variant="outline" size="sm" onClick={handleNext}>
              <ChevronRight className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchTasks}
              disabled={isLoading}
            >
              <RefreshCw
                className={`w-4 h-4 mr-2 ${isLoading ? "animate-spin" : ""}`}
              />
              {t("projects.gantt.refresh")}
            </Button>
          </div>
        </div>

        <Card className="overflow-hidden">
          <CardHeader className="border-b py-3 px-4 bg-muted/20">
            <div className="flex">
              <div className="w-1/4 min-w-[200px] font-medium text-sm text-muted-foreground uppercase">
                {t("projects.gantt.taskColumn")}
              </div>
              <div className="w-3/4 flex">
                {calendarDays.map((day) => (
                  <div
                    key={day.toISOString()}
                    className={`flex-1 text-center text-xs font-medium ${isSameDay(day, new Date()) ? "text-primary" : "text-muted-foreground"}`}
                  >
                    <div>{format(day, "E", { locale: getDateLocale() })}</div>
                    <div>{format(day, "d", { locale: getDateLocale() })}</div>
                  </div>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading && tasks.length === 0 ? (
              <div className="h-40 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
            ) : tasks.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-muted-foreground">
                {t("projects.gantt.noTasks")}
              </div>
            ) : (
              <div className="divide-y relative">
                {/* Vertical Grid Lines */}
                <div className="absolute inset-0 flex pointer-events-none pl-[25%]">
                  {calendarDays.map((_, i) => (
                    <div
                      key={i}
                      className="flex-1 border-r border-border border-dashed border-muted/50 last:border-0 h-full"
                    />
                  ))}
                </div>

                {tasks.map((task) => {
                  const style = getTaskStyle(task)
                  return (
                    <div
                      key={task.task_id}
                      className="flex hover:bg-muted/30 relative"
                    >
                      <div className="w-1/4 min-w-[200px] p-3 border-r border-border relative z-10 bg-background/50 truncate">
                        <div className="font-medium text-sm truncate">
                          {task.task_title}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          #{task.task_id}
                        </div>
                      </div>
                      <div className="w-3/4 relative h-12">
                        {style && (
                          <div
                            className={`absolute top-2.5 h-7 rounded-md text-xs flex items-center px-2 text-white overflow-hidden shadow-sm transition-all hover:scale-[1.01] cursor-pointer
                                                        ${task.status === TaskStatus.COMPLETED ? "bg-green-500" : "bg-primary"}
                                                    `}
                            style={style}
                          >
                            <span className="truncate">{task.task_title}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
