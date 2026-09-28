import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { ChatSidebar } from "./ChatSidebar"
import { useChangesetStore } from "@/stores/changesetStore"

vi.mock("@/components/Sidebar/ProjectSwitcher", () => ({
  ProjectSwitcher: () => <div data-testid="project-switcher">Project Switcher</div>,
}))

vi.mock("./sidebar/SidebarChatList", () => ({
  SidebarChatList: ({ threads, onNewChat }: any) => (
    <div data-testid="sidebar-chat-list">
      <button onClick={onNewChat}>New Chat Button</button>
      <div>Count: {threads.length}</div>
    </div>
  ),
}))

vi.mock("./sidebar/SidebarFilesTab", () => ({
  SidebarFilesTab: () => <div data-testid="sidebar-files-tab">Files Tab Content</div>,
}))

describe("ChatSidebar", () => {
  it("renders tabs and unviewed changes badge", () => {
    useChangesetStore.setState({
      changeset: [{ path: "file1.ts" }, { path: "file2.ts" }] as any,
      viewedChanges: new Set(["file1.ts"]),
    })

    render(
      <ChatSidebar
        threads={[{ id: "t-1", title: "Chat 1" }] as any}
        activeThreadId="t-1"
        setActiveThreadId={vi.fn()}
        projectId={1}
        onDeleteThread={vi.fn()}
        onNewChat={vi.fn()}
        activeTab="chats"
      />,
    )

    expect(screen.getByTestId("project-switcher")).toBeInTheDocument()
    expect(screen.getByTestId("sidebar-chat-list")).toBeInTheDocument()
    // Unviewed count is 1 (2 files - 1 viewed)
    expect(screen.getByText("1")).toBeInTheDocument()
  })

  it("renders files tab when activeTab is files", () => {
    render(
      <ChatSidebar
        threads={[]}
        activeThreadId=""
        setActiveThreadId={vi.fn()}
        projectId={1}
        onDeleteThread={vi.fn()}
        onNewChat={vi.fn()}
        activeTab="files"
      />,
    )

    expect(screen.getByTestId("sidebar-files-tab")).toBeInTheDocument()
  })
})
