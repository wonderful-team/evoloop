import { http, HttpResponse } from "msw"

// Mock data factories
export const createMockUser = (overrides = {}) => ({
  id: 1,
  email: "test@example.com",
  username: "testuser",
  nickname: "Test User",
  is_active: true,
  is_superuser: false,
  ...overrides,
})

export const createMockProject = (overrides = {}) => ({
  id: 1,
  project_id: 1,
  name: "Test Project",
  project_name: "Test Project",
  description: "Test Description",
  project_desc: "Test Description",
  status: 1,
  priority: 1,
  owner_member_id: 1,
  owner_member_name: "Test User",
  ...overrides,
})

export const createMockConversation = (overrides = {}) => ({
  id: "conv-1",
  title: "Test Conversation",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

// API Handlers
export const handlers = [
  // Auth endpoints
  http.post("/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { username: string; password: string }

    if (body.username === "test@example.com" && body.password === "password123") {
      return HttpResponse.json({
        access_token: "mock-access-token",
        token_type: "bearer",
      })
    }

    return HttpResponse.json(
      { detail: "Incorrect email or password" },
      { status: 401 }
    )
  }),

  http.post("/api/v1/auth/register", async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string }

    if (!body.email || !body.password) {
      return HttpResponse.json(
        { detail: "Missing required fields" },
        { status: 422 }
      )
    }

    return HttpResponse.json(createMockUser({ email: body.email }), { status: 201 })
  }),

  // User endpoints
  http.get("/api/v1/users/me", () => {
    return HttpResponse.json(createMockUser())
  }),

  http.patch("/api/v1/users/me", async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json(createMockUser(body))
  }),

  // Project endpoints
  http.get("/api/v1/projects", () => {
    return HttpResponse.json({
      list: [createMockProject(), createMockProject({ id: 2, name: "Project 2" })],
    })
  }),

  http.post("/api/v1/projects", async ({ request }) => {
    const body = (await request.json()) as { name: string }
    return HttpResponse.json(createMockProject({ name: body.name }), { status: 201 })
  }),

  http.get("/api/v1/projects/:projectId", ({ params }) => {
    return HttpResponse.json(createMockProject({ id: Number(params.projectId) }))
  }),

  // Conversation endpoints
  http.get("/api/v1/conversations", () => {
    return HttpResponse.json({
      list: [createMockConversation()],
    })
  }),

  http.post("/api/v1/conversations", async ({ request }) => {
    const body = (await request.json()) as { title: string }
    return HttpResponse.json(createMockConversation({ title: body.title }), { status: 201 })
  }),

  // Learning/Recording endpoints
  http.post("/api/v1/learning/start-recording", () => {
    return HttpResponse.json({ session_id: `session-${Date.now()}` })
  }),

  http.post("/api/v1/learning/stop-recording", () => {
    return HttpResponse.json({ success: true })
  }),

  http.post("/api/v1/learning/record-events", () => {
    return HttpResponse.json({ success: true })
  }),

  // Settings endpoints
  http.get("/api/v1/settings", () => {
    return HttpResponse.json({
      theme: "system",
      language: "en",
    })
  }),

  http.patch("/api/v1/settings", async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json(body)
  }),
]

// Error handlers for testing error scenarios
export const errorHandlers = [
  http.get("/api/v1/projects", () => {
    return HttpResponse.json(
      { detail: "Internal server error" },
      { status: 500 }
    )
  }),

  http.post("/api/v1/auth/login", () => {
    return HttpResponse.json(
      { detail: "Service unavailable" },
      { status: 503 }
    )
  }),

  http.get("/api/v1/users/me", () => {
    return HttpResponse.json(
      { detail: "Unauthorized" },
      { status: 401 }
    )
  }),
]

// Loading/slow response handlers
export const slowHandlers = [
  http.get("/api/v1/projects", async () => {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    return HttpResponse.json({
      list: [createMockProject()],
    })
  }),
]
