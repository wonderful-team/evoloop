/**
 * Domain Mode & Adapter Type Definitions
 * Support domain-agnostic workspaces across Software, Research, Design, Business, and General projects.
 */

export type ProjectDomainMode =
  | "software" // 软件工程
  | "research" // 学术科研 / 法律合规
  | "design" // 产品设计 / 创意 UI
  | "business" // 商业运营 / 营销策划
  | "general" // 通用工作区

export interface DomainMeta {
  mode: ProjectDomainMode
  name: string
  iconName: string
  description: string
}

export interface DomainAdapter {
  meta: DomainMeta
  labels: {
    assetsTab: string
    knowledgeTab: string
    workflowsTab: string
    vaultTab: string
    treeTitle: string
    summaryTitle: string
    clusterTitle: string
    macroLabel: string
  }
}
