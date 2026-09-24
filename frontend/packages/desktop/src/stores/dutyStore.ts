import {create} from "zustand"

/**
 * 全局自主值守状态 store。
 * 由 CustomerServiceDutyManager（全局 headless，非懒加载 chunk）用
 * SystemService 读取并填充。懒加载组件（项目值守页/项目切换）从本 store
 * 读取全局状态，避免在懒加载 chunk 直接 import SystemService
 * （vite chunk 命名导出冲突会导致运行时 "Can't find variable"）。
 */
interface DutyGlobalState {
  globalEnabled: boolean
  wecomEnabled: boolean
  setGlobalState: (enabled: boolean, wecom: boolean) => void
}

export const useDutyStore = create<DutyGlobalState>((set) => ({
  globalEnabled: false,
  wecomEnabled: false,
  setGlobalState: (enabled, wecom) =>
    set({ globalEnabled: enabled, wecomEnabled: wecom }),
}))
