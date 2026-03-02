import { describe, it, expect, vi, beforeEach } from "vitest"
import { useProjectStore } from "../projectStore"

// Mock the client
vi.mock("@/client", () => ({
  ProjectsService: {
    getProjects: vi.fn(),
  },
}))

import { ProjectsService } from "@/client"

describe("useProjectStore", () => {
  const createMockProject = (id: number, overrides = {}) => ({
    id,
    project_id: id,
    name: `Project ${id}`,
    project_name: `Project ${id}`,
    description: "Test description",
    project_desc: "Test description",
    path: `/path/to/project${id}`,
    external_path: `/path/to/project${id}`,
    status: 1,
    priority: 1,
    owner_member_id: 1,
    owner_member_name: "Test User",
    start_time: Date.now(),
    expected_end_time: Date.now() + 86400000,
    actual_end_time: 0,
    create_time: Date.now(),
    update_time: Date.now(),
    external_source: "local",
    external_id: `proj-${id}`,
    last_sync_time: Date.now(),
    member_count: 1,
    task_stats: {
      total: 10,
      pending: 2,
      in_progress: 5,
      completed: 3,
      overdue: 0,
      high_priority: 1,
    },
    create_time_format: "2024-01-01",
    start_time_format: "2024-01-01",
    update_time_format: "2024-01-01",
    last_sync_time_format: "2024-01-01",
    status_text: "Active",
    priority_text: "Normal",
    indexing_status: "completed",
    ...overrides,
  })

  beforeEach(() => {
    useProjectStore.setState({
      projects: [],
      currentProject: null,
      isLoading: false,
    })
    vi.clearAllMocks()
    localStorage.clear()
  })

  describe("initial state", () => {
    it("should have correct initial values", () => {
      const state = useProjectStore.getState()

      expect(state.projects).toEqual([])
      expect(state.currentProject).toBeNull()
      expect(state.isLoading).toBe(false)
    })
  })

  describe("setProject", () => {
    it("should set current project", () => {
      const project = createMockProject(1)
      const { setProject } = useProjectStore.getState()

      setProject(project)

      expect(useProjectStore.getState().currentProject).toEqual(project)
    })

    it("should update current project", () => {
      const project1 = createMockProject(1)
      const project2 = createMockProject(2)
      const store = useProjectStore.getState()

      store.setProject(project1)
      store.setProject(project2)

      expect(useProjectStore.getState().currentProject).toEqual(project2)
    })
  })

  describe("getProject", () => {
    it("should return project by id", () => {
      const project1 = createMockProject(1)
      const project2 = createMockProject(2)

      useProjectStore.setState({
        projects: [project1, project2],
      })

      const found = useProjectStore.getState().getProject(1)
      expect(found).toEqual(project1)
    })

    it("should return undefined for non-existent project", () => {
      const project = createMockProject(1)

      useProjectStore.setState({
        projects: [project],
      })

      const found = useProjectStore.getState().getProject(999)
      expect(found).toBeUndefined()
    })
  })

  describe("updateProjectStatus", () => {
    it("should update project status", () => {
      const project = createMockProject(1, { status: 1, status_text: "Active" })

      useProjectStore.setState({
        projects: [project],
      })

      const { updateProjectStatus } = useProjectStore.getState()
      updateProjectStatus(1, { status: 2, status_text: "Completed" })

      const updatedProject = useProjectStore.getState().projects[0]
      expect(updatedProject.status).toBe(2)
      expect(updatedProject.status_text).toBe("Completed")
    })

    it("should update current project if it matches", () => {
      const project = createMockProject(1, { name: "Original" })

      useProjectStore.setState({
        projects: [project],
        currentProject: project,
      })

      const { updateProjectStatus } = useProjectStore.getState()
      updateProjectStatus(1, { name: "Updated" })

      expect(useProjectStore.getState().currentProject?.name).toBe("Updated")
    })

    it("should not affect other projects", () => {
      const project1 = createMockProject(1, { name: "Project 1" })
      const project2 = createMockProject(2, { name: "Project 2" })

      useProjectStore.setState({
        projects: [project1, project2],
      })

      const { updateProjectStatus } = useProjectStore.getState()
      updateProjectStatus(1, { name: "Updated Project 1" })

      const projects = useProjectStore.getState().projects
      expect(projects[0].name).toBe("Updated Project 1")
      expect(projects[1].name).toBe("Project 2")
    })
  })

  describe("fetchProjects", () => {
    it("should set loading state while fetching", async () => {
      const mockResponse = { list: [] }
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockResponse)

      const promise = useProjectStore.getState().fetchProjects()
      expect(useProjectStore.getState().isLoading).toBe(true)

      await promise
      expect(useProjectStore.getState().isLoading).toBe(false)
    })

    it("should handle array response format", async () => {
      const mockProjects = [createMockProject(1), createMockProject(2)]
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockProjects)

      await useProjectStore.getState().fetchProjects()

      const state = useProjectStore.getState()
      expect(state.projects).toHaveLength(2)
      expect(state.projects[0].id).toBe(1)
      expect(state.projects[1].id).toBe(2)
    })

    it("should handle { list: [...] } response format", async () => {
      const mockProjects = [createMockProject(1)]
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        list: mockProjects,
      })

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().projects).toHaveLength(1)
    })

    it("should handle { projects: [...] } response format", async () => {
      const mockProjects = [createMockProject(1)]
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        projects: mockProjects,
      })

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().projects).toHaveLength(1)
    })

    it("should auto-select first project when no current project", async () => {
      const mockProjects = [createMockProject(1), createMockProject(2)]
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockProjects)

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().currentProject?.id).toBe(1)
    })

    it("should update current project if it exists in new list", async () => {
      const initialProject = createMockProject(1, { name: "Old Name" })
      useProjectStore.setState({
        currentProject: initialProject,
      })

      const updatedProject = createMockProject(1, { name: "New Name" })
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce([updatedProject])

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().currentProject?.name).toBe("New Name")
    })

    it("should select first project if current project not in new list", async () => {
      const oldProject = createMockProject(999)
      useProjectStore.setState({
        currentProject: oldProject,
      })

      const newProjects = [createMockProject(1), createMockProject(2)]
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce(newProjects)

      await useProjectStore.getState().fetchProjects()

      expect(useProjectStore.getState().currentProject?.id).toBe(1)
    })

    it("should handle fetch error gracefully", async () => {
      const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Network error")
      )

      await useProjectStore.getState().fetchProjects()

      const state = useProjectStore.getState()
      expect(state.projects).toEqual([])
      expect(state.isLoading).toBe(false)
      expect(state.currentProject).toBeNull()
      expect(consoleError).toHaveBeenCalledWith("Failed to fetch projects", expect.any(Error))

      consoleError.mockRestore()
    })

    it("should map project fields correctly", async () => {
      const rawProject = {
        project_id: 123,
        project_name: "API Project",
        project_desc: "From API",
        external_path: "/api/path",
        // ... other required fields
      }
      ;(ProjectsService.getProjects as ReturnType<typeof vi.fn>).mockResolvedValueOnce([rawProject])

      await useProjectStore.getState().fetchProjects()

      const project = useProjectStore.getState().projects[0]
      expect(project.id).toBe(123)
      expect(project.name).toBe("API Project")
      expect(project.description).toBe("From API")
      expect(project.path).toBe("/api/path")
    })
  })
})
