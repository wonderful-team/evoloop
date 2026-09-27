import { beforeEach, describe, expect, it } from "vitest"
import { PLAN_KEY_MAP, useBenefitStore } from "./benefitStore"
import { useDutyStore } from "./dutyStore"
import { useUnreadCompletionsStore } from "./unreadCompletionsStore"

describe("desktop secondary stores", () => {
  beforeEach(() => {
    useDutyStore.setState({ globalEnabled: false, wecomEnabled: false })
    useUnreadCompletionsStore.setState({ unread: {} })
    useBenefitStore.setState({ isOpen: false, info: null })
  })

  describe("useDutyStore", () => {
    it("updates global and wecom duty states", () => {
      expect(useDutyStore.getState().globalEnabled).toBe(false)
      expect(useDutyStore.getState().wecomEnabled).toBe(false)

      useDutyStore.getState().setGlobalState(true, true)

      expect(useDutyStore.getState().globalEnabled).toBe(true)
      expect(useDutyStore.getState().wecomEnabled).toBe(true)
    })
  })

  describe("useUnreadCompletionsStore", () => {
    it("marks and clears unread status by thread id", () => {
      useUnreadCompletionsStore.getState().markUnread("thread-1")
      expect(useUnreadCompletionsStore.getState().unread["thread-1"]).toBe(true)

      // idempotent marking
      useUnreadCompletionsStore.getState().markUnread("thread-1")
      expect(useUnreadCompletionsStore.getState().unread["thread-1"]).toBe(true)

      useUnreadCompletionsStore.getState().clearUnread("thread-1")
      expect(
        useUnreadCompletionsStore.getState().unread["thread-1"],
      ).toBeUndefined()
    })
  })

  describe("useBenefitStore", () => {
    it("maps plan Chinese names to internal keys", () => {
      expect(PLAN_KEY_MAP["创作者版"]).toBe("creator")
      expect(PLAN_KEY_MAP["极客版"]).toBe("geek")
      expect(PLAN_KEY_MAP["专家版"]).toBe("expert")
      expect(PLAN_KEY_MAP["企业版"]).toBe("enterprise")
    })

    it("opens and closes benefit modal with info payload", () => {
      expect(useBenefitStore.getState().isOpen).toBe(false)

      const info = {
        feature: "pro_model",
        featureName: "专家模型接入",
        requiredPlan: "专家版",
      }

      useBenefitStore.getState().openDialog(info)
      expect(useBenefitStore.getState().isOpen).toBe(true)
      expect(useBenefitStore.getState().info).toEqual(info)

      useBenefitStore.getState().closeDialog()
      expect(useBenefitStore.getState().isOpen).toBe(false)
      expect(useBenefitStore.getState().info).toBeNull()
    })
  })
})
