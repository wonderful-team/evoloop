import React, { ReactElement } from "react"
import { render as rtlRender, RenderOptions } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router"

// Create a custom render function that includes providers
interface CustomRenderOptions extends Omit<RenderOptions, "wrapper"> {
  initialRoute?: string
  queryClient?: QueryClient
}

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
    },
  })
}

export function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions = {}
) {
  const { initialRoute = "/", queryClient = createTestQueryClient(), ...renderOptions } = options

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }

  return {
    ...rtlRender(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  }
}

// Re-export everything from testing-library
export * from "@testing-library/react"
export { renderWithProviders as render }

// Test data factories
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
  name: "Test Project",
  description: "A test project",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

export const createMockMessage = (overrides = {}) => ({
  id: "msg-1",
  content: "Hello, world!",
  role: "user" as const,
  timestamp: new Date().toISOString(),
  ...overrides,
})

export const createMockConversation = (overrides = {}) => ({
  id: "conv-1",
  title: "Test Conversation",
  messages: [createMockMessage()],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})
