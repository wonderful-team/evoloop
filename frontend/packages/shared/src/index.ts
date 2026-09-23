// @evoloop/shared - Shared components, hooks, utilities, and locales
// This package is consumed by both @evoloop/desktop and @evoloop/mobile

// Re-export UI components
export * from "./components/ui/alert"
export * from "./components/ui/alert-dialog"
export * from "./components/ui/avatar"
export * from "./components/ui/badge"
export { Button, buttonVariants } from "./components/ui/button"
export * from "./components/ui/button-group"
export * from "./components/ui/calendar"
export * from "./components/ui/card"
export * from "./components/ui/checkbox"
export * from "./components/ui/collapsible"
export * from "./components/ui/context-menu"
export * from "./components/ui/dialog"
export * from "./components/ui/dropdown-menu"
export * from "./components/ui/form"
export * from "./components/ui/input"
export * from "./components/ui/label"
export * from "./components/ui/loading-button"
export * from "./components/ui/pagination"
export * from "./components/ui/password-input"
export * from "./components/ui/popover"
export * from "./components/ui/radio-group"
export * from "./components/ui/resizable"
export * from "./components/ui/scroll-area"
export * from "./components/ui/select"
export * from "./components/ui/separator"
export * from "./components/ui/sheet"
export * from "./components/ui/sidebar"
export * from "./components/ui/skeleton"
export * from "./components/ui/sonner"
export * from "./components/ui/table"
export * from "./components/ui/tabs"
export * from "./components/ui/textarea"
export * from "./components/ui/tooltip"
// Re-export utilities
export { cn } from "./lib/utils"

// Re-export hooks
export * from "./hooks/useMobile"

// Re-export Universal HITL Components
export * from "./components/hitl/types"
export { HumanRequestCard } from "./components/hitl/HumanRequestCard"

// Re-export Universal Task Proposal Components
export * from "./components/proposal/types"
export { TaskProposalCard } from "./components/proposal/TaskProposalCard"

// Re-export Universal Agent Trace & Execution Components
export * from "./components/trace/types"
export { ToolCallItem } from "./components/trace/ToolCallItem"
export { ThinkingBlock } from "./components/trace/ThinkingBlock"
export { AgentExecutionTimeline } from "./components/trace/AgentExecutionTimeline"

export { MarkdownText } from "./components/markdown/MarkdownText"
