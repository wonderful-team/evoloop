import { test, expect } from "@playwright/test"
import { ChatPage } from "../pom/ChatPage"

test.describe("Chat Functionality", () => {
  let chatPage: ChatPage

  test.beforeEach(async ({ page }) => {
    chatPage = new ChatPage(page)
    await chatPage.goto()
  })

  test("should display chat input and send button", async () => {
    await expect(chatPage.chatInput).toBeVisible()
    await expect(chatPage.sendButton).toBeVisible()
  })

  test("should send a message and receive response", async () => {
    const message = "Hello, can you help me with a simple task?"
    await chatPage.sendMessage(message)

    // Check that user message appears
    await expect(chatPage.page.getByText(message)).toBeVisible()

    // Wait for response (this will depend on your actual implementation)
    await chatPage.waitForResponse(30000)
  })

  test("should disable send button when input is empty", async () => {
    await expect(chatPage.sendButton).toBeDisabled()
  })

  test("should enable send button when input has text", async () => {
    await chatPage.chatInput.fill("Test message")
    await expect(chatPage.sendButton).toBeEnabled()
  })

  test("should start a new conversation", async () => {
    await chatPage.startNewChat()
    // After starting new chat, message list should be empty or have welcome message
    await expect(chatPage.messageList).toBeVisible()
  })

  test("should toggle sidebar visibility", async () => {
    await chatPage.toggleSidebar()
    // Check sidebar state after toggle
    await expect(chatPage.page.getByTestId("chat-sidebar")).not.toBeVisible()
  })

  test("should handle multiple messages in conversation", async () => {
    const messages = ["First message", "Second message", "Third message"]

    for (const message of messages) {
      await chatPage.sendMessage(message)
      await expect(chatPage.page.getByText(message)).toBeVisible()
    }

    const allMessages = await chatPage.getMessages()
    expect(allMessages.length).toBeGreaterThanOrEqual(messages.length)
  })

  test("should show loading state while waiting for response", async () => {
    await chatPage.sendMessage("Please tell me about React")
    // Check for loading indicator
    await expect(chatPage.stopButton).toBeVisible()
  })

  test("should stop generation when stop button is clicked", async () => {
    await chatPage.sendMessage("Write a long essay about programming")
    await expect(chatPage.stopButton).toBeVisible()
    await chatPage.stopButton.click()
    await expect(chatPage.stopButton).not.toBeVisible()
  })
})

test.describe("Chat with Context", () => {
  let chatPage: ChatPage

  test.beforeEach(async ({ page }) => {
    chatPage = new ChatPage(page)
    await chatPage.goto()
  })

  test("should mention active context in UI", async () => {
    // Test for context panel or active context display
    await expect(chatPage.page.getByTestId("context-panel")).toBeVisible()
  })

  test("should allow clearing context", async () => {
    const clearContextButton = chatPage.page.getByRole("button", { name: /clear context/i })
    if (await clearContextButton.isVisible().catch(() => false)) {
      await clearContextButton.click()
      await expect(chatPage.page.getByText(/context cleared/i)).toBeVisible()
    }
  })
})
