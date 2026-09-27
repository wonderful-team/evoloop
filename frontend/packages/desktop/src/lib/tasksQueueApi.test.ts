import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TasksQueueService } from "@/client"
import { ApiError } from "@/client/core/ApiError"
import { TasksQueueApi } from "./tasksQueueApi"

/**
 * 任务队列 API 门面契约（2026-09-25 收敛：HTTP 层全部下沉生成 client）：
 * - 参数/路径单一来源 = sdk.gen.ts（门面只做映射与类型收窄）；
 * - 提案驳回走 cancel 语义（editTask），与验收驳回（rejectTask）分流；
 * - ApiError 的 body.detail 提升为 Error.message（toast 可见后端原因）。
 * 旧手写 fetch 层（Bearer/Cookie 双通道鉴权）已随生成 client core 承接，
 * 鉴权契约测试随之下沉，门面层不再测 fetch 管线。
 */

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function apiError(status: number, statusText: string, body: unknown): ApiError {
  const err = new ApiError(
    {
      method: "GET",
      url: "/test",
    } as never,
    { url: "/test", status, statusText, body } as never,
    statusText,
  )
  return err
}

describe("TasksQueueApi 参数映射（单一来源=生成 client）", () => {
  it("list → listQueue（camelCase 参数 + 分页）", async () => {
    const listQueue = vi
      .spyOn(TasksQueueService, "listQueue")
      .mockResolvedValue({} as never)
    await TasksQueueApi.list("pending", 7, true, 50, 100, "recent")
    expect(listQueue).toHaveBeenCalledWith({
      status: "pending",
      projectId: 7,
      rootOnly: true,
      limit: 50,
      offset: 100,
      order: "recent",
    })
  })

  it("create → createTask（requestBody 直传）", async () => {
    const createTask = vi
      .spyOn(TasksQueueService, "createTask")
      .mockResolvedValue({} as never)
    await TasksQueueApi.create({ title: "t", project_id: 1 })
    expect(createTask).toHaveBeenCalledWith({
      requestBody: { title: "t", project_id: 1 },
    })
  })

  it("dashboard → queueDashboard", async () => {
    const dashboard = vi
      .spyOn(TasksQueueService, "queueDashboard")
      .mockResolvedValue({} as never)
    await TasksQueueApi.dashboard(3)
    expect(dashboard).toHaveBeenCalledWith({ projectId: 3 })
  })
})

describe("TasksQueueApi 提案驳回 vs 验收驳回分流", () => {
  it("rejectProposed → editTask cancel 语义（不再错调 acceptance reject）", async () => {
    const editTask = vi
      .spyOn(TasksQueueService, "editTask")
      .mockResolvedValue({} as never)
    await TasksQueueApi.rejectProposed("t-1", "方案不可行")
    expect(editTask).toHaveBeenCalledWith({
      taskId: "t-1",
      requestBody: { cancel: true, description: "方案不可行" },
    })
  })

  it("reject（验收驳回）→ rejectTask（仅 waiting_acceptance）", async () => {
    const rejectTask = vi
      .spyOn(TasksQueueService, "rejectTask")
      .mockResolvedValue({} as never)
    await TasksQueueApi.reject("t-2", "质量不达标")
    expect(rejectTask).toHaveBeenCalledWith({
      taskId: "t-2",
      requestBody: { feedback: "质量不达标" },
    })
  })
})

describe("TasksQueueApi 错误透传", () => {
  it("ApiError body.detail → Error.message（toast 可见后端原因）", async () => {
    vi.spyOn(TasksQueueService, "rerunFailedTask").mockRejectedValue(
      apiError(409, "Conflict", { detail: "task is in_progress, not failed" }),
    )
    await expect(TasksQueueApi.rerun("t-1")).rejects.toThrow(
      "task is in_progress, not failed",
    )
  })

  it("ApiError 无 detail → 回落 statusText", async () => {
    vi.spyOn(TasksQueueService, "listQueue").mockRejectedValue(
      apiError(500, "Internal Server Error", null),
    )
    await expect(TasksQueueApi.list()).rejects.toThrow("Internal Server Error")
  })

  it("非 ApiError 原样上抛", async () => {
    const boom = new Error("network down")
    vi.spyOn(TasksQueueService, "listQueue").mockRejectedValue(boom)
    await expect(TasksQueueApi.list()).rejects.toThrow("network down")
  })
})
