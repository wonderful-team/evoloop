/**
 * RunningTasksDock – 输入框上方的"执行中的命令"状态条。
 *
 * 显示当前线程所有正在执行的后台命令（BackgroundTask）TaskPill，
 * 让执行中的命令与输入工具条（模型选择器等）分离。
 * 点击某个 task 卡片切换到 Terminal Mode 以便查看实时输出。
 */

import { Clock, Loader2, Square } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { ActiveTaskInfo } from "@/stores/chat/types"
import { useChatStore } from "@/stores/chatStore"

function TaskPill({
  task,
  onClick,
  onStop,
}: {
  task: ActiveTaskInfo
  onClick: () => void
  onStop: () => void
}) {
  const { t } = useTranslation()
  const isRunning = task.status === "running"
  const label =
    task.title.length > 80
      ? `${task.title.slice(0, 77)}${t("common.ellipsis")}`
      : task.title

  return (
    <div
      className="group flex items-center gap-1 rounded-md text-xs font-mono transition-all w-full
                    bg-background border border-border text-foreground
                    hover:border-primary/60"
    >
      <button
        onClick={onClick}
        type="button"
        className="flex items-center gap-1.5 px-2.5 py-1.5 min-w-0 flex-1 text-left
                   focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
        title={t("chat.runningTasks.openTerminalTitle", { title: task.title })}
      >
        {isRunning ? (
          <Loader2 className="h-3 w-3 animate-spin text-success flex-shrink-0" />
        ) : (
          <Clock className="h-3 w-3 text-warning flex-shrink-0" />
        )}
        <span className="min-w-0 truncate">{label}</span>
      </button>
      {isRunning && (
        <button
          onClick={onStop}
          type="button"
          className="hover:bg-background text-muted-foreground hover:text-destructive transition-colors
                     w-7 h-full flex items-center justify-center self-stretch
                     focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded-r-md"
          title={t("chat.runningTasks.stop")}
        >
          <Square size={12} className="fill-current" />
        </button>
      )}
    </div>
  )
}

export function RunningTasksDock() {
  const activeTasks = useChatStore((s) => s.activeTasks)
  const setTerminalMode = useChatStore((s) => s.setTerminalMode)
  const cancelTask = useChatStore((s) => s.cancelTask)

  const tasks = Object.values(activeTasks)
  if (tasks.length === 0) return null

  return (
    <div className="flex flex-col gap-1 px-2 py-1.5 border-t border-border bg-muted/80 backdrop-blur-sm">
      {tasks.map((task) => (
        <TaskPill
          key={task.task_id}
          task={task}
          onClick={() => setTerminalMode(true)}
          onStop={() => cancelTask(task.task_id)}
        />
      ))}
    </div>
  )
}
