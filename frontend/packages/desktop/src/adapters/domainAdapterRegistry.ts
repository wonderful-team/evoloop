import type { DomainAdapter, ProjectDomainMode } from "@/types/domain"

export const domainAdapters: Record<ProjectDomainMode, DomainAdapter> = {
  software: {
    meta: {
      mode: "software",
      name: "软件工程",
      iconName: "Code2",
      description: "包含源码文件树、AST 符号、API 路由、依赖拓扑与代码生成",
    },
    labels: {
      assetsTab: "资产与结构",
      knowledgeTab: "知识与探索",
      workflowsTab: "任务与流程",
      vaultTab: "密钥保险箱",
      treeTitle: "源码与符号目录树",
      summaryTitle: "项目架构与技术栈",
      clusterTitle: "Leiden 代码社区",
      macroLabel: "Macro SOP 库",
    },
  },
  research: {
    meta: {
      mode: "research",
      name: "学术科研",
      iconName: "GraduationCap",
      description: "适用于论文研读、文献综述、法条分析与科研数据集拆解",
    },
    labels: {
      assetsTab: "文献与资产",
      knowledgeTab: "综述与概念",
      workflowsTab: "研究里程碑",
      vaultTab: "机密凭据箱",
      treeTitle: "文献与数据集目录",
      summaryTitle: "研究摘要与 Abstract",
      clusterTitle: "核心概念图谱",
      macroLabel: "数据清洗 SOP",
    },
  },
  design: {
    meta: {
      mode: "design",
      name: "创意设计",
      iconName: "Palette",
      description: "包含 UI 设计稿、切图资产、Design Token 与品牌规范",
    },
    labels: {
      assetsTab: "设计与切图",
      knowledgeTab: "规范与 Moodboard",
      workflowsTab: "评审与交付",
      vaultTab: "凭据保险箱",
      treeTitle: "设计稿与组件库",
      summaryTitle: "设计系统与规范说明",
      clusterTitle: "设计主题分类",
      macroLabel: "批量导出 SOP",
    },
  },
  business: {
    meta: {
      mode: "business",
      name: "商业运营",
      iconName: "Briefcase",
      description: "适用于活动策划、市场调研、Excel 报表与渠道投放",
    },
    labels: {
      assetsTab: "策划与报表",
      knowledgeTab: "研报与文案",
      workflowsTab: "甘特图与执行",
      vaultTab: "渠道凭据箱",
      treeTitle: "策划案与数据报表",
      summaryTitle: "活动 Executive Summary",
      clusterTitle: "调研主题大纲",
      macroLabel: "自动数据汇总 SOP",
    },
  },
  general: {
    meta: {
      mode: "general",
      name: "通用工作区",
      iconName: "FileBox",
      description: "通用基础项目模式，适用于日常文档与任务管理",
    },
    labels: {
      assetsTab: "项目资产",
      knowledgeTab: "知识与文档",
      workflowsTab: "任务与流程",
      vaultTab: "密钥保险箱",
      treeTitle: "工作区文件目录",
      summaryTitle: "项目首页概览",
      clusterTitle: "主题文档分类",
      macroLabel: "自动化工作流",
    },
  },
}

export function getDomainAdapter(mode: ProjectDomainMode | string | undefined): DomainAdapter {
  if (mode && mode in domainAdapters) {
    return domainAdapters[mode as ProjectDomainMode]
  }
  return domainAdapters.software
}
