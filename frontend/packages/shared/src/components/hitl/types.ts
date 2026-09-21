import type React from "react"

export type HumanRequestType =
  | "text"
  | "choice"
  | "multi_choice"
  | "confirmation"
  | "approval"
  | "project_switch"
  | "file_select"
  | string

export interface HumanRequestItem {
  id: string
  type: HumanRequestType
  prompt: string
  options?: string[]
  context?: string | null
  thread_id?: string
  payload?: {
    allow_global?: boolean
    suggested_project_id?: number
    show_project_list?: boolean
    temporary?: boolean
    multiple?: boolean
    file_types?: string[]
    [key: string]: unknown
  }
  status?: "waiting_human" | "completed" | "cancelled" | "rejected" | string
}

export interface HumanRequestCardProps {
  request: HumanRequestItem
  /** 响应提交回调 (response: 用户输入或选定项, grantMode?: once|always|default) */
  onRespond?: (
    response: string,
    grantMode?: "once" | "always" | "default",
  ) => Promise<void> | void
  /** 取消/终止回调 */
  onCancel?: () => Promise<void> | void
  /** 拒绝回调（可选提供驳回原因） */
  onReject?: (feedback?: string) => Promise<void> | void
  /** 项目切换器插槽（供 project_switch 题型注入） */
  renderProjectSwitcher?: (props: {
    onSelect: (project: { id: number | string; name: string; path?: string }) => void
    disabled?: boolean
  }) => React.ReactNode
  /** 自定义内容渲染器（例如注入 MessageContent） */
  renderContent?: (content: string) => React.ReactNode
  className?: string
}
