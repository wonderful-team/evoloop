import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ProjectActions } from "./ProjectActions"
import { ProjectsService, WikiService } from "@/client"
import { useProjectStore } from "@/stores/projectStore"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

// Radix DropdownMenu uses pointer-events and portals in JSDOM; mock it to keep items in DOM when opened
vi.mock("@evoloop/shared/components/ui/dropdown-menu", () => {
  return {
    DropdownMenu: ({ children }: any) => <div data-testid="dropdown">{children}</div>,
    DropdownMenuTrigger: ({ children }: any) => <div>{children}</div>,
    DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
    DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
    DropdownMenuItem: ({ children, onClick, className }: any) => (
      <div role="menuitem" onClick={onClick} className={className}>
        {children}
      </div>
    ),
  }
})

vi.mock("./Modules/Overview/DiscoverDialog", () => ({
  DiscoverDialog: ({ open }: any) => (open ? <div data-testid="discover-dialog">Discover Dialog</div> : null),
}))

describe("ProjectActions", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
  })

  it("triggers wiki generation when menu item clicked", async () => {
    const generateWikiSpy = vi.spyOn(WikiService, "generateWiki").mockResolvedValue({} as any)
    const mockProject = { id: 10, name: "Alpha", has_wiki: false }

    render(
      <QueryClientProvider client={queryClient}>
        <ProjectActions project={mockProject} />
      </QueryClientProvider>,
    )

    // Click generate wiki
    const wikiItem = screen.getByText("wiki.generate")
    fireEvent.click(wikiItem)

    await waitFor(() => {
      expect(generateWikiSpy).toHaveBeenCalled()
    })
  })

  it("opens delete confirmation and executes deleteMutation", async () => {
    const deleteSpy = vi.spyOn(ProjectsService, "deleteProject").mockResolvedValue({} as any)
    const mockProject = { id: 10, name: "Alpha", has_wiki: true }
    useProjectStore.setState({ currentProject: mockProject as any })

    render(
      <QueryClientProvider client={queryClient}>
        <ProjectActions project={mockProject} />
      </QueryClientProvider>,
    )

    // Click delete item
    const deleteItem = screen.getByText("projects.actions.delete")
    fireEvent.click(deleteItem)

    // Dialog title
    expect(screen.getByText("projects.actions.confirmTitle")).toBeInTheDocument()

    // Confirm delete
    const confirmBtn = screen.getByText("projects.actions.deleteConfirm")
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith({ projectId: 10 })
    })
  })
})
