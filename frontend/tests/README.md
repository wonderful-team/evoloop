# Frontend Test Suite

This directory contains comprehensive test suites for the Evoloop frontend application.

## Test Structure

```
tests/
├── e2e/                    # End-to-end Playwright tests
│   ├── chat.spec.ts        # Chat functionality tests
│   ├── projects.spec.ts    # Project management tests
│   ├── navigation.spec.ts  # Navigation tests
│   ├── learning.spec.ts    # Learning mode tests
│   ├── settings-extended.spec.ts  # Extended settings tests
│   └── accessibility.spec.ts      # Accessibility tests
├── mobile/                 # Mobile-specific tests
│   └── navigation.spec.ts  # Mobile navigation tests
├── pom/                    # Page Object Models
│   ├── ChatPage.ts         # Chat page interactions
│   ├── ProjectsPage.ts     # Projects page interactions
│   └── SettingsPage.ts     # Settings page interactions
├── unit/                   # Unit test utilities
│   └── test-utils.tsx      # Shared testing utilities
├── utils/                  # Test utilities
│   ├── random.ts           # Random data generators
│   ├── user.ts             # User authentication helpers
│   ├── privateApi.ts       # API helpers
│   └── mailcatcher.ts      # Email testing helpers
├── *.spec.ts               # Root level E2E tests
├── auth.setup.ts           # Authentication setup
└── config.ts               # Test configuration
```

## Running Tests

### Unit Tests (Vitest)

```bash
# Run unit tests
npm run test

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage
```

### E2E Tests (Playwright)

```bash
# Run E2E tests
npm run test:e2e

# Run with UI
npm run test:e2e:ui

# Run specific test file
npx playwright test tests/e2e/chat.spec.ts

# Run with debug
npm run test:e2e:debug
```

### All Tests

```bash
# Run both unit and E2E tests
npm run test:all
```

## Test Categories

### 1. Unit Tests

Located in `packages/*/src/**/__tests__/*.test.ts`

- **Hooks**: `useAuth`, `useCopyToClipboard`, `useMobile`, `useProjectStatus`
- **Stores**: `chatStore`, `projectStore`, `recordingStore`
- **Components**: Button, Input, Alert, and other shared UI components

### 2. E2E Tests

Located in `tests/e2e/*.spec.ts`

- **Chat**: Message sending, receiving, context management
- **Projects**: Project switching, creation, management
- **Navigation**: Route navigation, authentication redirects
- **Learning**: Recording, skill synthesis, MCP management
- **Settings**: Profile, password, theme, model configuration
- **Accessibility**: ARIA roles, keyboard navigation, contrast

### 3. Mobile Tests

Located in `tests/mobile/*.spec.ts`

- Mobile-specific navigation and interactions
- Responsive design testing
- Touch gesture support

## Configuration

### Environment Variables

Create a `.env` file in the `tests/` directory:

```env
# Test credentials
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=admin123

# API endpoints
API_URL=http://localhost:8000
```

### Playwright Configuration

See `playwright.config.ts` for browser, viewport, and execution settings.

### Vitest Configuration

See `vitest.config.ts` for unit test settings, coverage thresholds, and aliases.

## Writing Tests

### Unit Test Example

```typescript
import { describe, it, expect } from "vitest"
import { renderHook, act } from "@testing-library/react"
import useMyHook from "../useMyHook"

describe("useMyHook", () => {
  it("should do something", () => {
    const { result } = renderHook(() => useMyHook())

    act(() => {
      result.current.doSomething()
    })

    expect(result.current.value).toBe("expected")
  })
})
```

### E2E Test Example

```typescript
import { test, expect } from "@playwright/test"
import { ChatPage } from "../pom/ChatPage"

test("should send message", async ({ page }) => {
  const chatPage = new ChatPage(page)
  await chatPage.goto()
  await chatPage.sendMessage("Hello")
  await chatPage.expectMessageVisible("Hello")
})
```

## Best Practices

1. **Use Page Object Models** for E2E tests to separate test logic from UI selectors
2. **Mock external APIs** in unit tests using MSW or Vitest mocks
3. **Use test data factories** for consistent test data
4. **Clean up state** after each test using `afterEach`
5. **Group related tests** using `describe` blocks
6. **Use semantic selectors** (role, label) over test IDs when possible
7. **Add accessibility checks** to ensure inclusive design

## Coverage Requirements

- Lines: 60%
- Functions: 60%
- Branches: 50%
- Statements: 60%

## Continuous Integration

Tests are configured to run in CI with:
- Parallel execution disabled (`workers: 1`)
- Retry on failure (`retries: 2`)
- Blob reporter for CI results

## Troubleshooting

### Common Issues

1. **Tests fail with "Browser not found"**
   - Run `npx playwright install` to install browsers

2. **API calls fail in tests**
   - Ensure mock server is running or mock the API calls

3. **Test timeouts**
   - Increase timeout in `playwright.config.ts` or `vitest.config.ts`

4. **Flaky tests**
   - Use `waitFor` for async operations
   - Add appropriate delays for animations
