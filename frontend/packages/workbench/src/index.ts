/**
 * @evoloop/workbench
 *
 * EvoLoop 协同工作台核心包：
 * - Autonomous Duty Workbench (自主值守工作台：v2 无限画布模式 + v1 经典列表模式)
 */

// Autonomous Duty Workbench (v1 & v2 统一入口)
export { DutyWorkbench, AutonomousDutyPage } from "./DutyWorkbench"
export { default } from "./DutyWorkbench"

// v2: 自主值守无限画布模式专用导出
export { default as AutonomousDutyCanvasApp } from "./v2/AutonomousDutyCanvasApp"
export { DutyCanvas } from "./v2/components/DutyCanvas"
export { DutyTopBar } from "./v2/components/DutyTopBar"
export { DutyLeftSidebar } from "./v2/components/DutyLeftSidebar"
export { DutyNodeCard } from "./v2/components/DutyNodeCard"
export { DutyNodePageContent } from "./v2/components/DutyNodePageContent"
export { DutyHumanRequestCard } from "./v2/components/DutyHumanRequestCard"
export { layoutDutyTasks, deriveDutyEdges } from "./v2/layoutEngine"
export * from "./v2/types"
