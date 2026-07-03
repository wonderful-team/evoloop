import { Button } from "@evoloop/shared/components/ui/button"
import {
  CheckCircle2,
  Database,
  Layers,
  Monitor,
  Play,
  Settings2,
  Trash2,
  X,
  Zap,
} from "lucide-react"
import React from "react"
import { toast } from "sonner"
import { v4 as uuidv4 } from "uuid"
import { AgentService } from "@/client/sdk.gen"
import { useAgentStore } from "@/stores/agentStore"
import { useChatStore } from "@/stores/chatStore"
import { generateMockMessages } from "./debug/mockData"

interface DebugManagerPanelProps {
  onClose: () => void
}

export function DebugManagerPanel({ onClose }: DebugManagerPanelProps) {
  const messages = useChatStore((s) => s.messages)
  const clearContent = useChatStore((s) => s.clearContent)
  const [isStreaming, setIsStreaming] = React.useState(false)
  const [currentScenario, setCurrentScenario] = React.useState<string | null>(
    null,
  )

  const injectMocks = () => {
    const mocks = generateMockMessages()
    useChatStore.setState({ messages: mocks })
    toast.success("5大类21种形态全域消息块已注入")
  }

  const startStreamingSimulation = async (scenario: string = "happy_path") => {
    if (isStreaming) return

    const threadId = useChatStore.getState().threadId
    if (!threadId) {
      toast.error("请先在左侧选中或创建一个对话")
      return
    }

    setIsStreaming(true)
    setCurrentScenario(scenario)

    try {
      await AgentService.mockChat({
        requestBody: {
          thread_id: threadId,
          message: "Mock Stream Request",
          scenario: scenario,
        },
      })

      toast.success("真实后端流式输出模拟已启动")
    } catch (err) {
      toast.error("请求后端模拟流失败")
      console.error(err)
    } finally {
      setIsStreaming(false)
      setCurrentScenario(null)
    }
  }

  const simulateHITL = (
    type:
      | "approval"
      | "text"
      | "choice"
      | "confirmation"
      | "project_switch"
      | "file_select" = "approval",
  ) => {
    let prompt = ""
    let options: string[] | undefined

    switch (type) {
      case "approval":
        prompt = "是否批准部署到生产环境？"
        break
      case "text":
        prompt = "请输入你的 API Key 以继续："
        break
      case "choice":
        prompt = "请选择你要执行的重构策略："
        options = ["快速重构", "深度优化", "保守修复"]
        break
      case "confirmation":
        prompt = "检测到 node_modules 异常，是否执行强制清理？"
        break
      case "project_switch":
        prompt = "当前操作跨越了多个目录，建议切换到更合适的项目上下文："
        break
      case "file_select":
        prompt = "请选择需要作为上下文参考的本地源代码文件："
        break
    }

    useAgentStore.setState({
      status: "interrupted",
      humanRequest: {
        id: uuidv4(),
        type,
        prompt,
        context: "此请求来自 Agent 的核心安全策略校验。",
        options,
        status: "waiting_human",
      },
    })
    toast.success(`${type} 类型的 HITL 已注入`)
  }

  const clearMessages = () => {
    clearContent()
    useAgentStore.getState().clearContent()
    toast.info("会话已清空")
  }

  return (
    <div className="flex flex-col gap-1.5 p-2.5 w-56">
      {/* Header */}
      <div className="px-2 py-1 mb-1 border-b border-white/10 flex items-center justify-between">
        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
          <Settings2 className="h-3 w-3 text-primary animate-pulse" />
          Control Center
        </span>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-5 w-5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/10"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Actions Group */}
      <div className="space-y-1">
        <DebugButton
          icon={<Layers className="h-3.5 w-3.5" />}
          label="注入全域消息块 (本地)"
          onClick={injectMocks}
          variant="primary"
        />

        <div className="text-[9px] text-zinc-500 font-bold px-2 py-1 mt-1 border-t border-white/5 uppercase tracking-wide">
          后端流式场景模拟
        </div>

        <DebugButton
          icon={<Play className="h-3.5 w-3.5" />}
          label="模拟：正常流程"
          onClick={() => startStreamingSimulation("happy_path")}
          disabled={isStreaming}
          loading={isStreaming && currentScenario === "happy_path"}
        />

        <DebugButton
          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
          label="模拟：交互拦截 (HITL)"
          onClick={() => startStreamingSimulation("hitl")}
          disabled={isStreaming}
          loading={isStreaming && currentScenario === "hitl"}
        />

        <DebugButton
          icon={<Database className="h-3.5 w-3.5" />}
          label="模拟：长程任务/文件"
          onClick={() => startStreamingSimulation("long_task")}
          disabled={isStreaming}
          loading={isStreaming && currentScenario === "long_task"}
        />

        <DebugButton
          icon={<Zap className="h-3.5 w-3.5" />}
          label="模拟：配额耗尽"
          onClick={() => startStreamingSimulation("quota_exhausted")}
          disabled={isStreaming}
          loading={isStreaming && currentScenario === "quota_exhausted"}
          variant="danger"
        />

        <div className="text-[9px] text-zinc-500 font-bold px-2 py-1 border-t border-white/5 uppercase tracking-wide">
          本地组件注入
        </div>

        <div className="grid grid-cols-3 gap-1">
          <DebugButton
            icon={<CheckCircle2 className="h-3 w-3" />}
            label="审批"
            onClick={() => simulateHITL("approval")}
          />
          <DebugButton
            icon={<Zap className="h-3 w-3" />}
            label="确认"
            onClick={() => simulateHITL("confirmation")}
          />
          <DebugButton
            icon={<Layers className="h-3 w-3" />}
            label="选择"
            onClick={() => simulateHITL("choice")}
          />
          <DebugButton
            icon={<Play className="h-3 w-3" />}
            label="输入"
            onClick={() => simulateHITL("text")}
          />
          <DebugButton
            icon={<Monitor className="h-3 w-3" />}
            label="切换"
            onClick={() => simulateHITL("project_switch")}
          />
          <DebugButton
            icon={<Database className="h-3 w-3" />}
            label="文件"
            onClick={() => simulateHITL("file_select")}
          />
        </div>
      </div>

      {/* System Group */}
      <div className="mt-1 pt-2 border-t border-white/5 space-y-1">
        <DebugButton
          icon={<Trash2 className="h-3.5 w-3.5" />}
          label="清空当前消息"
          onClick={clearMessages}
          variant="danger"
        />
      </div>

      {/* Footer info */}
      <div className="mt-1 pt-1.5 flex justify-between items-center opacity-40 px-1">
        <div className="flex items-center gap-1">
          <Database className="h-2.5 w-2.5" />
          <span className="text-[9px] font-mono">{messages.length} MSGS</span>
        </div>
        <span className="text-[9px] font-mono font-bold uppercase tracking-tighter">
          V2.0-UNIVERSAL
        </span>
      </div>
    </div>
  )
}

/** @deprecated Use DebugManagerPanel inside AppSidebar trigger instead */
export function DebugManager() {
  const isDev = import.meta.env.DEV
  if (!isDev) return null

  return null
}

function DebugButton({
  icon,
  label,
  onClick,
  variant = "default",
  disabled = false,
  loading = false,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  variant?: "default" | "primary" | "danger"
  disabled?: boolean
  loading?: boolean
}) {
  const styles = {
    default: "hover:bg-white/5 text-zinc-300",
    primary: "hover:bg-primary/20 text-primary-foreground hover:text-primary",
    danger: "hover:bg-red-500/20 text-zinc-400 hover:text-red-400",
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={disabled}
      className={`w-full justify-start gap-2.5 h-9 px-3 rounded-xl transition-all active:scale-95 ${styles[variant]}`}
    >
      {loading ? (
        <Zap className="h-3.5 w-3.5 animate-spin text-primary" />
      ) : (
        icon
      )}
      <span className="text-[11px] font-medium tracking-tight">{label}</span>
    </Button>
  )
}
