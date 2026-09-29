import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen } from "@testing-library/react"
import React from "react"
import { describe, expect, it, vi } from "vitest"
import { adaptQueueTasksToDutyTasks } from "../core/taskAdapter"
import type { DutyTask } from "../core/types"
import { DutyNodeCard } from "./DutyNodeCard"
import { DutyNodePageContent } from "./DutyNodePageContent"

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  useRouter: () => ({ state: { location: { search: "" } } }),
}))

vi.mock("@/stores/chatStore", () => ({
  useChatStore: {
    getState: () => ({
      setThread: vi.fn(),
    }),
  },
}))

vi.mock("@/lib/tasksQueueApi", () => ({
  TasksQueueApi: {
    hitlPending: vi.fn().mockResolvedValue({ items: [] }),
    update: vi.fn().mockResolvedValue({ success: true }),
    rerun: vi.fn().mockResolvedValue({ success: true }),
  },
}))

function renderWithClient(ui: React.ReactElement) {
  const testClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={testClient}>{ui}</QueryClientProvider>,
  )
}

describe("人工仲裁闭环 (Arbitration Closed Loop)", () => {
  it("taskAdapter 正确为 failed 或 escalated 任务注入 arbitration 规格", () => {
    const rawQueueTasks: any[] = [
      {
        id: "task-1",
        title: "上游任务",
        status: "failed",
        task_no: 1,
        source: "agent",
        escalated: true,
        last_error: "评审 2 轮未通过，触发升级",
      },
    ]

    const adapted = adaptQueueTasksToDutyTasks(rawQueueTasks)
    expect(adapted).toHaveLength(1)
    expect(adapted[0].arbitration).toBeDefined()
    expect(adapted[0].arbitration?.status).toBe("needed")
    expect(adapted[0].arbitration?.options).toHaveLength(3)
    expect(adapted[0].arbitration?.options.map((o) => o.key)).toEqual([
      "retry_upstream",
      "cancel_downstream",
      "reopen_modified",
    ])
  })

  it("DutyNodePageContent 在任务失败/升级阻断时渲染人工仲裁控制台并响应三键操作", async () => {
    const onArbitrate = vi.fn()
    const task: DutyTask = {
      id: "task-failed-1",
      taskNo: 101,
      title: "数据抽取节点",
      description: "执行 Python 脚本抓取行情",
      category: "analysis",
      status: "failed",
      priority: "high",
      riskLevel: "T3",
      source: "agent_proposal",
      dependencies: ["task-upstream-0"],
      x: 0,
      y: 0,
      w: 320,
      h: 180,
      provenance: {
        sourceRef: "测试",
        upstreamSummary: "前序数据",
        downstreamTargets: ["task-downstream-2"],
        endorsement: "无",
      },
      arbitration: {
        status: "needed",
        failedTaskTitle: "数据抽取节点",
        options: [
          { key: "retry_upstream", label: "重跑上游", hint: "" },
          { key: "cancel_downstream", label: "截断下游", hint: "" },
          { key: "reopen_modified", label: "改参重开", hint: "" },
        ],
      },
      rawQueueTask: {
        id: "task-failed-1",
        status: "failed",
        escalated: true,
        last_error: "评审未通过",
      } as any,
    }

    const allTasks: DutyTask[] = [
      {
        id: "task-upstream-0",
        taskNo: 100,
        title: "数据清洗",
        category: "analysis",
        status: "failed",
        priority: "medium",
        riskLevel: "T4",
        source: "agent_proposal",
        dependencies: [],
        x: 0,
        y: 0,
        w: 320,
        provenance: {
          sourceRef: "",
          upstreamSummary: "",
          downstreamTargets: [],
          endorsement: "",
        },
      },
      task,
      {
        id: "task-downstream-2",
        taskNo: 102,
        title: "图表生成",
        category: "delivery",
        status: "pending",
        priority: "low",
        riskLevel: "T4",
        source: "agent_proposal",
        dependencies: ["task-failed-1"],
        x: 0,
        y: 0,
        w: 320,
        provenance: {
          sourceRef: "",
          upstreamSummary: "",
          downstreamTargets: [],
          endorsement: "",
        },
      },
    ]

    renderWithClient(
      <DutyNodePageContent
        task={task}
        allTasks={allTasks}
        onClose={vi.fn()}
        onArbitrate={onArbitrate}
      />,
    )

    // 验证仲裁控制台标题与评审未收敛徽标
    expect(screen.getByText("执行阻断 · 人工仲裁控制台")).toBeInTheDocument()
    expect(screen.getByText("监察评审未收敛 (2轮驳回)")).toBeInTheDocument()

    // 验证依赖诊断
    expect(screen.getByText(/1 个子任务受阻/)).toBeInTheDocument()

    // 验证三键存在
    const retryBtn = screen.getByRole("button", { name: /重跑上游/ })
    const cancelDownstreamBtn = screen.getByRole("button", { name: /截断下游/ })
    const reopenBtn = screen.getByRole("button", { name: /改参重开/ })

    expect(retryBtn).toBeInTheDocument()
    expect(cancelDownstreamBtn).toBeInTheDocument()
    expect(reopenBtn).toBeInTheDocument()

    // 测试 1: 点击「重跑上游」
    await act(async () => {
      fireEvent.click(retryBtn)
    })
    expect(onArbitrate).toHaveBeenCalledWith("retry_upstream", "task-failed-1")

    // 测试 2: 点击「截断下游」
    await act(async () => {
      fireEvent.click(cancelDownstreamBtn)
    })
    expect(onArbitrate).toHaveBeenCalledWith(
      "cancel_downstream",
      "task-failed-1",
    )

    // 测试 3: 点击「改参重开」，输入新描述并保存
    await act(async () => {
      fireEvent.click(reopenBtn)
    })
    const textarea = screen.getByPlaceholderText(
      "输入针对此任务的补充修正指令或调整后的参数描述...",
    )
    expect(textarea).toBeInTheDocument()

    await act(async () => {
      fireEvent.change(textarea, {
        target: { value: "微调后的抓取指令：增加 timeout 限制" },
      })
    })

    const submitBtn = screen.getByRole("button", { name: "保存并重新排队" })
    await act(async () => {
      fireEvent.click(submitBtn)
    })

    expect(onArbitrate).toHaveBeenCalledWith(
      "reopen_modified",
      "task-failed-1",
      { description: "微调后的抓取指令：增加 timeout 限制" },
    )
  })

  it("DutyNodeCard 常态卡片呈现紧凑仲裁栏，支持快速重跑与截断", () => {
    const onArbitrate = vi.fn()
    const task: DutyTask = {
      id: "t-card-failed",
      taskNo: 55,
      title: "异常节点",
      status: "failed",
      category: "creation",
      priority: "medium",
      riskLevel: "T4",
      source: "manual",
      dependencies: [],
      x: 0,
      y: 0,
      w: 320,
      provenance: {
        sourceRef: "",
        upstreamSummary: "",
        downstreamTargets: [],
        endorsement: "",
      },
      arbitration: {
        status: "needed",
        failedTaskTitle: "异常节点",
        options: [],
      },
    }

    render(
      <DutyNodeCard
        task={task}
        isFocused={false}
        onFocus={vi.fn()}
        onUnfocus={vi.fn()}
        onArbitrate={onArbitrate}
      />,
    )

    expect(screen.getByText("执行阻断 · 人工仲裁")).toBeInTheDocument()
    const retryBtn = screen.getByRole("button", { name: /重跑上游/ })
    const cancelBtn = screen.getByRole("button", { name: /截断下游/ })

    fireEvent.click(retryBtn)
    expect(onArbitrate).toHaveBeenCalledWith("retry_upstream", "t-card-failed")

    fireEvent.click(cancelBtn)
    expect(onArbitrate).toHaveBeenCalledWith(
      "cancel_downstream",
      "t-card-failed",
    )
  })
})
