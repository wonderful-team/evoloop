/**
 * RunningTasksDock – 输入框上方的"执行中的命令"状态条。
 *
 * 显示当前线程所有正在执行的后台命令（BackgroundTask）TaskPill，
 * 让执行中的命令与输入工具条（模型选择器等）分离。
 * 点击某个 task 卡片切换到 Terminal Mode 以便查看实时输出。
 */

import { Clock, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { ActiveTaskInfo } from "@/stores/chat/types"
import { useChatStore } from "@/stores/chatStore"

function TaskPill({
  task,
  onClick,
}: {
  task: ActiveTaskInfo
  onClick: () => void
}) {
  const { t } = useTranslation()
  const isRunning = task.status === "running"
  const label =
    task.title.length > 80
      ? `${task.title.slice(0, 77)}${t("common.ellipsis")}`
      : task.title

  return (
    <button
      onClick={onClick}
      type="button"
      className="group flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-mono transition-all w-full text-left
                 bg-background border border-border text-foreground
                 hover:border-primary hover:bg-muted/50
                 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
      title={t("chat.runningTasks.openTerminalTitle", { title: task.title })}
    >
      {isRunning ? (
        <Loader2 className="h-3 w-3 animate-spin text-green-500 flex-shrink-0" />
      ) : (
        <Clock className="h-3 w-3 text-amber-500 flex-shrink-0" />
      )}
      <span className="min-w-0 truncate">{label}</span>
    </button>
  )
}

export function RunningTasksDock() {
  const activeTasks = useChatStore((s) => s.activeTasks)
  const setTerminalMode = useChatStore((s) => s.setTerminalMode)

  const tasks = Object.values(activeTasks)
  if (tasks.length === 0) return null

  return (
    <div className="flex flex-col gap-1 px-2 py-1.5 border-t border-border bg-muted/80 backdrop-blur-sm">
      {tasks.map((task) => (
        <TaskPill
          key={task.task_id}
          task={task}
          onClick={() => setTerminalMode(true)}
        />
      ))}
    </div>
  )
}
