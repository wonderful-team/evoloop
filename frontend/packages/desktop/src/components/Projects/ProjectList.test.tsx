import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ProjectList } from "./ProjectList"
import { useProjectStore } from "@/stores/projectStore"

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock("./AddProject", () => ({
  default: () => <button>Add Project Button</button>,
}))

vi.mock("./ImportProject", () => ({
  default: () => <button>Import Project Button</button>,
}))

vi.mock("./ProjectActions", () => ({
  ProjectActions: () => <div data-testid="project-actions">Actions</div>,
}))

describe("ProjectList", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState({
      fetchProjects: vi.fn(),
      isLoading: false,
    })
  })

  it("renders empty state when projects is empty", () => {
    useProjectStore.setState({ projects: [], isLoading: false })

    render(<ProjectList />)

    expect(screen.getByText("projects.title")).toBeInTheDocument()
    expect(screen.getByText("projects.emptyState")).toBeInTheDocument()
  })

  it("renders project cards with indexing and status badges and handles project select", () => {
    const setProjectSpy = vi.fn()
    const projects = [
      {
        id: 1,
        name: "Evoloop Core",
        description: "Agent orchestrator",
        indexing_status: "indexing",
        files_count: 120,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]

    useProjectStore.setState({
      projects: projects as any,
      isLoading: false,
      setProject: setProjectSpy,
    })

    render(<ProjectList />)

    expect(screen.getByText("Evoloop Core")).toBeInTheDocument()
    expect(screen.getByText("Agent orchestrator")).toBeInTheDocument()
    expect(screen.getByText("projects.status.indexing")).toBeInTheDocument()

    // Click project card to select
    fireEvent.click(screen.getByText("Evoloop Core"))
    expect(setProjectSpy).toHaveBeenCalledWith(projects[0])
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/projects/1" })
  })
})
