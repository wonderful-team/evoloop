import { describe, it, expect, beforeEach } from "vitest"
import { useMobileStore } from "../useMobileStore"

describe("useMobileStore", () => {
  beforeEach(() => {
    useMobileStore.setState({
      currentProject: null,
      isProjectInitialized: false,
      activeTab: "cloud",
    })
  })

  describe("initial state", () => {
    it("should have correct initial values", () => {
      const state = useMobileStore.getState()

      expect(state.currentProject).toBeNull()
      expect(state.isProjectInitialized).toBe(false)
      expect(state.activeTab).toBe("cloud")
    })
  })

  describe("setCurrentProject", () => {
    it("should set current project", () => {
      const project = { id: 1, name: "Test Project" }
      const { setCurrentProject } = useMobileStore.getState()

      setCurrentProject(project)

      expect(useMobileStore.getState().currentProject).toEqual(project)
    })

    it("should update current project", () => {
      const project1 = { id: 1, name: "Project 1" }
      const project2 = { id: 2, name: "Project 2" }
      const store = useMobileStore.getState()

      store.setCurrentProject(project1)
      store.setCurrentProject(project2)

      expect(useMobileStore.getState().currentProject).toEqual(project2)
    })

    it("should clear current project with null", () => {
      const project = { id: 1, name: "Test Project" }
      const store = useMobileStore.getState()

      store.setCurrentProject(project)
      store.setCurrentProject(null)

      expect(useMobileStore.getState().currentProject).toBeNull()
    })
  })

  describe("setProjectInitialized", () => {
    it("should set initialized to true", () => {
      const { setProjectInitialized } = useMobileStore.getState()

      setProjectInitialized(true)

      expect(useMobileStore.getState().isProjectInitialized).toBe(true)
    })

    it("should set initialized to false", () => {
      const store = useMobileStore.getState()

      store.setProjectInitialized(true)
      store.setProjectInitialized(false)

      expect(useMobileStore.getState().isProjectInitialized).toBe(false)
    })
  })

  describe("setActiveTab", () => {
    it("should set active tab to local", () => {
      const { setActiveTab } = useMobileStore.getState()

      setActiveTab("local")

      expect(useMobileStore.getState().activeTab).toBe("local")
    })

    it("should set active tab to cloud", () => {
      const store = useMobileStore.getState()

      store.setActiveTab("local")
      store.setActiveTab("cloud")

      expect(useMobileStore.getState().activeTab).toBe("cloud")
    })

    it("should only accept valid tab values", () => {
      const { setActiveTab } = useMobileStore.getState()

      // TypeScript should enforce this, but we test runtime behavior
      setActiveTab("cloud")
      expect(useMobileStore.getState().activeTab).toBe("cloud")

      setActiveTab("local")
      expect(useMobileStore.getState().activeTab).toBe("local")
    })
  })

  describe("combined operations", () => {
    it("should handle complete project selection flow", () => {
      const store = useMobileStore.getState()
      const project = { id: 1, name: "Test Project" }

      // Select project
      store.setCurrentProject(project)
      store.setProjectInitialized(true)
      store.setActiveTab("local")

      const state = useMobileStore.getState()
      expect(state.currentProject).toEqual(project)
      expect(state.isProjectInitialized).toBe(true)
      expect(state.activeTab).toBe("local")
    })

    it("should handle project reset flow", () => {
      const store = useMobileStore.getState()
      const project = { id: 1, name: "Test Project" }

      // Set up state
      store.setCurrentProject(project)
      store.setProjectInitialized(true)
      store.setActiveTab("local")

      // Reset
      store.setCurrentProject(null)
      store.setProjectInitialized(false)
      store.setActiveTab("cloud")

      const state = useMobileStore.getState()
      expect(state.currentProject).toBeNull()
      expect(state.isProjectInitialized).toBe(false)
      expect(state.activeTab).toBe("cloud")
    })
  })
})
