import { create } from "zustand"

export interface BenefitRequirementInfo {
  feature?: string
  featureName?: string
  requiredPlan?: string
  message?: string
  upgradeUrl?: string
}

interface BenefitState {
  isOpen: boolean
  info: BenefitRequirementInfo | null
  openDialog: (info: BenefitRequirementInfo) => void
  closeDialog: () => void
}

export const PLAN_KEY_MAP: Record<string, string> = {
  创作者版: "creator",
  极客版: "geek",
  专家版: "expert",
  企业版: "enterprise",
}

export const useBenefitStore = create<BenefitState>((set) => ({
  isOpen: false,
  info: null,
  openDialog: (info) => set({ isOpen: true, info }),
  closeDialog: () => set({ isOpen: false, info: null }),
}))
