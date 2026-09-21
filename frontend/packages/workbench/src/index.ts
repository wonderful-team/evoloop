/**
 * @evoloop/workbench
 *
 * EvoLoop 协同工作台核心包：
 * - Autonomous Duty Workbench (自主值守工作台：无限画布模式 + 调度队列协同)
 */

// Autonomous Duty Workbench 统一入口
export { DutyWorkbench, AutonomousDutyPage } from "./DutyWorkbench"
export { default } from "./DutyWorkbench"

// 画布领域导出
export { default as AutonomousDutyCanvasApp } from "./canvas/AutonomousDutyCanvasApp"
export { DutyCanvas } from "./canvas/DutyCanvas"
export { DutyTopBar } from "./canvas/DutyTopBar"
export { DutyLeftSidebar } from "./canvas/DutyLeftSidebar"
export { DutyNodeCard } from "./canvas/DutyNodeCard"
export { DutyNodePageContent } from "./canvas/DutyNodePageContent"
export { layoutDutyTasks, deriveDutyEdges } from "./canvas/layoutEngine"

// 详情与执行领域导出
export { PlanPanel } from "./detail/PlanPanel"
export { ExecutionPanel } from "./detail/ExecutionPanel"
export { ProposalCard, InlineProposal } from "./detail/ProposalCards"
export { ResultCard } from "./detail/ResultCard"
export { ReviewProgressCard } from "./detail/ReviewProgressCard"
export { PendingTaskBrief } from "./detail/PendingTaskBrief"

// 队列与控制领域导出
export { TaskRow } from "./queue/TaskRow"
export { DutyStartStopButton, DutyRitualOverlay } from "./queue/DutyStartStopButton"
export { PulseWave } from "./queue/AgentPulse"

// 核心契约与适配器导出
export * from "./core/taskAdapter"
export * from "./core/types"
export { CustomerServiceDutyManager } from "./core/CustomerServiceDutyManager"
