import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import useProjectStatus from "../useProjectStatus"

// Mock the client
vi.mock("@/client", () => ({
  ProjectsService: {
    getProjectStatus: vi.fn(),
  },
}))

import { ProjectsService } from "@/client"

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe("useProjectStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("should fetch project status successfully", async () => {
    const mockStatus = {
      id: 1,
      name: "Test Project",
      status: "active",
      progress: 75,
    }
    ;(ProjectsService.getProjectStatus as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockStatus)

    const { result } = renderHook(() => useProjectStatus(1), {
      wrapper: createWrapper(),
    })

    // Initially loading
    expect(result.current.isLoading).toBe(true)

    // Wait for data
    await waitFor(() => {
      expect(result.current.data).toEqual(mockStatus)
    })

    expect(result.current.isLoading).toBe(false)
    expect(ProjectsService.getProjectStatus).toHaveBeenCalledWith({ projectId: 1 })
  })

  it("should not fetch when projectId is null", () => {
    const { result } = renderHook(() => useProjectStatus(null), {
      wrapper: createWrapper(),
    })

    expect(result.current.isLoading).toBe(false)
    expect(result.current.data).toBeUndefined()
    expect(ProjectsService.getProjectStatus).not.toHaveBeenCalled()
  })

  it("should handle error state", async () => {
    const error = new Error("Failed to fetch")
    ;(ProjectsService.getProjectStatus as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error)

    const { result } = renderHook(() => useProjectStatus(1), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error).toBeDefined()
  })

  it("should refetch when projectId changes", async () => {
    const mockStatus1 = { id: 1, name: "Project 1", status: "active" }
    const mockStatus2 = { id: 2, name: "Project 2", status: "inactive" }

    ;(ProjectsService.getProjectStatus as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(mockStatus1)
      .mockResolvedValueOnce(mockStatus2)

    const { result, rerender } = renderHook(({ id }) => useProjectStatus(id), {
      wrapper: createWrapper(),
      initialProps: { id: 1 },
    })

    await waitFor(() => {
      expect(result.current.data).toEqual(mockStatus1)
    })

    rerender({ id: 2 })

    await waitFor(() => {
      expect(result.current.data).toEqual(mockStatus2)
    })
  })
})
