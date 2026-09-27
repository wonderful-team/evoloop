import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi } from "vitest"

import { McpService } from "@/client"
import McpServerModal from "./McpServerModal"

vi.mock("@/client", () => ({
  McpService: {
    addMcpServer: vi.fn(),
  },
}))

function renderModal(props: {
  mode?: "add" | "edit"
  initialData?: {
    name: string
    command: string
    status: string
    tools_count: number
  }
}) {
  const queryClient = new QueryClient()
  const onOpenChange = vi.fn()
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <McpServerModal
        open
        onOpenChange={onOpenChange}
        mode={props.mode ?? "add"}
        initialData={props.initialData ?? null}
      />
    </QueryClientProvider>,
  )
  return { ...utils, onOpenChange }
}

describe("McpServerModal", () => {
  beforeEach(() => {
    vi.mocked(McpService.addMcpServer).mockReset()
    vi.mocked(McpService.addMcpServer).mockResolvedValue({} as any)
  })

  it("renders add-mode title and description keys", () => {
    renderModal({ mode: "add" })
    expect(screen.getByText("mcp.addTitle")).toBeInTheDocument()
    expect(screen.getByText("mcp.addDesc")).toBeInTheDocument()
  })

  it("renders edit-mode title and description keys", () => {
    renderModal({
      mode: "edit",
      initialData: {
        name: "files",
        command: "npx -y @server/filesystem",
        status: "ok",
        tools_count: 4,
      },
    })
    expect(screen.getByText("mcp.editTitle")).toBeInTheDocument()
    expect(screen.getByText("mcp.editDesc")).toBeInTheDocument()
  })

  it("shows validation errors when submitting an empty form", async () => {
    renderModal({ mode: "add" })
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "mcp.add" }))
    await waitFor(() => {
      expect(screen.getByText("mcp.nameRequired")).toBeInTheDocument()
      expect(screen.getByText("mcp.commandRequired")).toBeInTheDocument()
    })
    expect(McpService.addMcpServer).not.toHaveBeenCalled()
  })

  it("submits add with trimmed args split on spaces", async () => {
    renderModal({ mode: "add" })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText("mcp.nameLabel"), "files")
    await user.type(screen.getByLabelText("mcp.commandLabel"), "npx -y pkg")
    await user.type(screen.getByLabelText("mcp.argsLabel"), "a b c")
    await user.click(screen.getByRole("button", { name: "mcp.add" }))

    await waitFor(() => {
      expect(McpService.addMcpServer).toHaveBeenCalledWith(
        expect.objectContaining({
          requestBody: expect.objectContaining({
            name: "files",
            command: "npx -y pkg",
            args: ["a", "b", "c"],
          }),
        }),
      )
    })
  })
})
