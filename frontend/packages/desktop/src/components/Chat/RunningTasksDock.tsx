/**
 * RunningTasksDock – Floating status bar shown above the input area.
 *
 * Displays all actively running BackgroundTasks for the current thread.
 * Clicking a task card switches the view to Terminal Mode so the user can
 * see the live output.
 */

import { Terminal, X, Clock, Loader2 } from "lucide-react"
import { useChatStore } from "@/stores/chatStore"
import type { ActiveTaskInfo } from "@/stores/chat/types"

function TaskPill({
  task,
  onClick,
}: {
  task: ActiveTaskInfo
  onClick: () => void
}) {
  const isRunning = task.status === "running"
  const label =
    task.title.length > 40 ? task.title.slice(0, 37) + "…" : task.title

  return (
    <button
      onClick={onClick}
      className="group flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono transition-all
                 bg-background border border-border text-foreground
                 hover:border-primary hover:bg-muted/50
                 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
      title={`Open terminal – ${task.title}`}
    >
      {isRunning ? (
        <Loader2 className="h-3 w-3 animate-spin text-green-500 flex-shrink-0" />
      ) : (
        <Clock className="h-3 w-3 text-amber-500 flex-shrink-0" />
      )}
      <span className="max-w-[160px] truncate">{label}</span>
    </button>
  )
}

export function RunningTasksDock() {
  const activeTasks = useChatStore((s) => s.activeTasks)
  const isTerminalMode = useChatStore((s) => s.isTerminalMode)
  const setTerminalMode = useChatStore((s) => s.setTerminalMode)

  const tasks = Object.values(activeTasks)
  if (tasks.length === 0 && !isTerminalMode) return null

  return (
    <div className="flex items-center gap-2 px-4 py-1.5 border-t border-border bg-muted/80 backdrop-blur-sm">
      <Terminal className="h-3.5 w-3.5 text-primary flex-shrink-0" />

      <div className="flex items-center gap-1.5 flex-1 min-w-0 overflow-x-auto hide-scrollbar">
        {tasks.length === 0 && (
          <span className="text-xs text-muted-foreground font-mono">
            Terminal Mode active
          </span>
        )}
        {tasks.map((task) => (
          <TaskPill
            key={task.task_id}
            task={task}
            onClick={() => setTerminalMode(true)}
          />
        ))}
      </div>

      {/* Terminal mode toggle button */}
      <button
        onClick={() => setTerminalMode(!isTerminalMode)}
        className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono transition-all border
                    focus:outline-none focus-visible:ring-1 focus-visible:ring-primary
                    ${
                      isTerminalMode
                        ? "bg-primary/10 text-primary border-primary/30"
                        : "text-muted-foreground border-transparent hover:text-primary hover:border-border"
                    }`}
        title={isTerminalMode ? "Switch to Chat view" : "Switch to Terminal view"}
      >
        {isTerminalMode ? (
          <>
            <X className="h-3 w-3" />
            <span>Exit</span>
          </>
        ) : (
          <>
            <Terminal className="h-3 w-3" />
            <span>&gt;_</span>
          </>
        )}
      </button>
    </div>
  )
}
